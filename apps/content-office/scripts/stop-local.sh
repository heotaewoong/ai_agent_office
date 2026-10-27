#!/usr/bin/env bash
set -euo pipefail
script_dir="$(cd -- "$(dirname -- "${BASH_SOURCE[0]}")" && pwd)"
app_dir="$(cd -- "$script_dir/.." && pwd)"
exec "$app_dir/backend/.venv/bin/python" - "$app_dir" "${1:---all}" <<'PY'
import json
import os
import signal
import sys
import time
from pathlib import Path

app = Path(sys.argv[1]).resolve()
mode = sys.argv[2]
if mode not in ("--all", "--worker", "--watcher"):
    raise SystemExit("Usage: stop-local.sh [--all|--worker|--watcher]")
sys.path.insert(0, str(app / "backend"))
from office.bootstrap import default_store
from office.runtime import ProcessLock, process_identity
from office.store import canonical
store = default_store()
runtime = store.root / "runtime"
registry = runtime / "services.json"
with ProcessLock(runtime / "services-management.lock"):
    if not registry.exists():
        raise SystemExit("No managed service PID registry exists. No process was signalled.")
    record = json.loads(registry.read_text())
    if record.get("scope") != "heobrain-content-office" or record.get("app_dir") != str(app):
        raise SystemExit("Service registry belongs to another project. No process was signalled.")
    stopped = []
    targets = list(record["services"]) if mode == "--all" else [mode[2:]]
    for name in targets:
        item = record["services"].get(name)
        if not item:
            continue
        identity = process_identity(item["pid"])
        if not identity or identity["start_ticks"] != item.get("start_ticks") or identity["args"] != item.get("args"):
            continue
        os.killpg(item["pid"], signal.SIGTERM)
        stopped.append(name)
    # Graceful shutdown retains cost reservations and records uncertain in-flight tasks.
    until = time.monotonic() + 5
    while time.monotonic() < until:
        if not any(process_identity(record["services"][name]["pid"]) for name in stopped):
            break
        time.sleep(.1)
    for name in stopped:
        record["services"][name]["termination_requested"] = True
    registry.write_text(canonical(record))
print("Termination requested for: " + (", ".join(stopped) if stopped else "no matching managed processes"))
PY
