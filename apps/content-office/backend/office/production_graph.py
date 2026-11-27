"""나눠 만들기(2026-11-27 사용자 결정): 승인① 뒤에는 블로그, 글 채널, 카드뉴스를 먼저 만들고
영상은 사람이 예상 비용을 보고 '영상 만들기'를 눌렀을 때만 만든다.

순서는 LangGraph StateGraph로 고정한다(plan → text_outputs → video_gate → video_output). 에이전트가 고르지 않는다.
- 승인과 비용 확인의 기준은 Store다. 사람이 누른 영상 제작 요청은 tasks 표의 produce 작업(stage=video)이고,
  interrupt는 멈추는 자리일 뿐이다. 재개 값에는 그 작업 id만 넣고, 관문이 Store에서 다시 확인한다.
- video_gate는 interrupt 앞에 돈 드는 일을 하지 않는다. 재개하면 노드가 처음부터 다시 돌기 때문이다.
- 상태에는 본문 대신 id와 해시만 둔다. 체크포인트는 로컬 SQLite(0600)이고 외부 추적은 끈다.
- 제작 노드가 멈추면 error_handler가 인수인계 3칸(한 것, 멈춘 곳, 이유)을 Store에 남기고 같은 오류로 멈춘다.
  유료 호출을 다시 하지 않는다. 재시도는 지금처럼 사람이 누른다.
- 시간 제한(TimeoutPolicy)은 걸지 않는다. 동기 렌더는 스레드를 멈출 수 없어 제한이 지나도 뒤에서 계속 돌 수 있다.
  ffmpeg 명령마다 있는 시간 제한과 제작 잠금(production_lock)이 그 자리를 맡는다.
"""
from __future__ import annotations

import os
import sqlite3
from contextlib import closing
from typing import TypedDict

from .store import WorkflowError, digest

VERSION = "production-stages-v1"
TEXT_OUTPUTS = ("blog", "cards", "pdf")


def staged(selections) -> bool:
    """영상과 다른 제작물을 같이 골랐으면 영상은 따로 누를 때까지 미룬다. 영상만 고른 작업은 예전처럼 바로 만든다."""
    selections = selections or {}
    return bool(selections.get("video")) and any(selections.get(kind) for kind in TEXT_OUTPUTS)


class ProductionState(TypedDict, total=False):
    job_id: str
    source_hash: str
    stage: str
    request: str | None
    defer: bool
    manifest_hash: str | None
    video_state: str | None
    path: list[str]


def _video_state(manifest) -> str | None:
    return ((manifest or {}).get("output_status", {}).get("video") or {}).get("state")


def require_video_request(store, job_id, source_hash, request) -> None:
    """사람이 화면에서 누른 영상 제작 요청인지 Store에서 확인한다. 그래프 안의 값만 믿지 않는다."""
    try:
        task = store.task(request) if isinstance(request, str) and request else None
    except Exception:
        task = None
    payload = (task or {}).get("payload") or {}
    if (not task or task.get("kind") != "produce" or task.get("state") not in ("queued", "running")
            or payload.get("job_id") != job_id or payload.get("source_hash") != source_hash or payload.get("stage") != "video"):
        raise WorkflowError("영상 제작은 제작·출고함에서 예상 비용을 보고 누른 요청으로만 시작해요")


