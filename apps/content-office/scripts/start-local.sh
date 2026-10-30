#!/usr/bin/env bash
set -euo pipefail
script_dir="$(cd -- "$(dirname -- "${BASH_SOURCE[0]}")" && pwd)"
app_dir="$(cd -- "$script_dir/.." && pwd)"
# Node(next)·Codex CLI가 설치된 사용자 Node 폴더를 항상 실행 경로에 넣는다. 이 경로 없이 띄우면
# Codex 구독 배경처럼 CLI가 필요한 기능이 '연결 안 됨'으로 보인다(2026-10-30 실제 사고).
if [[ -d "$HOME/.local/node/bin" && ":$PATH:" != *":$HOME/.local/node/bin:"* ]]; then
  export PATH="$HOME/.local/node/bin:$PATH"
fi
if [[ -n "${OFFICE_ENV_FILE:-}" ]]; then
  set -a
  source "$OFFICE_ENV_FILE"
  set +a
fi
exec "$app_dir/backend/.venv/bin/python" - "$app_dir" <<'PY'
import json
import os
import signal
import socket
import subprocess
import sys
import time
from pathlib import Path

app = Path(sys.argv[1]).resolve()
sys.path.insert(0, str(app / "backend"))
from office.bootstrap import default_store, initialize
from office.runtime import ProcessLock, process_identity, window_open
from office.store import canonical

store = default_store()
initialize(store, live=False, create_selected=False)
runtime = store.root / "runtime"
runtime.mkdir(exist_ok=True)
registry = runtime / "services.json"
with ProcessLock(runtime / "services-management.lock"):
    if registry.exists():
        saved = json.loads(registry.read_text())
        for item in saved.get("services", {}).values():
            identity = process_identity(item["pid"])
            if identity and identity["start_ticks"] == item.get("start_ticks"):
                raise SystemExit("Managed services are already running; use stop-local.sh before starting again.")
    for port in (8510, 3110):
        with socket.socket() as sock:
            if sock.connect_ex(("127.0.0.1", port)) == 0:
                raise SystemExit(f"Port {port} is already in use. No duplicate services were started.")
    commands = {
        "api": ([sys.executable, "-m", "uvicorn", "office.api:app", "--host", "127.0.0.1", "--port", "8510"], app / "backend"),
        "frontend": ([str(app / "frontend/node_modules/.bin/next"), "start" if (app / "frontend/.next/BUILD_ID").is_file() else "dev", "--hostname", "127.0.0.1", "--port", "3110"], app / "frontend"),
    }
    active = window_open(store)
    if active:
        commands["worker"] = ([sys.executable, "-m", "office.worker"], app / "backend")
        if store.setting("work_window", {}).get("authorized_end"):
            commands["watcher"] = ([sys.executable, str(app / "scripts/watch_window.py")], app)
    services = {}
    children = []
    try:
        for name, (command, cwd) in commands.items():
            log = runtime / f"{name}.log"
            with log.open("ab") as output:
                process = subprocess.Popen(command, cwd=cwd, env=os.environ.copy(), stdin=subprocess.DEVNULL, stdout=output, stderr=subprocess.STDOUT, start_new_session=True)
            children.append(process)
            time.sleep(.15)
            identity = process_identity(process.pid)
            if process.poll() is not None or not identity:
                raise RuntimeError(f"{name} did not start; inspect {log}")
            services[name] = {**identity, "log": str(log), "cwd": str(cwd)}
        record = {"scope": "heobrain-content-office", "app_dir": str(app), "services": services, "ports": {"api": 8510, "frontend": 3110}}
        if os.environ.get('OFFICE_ENV_FILE'):
            record['env_file'] = str(Path(os.environ['OFFICE_ENV_FILE']).expanduser().resolve())
        registry.write_text(canonical(record))
        registry.chmod(0o600)
    except BaseException:
        for process in children:
            if process.poll() is None:
                os.killpg(process.pid, signal.SIGTERM)
        raise
print("Local office started: http://127.0.0.1:3110 (API http://127.0.0.1:8510)")
print(f"PID registry and logs: {runtime}")
if not active:
    print("The authorized window has ended; API and frontend are available for reading. Worker and monitoring were not started.")
PY
