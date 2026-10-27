"""Local process ownership, conservative recovery, and the authorized work window."""
from __future__ import annotations

import fcntl
import json
import os
import signal
import threading
import time
from datetime import datetime, timedelta, timezone
from pathlib import Path
from zoneinfo import ZoneInfo

from .store import WorkflowError, canonical, now

SEOUL = ZoneInfo("Asia/Seoul")


def utcnow():
    return datetime.now(timezone.utc)


def aware_time(value):
    result = datetime.fromisoformat(value) if isinstance(value, str) else value
    if not isinstance(result, datetime) or result.tzinfo is None or result.utcoffset() is None:
        raise WorkflowError("작업 시간대가 필요합니다. UTC 또는 Asia/Seoul offset을 지정하세요")
    return result


def window_open(store, current=None):
    window = store.setting("work_window", {})
    if window.get("status") in ("closed", "stopped"):
        return False
    current = aware_time(current or utcnow())
    return not window.get("authorized_end") or current < aware_time(window["authorized_end"])


class AlreadyRunning(WorkflowError):
    pass


class WorkerInterrupted(BaseException):
    pass


class WindowDeadline(BaseException):
    pass


class ProcessLock:
    """flock is released by the OS on process death; PID files alone are not locks."""
    def __init__(self, path):
        self.path = Path(path)
        self.handle = None

    def __enter__(self):
        self.path.parent.mkdir(parents=True, exist_ok=True)
        self.handle = self.path.open("a+")
        try:
            fcntl.flock(self.handle.fileno(), fcntl.LOCK_EX | fcntl.LOCK_NB)
        except BlockingIOError:
            self.handle.close()
            self.handle = None
            raise AlreadyRunning(f"already running: {self.path.name}") from None
        self.handle.seek(0)
        self.handle.truncate()
        self.handle.write(str(os.getpid()) + "\n")
        self.handle.flush()
        return self

    def __exit__(self, *_):
        if self.handle is not None:
            fcntl.flock(self.handle.fileno(), fcntl.LOCK_UN)
            self.handle.close()
            self.handle = None


def mark_running_unknown(store, *, owner=None, reason="worker_process_lost"):
    """Caller must own worker.lock. Never requeue or release an open cost reservation."""
    recovered = []
    with store.connection(transaction=True) as db:
        sql = "SELECT * FROM tasks WHERE state='running'"
        rows = db.execute(sql + (" AND owner=?" if owner else ""), (owner,) if owner else ()).fetchall()
        for row in rows:
            payload = json.loads(row["payload"])
            result = {"error": "작업자 실행이 중단되어 외부 결과와 비용 대사가 필요합니다. 자동 재시도하지 않습니다", "reason": reason, "previous_owner": row["owner"], "automatic_retry": False}
            db.execute("UPDATE tasks SET state='unknown',result=?,updated_at=? WHERE id=? AND state='running'", (canonical(result), now(), row["id"]))
            job_id = payload.get("job_id")
            if job_id:
                exists = db.execute("SELECT data FROM jobs WHERE id=?", (job_id,)).fetchone()
                if exists:
                    job = json.loads(exists[0])
                    expected = payload.get("_source_hash_at_claim", payload.get("source_hash"))
                    has_snapshot = "_source_hash_at_claim" in payload or "source_hash" in payload
                    legacy_active = not has_snapshot and job.get("state") in ("producing", "drafting", "evaluating")
                    if (has_snapshot and job.get("source_hash") == expected) or legacy_active:
                        job.update(state="needs_reconciliation", error=result["error"])
                        store._write_job(db, job)
            store._event(db, "task_result_unknown", {"task_id": row["id"], "kind": row["kind"], **result}, job_id)
            recovered.append(row["id"])
    return recovered


class WorkerRuntime:
    def __init__(self, store, owner, heartbeat_interval=15):
        self.store = store
        self.owner = owner
        self.heartbeat_interval = heartbeat_interval
        self.lock = ProcessLock(store.root / "worker.lock")
        self.stop_event = threading.Event()
        self.thread = None

    def heartbeat(self, state="online", **values):
        worker_heartbeat(self.store, self.owner, state, single_worker_lock=True, **values)

    def _heartbeats(self):
        while not self.stop_event.wait(self.heartbeat_interval):
            self.heartbeat()

    def __enter__(self):
        self.lock.__enter__()
        try:
            self.recovered = mark_running_unknown(self.store)
            self.heartbeat(recovered_unknown_tasks=self.recovered)
            if self.heartbeat_interval:
                self.thread = threading.Thread(target=self._heartbeats, daemon=True)
                self.thread.start()
            return self
        except BaseException:
            self.lock.__exit__()
            raise

    def __exit__(self, exc_type, exc, traceback):
        self.stop_event.set()
        if self.thread:
            self.thread.join(timeout=2)
        try:
            mark_running_unknown(self.store, owner=self.owner, reason="worker_interrupted" if exc_type else "worker_stopped")
            self.heartbeat("stopped", stopped_at=now())
        finally:
            self.lock.__exit__()


