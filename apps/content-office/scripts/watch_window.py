#!/usr/bin/env python3
"""Read-only scheduled checks; never approves, enqueues, drafts, or calls a model."""
from __future__ import annotations

import argparse
import json
import multiprocessing
import signal
import sys
import time
from datetime import datetime, timezone
from pathlib import Path
from urllib.parse import urlparse
from urllib.request import urlopen

BACKEND = Path(__file__).resolve().parents[1] / "backend"
sys.path.insert(0, str(BACKEND))
from office.bootstrap import default_store
from office.runtime import WindowDeadline, WindowWatcher, aware_time, inspect_state, utcnow
from office.store import canonical


def rss_child(output, state_root, snapshot_root):
    import shutil
    from office.bootstrap import refresh
    from office.store import Store
    try:
        report = refresh(Store(state_root))
        raw_dir = Path(state_root) / "feeds"
        if raw_dir.exists():
            shutil.copytree(raw_dir, Path(snapshot_root) / "feeds", dirs_exist_ok=True)
        output.send({"state": "completed", "candidates_refreshed": True, "job_sources_modified": False, **report})
    except Exception as error:
        output.send({"state": "failed", "error_type": type(error).__name__})
    finally:
        output.close()


def rss_check(store, end_at):
    """Separate bounded process preserves a hard stop even during a slow network read."""
    root = store.root / "runtime" / "rss" / utcnow().strftime("%Y%m%dT%H%M%S%fZ")
    root.mkdir(parents=True, exist_ok=True)
    context = multiprocessing.get_context("spawn")
    receiver, sender = context.Pipe(duplex=False)
    process = context.Process(target=rss_child, args=(sender, str(store.root), str(root)), daemon=True)
    process.start()
    sender.close()
    try:
        remaining = max(0, (end_at - utcnow()).total_seconds() - 2)
        if receiver.poll(min(40, remaining)):
            report = receiver.recv()
        else:
            report = {"state": "timeout", "error": "RSS 검사 제한시간이 지나 조회 프로세스를 종료했습니다", "paid_calls": 0}
    finally:
        if process.is_alive():
            process.terminate()
        process.join(timeout=2)
        if process.is_alive():
            process.kill()
            process.join(timeout=1)
        receiver.close()
    report["snapshot_directory"] = str(root)
    (root / "report.json").write_text(canonical(report), encoding="utf-8")
    return report


def build_inspection(store, api_url, end_at):
    parsed = urlparse(api_url)
    if parsed.scheme != "http" or parsed.hostname not in ("127.0.0.1", "localhost") or parsed.username or parsed.password:
        raise ValueError("API must be a local loopback HTTP URL")
    seen = set()
    def inspect():
        started = time.monotonic()
        try:
            with urlopen(api_url.rstrip("/") + "/api/health", timeout=5) as response:
                health = json.loads(response.read(65536))
            api = {"state": "ok" if health.get("status") == "ok" else "failed", "response": health}
        except Exception as error:
            api = {"state": "failed", "error_type": type(error).__name__}
        state = inspect_state(store, seen)
        rss = rss_check(store, end_at)
        result = {"api": api, "integrity": state, "rss": rss, "elapsed_seconds": round(time.monotonic() - started, 3), "paid_calls": 0, "automatic_drafts": 0, "job_source_mutations": 0}
        store.set_setting("last_runtime_inspection", result)
        return result
    return inspect


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--end-at", help="Timezone-aware ISO deadline; defaults to the saved authorized_end")
    parser.add_argument("--api-url", default="http://127.0.0.1:8510")
    parser.add_argument("--check-once", action="store_true", help="One actual read-only check within the authorized window")
    args = parser.parse_args()
    store = default_store()
    saved = store.setting("work_window", {})
    end_value = args.end_at or saved.get("authorized_end")
    if not end_value:
        parser.error("A saved authorized_end or --end-at is required")
    end_at = aware_time(end_value)
    if saved.get("authorized_end") and end_at > aware_time(saved["authorized_end"]):
        parser.error("--end-at cannot extend the saved authorized work window")
    inspection = build_inspection(store, args.api_url, end_at)
    if args.check_once:
        if (end_at - utcnow()).total_seconds() <= 60:
            print(canonical({"state": "skipped", "reason": "authorized_window_ended_or_last_minute", "paid_calls": 0}))
            return
        print(canonical(inspection()))
        return
    seconds = (end_at - utcnow()).total_seconds()
    def deadline(signum, frame):
        raise WindowDeadline()
    def interrupt(signum, frame):
        raise KeyboardInterrupt()
    signal.signal(signal.SIGALRM, deadline)
    signal.signal(signal.SIGTERM, interrupt)
    signal.signal(signal.SIGINT, interrupt)
    # SIGALRM interrupts hashing, ffprobe, and network waits at the exact authorization boundary.
    if seconds > 0:
        signal.setitimer(signal.ITIMER_REAL, seconds)
    try:
        WindowWatcher(store, end_at, inspection).run()
    except KeyboardInterrupt:
        return
    finally:
        signal.setitimer(signal.ITIMER_REAL, 0)


if __name__ == "__main__":
    main()
