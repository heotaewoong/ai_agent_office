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
