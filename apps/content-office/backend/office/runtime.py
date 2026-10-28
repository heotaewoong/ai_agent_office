"""Local process ownership, conservative recovery, and the authorized work window."""
from __future__ import annotations

import json
import multiprocessing
import os
import signal
import sys
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
    """OS locks are released on process death; PID files alone are not locks."""
    def __init__(self, path):
        self.path = Path(path)
        self.handle = None

    def __enter__(self):
        self.path.parent.mkdir(parents=True, exist_ok=True)
        self.handle = os.fdopen(os.open(self.path, os.O_RDWR | os.O_CREAT, 0o600), "r+b")
        try:
            if os.name == "nt":
                import msvcrt
                # Windows byte-range locks require an existing byte. All owners
                # lock byte zero, including while the PID text is rewritten.
                self.handle.seek(0, os.SEEK_END)
                if not self.handle.tell():
                    self.handle.write(b"\0")
                    self.handle.flush()
                self.handle.seek(0)
                msvcrt.locking(self.handle.fileno(), msvcrt.LK_NBLCK, 1)
            else:
                import fcntl
                fcntl.flock(self.handle.fileno(), fcntl.LOCK_EX | fcntl.LOCK_NB)
        except OSError:
            self.handle.close()
            self.handle = None
            raise AlreadyRunning(f"already running: {self.path.name}") from None
        try:
            self.handle.seek(0)
            self.handle.write((str(os.getpid()) + "\n").encode("ascii"))
            self.handle.truncate()
            self.handle.flush()
        except BaseException:
            self.__exit__()
            raise
        return self

    def __exit__(self, *_):
        if self.handle is not None:
            try:
                if os.name == "nt":
                    import msvcrt
                    self.handle.seek(0)
                    msvcrt.locking(self.handle.fileno(), msvcrt.LK_UNLCK, 1)
                else:
                    import fcntl
                    fcntl.flock(self.handle.fileno(), fcntl.LOCK_UN)
            finally:
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


def same_managed_process(identity, recorded):
    """True only for the very process we started: same start time, and same argv or same executable.

    Next.js rewrites its argv to 'next-server (vX)', so argv alone wrongly rejects our own frontend.
    The start time already rules out PID reuse; the executable check keeps an unrelated program out.
    """
    if not identity or not recorded or identity.get("start_ticks") != recorded.get("start_ticks"):
        return False
    if identity.get("args") == recorded.get("args"):
        return True
    return bool(recorded.get("executable")) and identity.get("executable") == recorded.get("executable")


def process_identity(pid):
    """Creation token and command prevent signalling a reused, unrelated PID."""
    try:
        if not pid or int(pid) <= 0:
            return None
        if os.name == "nt" or sys.platform == "darwin":
            import psutil
            try:
                process = psutil.Process(int(pid))
                with process.oneshot():
                    prefix = "darwin:" if sys.platform == "darwin" else "windows:"
                    return {"pid": process.pid, "start_ticks": prefix + str(process.create_time()), "args": process.cmdline(), "executable": process.exe()}
            except psutil.Error:
                return None
        root = Path("/proc") / str(int(pid))
        stat = (root / "stat").read_text(encoding="utf-8").rsplit(")", 1)[1].split()
        args = (root / "cmdline").read_bytes().split(b"\0")
        return {"pid": int(pid), "start_ticks": stat[19], "args": [arg.decode(errors="replace") for arg in args if arg], "executable": str((root / "exe").resolve(strict=True))}
    except (OSError, TypeError, ValueError, IndexError):
        return None


def worker_heartbeat(store, owner, state="online", **values):
    identity = process_identity(os.getpid()) or {}
    previous = store.setting("worker_status", {})
    store.set_setting("worker_status", {**(previous if previous.get("owner") == owner else {}), "state": state, "pid": os.getpid(), "start_ticks": identity.get("start_ticks"), "identity": identity, "role": "office.worker", "state_root": str(store.root), "heartbeat": now(), "owner": owner, **values})


def stop_owned_worker(store, expected=None):
    status = store.setting("worker_status", {})
    pid = status.get("pid")
    identity = process_identity(pid) if pid else None
    saved_identity = status.get("identity", {})
    supervised = status.get("role") == "office.worker" and saved_identity == identity
    if not identity or ("office.worker" not in identity["args"] and not supervised):
        return {"state": "not_running_or_not_owned", "pid": pid}
    if status.get("state_root") != str(store.root) or not status.get("start_ticks") or identity["start_ticks"] != status["start_ticks"]:
        return {"state": "identity_changed", "pid": pid}
    if expected and (identity["pid"] != expected.get("pid") or identity["start_ticks"] != expected.get("start_ticks")):
        return {"state": "identity_changed", "pid": pid}
    if pid == os.getpid():
        return {"state": "refused_self", "pid": pid}
    try:
        if os.name == "nt":
            return {"pid": pid, "start_ticks": identity["start_ticks"], **_WindowsProcessTree(identity).stop()}
        else:
            os.kill(pid, signal.SIGTERM)
        return {"state": "termination_requested", "pid": pid, "start_ticks": identity["start_ticks"]}
    except ProcessLookupError:
        return {"state": "already_exited", "pid": pid}


