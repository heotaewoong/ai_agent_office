"""Starting the worker/watcher after an operator opens a work window from the UI. No real child processes here."""
import json
import os

import pytest

from office.store import Store, canonical


class FakeProcess:
    def __init__(self):
        self.pid = os.getpid()

    def poll(self):
        return None


def registry(store, app_dir, services=None):
    runtime = store.root / 'runtime'
    runtime.mkdir(parents=True, exist_ok=True)
    path = runtime / 'services.json'
    path.write_text(canonical({'scope': 'heobrain-content-office', 'app_dir': str(app_dir), 'services': services or {}, 'ports': {'api': 8510, 'frontend': 3110}}))
    return path


def test_windows_and_missing_registry_never_spawn(tmp_path):
    from office.services import start_window_services
    store = Store(tmp_path / 'state')
    spawned = []
    result = start_window_services(store, app_dir=tmp_path, platform='nt', spawn=lambda *a, **k: spawned.append(a))
    assert result['started'] == [] and 'start-windows.ps1' in result['note']
    result = start_window_services(store, app_dir=tmp_path, platform='posix', spawn=lambda *a, **k: spawned.append(a))
    assert result['started'] == [] and 'start-local.sh' in result['note']
    assert spawned == []


def test_foreign_registry_is_not_touched(tmp_path):
    from office.services import start_window_services
    store = Store(tmp_path / 'state')
    path = registry(store, tmp_path / 'other-app')
    before = path.read_text()
    spawned = []
    result = start_window_services(store, app_dir=tmp_path, platform='posix', spawn=lambda *a, **k: spawned.append(a))
    assert result['started'] == [] and spawned == [] and path.read_text() == before


def test_starts_worker_and_watcher_once_and_records_them(tmp_path):
    from office.services import start_window_services
    store = Store(tmp_path / 'state')
    path = registry(store, tmp_path, {'api': {'pid': 1, 'start_ticks': 'x'}})
    calls = []

    def spawn(command, **kwargs):
        calls.append({'command': [str(c) for c in command], 'cwd': str(kwargs['cwd']), 'new_session': kwargs.get('start_new_session')})
        return FakeProcess()
    result = start_window_services(store, app_dir=tmp_path, platform='posix', spawn=spawn)
    assert result['started'] == ['worker', 'watcher']
    assert any(c['command'][-2:] == ['-m', 'office.worker'] and c['cwd'].endswith('backend') for c in calls)
    assert any(c['command'][-1].endswith('watch_window.py') for c in calls)
    assert all(c['new_session'] is True for c in calls)
    saved = json.loads(path.read_text())
    assert {'api', 'worker', 'watcher'} <= set(saved['services'])
    assert saved['services']['worker']['pid'] == os.getpid() and saved['services']['worker']['log'].endswith('worker.log')
    again = start_window_services(store, app_dir=tmp_path, platform='posix', spawn=spawn)
    assert again['started'] == [] and set(again['running']) == {'worker', 'watcher'} and len(calls) == 2


def test_stop_windowless_services_terminates_managed_worker_only_without_active_window(tmp_path):
    import subprocess, sys, time
    from datetime import datetime, timedelta, timezone
    from office.runtime import process_identity
    from office.services import stop_windowless_services
    store = Store(tmp_path / 'state')
    child = subprocess.Popen([sys.executable, '-c', 'import time; time.sleep(60)'])
    try:
        time.sleep(.3)
        identity = process_identity(child.pid)
        assert identity
        path = registry(store, tmp_path, {'api': {'pid': 1, 'start_ticks': 'x'}, 'worker': {**identity, 'log': 'worker.log'}})
        # An active window means the worker belongs to that window: never touch it.
        store.set_setting('work_window', {'status': 'active', 'authorized_end': (datetime.now(timezone.utc) + timedelta(minutes=5)).isoformat()})
        assert stop_windowless_services(store, app_dir=tmp_path) == []
        assert child.poll() is None
        store.set_setting('work_window', None)
        assert stop_windowless_services(store, app_dir=tmp_path) == ['worker']
        for _ in range(50):
            if child.poll() is not None:
                break
            time.sleep(.1)
        assert child.poll() is not None
        saved = json.loads(path.read_text())
        assert 'worker' not in saved['services'] and saved['services']['api'] == {'pid': 1, 'start_ticks': 'x'}
        assert any(e['kind'] == 'window_services_stopped' and e['data']['stopped'] == ['worker'] for e in store.events(limit=5))
        assert stop_windowless_services(store, app_dir=tmp_path) == []
    finally:
        if child.poll() is None:
            child.kill()
