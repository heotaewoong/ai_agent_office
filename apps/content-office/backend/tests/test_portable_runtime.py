"""Portable ownership/deadline behavior; no external model or network calls."""
from datetime import datetime, timedelta, timezone
import json
import os
from pathlib import Path
import subprocess
import sys
import time
from types import SimpleNamespace

import pytest

from office import runtime
from office.store import Store


def blocked_operation(root):
    store = Store(root)
    with runtime.WorkerRuntime(store, "blocked", heartbeat_interval=0):
        store.claim("blocked")
        store.reserve_cost("test", 321, {"cache_key": "deadline-test"})
        (Path(root) / "started").write_text("ready", encoding="utf-8")
        time.sleep(60)
        (Path(root) / "continued").write_text("unauthorized", encoding="utf-8")


def completed_operation(root):
    (Path(root) / "completed").write_text("완료", encoding="utf-8")


def blocked_subprocess_operation(root):
    """Synthetic worker with a native subprocess representing blocked FFmpeg."""
    store = Store(root)
    with runtime.WorkerRuntime(store, "tree-worker", heartbeat_interval=0):
        store.claim("tree-worker")
        store.reserve_cost("test", 321, {"cache_key": "tree-deadline-test"})
        child = subprocess.Popen([sys.executable, "-c", "import time; time.sleep(300)"])
        try:
            ready = Path(root) / "tree-ready.tmp"
            ready.write_text(json.dumps({"worker": runtime.process_identity(os.getpid()), "child": runtime.process_identity(child.pid)}), encoding="utf-8")
            ready.replace(Path(root) / "tree-ready.json")
            child.wait(timeout=300)
        finally:
            # Native TerminateProcess bypasses this, as it does for production.
            if child.poll() is None:
                child.kill()
            child.wait(timeout=5)


def supervised_subprocess_operation(root):
    store = Store(root)
    original_capture = runtime._WindowsProcessTree.capture
    observed = False
    def capture(tree):
        nonlocal observed
        original_capture(tree)
        if not observed and len(tree.members) > 1:
            (Path(root) / "tree-observed").write_text("snapshotted", encoding="utf-8")
            observed = True
    runtime._WindowsProcessTree.capture = capture
    try:
        runtime.run_before_deadline(blocked_subprocess_operation, (root,), datetime.now(timezone.utc) + timedelta(seconds=180), subprocess_mode=True)
    except (runtime.WindowDeadline, runtime.WorkerInterrupted):
        with runtime.WorkerRuntime(store, "tree-recovery", heartbeat_interval=0):
            pass
    finally:
        runtime._WindowsProcessTree.capture = original_capture
    (Path(root) / "supervisor-done").write_text("stopped", encoding="utf-8")


@pytest.mark.skipif(os.name != "nt", reason="Real Windows process-tree termination regression")
@pytest.mark.parametrize("stop_mode", ["watcher", "external-worker-exit"])
def test_windows_supervisor_reaps_blocked_subprocess_when_worker_stops(tmp_path, stop_mode):
    import psutil
    store = Store(tmp_path)
    task = store.enqueue("refresh", {}, "tree-test")
    code = "import sys; sys.path.insert(0, sys.argv[1]); from test_portable_runtime import supervised_subprocess_operation; supervised_subprocess_operation(sys.argv[2])"
    supervisor = subprocess.Popen([sys.executable, "-c", code, str(Path(__file__).parent), str(tmp_path)])
    owned = []
    try:
        ready = tmp_path / "tree-ready.json"
        limit = time.monotonic() + 90
        while not ready.is_file() and time.monotonic() < limit:
            assert supervisor.poll() is None, "supervisor exited before starting the synthetic worker"
            time.sleep(.05)
        assert ready.is_file(), "synthetic worker did not start"
        tree = json.loads(ready.read_text(encoding="utf-8"))
        owned = [tree["worker"], tree["child"]]
        assert store.task(task["id"])["state"] == "running"
        if stop_mode == "watcher":
            watcher = runtime.WindowWatcher(store, datetime.now(timezone.utc), lambda: {})
            watcher.close()
        else:
            # Synchronize with a real capture; avoid relying on scheduler speed
            # before simulating an actor that kills only the worker.
            limit = time.monotonic() + 30
            while not (tmp_path / "tree-observed").is_file() and time.monotonic() < limit:
                time.sleep(.05)
            assert (tmp_path / "tree-observed").is_file()
            process = psutil.Process(tree["worker"]["pid"])
            assert "windows:" + str(process.create_time()) == tree["worker"]["start_ticks"]
            process.kill()
        supervisor.wait(timeout=30)
        assert supervisor.returncode == 0
        assert (tmp_path / "supervisor-done").is_file()
        for identity in owned:
            current = runtime.process_identity(identity["pid"])
            assert not current or current["start_ticks"] != identity["start_ticks"], "owned descendant survived worker termination"
        assert store.task(task["id"])["state"] == "unknown"
        assert store.budget()["reserved_krw"] == 321
        assert store.claim("unexpected-retry") is None
    finally:
        # Even a startup failure must reap this fixture's owned descendants.
        # The native Popen handle proves supervisor ownership; creation tokens
        # protect each snapshotted child if its PID is reused during teardown.
        if supervisor.poll() is None:
            try:
                for process in psutil.Process(supervisor.pid).children(recursive=True):
                    owned.append({"pid": process.pid, "start_ticks": "windows:" + str(process.create_time())})
            except psutil.Error:
                pass
            supervisor.kill()
        for identity in owned:
            current = runtime.process_identity(identity["pid"])
            if current and current["start_ticks"] == identity["start_ticks"]:
                process = psutil.Process(identity["pid"])
                if "windows:" + str(process.create_time()) == identity["start_ticks"]:
                    process.kill()
        supervisor.wait(timeout=20)


