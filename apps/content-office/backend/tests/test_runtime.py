from datetime import datetime, timedelta, timezone
import json
import os
import subprocess
import sys
from pathlib import Path

import pytest

from office.store import Store, WorkflowError


def runtime():
    from office import runtime
    return runtime


def make_task(store, source="old"):
    job = store.create_job({"id": "article-1", "title": "기사"})
    store.save_source(job["id"], {"title": "기사", "body": source})
    job = store.job(job["id"])
    task = store.enqueue("produce", {"job_id": job["id"], "source_hash": job["source_hash"]}, "one")
    store.claim("dead-worker")
    store.update_job(job["id"], state="producing")
    return job, task


def test_process_lock_rejects_live_duplicate_and_releases_on_exit(tmp_path):
    module = runtime()
    lock_path = tmp_path / "worker.lock"
    with module.ProcessLock(lock_path):
        child = subprocess.run([sys.executable, "-c", "from office.runtime import ProcessLock; import sys;\nwith ProcessLock(sys.argv[1]): pass", str(lock_path)], capture_output=True, text=True)
        assert child.returncode != 0
        assert "already running" in child.stderr
    with module.ProcessLock(lock_path):
        pass


def test_recovery_requires_worker_lock_and_preserves_cost_reservation(tmp_path):
    module = runtime()
    store = Store(tmp_path)
    job, task = make_task(store)
    cost = store.reserve_cost("tts", 321, {"cache_key": "pending-call"})
    with module.WorkerRuntime(store, "new-worker", heartbeat_interval=0):
        assert store.task(task["id"])["state"] == "unknown"
        assert store.job(job["id"])["state"] == "needs_reconciliation"
        assert store.budget()["reserved_krw"] == 321
        assert store.claim("new-worker") is None
        with pytest.raises(module.AlreadyRunning):
            with module.WorkerRuntime(store, "duplicate", heartbeat_interval=0):
                pass
        assert store.setting("worker_status")["owner"] == "new-worker"
    assert store.setting("worker_status")["state"] == "stopped"


def test_recovery_does_not_change_newer_source_or_approval(tmp_path):
    module = runtime()
    store = Store(tmp_path)
    job, task = make_task(store)
    newest = store.save_source(job["id"], {"title": "수정", "body": "new"})
    before = store.job(job["id"])
    with module.WorkerRuntime(store, "new-worker", heartbeat_interval=0):
        assert store.task(task["id"])["state"] == "unknown"
        assert store.job(job["id"]) == before
    assert newest["source_hash"] != job["source_hash"]


def test_worker_deadline_stops_before_claim_and_rejects_naive_time(tmp_path):
    module = runtime()
    store = Store(tmp_path)
    store.set_setting("work_window", {"authorized_end": "2026-10-26T08:20:00+09:00"})
    store.enqueue("refresh", {}, "refresh")
    current = datetime(2026, 10, 25, 23, 20, tzinfo=timezone.utc)
    assert module.window_open(store, current) is False
    store.set_setting("work_window", {"authorized_end": "2026-10-26T08:20:00"})
    with pytest.raises(WorkflowError, match="시간대"):
        module.window_open(store, current)


class FakeClock:
    def __init__(self, current):
        self.current = current
    def now(self):
        return self.current
    def sleep(self, seconds):
        self.current += timedelta(seconds=seconds)


def test_watcher_does_no_inspection_after_deadline_and_records_actual_stop(tmp_path):
    module = runtime()
    store = Store(tmp_path)
    end = datetime(2026, 10, 26, 8, 20, tzinfo=timezone(timedelta(hours=9)))
    fake = FakeClock(end + timedelta(seconds=3))
    def unexpected():
        raise AssertionError("expired window started an inspection")
    watcher = module.WindowWatcher(store, end, unexpected, clock=fake.now, sleeper=fake.sleep)
    watcher.run()
    status = store.setting("watcher_status")
    assert status["state"] == "stopped"
    assert status["checks_completed"] == 0
    assert status["stopped_at"] == "2026-10-26T08:20:03+09:00"
    assert store.setting("work_window")["status"] == "closed"


