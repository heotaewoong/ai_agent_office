"""매일 아침 뉴스 자동 수집 (2026-10-30 오너 결정).

운영자가 '제작 설정'에서 켠 일정(`daily_collect`)에 따라, cron이 15분마다 이 모듈을 부른다. 설정한 시각부터
15분 안의 첫 실행만 일한다: 짧은 작업 시간을 'scheduled_daily_collect'로 열고, RSS 수집과 한국어 카드 요약
(bootstrap.refresh)만 한 뒤, 연 시간을 스스로 닫는다.

하지 않는 것: 작업자(worker) 시작, 원고·제작·업로드, 기획 선택⓪·승인①②③, 운영자가 연 작업 시간의 연장·재사용.
비용은 이번 실행의 사용분(정산+예약)이 운영자가 정한 상한(max_krw)을 넘기 전에 요약을 멈춘다.
"""
from __future__ import annotations

import os
import re
import signal
import threading
from datetime import datetime, timedelta
from pathlib import Path

from .runtime import SEOUL, AlreadyRunning, ProcessLock, WindowDeadline, aware_time, close_work_window, run_before_deadline, utcnow
from .store import WorkflowError, now

SETTING = "daily_collect"
RUNS = "daily_collect_runs"
SOURCE = "scheduled_daily_collect"
DEFAULTS = {"enabled": False, "time_kst": "07:00", "minutes": 15, "max_krw": 100}
SLOT_MINUTES = 15  # cron 주기와 같다. 이 구간 안의 실행만 일한다.
MINUTES_RANGE = (5, 30)
MAX_KRW_RANGE = (10, 1000)
TIME_PATTERN = re.compile(r"^([01]\d|2[0-3]):[0-5]\d$")


def daily_collect_settings(store):
    saved = store.setting(SETTING) or {}
    return {**DEFAULTS, **saved}


def _validate(values):
    if type(values["enabled"]) is not bool:
        raise WorkflowError("자동 수집 사용 여부는 켜기/끄기로만 지정하세요")
    if not isinstance(values["time_kst"], str) or not TIME_PATTERN.match(values["time_kst"]):
        raise WorkflowError("수집 시각은 한국 시간 HH:MM(00:00~23:59)으로 입력하세요")
    low, high = MINUTES_RANGE
    if type(values["minutes"]) is not int or not low <= values["minutes"] <= high:
        raise WorkflowError(f"자동 수집 작업 시간은 {low}~{high}분의 정수로 입력하세요")
    low, high = MAX_KRW_RANGE
    if type(values["max_krw"]) is not int or not low <= values["max_krw"] <= high:
        raise WorkflowError(f"1회 비용 상한은 {low}~{high}원의 정수로 입력하세요")


def update_daily_collect_settings(store, patch, *, actor):
    unknown = set(patch) - set(DEFAULTS)
    if unknown:
        raise WorkflowError("알 수 없는 자동 수집 설정입니다: " + ", ".join(sorted(unknown)))
    values = {**daily_collect_settings(store), **patch}
    _validate(values)
    saved = {**{key: values[key] for key in DEFAULTS}, "updated_by": actor, "updated_at": now()}
    store.set_setting(SETTING, saved)
    store.event("daily_collect_updated", saved)
    return saved


def daily_collect_status(store):
    runs = store.setting(RUNS) or []
    return {"settings": daily_collect_settings(store), "last_run": runs[-1] if runs else None, "runs": runs[-7:],
            "slot_minutes": SLOT_MINUTES, "source": SOURCE,
            "limits": {"minutes": list(MINUTES_RANGE), "max_krw": list(MAX_KRW_RANGE)}}


def load_env_file(path):
    """`KEY=value`·`export KEY=value`·한 쌍의 따옴표·`#` 주석만 읽는다. 이미 있는 환경값은 덮지 않는다.
    값은 출력하지 않고 읽은 이름만 돌려준다."""
    names = []
    for raw in Path(path).expanduser().read_text(encoding="utf-8").splitlines():
        line = raw.strip()
        if not line or line.startswith("#"):
            continue
        if line.startswith("export "):
            line = line[len("export "):].lstrip()
        key, sep, value = line.partition("=")
        key = key.strip()
        if not sep or not re.match(r"^[A-Za-z_][A-Za-z0-9_]*$", key):
            continue
        value = value.strip()
        if len(value) >= 2 and value[0] == value[-1] and value[0] in "'\"":
            value = value[1:-1]
        names.append(key)
        os.environ.setdefault(key, value)
    return names


def _slot_day(settings, local):
    """현재 한국 시각이 [설정 시각, +15분) 안이면 그 구간이 시작된 날짜(YYYY-MM-DD)를 돌려준다."""
    hour, minute = map(int, settings["time_kst"].split(":"))
    for days in (0, 1):  # 23:55 같은 시각은 다음 날 0시대까지 이어진다
        start = (local - timedelta(days=days)).replace(hour=hour, minute=minute, second=0, microsecond=0)
        if start <= local < start + timedelta(minutes=SLOT_MINUTES):
            return start.date().isoformat()
    return None


def _window_blocks(window, current):
    """운영자(또는 다른 주체)의 작업 시간이 열려 있거나 종료가 확인되지 않았으면 True."""
    if not window or window.get("status") in ("closed", "stopped"):
        return False
    if not window.get("authorized_end"):
        return True
    return aware_time(window["authorized_end"]) > current


