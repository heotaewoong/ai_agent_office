"""매일 아침 뉴스 자동 수집: 운영자가 켠 일정에서만 짧은 작업 시간을 열어 수집·요약만 하고 닫는다."""
from datetime import datetime, timedelta, timezone

import pytest
from fastapi.testclient import TestClient

from office.store import Store, WorkflowError

KST = timezone(timedelta(hours=9))
AT_0703 = datetime(2026, 10, 30, 7, 3, tzinfo=KST)


def enabled(store, **values):
    from office.daily_collect import update_daily_collect_settings
    return update_daily_collect_settings(store, {"enabled": True, **values}, actor="local-operator")


def immediate(target, end_at):
    return target()


class FakeRefresh:
    """bootstrap.refresh 대역. 호출 중의 작업 시간을 기록하고 기사 한 건을 새로 저장한다."""

    def __init__(self, calls=0):
        self.windows = []
        self.provider = None
        self.calls = calls

    def __call__(self, store, provider=None):
        self.windows.append(store.setting("work_window"))
        self.provider = provider
        for _ in range(self.calls):
            try:
                provider.generate("card_ko", [], {})
            except WorkflowError:
                break
        store.save_articles([{"id": "new-1", "title": "새 기사", "url": "https://example.com/a"}])
        return {"active_article_ids": ["old-1", "new-1"], "eligible_items": 2, "total_items": 2, "feeds": []}


class PaidProvider:
    """호출마다 40원을 예약·정산하는 가짜 요약 모델."""

    def __init__(self, store, krw=40):
        self.store, self.krw, self.calls = store, krw, 0

    def generate(self, role, messages, schema, options=None):
        cost = self.store.reserve_cost("model", self.krw, {"role": role})
        self.store.settle_cost(cost["id"], self.krw, {})
        self.calls += 1
        return {}


def run(store, at=AT_0703, refresh=None, provider=None, **kw):
    from office.daily_collect import run_daily_collect
    return run_daily_collect(store, now=at, refresh=refresh or FakeRefresh(), provider_factory=lambda s: provider or PaidProvider(s), deadline_runner=immediate, **kw)


def test_defaults_are_off_and_settings_are_validated_and_recorded(tmp_path):
    from office.daily_collect import daily_collect_settings, update_daily_collect_settings
    store = Store(tmp_path)
    assert daily_collect_settings(store) == {"enabled": False, "time_kst": "07:00", "minutes": 15, "max_krw": 100}
    saved = update_daily_collect_settings(store, {"enabled": True, "time_kst": "06:30", "minutes": 20, "max_krw": 200}, actor="local-operator")
    assert saved["enabled"] is True and saved["time_kst"] == "06:30" and saved["updated_by"] == "local-operator" and saved["updated_at"]
    assert [e for e in store.events(limit=5) if e["kind"] == "daily_collect_updated"][0]["data"]["time_kst"] == "06:30"
    for bad in ({"time_kst": "7:00"}, {"time_kst": "24:00"}, {"time_kst": "07:60"}, {"minutes": 4}, {"minutes": 31}, {"minutes": 15.5},
                {"max_krw": 9}, {"max_krw": 1001}, {"enabled": "yes"}, {"minutes": True}, {"budget": 1}):
        with pytest.raises(WorkflowError):
            update_daily_collect_settings(store, bad, actor="local-operator")
    assert daily_collect_settings(store)["time_kst"] == "06:30"


def test_disabled_schedule_skips_without_window_or_refresh(tmp_path):
    store = Store(tmp_path)
    refresh = FakeRefresh()
    assert run(store, refresh=refresh) == {"status": "skipped", "reason": "disabled"}
    assert refresh.windows == [] and store.setting("work_window") is None


