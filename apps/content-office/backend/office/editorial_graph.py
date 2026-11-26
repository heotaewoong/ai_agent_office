"""Durable editorial calls. No approval, publication, or provider fallback."""
from __future__ import annotations

import json
import os
from contextlib import closing
from pathlib import Path
import sqlite3

from .store import WorkflowError, canonical, digest
from .runtime import ProcessLock

VERSION = "editorial-functional-v2"


def require_graph_runtime():
    # Checkpoints contain editorial content; do not opt into remote tracing implicitly.
    if any(os.environ.get(key, "").lower() in ("true", "1") for key in ("LANGCHAIN_TRACING_V2", "LANGCHAIN_TRACING", "LANGSMITH_TRACING_V2", "LANGSMITH_TRACING")):
        raise WorkflowError("원고 체크포인트의 외부 추적 전송은 승인되지 않았습니다")
    try:
        from langgraph.func import entrypoint, task
        from langgraph.checkpoint.sqlite import SqliteSaver
    except ImportError:
        raise WorkflowError("선택한 LangGraph 원고 실행기의 로컬 의존성을 설치하세요. 기존 실행기로 자동 전환하지 않습니다") from None
    return entrypoint, task, SqliteSaver


def run_editorial_graph(build_packet, provider, *, checkpoint_path, identity, check_current=None):
    entrypoint, task, SqliteSaver = require_graph_runtime()
    from langgraph.checkpoint.serde.jsonplus import JsonPlusSerializer
    from langsmith.run_helpers import tracing_context

    identity = {**identity, "version": VERSION}
    thread_id = digest(identity)
    path = Path(checkpoint_path)
    path.parent.mkdir(parents=True, exist_ok=True, mode=0o700)
    guard = check_current or (lambda: None)
    guard()
    with ProcessLock(path.with_suffix(path.suffix + ".lock")), tracing_context(enabled=False):
        with closing(sqlite3.connect(path, timeout=30, check_same_thread=False)) as connection, closing(sqlite3.connect(path, timeout=30, check_same_thread=False)) as checkpoint_connection:
            connection.execute("CREATE TABLE IF NOT EXISTS editorial_call_intents (thread TEXT, step INTEGER, request_hash TEXT, state TEXT, result TEXT, PRIMARY KEY(thread,step))")
            connection.commit()
            if connection.execute("SELECT 1 FROM editorial_call_intents WHERE state='started' LIMIT 1").fetchone():
                raise WorkflowError("이 작업의 이전 모델 호출 결과가 불명확합니다. 입력이나 모델이 바뀌어도 비용 예약을 유지하며 제공자 결과 대사 전 재호출하지 않습니다")
            if os.name != "nt":
                path.chmod(0o600)

            @task
            def model_call(request, step):
                guard()
                request_hash = digest(request)
                old = connection.execute("SELECT request_hash,state,result FROM editorial_call_intents WHERE thread=? AND step=?", (thread_id, step)).fetchone()
                if old:
                    if old[0] != request_hash:
                        raise WorkflowError("재개할 원고 호출의 입력 판본이 다릅니다")
                    if old[1] not in ("completed", "not_sent"):
                        raise WorkflowError("이전 모델 호출 결과를 확인하지 못했습니다. 비용 예약을 유지하며 제공자 결과 대사 전 재호출하지 않습니다")
                    if old[1] == "completed":
                        return {"request_hash": request_hash, "result": json.loads(old[2])}
                    connection.execute("UPDATE editorial_call_intents SET state='started' WHERE thread=? AND step=?", (thread_id, step))
                else:
                    connection.execute("INSERT INTO editorial_call_intents VALUES(?,?,?,'started',NULL)", (thread_id, step, request_hash))
                connection.commit()
                # A crash/timeout leaves 'started': restarting must never blindly charge again.
                try:
                    result = provider.generate(**request)
                except Exception as error:
                    # Only an explicit Provider pre-dispatch marker can clear this attempt.
                    # Unknown transport outcomes and process death retain their reservation.
                    if getattr(error, "provider_not_dispatched", False) is True:
                        connection.execute("UPDATE editorial_call_intents SET state='not_sent' WHERE thread=? AND step=?", (thread_id, step))
                        connection.commit()
                    raise
                connection.execute("UPDATE editorial_call_intents SET state='completed',result=? WHERE thread=? AND step=?", (canonical(result), thread_id, step))
                connection.commit()
                return {"request_hash": request_hash, "result": result}

            class CheckpointProvider:
                def __init__(self):
                    self.step = 0

                def generate(self, role, messages, schema, options=None):
                    self.step += 1
                    guard()
                    request = {"role": role, "messages": messages, "schema": schema, "options": options}
                    completed = model_call(request, self.step).result()
                    if completed["request_hash"] != digest(request):
                        raise WorkflowError("체크포인트의 모델 입력과 현재 프롬프트가 다릅니다")
                    return completed["result"]

            @entrypoint(checkpointer=SqliteSaver(checkpoint_connection, serde=JsonPlusSerializer(allowed_msgpack_modules=None, pickle_fallback=False)))
            def editorial_run(snapshot):
                return build_packet(CheckpointProvider())

            config = {"configurable": {"thread_id": thread_id}, "callbacks": []}
            previous = editorial_run.get_state(config)
            # A successful identical run is read-only; a failed run resumes saved tasks.
            if previous.created_at and not previous.next:
                guard()
                return previous.values
            result = editorial_run.invoke(None if previous.created_at else identity, config, durability="sync")
            guard()
            return result


def editorial_snapshot(store, job_id, *, job=None):
    job = store.job(job_id) if job is None else job
    return {"job_id": job_id, "inputs": {key: job.get(key) for key in
        ("source_hash", "article", "brief", "offer_hash", "offer", "packaging",
         "channel_titles", "selections", "source_approval", "release_approval")},
        "selected_model": store.setting("model")}


def graph_identity(snapshot, provider, **context):
    # Bind persisted replay to the code implementing prompts, validation and adaptation.
    folder = Path(__file__).parent
    modules = ("editorial", "editorial_graph", "brand", "channel_adaptation", "korean",
               "output_specs", "writing_style", "packaging", "offers", "briefs", "providers",
               "codex_text_provider", "content_api_mode", "text_selection", "bilingual_captions")
    if context.get("review_engine") == "v2_harness":
        modules += ("harness", "harness_rules", "harness_trace", "private_books")
    if context.get("writer_checks") not in (None, "off"):
        modules += ("writer_checks",)
    contract = digest({name: (folder / (name + ".py")).read_text(encoding="utf-8") for name in modules})
    return {"version": VERSION, "snapshot": snapshot, "model": getattr(provider, "model", None),
            "contract": contract, **context}


def event_once(store, job_id, identity, kind, data):
    # The editorial body replays on resume. Commit audit de-duplication in the same
    # Store transaction as the event, including across a process death.
    payload = {**data, "editorial_run": digest({**identity, "version": VERSION})}
    with store.connection(transaction=True) as db:
        if not db.execute("SELECT 1 FROM events WHERE job_id=? AND kind=? AND data=? LIMIT 1",
                          (job_id, kind, canonical(payload))).fetchone():
            store._event(db, kind, payload, job_id)
