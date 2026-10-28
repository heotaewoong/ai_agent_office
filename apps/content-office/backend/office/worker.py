from __future__ import annotations
import argparse
import json
import os
import signal
import time
from .bootstrap import default_store, refresh
from .editorial import prepare_source
from .store import WorkflowError, canonical, identifier, now
from .runtime import WorkerRuntime, WorkerInterrupted, WindowDeadline, run_before_deadline, window_open, worker_heartbeat


def process_task(store, task):
    payload = task["payload"]
    if task["kind"] == "refresh":
        return refresh(store)
    job_id = payload.get("job_id")
    if task["kind"] in ("draft", "evaluate"):
        if "source_hash" in payload and store.job(job_id).get("source_hash") != payload["source_hash"]:
            raise WorkflowError("대기 중인 원고 작업의 버전이 변경되었습니다")
        return {"job_id": job_id, "source_hash": prepare_source(store, job_id, evaluate_only=task["kind"] == "evaluate")["source_hash"]}
    if task["kind"] == "produce":
        from .media import produce, production_contract
        from .voice_selection import renderer_for_job
        from .image_selection import background_renderer_for_job
        from .video_selection import clip_renderer_for_job
        current = store.require_source_approval(job_id)
        if payload["source_hash"] != current["source_hash"]:
            raise WorkflowError("대기 중인 제작의 원고 버전이 변경되었습니다")
        renderer = renderer_for_job(store, current)
        background = background_renderer_for_job(store, current)
        clips = clip_renderer_for_job(store, current)
        if payload.get('production_contract') and payload['production_contract'] != production_contract(renderer, current['selections'], image_renderer=background, clip_renderer=clips)['hash']:
            raise WorkflowError('대기 중 제작 설정이 변경되었습니다. 현재 설정으로 제작을 다시 요청하세요')
        store.update_job(job_id, state="producing", error=None)
        manifest = produce(store, job_id, voice_renderer=renderer, background_renderer=background, clip_renderer=clips)
        return {"job_id": job_id, "manifest_hash": manifest["hash"], 'partial': any(status.get('state') != 'completed' for status in manifest.get('output_status', {}).values()), 'completed_outputs': manifest.get('completed_outputs')}
    raise WorkflowError("등록되지 않은 작업입니다")


def run_once(store, owner):
    if not window_open(store):
        return False
    worker_heartbeat(store, owner)
    task = store.claim(owner)
    if not task:
        return False
    job_id = task["payload"].get("job_id")
    if job_id:
        with store.connection(transaction=True) as db:
            job = store._job(db, job_id)
            task["payload"]["_source_hash_at_claim"] = task["payload"].get("source_hash", job.get("source_hash"))
            db.execute("UPDATE tasks SET payload=? WHERE id=? AND owner=? AND state='running'", (canonical(task["payload"]), task["id"], owner))
    try:
        if not window_open(store):
            raise WorkerInterrupted("authorized_window_ended")
        result = process_task(store, task)
        store.finish_task(task["id"], owner, result, state='partial' if result.get('partial') else 'completed')
    except Exception as error:
        # Provider helpers already turn secret-bearing transport errors into safe messages.
        message = str(error) if isinstance(error, WorkflowError) else f"{type(error).__name__}: 작업 처리 오류. 운영 기록을 확인하세요"
        uncertain = "예약을 유지" in message or "확인하지 못" in message
        store.finish_task(task["id"], owner, {"error": message, "automatic_retry": False}, state="unknown" if uncertain else "failed")
        job_id = task["payload"].get("job_id")
        if job_id:
            with store.connection(transaction=True) as db:
                current = store._job(db, job_id)
                if current.get("source_hash") == task["payload"].get("_source_hash_at_claim"):
                    current.update(state="needs_reconciliation" if uncertain else "blocked", error=message)
                    store._write_job(db, current)
        store.event("task_result_unknown" if uncertain else "task_failed", {"task_id": task["id"], "kind": task["kind"], "error": message}, job_id)
    finally:
        worker_heartbeat(store, owner)
    return True


def _worker_loop(state_root, owner, once, drain):
    from .store import Store
    store = Store(state_root)
    def interrupted(signum, frame):
        raise WorkerInterrupted(f"signal_{signum}")
    for signum in (signal.SIGTERM, signal.SIGINT):
        signal.signal(signum, interrupted)
    with WorkerRuntime(store, owner):
        while window_open(store):
            worked = run_once(store, owner)
            if once or (drain and not worked):
                break
            if not worked:
                time.sleep(2)


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--once", action="store_true")
    parser.add_argument("--drain", action="store_true")
    args = parser.parse_args()
    store = default_store()
    owner = identifier("worker")
    if not window_open(store):
        return
    def interrupted(signum, frame):
        raise WorkerInterrupted(f"signal_{signum}")
    for signum in (signal.SIGTERM, signal.SIGINT):
        signal.signal(signum, interrupted)
    try:
        run_before_deadline(_worker_loop, (str(store.root), owner, args.once, args.drain), store.setting("work_window", {}).get("authorized_end"))
    except (WorkerInterrupted, WindowDeadline):
        # Native Windows termination cannot unwind the child's Python finally.
        # Reacquire the OS lock before marking calls unknown; never release costs.
        with WorkerRuntime(store, owner, heartbeat_interval=0):
            pass



if __name__ == "__main__":
    main()