@pytest.mark.parametrize("at", [datetime(2026, 10, 30, 6, 59, tzinfo=KST), datetime(2026, 10, 30, 7, 15, tzinfo=KST), datetime(2026, 10, 30, 19, 3, tzinfo=KST)])
def test_outside_the_morning_slot_skips(tmp_path, at):
    store = Store(tmp_path)
    enabled(store)
    refresh = FakeRefresh()
    assert run(store, at=at, refresh=refresh)["reason"] == "outside_time"
    assert refresh.windows == [] and store.setting("work_window") is None


def test_happy_path_opens_scheduled_window_collects_and_closes_it(tmp_path):
    store = Store(tmp_path)
    store.save_articles([{"id": "old-1", "title": "어제 기사", "url": "https://example.com/old"}])
    enabled(store, minutes=10, max_krw=100)
    refresh = FakeRefresh(calls=1)
    result = run(store, refresh=refresh)
    assert result["status"] == "completed" and result["articles"] == 2 and result["new_articles"] == 1 and result["spent_krw"] == 40
    opened = refresh.windows[0]
    assert opened["status"] == "active" and opened["authorization_source"] == "scheduled_daily_collect"
    assert opened["operator_schedule"]["enabled"] is True and opened["operator_schedule"]["updated_by"] == "local-operator"
    assert datetime.fromisoformat(opened["authorized_end"]) - datetime.fromisoformat(opened["authorized_start"]) == timedelta(minutes=10)
    assert "원고" in opened["scope"]
    closed = store.setting("work_window")
    assert closed["id"] == opened["id"] and closed["status"] == "closed" and closed["closed_by"] == "scheduled_daily_collect"
    finished = [e for e in store.events(limit=50) if e["kind"] == "daily_collect_finished"]
    assert finished and finished[0]["data"]["status"] == "completed" and finished[0]["data"]["new_articles"] == 1
    assert store.setting("daily_collect_runs")[-1]["date"] == "2026-10-30"
    # 수집·요약만: 작업·작업자 할 일·기획·승인은 만들지 않는다
    assert store.jobs() == [] and store.tasks() == [] and store.ideas() == []
    assert not any(e["kind"].endswith("approved") or e["kind"].startswith("task_") for e in store.events(limit=200))


def test_second_run_on_the_same_day_skips(tmp_path):
    store = Store(tmp_path)
    enabled(store)
    assert run(store)["status"] == "completed"
    refresh = FakeRefresh()
    assert run(store, at=AT_0703 + timedelta(minutes=5), refresh=refresh)["reason"] == "already_ran_today"
    assert refresh.windows == []


def test_operator_window_is_never_touched(tmp_path):
    store = Store(tmp_path)
    enabled(store)
    window = {"id": "window-operator", "authorized_start": (AT_0703 - timedelta(minutes=30)).isoformat(),
              "authorized_end": (AT_0703 + timedelta(minutes=60)).isoformat(), "status": "active", "authorization_source": "local_operator_ui"}
    store.set_setting("work_window", window)
    refresh = FakeRefresh()
    result = run(store, refresh=refresh)
    assert result["status"] == "skipped" and result["reason"] == "operator_window_open"
    assert refresh.windows == [] and store.setting("work_window") == window
    assert [e for e in store.events(limit=10) if e["kind"] == "daily_collect_skipped"][0]["data"]["reason"] == "operator_window_open"


def test_cost_cap_stops_summaries_and_closes_the_window(tmp_path):
    store = Store(tmp_path)
    enabled(store, max_krw=100)
    provider = PaidProvider(store, krw=40)
    result = run(store, refresh=FakeRefresh(calls=5), provider=provider)
    assert provider.calls == 2  # 40 + 40 뒤 다음 40원은 한도 100원을 넘는다
    assert result["status"] == "stopped_cost_cap" and result["spent_krw"] == 80
    assert store.setting("work_window")["status"] == "closed"
    assert [e for e in store.events(limit=20) if e["kind"] == "daily_collect_finished"][0]["data"]["status"] == "stopped_cost_cap"