def run_production(store, job_id, *, task_id, stage, contract, produce):
    """produce(defer_video) -> manifest. 결과: manifest, 영상 관문에서 기다리는지, 지난 노드 순서."""
    from .editorial_graph import require_graph_runtime
    require_graph_runtime()  # 외부 추적이 켜져 있으면 시작하지 않는다(원고와 개인 자료가 상태에 닿을 수 있다)
    from langgraph.checkpoint.serde.jsonplus import JsonPlusSerializer
    from langgraph.checkpoint.sqlite import SqliteSaver
    from langgraph.errors import NodeError
    from langgraph.graph import END, START, StateGraph
    from langgraph.types import Command, interrupt
    from langsmith.run_helpers import tracing_context
    from .runtime import ProcessLock

    job = store.require_source_approval(job_id)
    source_hash = job["source_hash"]
    if stage == "video":
        # 재개 값은 한 번 넣으면 체크포인트에 남으니, 그래프에 넣기 전에 Store의 사람 요청부터 확인한다.
        require_video_request(store, job_id, source_hash, task_id)
    made = {}

    def plan(state):
        return {"defer": staged(job["selections"]), "path": ["plan"]}

    def text_outputs(state):
        current = job.get("manifest") or {}
        # 영상 요청인데 지금 완성본이 이미 같은 판본이면 글과 카드를 다시 저장하지 않는다(출고 승인②를 지우지 않으려고).
        if (state.get("stage") == "video" and current.get("source_hash") == source_hash
                and (current.get("production_contract") or {}).get("hash") == contract):
            manifest = current
        else:
            manifest = made["manifest"] = produce(defer_video=state["defer"])
        return {"manifest_hash": manifest.get("hash"), "video_state": _video_state(manifest), "path": state["path"] + ["text_outputs"]}

    def video_gate(state):
        request = state.get("request") if state.get("stage") == "video" else None
        if not request:
            request = interrupt({"waiting_for": "video_stage", "source_hash": source_hash, "manifest_hash": state.get("manifest_hash")})
        require_video_request(store, job_id, source_hash, request)
        return {"request": request, "path": state["path"] + ["video_gate"]}

    def video_output(state):
        manifest = made["manifest"] = produce(defer_video=False)
        return {"manifest_hash": manifest.get("hash"), "video_state": _video_state(manifest), "path": state["path"] + ["video_output"]}

    def handoff(state, error: NodeError):
        reason = str(error.error) if isinstance(error.error, WorkflowError) else "제작 도구 오류. 운영 기록을 확인하세요"
        store.event("production_handoff", {"done": state.get("path", []), "stopped_at": error.node, "reason": reason[:300],
                                           "source_hash": source_hash, "paid_retry": False}, job_id)
        raise error.error

    builder = StateGraph(ProductionState)
    builder.add_node("plan", plan)
    builder.add_node("text_outputs", text_outputs, error_handler=handoff)
    builder.add_node("video_gate", video_gate)
    builder.add_node("video_output", video_output, error_handler=handoff)
    builder.add_edge(START, "plan")
    builder.add_edge("plan", "text_outputs")
    builder.add_conditional_edges("text_outputs", lambda s: "video_gate" if s["defer"] and s.get("video_state") == "deferred" else END,
                                  ["video_gate", END])
    builder.add_edge("video_gate", "video_output")
    builder.add_edge("video_output", END)

    path = store.root / "production-checkpoints" / (digest(job_id) + ".sqlite3")
    path.parent.mkdir(parents=True, exist_ok=True, mode=0o700)
    thread = digest({"version": VERSION, "job_id": job_id, "source_hash": source_hash, "contract": contract})
    config = {"configurable": {"thread_id": thread}, "callbacks": [], "recursion_limit": 12}
    with ProcessLock(path.with_suffix(path.suffix + ".lock")), tracing_context(enabled=False):
        with closing(sqlite3.connect(path, timeout=30, check_same_thread=False)) as connection:
            if os.name != "nt":
                path.chmod(0o600)
            app = builder.compile(checkpointer=SqliteSaver(connection, serde=JsonPlusSerializer(allowed_msgpack_modules=None, pickle_fallback=False)))
            if stage == "video" and app.get_state(config).next == ("video_gate",):
                result = app.invoke(Command(resume=task_id), config, durability="sync")
            else:
                result = app.invoke({"job_id": job_id, "source_hash": source_hash, "stage": stage,
                                     "request": task_id if stage == "video" else None}, config, durability="sync")
    return {"manifest": made.get("manifest") or store.job(job_id).get("manifest"),
            "awaiting_video": bool(result.get("__interrupt__")), "path": result.get("path", [])}
