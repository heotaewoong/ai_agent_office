"""Start the worker and watcher after an operator opens a work window from the UI (Linux/EC2).

start-local.sh starts these only when a window is already open at launch, and the worker exits when
the window closes. Opening a new window from the UI therefore needs a matching start, recorded in the
same PID registry so stop-local.sh can stop them. Windows keeps using start-windows.ps1 -Worker -Watcher.
"""
from __future__ import annotations

import json
import os
from pathlib import Path
import subprocess
import sys
import time

from .runtime import ProcessLock, process_identity
from .store import canonical

SCOPE = "heobrain-content-office"


def _alive(record):
    identity = process_identity(record.get("pid")) if record.get("pid") else None
    return bool(identity and identity.get("start_ticks") == record.get("start_ticks"))


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
