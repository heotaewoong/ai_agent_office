from datetime import datetime, timedelta, timezone

import pytest

from office.store import Store, WorkflowError

AT = datetime(2026, 10, 26, 0, 0, tzinfo=timezone.utc)


def test_new_manual_session_preserves_old_window_and_all_open_costs(tmp_path):
    from office.session import start_session
    store = Store(tmp_path)
    old = {'authorized_start': (AT - timedelta(hours=7)).isoformat(), 'authorized_end': (AT - timedelta(hours=1)).isoformat(), 'status': 'closed'}
    store.set_setting('work_window', old)
    cost = store.reserve_cost('model', 300, {'cache_key': 'unknown-prior'})
    store.unknown_cost(cost['id'], 'prior-lost-response')
    before = store.budget()
    new = start_session(store, minutes=60, current=AT)
    assert datetime.fromisoformat(new['authorized_end']) == AT + timedelta(minutes=60)
    assert new['authorization_source'] == 'local_operator_cli'
    assert store.setting('work_window_history')[-1] == old
    assert store.budget() == before


def test_existing_active_window_cannot_be_silently_extended(tmp_path):
    from office.session import start_session
    store = Store(tmp_path)
    old = {'authorized_end': (AT + timedelta(minutes=1)).isoformat(), 'status': 'active'}
    store.set_setting('work_window', old)
    with pytest.raises(WorkflowError, match='진행|종료'):
        start_session(store, minutes=60, current=AT)
    assert store.setting('work_window') == old


@pytest.mark.parametrize('minutes', [0, 361, True, 1.5])
def test_manual_session_requires_bounded_explicit_minutes(tmp_path, minutes):
    from office.session import start_session
    with pytest.raises(WorkflowError, match='시간|분'):
        start_session(Store(tmp_path), minutes=minutes, current=AT)


def test_still_running_watcher_prevents_new_session_from_racing_old_close(tmp_path):
    from office.session import start_session
    from office.runtime import ProcessLock
    store = Store(tmp_path)
    with ProcessLock(store.root / 'watcher.lock'):
        with pytest.raises(WorkflowError, match='종료|실행'):
            start_session(store, minutes=60, current=AT)
    assert store.setting('work_window') is None


def test_windowless_worker_is_stopped_so_operator_can_open_window(tmp_path):
    """start-local.sh starts a worker when no window exists; opening the first window must replace it, not fail."""
    from office.session import start_session
    from office.runtime import ProcessLock
    store = Store(tmp_path)
    lock = ProcessLock(store.root / 'worker.lock')
    lock.__enter__()
    calls = []

    def stop_services(s):
        calls.append(s)
        lock.__exit__(None, None, None)
        return ['worker']
    window = start_session(store, minutes=30, current=AT, source='local_operator_ui', stop_services=stop_services)
    assert calls == [store] and window['status'] == 'active' and window['authorization_source'] == 'local_operator_ui'
    assert datetime.fromisoformat(window['authorized_end']) == AT + timedelta(minutes=30)


def test_window_open_still_fails_when_nothing_could_be_stopped(tmp_path):
    from office.session import start_session
    from office.runtime import ProcessLock
    store = Store(tmp_path)
    with ProcessLock(store.root / 'worker.lock'):
        with pytest.raises(WorkflowError, match='실행 중'):
            start_session(store, minutes=30, current=AT, stop_services=lambda s: [])
    assert store.setting('work_window') is None