def test_watcher_runs_real_checks_every_twenty_minutes_and_waits_separately(tmp_path):
    module = runtime()
    store = Store(tmp_path)
    start = datetime(2026, 10, 26, 7, 38, tzinfo=timezone(timedelta(hours=9)))
    end = datetime(2026, 10, 26, 8, 20, tzinfo=timezone(timedelta(hours=9)))
    fake = FakeClock(start)
    checks = []
    def inspect():
        checks.append(fake.now())
        return {"api": "ok", "paid_calls": 0}
    watcher = module.WindowWatcher(store, end, inspect, clock=fake.now, sleeper=fake.sleep)
    watcher.run()
    assert checks == [start, start + timedelta(minutes=20), start + timedelta(minutes=40)]
    events = [json.loads(line) for line in watcher.log_path.read_text().splitlines()]
    assert sum(event["kind"] == "inspection_completed" for event in events) == 3
    assert any(event["kind"] == "waiting" for event in events)
    assert store.setting("watcher_status")["checks_completed"] == 3
    assert store.setting("watcher_status")["stopped_at"] == "2026-10-26T08:20:00+09:00"


def test_watcher_does_not_start_heavy_check_in_last_minute(tmp_path):
    module = runtime()
    store = Store(tmp_path)
    end = datetime(2026, 10, 26, 8, 20, tzinfo=timezone(timedelta(hours=9)))
    fake = FakeClock(end - timedelta(seconds=59))
    def unexpected():
        raise AssertionError("last-minute inspection")
    watcher = module.WindowWatcher(store, end, unexpected, clock=fake.now, sleeper=fake.sleep)
    watcher.run()
    assert store.setting("watcher_status")["checks_completed"] == 0
    assert fake.now() == end


def test_watcher_duplicate_never_closes_live_window(tmp_path):
    module = runtime()
    store = Store(tmp_path)
    store.set_setting("work_window", {"status": "active"})
    end = datetime.now(timezone.utc) + timedelta(hours=1)
    with module.ProcessLock(store.root / "watcher.lock"):
        with pytest.raises(module.AlreadyRunning):
            module.WindowWatcher(store, end, lambda: {}).run()
    assert store.setting("work_window")["status"] == "active"


def test_run_once_after_deadline_leaves_queued_task_untouched(tmp_path):
    from office.worker import run_once
    store = Store(tmp_path)
    store.set_setting("work_window", {"authorized_end": "2000-01-01T00:00:00+09:00"})
    task = store.enqueue("refresh", {}, "refresh")
    assert run_once(store, "worker") is False
    assert store.task(task["id"])["state"] == "queued"


def test_interrupted_worker_records_uncertainty(tmp_path):
    module = runtime()
    store = Store(tmp_path)
    with pytest.raises(module.WorkerInterrupted):
        with module.WorkerRuntime(store, "new-worker", heartbeat_interval=0):
            task = store.enqueue("refresh", {}, "new-task")
            store.claim("new-worker")
            raise module.WorkerInterrupted()
    assert store.task(task["id"])["state"] == "unknown"


def test_state_inspection_detects_approval_and_asset_corruption(tmp_path):
    module = runtime()
    store = Store(tmp_path)
    job, _ = make_task(store)
    store.update_job(job["id"], source_approval={"version": "wrong", "decision": "approved", "selections": job["selections"]})
    report = module.inspect_state(store, set())
    assert report["ok"] is False
    assert any(item["code"] == "source_approval_mismatch" for item in report["issues"])
    store.update_job(job["id"], source_approval=None, manifest={"hash": "manifest", "source_hash": job["source_hash"], "files": [{"id": "asset_1", "name": "test.txt", "path": "../escape.txt", "sha256": "x"}]})
    report = module.inspect_state(store, set())
    assert any(item["code"] == "artifact_path_invalid" for item in report["issues"])


def test_state_inspection_hashes_actual_files_once_per_new_manifest(tmp_path):
    module = runtime()
    import hashlib
    store = Store(tmp_path)
    job, _ = make_task(store)
    asset = store.artifacts / "actual.txt"
    asset.write_text("actual file")
    store.update_job(job["id"], manifest={"hash": "manifest", "source_hash": job["source_hash"], "files": [{"id": "asset_1", "name": "actual.txt", "path": "actual.txt", "sha256": hashlib.sha256(b"actual file").hexdigest()}]})
    seen = set()
    first = module.inspect_state(store, seen)
    assert first["new_manifests_checked"] == 1
    assert first["files_checked"] == 1
    assert module.inspect_state(store, seen)["new_manifests_checked"] == 0
    store.update_job(job["id"], manifest={"hash": "manifest-v2", "source_hash": job["source_hash"], "files": [{"id": "asset_1", "name": "actual.txt", "path": "actual.txt", "sha256": "bad"}]})
    assert module.inspect_state(store, seen)["ok"] is False
    assert "manifest-v2" not in seen


