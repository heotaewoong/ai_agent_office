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
    if task['kind'] == 'discover':
        from .discovery import run
        return run(store, payload.get('config_hash'))
    job_id = payload.get("job_id")
    if task["kind"] == "thumbnail_images":
        from .thumbnail_images import generate
        return generate(store, payload)
    if task['kind']=='private_delivery':
        from .delivery_queue import process
        return process(store,payload)
    if task["kind"] in ("draft", "evaluate"):
        if "source_hash" in payload and store.job(job_id).get("source_hash") != payload["source_hash"]:
            raise WorkflowError("대기 중인 원고 작업의 버전이 변경되었습니다")
        return {"job_id": job_id, "source_hash": prepare_source(store, job_id, evaluate_only=task["kind"] == "evaluate")["source_hash"]}
    if task["kind"] == "produce":
        from .media import produce, production_contract
        from .voice_selection import renderer_for_job
        from .image_selection import background_renderer_for_job
        from .video_selection import clip_renderer_for_job
        from .channels import registry
        current = store.require_source_approval(job_id)
        if payload["source_hash"] != current["source_hash"]:
            raise WorkflowError("대기 중인 제작의 원고 버전이 변경되었습니다")
        renderer = renderer_for_job(store, current)
        background = background_renderer_for_job(store, current)
        clips = clip_renderer_for_job(store, current)
        if getattr(clips, 'paid', False) and payload.get('paid_clips_confirmed') is not True:
            # Paid clips need the operator's on-page confirmation; no automatic path may start them.
            raise WorkflowError('유료 영상 클립은 운영자가 화면에서 확인한 제작에서만 만듭니다. 제작을 다시 요청하세요')
        if payload.get('production_contract') and payload['production_contract'] != production_contract(renderer, current['selections'], image_renderer=background, clip_renderer=clips, channel_registry=registry(store) if current['selections'].get('blog') else None)['hash']:
            raise WorkflowError('대기 중 제작 설정이 변경되었습니다. 현재 설정으로 제작을 다시 요청하세요')
        store.update_job(job_id, state="producing", error=None)
        # 제작과 함께 같은 원고의 퀴즈·카드뉴스를 자동으로 줄 세운다. 이미 현재 버전 결과가 있으면 건너뛴다.
        from .quiz import enqueue_missing_outputs
        queued_outputs = enqueue_missing_outputs(store, current)
        manifest = produce(store, job_id, voice_renderer=renderer, background_renderer=background, clip_renderer=clips)
        return {"job_id": job_id, "manifest_hash": manifest["hash"], 'partial': any(status.get('state') != 'completed' for status in manifest.get('output_status', {}).values()), 'completed_outputs': manifest.get('completed_outputs'), 'queued_outputs': queued_outputs}
    if task["kind"] in ("quiz", "cards"):
        from .quiz import generate_quiz
        from .cards import plan_cards
        current = store.require_source_approval(job_id)
        if payload.get("source_hash") != current["source_hash"]:
            raise WorkflowError("대기 중인 퀴즈·카드 작업의 원고 버전이 변경되었습니다")
        result = generate_quiz(store, job_id) if task["kind"] == "quiz" else plan_cards(store, job_id, images=task["payload"].get("images"))
        return {"job_id": job_id, "source_hash": current["source_hash"], "version": result["version"], "passed": result["checks"]["passed"], "issues": len(result["checks"]["issues"])}
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
        # 퀴즈·카드뉴스는 부가 산출물이라 실패해도 작업 상태(출고 흐름)를 막지 않는다. 실패 기록은 작업·이벤트에 남는다.
        if job_id and task["kind"] not in ("quiz", "cards", "private_delivery", "thumbnail_images"):
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