class _CostCap:
    """요약 모델 앞에 두는 이번 실행 전용 상한. 다음 호출이 지금까지 가장 비싼 한 번만큼 든다고 보고 미리 멈춘다."""

    def __init__(self, inner, store, cap_krw):
        self.inner, self.store, self.cap = inner, store, cap_krw
        self.baseline = self._total()
        self.largest = 0
        self.hit = False

    def _total(self):
        budget = self.store.budget()
        return budget["spent_krw"] + budget["reserved_krw"]

    def used(self):
        return max(0, self._total() - self.baseline)

    def generate(self, role, messages, schema, options=None):
        before = self.used()
        if before >= self.cap or before + self.largest > self.cap:
            self.hit = True
            raise WorkflowError(f"매일 자동 수집의 1회 비용 상한({self.cap}원)에 닿아 남은 카드 요약을 멈춥니다")
        try:
            return self.inner.generate(role, messages, schema, options)
        finally:
            self.largest = max(self.largest, self.used() - before)


def _run_until(target, end_at):
    """POSIX(EC2)의 cron 실행은 주 스레드라 SIGALRM으로 마감에 끊는다. 그 밖에서는 제공자의 작업 시간 검사에 맡긴다."""
    if hasattr(signal, "SIGALRM") and threading.current_thread() is threading.main_thread():
        return run_before_deadline(target, (), end_at, subprocess_mode=False)
    return target()


def _record_run(store, run):
    runs = [r for r in (store.setting(RUNS) or []) if r.get("run_id") != run["run_id"]]
    runs.append(run)
    store.set_setting(RUNS, runs[-30:])


def _skip(store, run, reason, **values):
    run.update(status="skipped", reason=reason, finished_at=datetime.now(SEOUL).isoformat(), **values)
    _record_run(store, run)
    store.event("daily_collect_skipped", {"reason": reason, "date": run["date"], **values})
    return {"status": "skipped", "reason": reason, "date": run["date"], **values}


def run_daily_collect(store, now=None, *, refresh=None, provider_factory=None, deadline_runner=None):
    """cron이 부르는 한 번의 확인. 조건이 맞을 때만 수집하고 결과 dict를 돌려준다."""
    current = aware_time(now or utcnow())
    local = current.astimezone(SEOUL)
    settings = daily_collect_settings(store)
    if not settings["enabled"]:
        return {"status": "skipped", "reason": "disabled"}
    day = _slot_day(settings, local)
    if day is None:
        return {"status": "skipped", "reason": "outside_time"}
    try:
        lock = ProcessLock(store.root / "runtime" / "daily-collect.lock")
        lock.__enter__()
    except AlreadyRunning:
        return {"status": "skipped", "reason": "already_running", "date": day}
    try:
        if any(r.get("date") == day for r in store.setting(RUNS) or []):
            return {"status": "skipped", "reason": "already_ran_today", "date": day}
        run = {"run_id": f"{day}@{local.isoformat()}", "date": day, "status": "running", "started_at": local.isoformat(),
               "max_krw": settings["max_krw"], "minutes": settings["minutes"]}
        _record_run(store, run)  # 실행 도중 멈춰도 같은 날 다시 열지 않는다
        if _window_blocks(store.setting("work_window"), current):
            return _skip(store, run, "operator_window_open")
        from .session import start_session
        try:
            window = start_session(store, minutes=settings["minutes"], current=current, source=SOURCE, schedule=settings)
        except WorkflowError as error:
            return _skip(store, run, "window_unavailable", detail=str(error))
        return _collect(store, run, window, settings, refresh, provider_factory, deadline_runner or _run_until)
    finally:
        lock.__exit__()


def _collect(store, run, window, settings, refresh, provider_factory, deadline_runner):
    run["window_id"] = window["id"]
    locks = [ProcessLock(store.root / "watcher.lock"), ProcessLock(store.root / "worker.lock")]
    held = []
    try:
        # 이 시간 동안 작업자·감시가 새로 뜨지 않게 두 잠금을 쥔다(작업자는 시작하지 않는다).
        for lock in locks:
            lock.__enter__()
            held.append(lock)
    except AlreadyRunning:
        for lock in reversed(held):
            lock.__exit__()
        close_work_window(store, datetime.now(SEOUL).isoformat(), window_id=window["id"], closed_by=SOURCE)
        return _skip(store, run, "services_running", window_id=window["id"])
    if refresh is None:
        from .bootstrap import refresh
    if provider_factory is None:
        from .bootstrap import card_provider as provider_factory
    before_ids = {article["id"] for article in store.articles_list()}
    capped = None
    report, status, error_type = None, "completed", None
    try:
        capped = _CostCap(provider_factory(store), store, settings["max_krw"])
        end_at = aware_time(window["authorized_end"]) - timedelta(seconds=5)
        report = deadline_runner(lambda: refresh(store, provider=capped), end_at)
    except WindowDeadline:
        status = "timeout"
    except Exception as error:
        status, error_type = "failed", type(error).__name__
    except BaseException:
        status = "interrupted"
        raise
    finally:
        close_work_window(store, datetime.now(SEOUL).isoformat(), window_id=window["id"], closed_by=SOURCE)
        for lock in reversed(held):
            lock.__exit__()
        spent = capped.used() if capped else 0
        if status == "completed" and capped and capped.hit:
            status = "stopped_cost_cap"
        active = (report or {}).get("active_article_ids") or []
        summary = {"status": status, "date": run["date"], "window_id": window["id"], "articles": len(active),
                   "new_articles": len(set(active) - before_ids), "spent_krw": spent, "max_krw": settings["max_krw"],
                   "over_cap": spent > settings["max_krw"]}
        if error_type:
            summary["error_type"] = error_type
        run.update(summary, finished_at=datetime.now(SEOUL).isoformat())
        _record_run(store, run)
        store.event("daily_collect_finished", summary)
    return summary