def test_uncertain_external_result_is_unknown_and_not_failed_retryable(tmp_path, monkeypatch):
    from office import worker
    store = Store(tmp_path)
    task = store.enqueue("refresh", {}, "refresh")
    def unknown_result(store, task):
        raise WorkflowError("모델 응답을 확인하지 못했습니다. 비용 예약을 유지하며 자동 재호출하지 않습니다")
    monkeypatch.setattr(worker, "process_task", unknown_result)
    worker.run_once(store, "worker")
    assert store.task(task["id"])["state"] == "unknown"


def test_watch_script_expired_window_makes_no_network_calls(tmp_path):
    store = Store(tmp_path)
    store.set_setting("work_window", {"authorized_end": "2000-01-01T00:00:00+09:00"})
    script = Path(__file__).resolve().parents[2] / "scripts/watch_window.py"
    environment = {**os.environ, "OFFICE_STATE_DIR": str(tmp_path)}
    process = subprocess.run([sys.executable, str(script), "--check-once"], env=environment, capture_output=True, text=True, timeout=10)
    assert process.returncode == 0, process.stderr
    assert json.loads(process.stdout)["state"] == "skipped"
    assert not (tmp_path / "runtime/rss").exists()
    assert store.setting("feed_report") is None


def test_worker_process_death_is_recovered_only_after_os_lock_is_released(tmp_path):
    module = runtime()
    store = Store(tmp_path)
    task = store.enqueue("refresh", {}, "refresh")
    code = "from office.store import Store; from office.runtime import WorkerRuntime; import sys,time; s=Store(sys.argv[1]); r=WorkerRuntime(s,'dead',heartbeat_interval=0); r.__enter__(); s.claim('dead'); s.reserve_cost('test',321,{'cache_key':'dead-worker'}); print('ready',flush=True); time.sleep(60)"
    child = subprocess.Popen([sys.executable, "-c", code, str(tmp_path)], stdout=subprocess.PIPE, text=True)
    owned_process = None
    try:
        assert child.stdout.readline().strip() == "ready"
        with pytest.raises(module.AlreadyRunning):
            with module.WorkerRuntime(store, "new", heartbeat_interval=0):
                pass
        assert store.task(task["id"])["state"] == "running"
        status = store.setting("worker_status")
        identity = status["identity"]
        assert module.process_identity(status["pid"]) == identity
        if os.name == "nt":
            import psutil
            # Popen may own the venv redirector rather than the actual process
            # holding worker.lock. Verify and kill the heartbeat's OS owner.
            owned_process = psutil.Process(identity["pid"])
            assert "windows:" + str(owned_process.create_time()) == identity["start_ticks"]
            owned_process.kill()
            owned_process.wait(timeout=20)
        else:
            assert identity["pid"] == child.pid
            child.kill()
        child.wait(timeout=20)
        current = module.process_identity(identity["pid"])
        assert not current or current["start_ticks"] != identity["start_ticks"]
        with module.WorkerRuntime(store, "new", heartbeat_interval=0):
            assert store.task(task["id"])["state"] == "unknown"
            assert store.budget()["reserved_krw"] == 321
            assert store.claim("new") is None
        with store.connection() as db:
            assert db.execute("SELECT COUNT(*) FROM approvals").fetchone()[0] == 0
    finally:
        if owned_process is not None and owned_process.is_running():
            owned_process.kill()  # psutil checks the captured creation identity
            owned_process.wait(timeout=20)
        if child.poll() is None:
            child.kill()
        child.wait(timeout=20)


def test_stale_queued_task_failure_does_not_block_a_new_source(tmp_path):
    from office.worker import run_once
    store = Store(tmp_path)
    job = store.create_job({"id": "article-1", "title": "기사"})
    first = store.save_source(job["id"], {"title": "옛 제목", "body": "옛 원고"})
    task = store.enqueue("produce", {"job_id": job["id"], "source_hash": first["source_hash"]}, "old")
    current = store.save_source(job["id"], {"title": "새 제목", "body": "새 원고"})
    assert run_once(store, "worker") is True
    assert store.task(task["id"])["state"] == "failed"
    assert store.job(job["id"]) == current