def process_identity(pid):
    """Linux start ticks and command prevent signalling a reused, unrelated PID."""
    try:
        root = Path("/proc") / str(int(pid))
        stat = (root / "stat").read_text().rsplit(")", 1)[1].split()
        args = (root / "cmdline").read_bytes().split(b"\0")
        return {"pid": int(pid), "start_ticks": stat[19], "args": [arg.decode(errors="replace") for arg in args if arg]}
    except (OSError, ValueError, IndexError):
        return None


def worker_heartbeat(store, owner, state="online", **values):
    identity = process_identity(os.getpid()) or {}
    previous = store.setting("worker_status", {})
    store.set_setting("worker_status", {**(previous if previous.get("owner") == owner else {}), "state": state, "pid": os.getpid(), "start_ticks": identity.get("start_ticks"), "state_root": str(store.root), "heartbeat": now(), "owner": owner, **values})


def stop_owned_worker(store, expected=None):
    status = store.setting("worker_status", {})
    pid = status.get("pid")
    identity = process_identity(pid) if pid else None
    if not identity or "office.worker" not in identity["args"]:
        return {"state": "not_running_or_not_owned", "pid": pid}
    if status.get("state_root") != str(store.root) or not status.get("start_ticks") or identity["start_ticks"] != status["start_ticks"]:
        return {"state": "identity_changed", "pid": pid}
    if expected and (identity["pid"] != expected.get("pid") or identity["start_ticks"] != expected.get("start_ticks")):
        return {"state": "identity_changed", "pid": pid}
    if pid == os.getpid():
        return {"state": "refused_self", "pid": pid}
    try:
        os.kill(pid, signal.SIGTERM)
        return {"state": "termination_requested", "pid": pid, "start_ticks": identity["start_ticks"]}
    except ProcessLookupError:
        return {"state": "already_exited", "pid": pid}


class WindowWatcher:
    def __init__(self, store, end_at, inspect, *, clock=utcnow, sleeper=time.sleep, stop_worker=None, interval=1200, heartbeat=60):
        self.store = store
        self.end_at = aware_time(end_at)
        self.inspect = inspect
        self.clock = clock
        self.sleeper = sleeper
        self.stop_worker = stop_worker or (lambda: stop_owned_worker(store))
        self.interval = interval
        self.heartbeat_seconds = heartbeat
        self.log_path = store.root / "runtime" / "watch-window.jsonl"
        self.checks_completed = 0
        self.state = "starting"

    def emit(self, kind, **values):
        record = {"at": aware_time(self.clock()).astimezone(SEOUL).isoformat(), "kind": kind, "pid": os.getpid(), **values}
        self.log_path.parent.mkdir(parents=True, exist_ok=True)
        with self.log_path.open("a", encoding="utf-8") as stream:
            stream.write(canonical(record) + "\n")
        return record

    def status(self, state, **values):
        self.state = state
        self.store.set_setting("watcher_status", {"state": state, "pid": os.getpid(), "heartbeat": aware_time(self.clock()).astimezone(SEOUL).isoformat(), "authorized_end": self.end_at.astimezone(SEOUL).isoformat(), "checks_completed": self.checks_completed, "paid_calls": 0, "automatic_drafts": 0, "log_path": str(self.log_path), **values})

    def close(self):
        stopped = aware_time(self.clock()).astimezone(SEOUL).isoformat()
        outcome = self.stop_worker()
        with self.store.connection(transaction=True) as db:
            row = db.execute("SELECT value FROM settings WHERE key='work_window'").fetchone()
            window = json.loads(row[0]) if row else {}
            window.update(status="closed", actual_stopped_at=stopped, automatic_research_stopped_at=stopped)
            db.execute("INSERT OR REPLACE INTO settings VALUES('work_window',?)", (canonical(window),))
        self.status("stopped", stopped_at=stopped, worker_stop=outcome)
        self.emit("window_stopped", stopped_at=stopped, worker_stop=outcome)

    def run(self):
        with ProcessLock(self.store.root / "watcher.lock"):
            next_check = aware_time(self.clock())
            self.emit("watcher_started", authorized_end=self.end_at.astimezone(SEOUL).isoformat())
            try:
                while True:
                    current = aware_time(self.clock())
                    remaining = (self.end_at - current).total_seconds()
                    if remaining <= 0:
                        self.close()
                        return
                    self.status("online")
                    if current >= next_check and remaining > 60:
                        self.emit("inspection_started")
                        try:
                            report = self.inspect()
                            self.checks_completed += 1
                            self.emit("inspection_completed", report=report)
                        except Exception as error:
                            self.emit("inspection_failed", error_type=type(error).__name__, error="검사에 실패했습니다. 서비스와 검사 기록을 확인하세요")
                        next_check = aware_time(self.clock()) + timedelta(seconds=self.interval)
                    else:
                        self.emit("waiting", reason="deadline_guard" if remaining <= 60 else "next_scheduled_inspection", seconds_remaining=max(0, remaining))
                    after = aware_time(self.clock())
                    until_heartbeat = max(0, self.heartbeat_seconds - (after - current).total_seconds())
                    self.sleeper(min(until_heartbeat, max(0, (self.end_at - after).total_seconds())))
            except WindowDeadline:
                self.close()
                return
            except BaseException:
                self.status("interrupted", stopped_at=aware_time(self.clock()).astimezone(SEOUL).isoformat())
                self.emit("watcher_interrupted")
                raise


