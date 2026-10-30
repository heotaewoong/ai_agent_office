"""Explicit local-operator authorization for a later work window; never resets costs."""
from __future__ import annotations

import argparse
import json
from datetime import timedelta

from .bootstrap import default_store
from .runtime import AlreadyRunning, ProcessLock, aware_time, utcnow
from .store import WorkflowError, canonical, identifier


SOURCES = ('local_operator_cli', 'local_operator_ui', 'scheduled_daily_collect')
OPERATOR_SCOPE = 'RSS, drafts, media after source approval; existing total budget retained; publication not included'
# 운영자가 켠 '매일 자동 수집' 일정이 여는 시간. 작업자를 띄우지 않고 수집·한국어 카드 요약만 한다.
SCHEDULED_SCOPE = 'RSS 수집과 한국어 카드 요약만. 원고·제작·승인·발행·작업자 시작 없음; existing total budget retained'


def start_session(store, *, minutes, current=None, source='local_operator_cli', stop_services=None, schedule=None):
    """Issue a new work window. `stop_services(store)` may stop a worker/watcher that was started
    before any window existed (start-local.sh does that); it returns the names it stopped.

    A 'scheduled_daily_collect' window must carry the operator's saved schedule (`schedule`), so the
    record shows which operator setting authorized it."""
    if source == 'scheduled_daily_collect' and not (isinstance(schedule, dict) and schedule.get('enabled') is True and schedule.get('updated_by')):
        raise WorkflowError('자동 수집 시간은 운영자가 켠 일정 설정으로만 열 수 있습니다')
    if type(minutes) is not int or not 1 <= minutes <= 360:
        raise WorkflowError('작업 시간은 1~360분의 정수로 직접 지정하세요')
    current = aware_time(current or utcnow())
    try:
        return _issue_window(store, minutes, current, source, schedule)
    except AlreadyRunning:
        if stop_services and stop_services(store):
            try:
                return _issue_window(store, minutes, current, source, schedule)
            except AlreadyRunning:
                pass
        raise WorkflowError('이전 작업자 또는 감시가 실행 중입니다. 종료를 확인한 뒤 새 세션을 시작하세요') from None


def _issue_window(store, minutes, current, source, schedule=None):
    # An old watcher must finish closing its own window before a new one is issued.
    with ProcessLock(store.root / 'watcher.lock'), ProcessLock(store.root / 'worker.lock'):
        with store.connection(transaction=True) as db:
            row = db.execute("SELECT value FROM settings WHERE key='work_window'").fetchone()
            previous = json.loads(row[0]) if row else None
            if previous and previous.get('authorized_end') and aware_time(previous['authorized_end']) > current:
                raise WorkflowError('기존 작업 시간이 진행 중입니다. 현재 시간의 종료를 확인한 뒤 새 세션을 시작하세요')
            row = db.execute("SELECT value FROM settings WHERE key='work_window_history'").fetchone()
            history = json.loads(row[0]) if row else []
            if previous:
                history.append(previous)
            window = {'id': identifier('window'), 'authorized_start': current.isoformat(),
                      'authorized_end': (current + timedelta(minutes=minutes)).isoformat(),
                      'status': 'active', 'user_confirmed': True, 'authorization_source': source if source in SOURCES else 'local_operator_cli',
                      'scope': OPERATOR_SCOPE}
            if window['authorization_source'] == 'scheduled_daily_collect':
                window.update(scope=SCHEDULED_SCOPE, confirmed_via='operator_schedule', operator_schedule=schedule)
            db.execute("INSERT OR REPLACE INTO settings VALUES('work_window_history',?)", (canonical(history[-100:]),))
            db.execute("INSERT OR REPLACE INTO settings VALUES('work_window',?)", (canonical(window),))
            store._event(db, 'manual_work_window_started', window)
            return window

def main():
    parser = argparse.ArgumentParser(description=__doc__)
    commands = parser.add_subparsers(dest='command', required=True)
    commands.add_parser('status', help='현재 작업 시간과 누적 비용을 읽습니다')
    start = commands.add_parser('start', help='종료된 세션 이후 운영자가 새 시간을 명시합니다. 비용은 초기화하지 않습니다')
    start.add_argument('--minutes', required=True, type=int)
    args = parser.parse_args()
    store = default_store()
    try:
        if args.command == 'start':
            window = start_session(store, minutes=args.minutes)
            print(canonical({'work_window': window, 'budget': store.budget(), 'next_action': '새 worker와 watcher를 시작하세요. 기존 열린 예약과 총한도는 유지됩니다'}))
        else:
            print(canonical({'work_window': store.setting('work_window'), 'budget': store.budget()}))
    except WorkflowError as error:
        parser.exit(1, str(error) + '\n')


if __name__ == '__main__':
    main()