def test_stop_worker_refuses_reused_pid_even_if_module_name_matches(tmp_path, monkeypatch):
    module = runtime()
    store = Store(tmp_path)
    store.set_setting("worker_status", {"pid": 99999, "start_ticks": "old", "state_root": str(store.root)})
    monkeypatch.setattr(module, "process_identity", lambda pid: {"pid": 99999, "start_ticks": "new", "args": ["python", "-m", "office.worker"]})
    def forbidden_signal(*args):
        raise AssertionError("signalled a reused PID")
    monkeypatch.setattr(module.os, "kill", forbidden_signal)
    result = module.stop_owned_worker(store)
    assert result["state"] == "identity_changed"


def test_inspection_ffprobes_real_audio_and_rejects_over_one_minute(tmp_path):
    import hashlib
    import wave
    module = runtime()
    store = Store(tmp_path)
    job, _ = make_task(store)
    audio = store.artifacts / "voice.wav"
    def manifest(seconds, version):
        with wave.open(str(audio), "wb") as stream:
            stream.setnchannels(1)
            stream.setsampwidth(2)
            stream.setframerate(8000)
            stream.writeframes(b"\0\0" * int(8000 * seconds))
        store.update_job(job["id"], manifest={"hash": version, "source_hash": job["source_hash"], "files": [{"id": "asset_voice", "name": "voice.wav", "path": "voice.wav", "sha256": hashlib.sha256(audio.read_bytes()).hexdigest()}]})
    manifest(.25, "short")
    report = module.inspect_state(store, set())
    assert report["media_probes"][0]["duration_seconds"] == .25
    assert report["ok"] is True
    manifest(61, "too-long")
    report = module.inspect_state(store, set())
    assert any(item["code"] == "media_probe_failed" for item in report["issues"])


@pytest.mark.skipif(os.name == "nt", reason="POSIX launcher; Windows launcher has separate lifecycle tests")
def test_start_script_refuses_a_live_managed_process_without_launching_services(tmp_path):
    module = runtime()
    store = Store(tmp_path)
    scripts = Path(__file__).resolve().parents[2] / "scripts"
    directory = tmp_path / "runtime"
    directory.mkdir()
    (directory / "services.json").write_text(json.dumps({"services": {"api": module.process_identity(os.getpid())}}))
    result = subprocess.run([str(scripts / "start-local.sh")], env={**os.environ, "OFFICE_STATE_DIR": str(tmp_path)}, capture_output=True, text=True, timeout=10)
    assert result.returncode != 0
    assert "already running" in result.stderr
    assert not (directory / "api.log").exists()


@pytest.mark.skipif(os.name == "nt", reason="POSIX launcher; Windows launcher has separate lifecycle tests")
def test_stop_script_never_signals_a_reused_registry_pid(tmp_path):
    module = runtime()
    store = Store(tmp_path)
    scripts = Path(__file__).resolve().parents[2] / "scripts"
    identity = module.process_identity(os.getpid())
    identity["start_ticks"] = "wrong-old-process"
    directory = tmp_path / "runtime"
    directory.mkdir()
    (directory / "services.json").write_text(json.dumps({"scope": "heobrain-content-office", "app_dir": str(scripts.parent), "services": {"api": identity}}))
    result = subprocess.run([str(scripts / "stop-local.sh")], env={**os.environ, "OFFICE_STATE_DIR": str(tmp_path)}, capture_output=True, text=True, timeout=10)
    assert result.returncode == 0
    assert "no matching managed processes" in result.stdout
def test_queued_production_contract_change_is_returned_for_review(tmp_path, monkeypatch):
    from office import media, worker
    from office.store import Store, WorkflowError
    store = Store(tmp_path / 'state')
    job = store.create_job({'id': 'fixture', 'title': '설정 변경 시험'})
    job = store.save_source(job['id'], {'title': '합성 원고', 'body': '합성 본문', 'quality': {'status': 'passed', 'critical': []}})
    store.review_source(job['id'], job['source_hash'], 'approved', 'fixture-operator', {'blog': True, 'video': False})
    job = store.job(job['id'])
    previous = media.production_contract(None, job['selections'])['hash']
    monkeypatch.setattr(media, 'RENDER_VERSION', 'changed-after-queue')
    task = {'kind': 'produce', 'payload': {'job_id': job['id'], 'source_hash': job['source_hash'], 'production_contract': previous}}
    with pytest.raises(WorkflowError, match='제작 설정|설정.*변경'):
        worker.process_task(store, task)
    assert not list(store.artifacts.rglob('tistory.html'))