def test_failure_and_timeout_still_close_the_window(tmp_path):
    from office.runtime import WindowDeadline
    store = Store(tmp_path)
    enabled(store)

    def timeout(store, provider=None):
        raise WindowDeadline()

    assert run(store, refresh=timeout)["status"] == "timeout"
    assert store.setting("work_window")["status"] == "closed"


def test_concurrent_run_is_refused_by_the_dedicated_lock(tmp_path):
    from office.runtime import ProcessLock
    store = Store(tmp_path)
    enabled(store)
    refresh = FakeRefresh()
    with ProcessLock(store.root / "runtime" / "daily-collect.lock"):
        assert run(store, refresh=refresh)["reason"] == "already_running"
    assert refresh.windows == [] and store.setting("work_window") is None


def test_running_worker_blocks_the_scheduled_window(tmp_path):
    from office.runtime import ProcessLock
    store = Store(tmp_path)
    enabled(store)
    refresh = FakeRefresh()
    with ProcessLock(store.root / "worker.lock"):
        assert run(store, refresh=refresh)["reason"] == "window_unavailable"
    assert refresh.windows == [] and store.setting("work_window") is None


def test_slot_that_crosses_midnight_counts_for_the_day_it_started(tmp_path):
    store = Store(tmp_path)
    enabled(store, time_kst="23:55")
    result = run(store, at=datetime(2026, 10, 31, 0, 5, tzinfo=KST))
    assert result["status"] == "completed"
    assert store.setting("daily_collect_runs")[-1]["date"] == "2026-10-30"


def test_env_file_is_loaded_without_overriding_existing_values(tmp_path, monkeypatch):
    from office.daily_collect import load_env_file
    path = tmp_path / "office.env"
    path.write_text("# 주석\nexport GEMINI_API_KEY='abc'\nOFFICE_CARD_MODEL=gemini-3.5-flash-lite\nEMPTY=\n", encoding="utf-8")
    monkeypatch.delenv("GEMINI_API_KEY", raising=False)
    monkeypatch.setenv("OFFICE_CARD_MODEL", "kept")
    names = load_env_file(path)
    import os
    assert os.environ["GEMINI_API_KEY"] == "abc" and os.environ["OFFICE_CARD_MODEL"] == "kept"
    assert "GEMINI_API_KEY" in names
    monkeypatch.delenv("GEMINI_API_KEY")


def test_settings_route_reads_and_updates_with_csrf(tmp_path):
    from office.api import create_app
    store = Store(tmp_path)
    client = TestClient(create_app(store), base_url="http://localhost:8510")
    token = client.get("/api/session").json()["csrf"]
    headers = {"Origin": "http://localhost:3110", "X-Office-CSRF": token}
    body = client.get("/api/settings/daily-collect").json()
    assert body["settings"]["enabled"] is False and body["last_run"] is None
    assert client.put("/api/settings/daily-collect", json={"enabled": True}, headers={"Origin": "http://localhost:3110"}).status_code == 403
    assert client.put("/api/settings/daily-collect", json={"minutes": 45}, headers=headers).status_code == 409
    response = client.put("/api/settings/daily-collect", json={"enabled": True, "time_kst": "06:45"}, headers=headers)
    assert response.status_code == 200, response.text
    assert response.json()["settings"]["time_kst"] == "06:45" and store.setting("daily_collect")["updated_by"] == "local-operator"
    assert store.setting("work_window") is None  # 설정 저장은 작업 시간을 열지 않는다


def test_scheduled_source_requires_the_operators_enabled_schedule(tmp_path):
    from office.session import start_session
    store = Store(tmp_path)
    for schedule in (None, {"enabled": False, "updated_by": "local-operator"}, {"enabled": True}):
        with pytest.raises(WorkflowError, match="일정"):
            start_session(store, minutes=15, current=AT_0703, source="scheduled_daily_collect", schedule=schedule)
    assert store.setting("work_window") is None