def inspect_state(store, seen_manifests):
    """Inspect current approval bindings and each newly observed manifest's actual files."""
    import hashlib
    import math
    import subprocess
    from .store import digest

    issues = []
    files_checked = 0
    media_probes = []
    checked = 0
    jobs = store.jobs()
    budget = store.budget()
    if budget["remaining_krw"] < 0 or budget["cap_krw"] > 10000:
        issues.append({"code": "budget_exceeded"})
    for job in jobs:
        job_id = job["id"]
        if job.get("source_packet") and digest(job["source_packet"]) != job.get("source_hash"):
            issues.append({"code": "source_hash_mismatch", "job_id": job_id})
        approval = job.get("source_approval") or {}
        if approval and (approval.get("version") != job.get("source_hash") or approval.get("selections") != job.get("selections")):
            issues.append({"code": "source_approval_mismatch", "job_id": job_id})
        manifest = job.get("manifest") or {}
        if not manifest:
            continue
        if manifest.get("source_hash") != job.get("source_hash"):
            issues.append({"code": "manifest_source_mismatch", "job_id": job_id})
        release = job.get("release_approval") or {}
        if release and release.get("version") != manifest.get("hash"):
            issues.append({"code": "release_approval_mismatch", "job_id": job_id})
        version = manifest.get("hash")
        if not version or version in seen_manifests:
            continue
        checked += 1
        before = len(issues)
        for artifact in manifest.get("files", []):
            path = (store.artifacts / artifact["path"]).resolve()
            if not path.is_relative_to(store.artifacts.resolve()):
                issues.append({"code": "artifact_path_invalid", "job_id": job_id, "asset_id": artifact.get("id")})
                continue
            if not path.is_file():
                issues.append({"code": "artifact_missing", "job_id": job_id, "asset_id": artifact.get("id")})
                continue
            files_checked += 1
            hasher = hashlib.sha256()
            with path.open("rb") as stream:
                for block in iter(lambda: stream.read(1024 * 1024), b""):
                    hasher.update(block)
            if hasher.hexdigest() != artifact.get("sha256"):
                issues.append({"code": "artifact_hash_mismatch", "job_id": job_id, "asset_id": artifact.get("id")})
            if path.suffix.lower() in (".mp4", ".mp3", ".wav", ".m4a"):
                try:
                    result = subprocess.run(["ffprobe", "-v", "error", "-show_format", "-show_streams", "-of", "json", str(path)], capture_output=True, text=True, timeout=10, check=True)
                    probe = json.loads(result.stdout)
                    duration = float(probe["format"]["duration"])
                    if not math.isfinite(duration) or not 0 < duration <= 60.1:
                        raise ValueError("duration")
                    streams = probe.get("streams", [])
                    if not any(stream.get("codec_type") == "audio" for stream in streams):
                        raise ValueError("audio missing")
                    if path.suffix.lower() == ".mp4" and not any(stream.get("codec_type") == "video" and stream.get("width") == 1080 and stream.get("height") == 1920 for stream in streams):
                        raise ValueError("portrait dimensions")
                    media_probes.append({"asset_id": artifact.get("id"), "duration_seconds": duration, "streams": [{key: stream.get(key) for key in ("codec_type", "codec_name", "width", "height", "sample_rate")} for stream in streams]})
                except (OSError, ValueError, KeyError, subprocess.SubprocessError):
                    issues.append({"code": "media_probe_failed", "job_id": job_id, "asset_id": artifact.get("id")})
        if len(issues) == before:
            seen_manifests.add(version)
    return {"ok": not issues, "issues": issues, "jobs_checked": len(jobs), "budget": budget, "new_manifests_checked": checked, "files_checked": files_checked, "media_probes": media_probes, "paid_calls": 0, "automatic_drafts": 0}