class _WindowsProcessTree:
    """Retain native creation identities even after the owned root exits.

    A descendant is admitted only through psutil's PID-reuse-aware children()
    traversal of a previously verified tree member. Every suspend/kill obtains
    a fresh Process and rechecks creation time; a reused PID is never signalled.
    """
    def __init__(self, identity):
        self.root = (identity["pid"], identity["start_ticks"])
        self.members = {self.root: None}
        self.changed = set()
        self.errors = set()

    def _matching(self, identity):
        import psutil
        try:
            process = psutil.Process(identity[0])
            if "windows:" + str(process.create_time()) != identity[1]:
                self.changed.add(identity)
                return None
            return process
        except psutil.NoSuchProcess:
            return None
        except psutil.Error:
            self.errors.add(identity)
            return None

    def capture(self):
        import psutil
        visited = set()
        # A retained child remains owned after its root exits. Traverse that
        # verified child too, including grandchildren created since last poll.
        for anchor in list(self.members):
            if anchor in visited:
                continue
            owner = self._matching(anchor)
            if owner is None:
                continue
            try:
                visited.add(anchor)
                for child in owner.children(recursive=True):
                    try:
                        identity = (child.pid, "windows:" + str(child.create_time()))
                        self.members.setdefault(identity, None)
                        visited.add(identity)
                    except psutil.NoSuchProcess:
                        continue
                    except psutil.Error:
                        self.errors.add((child.pid, "unreadable"))
            except psutil.NoSuchProcess:
                continue
            except psutil.Error:
                self.errors.add(anchor)

    def stop(self):
        import psutil
        # Freeze each proven member before the final snapshot so a subprocess
        # cannot create a new generation while its ancestors are being stopped.
        frozen = set()
        while True:
            for identity in list(self.members):
                if identity in frozen:
                    continue
                process = self._matching(identity)
                if process is not None:
                    try:
                        process.suspend()
                    except psutil.NoSuchProcess:
                        pass
                    except psutil.Error:
                        self.errors.add(identity)
                frozen.add(identity)
            self.capture()
            if all(identity in frozen for identity in self.members):
                break
        signalled = []
        for identity in reversed(self.members):
            process = self._matching(identity)
            if process is None:
                continue
            try:
                # psutil also checks for PID reuse immediately before kill().
                process.kill()
                signalled.append(process)
            except psutil.NoSuchProcess:
                pass
            except psutil.Error:
                self.errors.add(identity)
        alive = psutil.wait_procs(signalled, timeout=2)[1] if signalled else []
        if alive or self.errors:
            return {"state": "termination_failed", "remaining_pids": [process.pid for process in alive], "unverified_pids": sorted({identity[0] for identity in self.errors})}
        if self.root in self.changed:
            return {"state": "identity_changed"}
        return {"state": "termination_requested" if signalled else "already_exited", "tree_verified": True, "processes_stopped": len(signalled)}


def _terminate_deadline_child(process, tree=None):
    """Stop retained descendants even when the owned worker has already died."""
    if os.name == "nt":
        if tree is None and process.is_alive():
            identity = process_identity(process.pid)
            if identity:
                tree = _WindowsProcessTree(identity)
        if tree is not None:
            outcome = tree.stop()
            if outcome["state"] == "termination_failed":
                raise WorkflowError("마감 작업 프로세스 트리 종료를 확인하지 못했습니다. 운영 기록과 작업 잠금을 확인하세요")
        elif process.is_alive():
            # The multiprocessing handle still proves ownership of this child;
            # stop it, but never claim its unobservable subtree was verified.
            process.terminate()
            process.join(timeout=2)
            raise WorkflowError("마감 작업 프로세스의 소유 트리를 확인하지 못했습니다")
    elif process.is_alive():
        process.terminate()
    process.join(timeout=2)
    if process.is_alive():
        process.kill()
        process.join(timeout=2)
    if process.is_alive():
        raise WorkflowError("마감 작업 프로세스 종료를 확인하지 못했습니다. 작업 잠금을 확인하세요")


def run_before_deadline(target, args, end_at, *, subprocess_mode=None):
    """Run a picklable target until authorization expires, including blocked I/O.

    POSIX retains synchronous SIGALRM unwinding. Windows supervises a spawned
    process because Python threads/signals cannot interrupt native blocking I/O.
    The caller reconciles state after WindowDeadline under its normal OS lock.
    """
    end_at = aware_time(end_at) if end_at else None
    seconds = (end_at - utcnow()).total_seconds() if end_at else None
    if seconds is not None and seconds <= 0:
        raise WindowDeadline()
    subprocess_mode = os.name == "nt" if subprocess_mode is None else subprocess_mode
    if subprocess_mode:
        process = multiprocessing.get_context("spawn").Process(target=target, args=args)
        process.start()
        tree = None
        try:
            if os.name == "nt":
                identity = process_identity(process.pid)
                if identity:
                    tree = _WindowsProcessTree(identity)
                elif process.is_alive():
                    raise WorkflowError("작업 프로세스 소유자를 확인하지 못했습니다")
            while process.is_alive():
                if end_at and (end_at - utcnow()).total_seconds() <= 0:
                    _terminate_deadline_child(process, tree)
                    raise WindowDeadline()
                if tree is not None:
                    tree.capture()
                # Startup counts against authorization. Poll native descendants
                # so cleanup retains their identities if another actor kills
                # the root before the deadline supervisor wakes up.
                remaining = (end_at - utcnow()).total_seconds() if end_at else None
                if remaining is not None and remaining <= 0:
                    _terminate_deadline_child(process, tree)
                    raise WindowDeadline()
                process.join(timeout=min(.2, remaining) if remaining is not None else .2)
            if process.exitcode:
                raise WorkerInterrupted(f"child_exit_{process.exitcode}")
        finally:
            _terminate_deadline_child(process, tree)
            process.close()
        return
    if end_at is None:
        return target(*args)
    def deadline(signum, frame):
        raise WindowDeadline()
    previous = signal.signal(signal.SIGALRM, deadline)
    signal.setitimer(signal.ITIMER_REAL, seconds)
    try:
        return target(*args)
    finally:
        signal.setitimer(signal.ITIMER_REAL, 0)
        signal.signal(signal.SIGALRM, previous)


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
