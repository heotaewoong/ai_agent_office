"""Start the worker and watcher after an operator opens a work window from the UI (Linux/EC2).

start-local.sh starts these only when a window is already open at launch, and the worker exits when
the window closes. Opening a new window from the UI therefore needs a matching start, recorded in the
same PID registry so stop-local.sh can stop them. Windows keeps using start-windows.ps1 -Worker -Watcher.
"""
from __future__ import annotations

import json
import os
import signal
from pathlib import Path
import subprocess
import sys
import time

from .runtime import ProcessLock, aware_time, process_identity, utcnow
from .store import canonical

SCOPE = "heobrain-content-office"


def _alive(record):
    identity = process_identity(record.get("pid")) if record.get("pid") else None
    return bool(identity and identity.get("start_ticks") == record.get("start_ticks"))


def _active_window(store):
    window = store.setting("work_window", {}) or {}
    if window.get("status") in ("closed", "stopped") or not window.get("authorized_end"):
        return False
    return utcnow() < aware_time(window["authorized_end"])


def stop_windowless_services(store, *, app_dir=None, timeout=10.0, kill=None):
    """Stop the worker/watcher that start-local.sh launched while no work window existed.

    Such a worker has no deadline, so it would run past any window the operator opens next; the
    operator's "작업 시간 열기" replaces it with a deadline-bound one. A worker that belongs to an
    active window is never touched. Returns the names that were stopped.
    """
    if _active_window(store):
        return []
    app = Path(app_dir or Path(__file__).resolve().parents[2]).resolve()
    runtime = store.root / "runtime"
    registry = runtime / "services.json"
    if not registry.is_file():
        return []
    kill = kill or (lambda pid: os.kill(pid, signal.SIGTERM))
    stopped = []
    with ProcessLock(runtime / "services-management.lock"):
        record = json.loads(registry.read_text())
        if record.get("scope") != SCOPE or record.get("app_dir") != str(app):
            return []
        services = record.setdefault("services", {})
        for name in ("watcher", "worker"):
            entry = services.get(name)
            if not entry or not _alive(entry):
                services.pop(name, None) if entry else None
                continue
            kill(int(entry["pid"]))
            deadline = time.monotonic() + timeout
            while _alive(entry) and time.monotonic() < deadline:
                time.sleep(.1)
            if _alive(entry):
                continue
            services.pop(name, None)
            stopped.append(name)
        registry.write_text(canonical(record))
        registry.chmod(0o600)
    if stopped:
        store.event("window_services_stopped", {"stopped": stopped, "reason": "windowless_services_replaced", "source": "local_operator_ui"})
    return stopped


def start_window_services(store, *, app_dir=None, platform=None, spawn=None):
    platform = platform or os.name
    app = Path(app_dir or Path(__file__).resolve().parents[2]).resolve()
    if platform == "nt":
        return {"started": [], "running": [], "note": "Windows에서는 start-windows.ps1 -Worker -Watcher로 작업자를 시작하세요"}
    runtime = store.root / "runtime"
    registry = runtime / "services.json"
    if not registry.is_file():
        return {"started": [], "running": [], "note": "start-local.sh로 시작된 서비스 장부가 없어 작업자를 시작하지 않았습니다"}
    spawn = spawn or subprocess.Popen
    started, running = [], []
    with ProcessLock(runtime / "services-management.lock"):
        record = json.loads(registry.read_text())
        if record.get("scope") != SCOPE or record.get("app_dir") != str(app):
            return {"started": [], "running": [], "note": "다른 프로젝트의 서비스 장부라 작업자를 시작하지 않았습니다"}
        services = record.setdefault("services", {})
        commands = {
            "worker": ([sys.executable, "-m", "office.worker"], app / "backend"),
            "watcher": ([sys.executable, str(app / "scripts" / "watch_window.py")], app),
        }
        for name, (command, cwd) in commands.items():
            if name in services and _alive(services[name]):
                running.append(name)
                continue
            log = runtime / f"{name}.log"
            with log.open("ab") as output:
                process = spawn(command, cwd=cwd, env=os.environ.copy(), stdin=subprocess.DEVNULL,
                                stdout=output, stderr=subprocess.STDOUT, start_new_session=True)
            time.sleep(.15)
            identity = process_identity(process.pid)
            if process.poll() is not None or not identity:
                continue
            services[name] = {**identity, "log": str(log), "cwd": str(cwd)}
            started.append(name)
        registry.write_text(canonical(record))
        registry.chmod(0o600)
    store.event("window_services_started", {"started": started, "running": running, "source": "local_operator_ui"})
    return {"started": started, "running": running, "note": "작업 시간이 끝나면 작업자는 스스로 종료합니다"}