@pytest.mark.skipif(os.name != "nt", reason="Native Windows creation-identity boundary")
def test_windows_tree_stop_refuses_a_changed_creation_identity():
    child = subprocess.Popen([sys.executable, "-c", "import time; time.sleep(120)"])
    try:
        identity = runtime.process_identity(child.pid)
        stale = {**identity, "start_ticks": "windows:0.0"}
        outcome = runtime._WindowsProcessTree(stale).stop()
        assert outcome["state"] == "identity_changed"
        assert child.poll() is None, "a process with a different creation identity was signalled"
        assert runtime.process_identity(child.pid) == identity
    finally:
        if child.poll() is None:
            child.kill()
        child.wait(timeout=5)


def test_runtime_import_does_not_require_posix_fcntl():
    code = """
import builtins
original = builtins.__import__
def guarded(name, *args, **kwargs):
    if name == 'fcntl':
        raise ModuleNotFoundError('fcntl unavailable on Windows')
    return original(name, *args, **kwargs)
builtins.__import__ = guarded
import office.runtime
"""
    result = subprocess.run([sys.executable, "-c", code], capture_output=True, text=True, timeout=15)
    assert result.returncode == 0, result.stderr


def test_identity_has_executable_and_creation_token():
    identity = runtime.process_identity(os.getpid())
    assert identity["pid"] == os.getpid()
    assert identity["start_ticks"]
    # A Windows venv's sys.executable is a redirector, while the OS process
    # runs the base interpreter. Keep the executable equality check exact.
    expected_executable = sys._base_executable if os.name == "nt" else sys.executable
    assert Path(identity["executable"]).samefile(expected_executable)
    assert identity["args"]
    assert runtime.process_identity(-1) is None


def test_windows_stop_handles_worker_exit_after_identity_check(tmp_path, monkeypatch):
    # Native-only API boundary: simulate the race after ownership was verified.
    store = Store(tmp_path)
    identity = {"pid": 12345, "start_ticks": "windows:123.0", "args": ["python", "-m", "office.worker"]}
    store.set_setting("worker_status", {**identity, "state_root": str(store.root)})
    class GoneProcess(Exception):
        pass
    def process(pid):
        raise GoneProcess()
    monkeypatch.setattr(runtime, "process_identity", lambda pid: identity)
    monkeypatch.setattr(runtime, "os", SimpleNamespace(name="nt", getpid=os.getpid))
    monkeypatch.setitem(sys.modules, "psutil", SimpleNamespace(Process=process, Error=GoneProcess, NoSuchProcess=GoneProcess))
    assert runtime.stop_owned_worker(store)["state"] == "already_exited"


def test_spawn_deadline_stops_blocked_work_and_retains_reservation(tmp_path):
    runner = getattr(runtime, "run_before_deadline", None)
    assert callable(runner), "shared portable deadline runner is required"
    store = Store(tmp_path)
    task = store.enqueue("refresh", {}, "deadline-refresh")
    # Include spawned interpreter startup on slower Windows machines.
    deadline = datetime.now(timezone.utc) + timedelta(seconds=8)
    started = time.monotonic()
    with pytest.raises(runtime.WindowDeadline):
        runner(blocked_operation, (str(tmp_path),), deadline, subprocess_mode=True)
    assert time.monotonic() - started < 15
    assert (tmp_path / "started").is_file()
    assert not (tmp_path / "continued").exists()
    with runtime.WorkerRuntime(store, "recovery", heartbeat_interval=0):
        assert store.task(task["id"])["state"] == "unknown"
        assert store.budget()["reserved_krw"] == 321
        assert store.claim("recovery") is None


def test_spawn_deadline_allows_completed_work(tmp_path):
    runner = getattr(runtime, "run_before_deadline", None)
    assert callable(runner), "shared portable deadline runner is required"
    runner(completed_operation, (str(tmp_path),), datetime.now(timezone.utc) + timedelta(seconds=15), subprocess_mode=True)
    assert (tmp_path / "completed").read_text(encoding="utf-8") == "완료"


def test_expired_deadline_never_starts_work(tmp_path):
    runner = getattr(runtime, "run_before_deadline", None)
    assert callable(runner), "shared portable deadline runner is required"
    with pytest.raises(runtime.WindowDeadline):
        runner(completed_operation, (str(tmp_path),), datetime(2000, 1, 1, tzinfo=timezone.utc), subprocess_mode=True)
    assert not (tmp_path / "completed").exists()


def test_bootstrap_configuration_uses_utf8_under_windows_locale(tmp_path, monkeypatch):
    from office import bootstrap
    (tmp_path / "config").mkdir()
    (tmp_path / "config/editorial-seed.json").write_text(json.dumps({"selected": [], "candidates": [{"url": "https://example.org", "id": "한국어"}]}, ensure_ascii=False), encoding="utf-8")
    original = Path.read_text
    def windows_read(path, encoding=None, **kwargs):
        return original(path, encoding=encoding or "cp949", **kwargs)
    monkeypatch.setattr(Path, "read_text", windows_read)
    monkeypatch.setattr(bootstrap, "BACKEND", tmp_path)
    assert bootstrap.enrich([{"url": "https://example.org"}])[0]["event_id"] == "한국어"
