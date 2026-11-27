"""트렌드 신호: 자동완성 세 곳과 위키백과 조회수를 0원으로 모으고, 막힌 곳은 비워 두며, 새로 나온 자동완성만 표시한다."""
import json
from datetime import date
from urllib.parse import parse_qs, urlsplit

import pytest
import requests

from office import trend_signals
from office.store import Store, WorkflowError


def http_error(code):
    response = requests.Response()
    response.status_code = code
    return requests.HTTPError(response=response)


class FakeWeb:
    def __init__(self, google=("정보처리기사 실기", "정보처리기사 필기"), blocked=()):
        self.google, self.blocked, self.calls = list(google), set(blocked), []

    def __call__(self, url, *, maximum, allowed_hosts):
        parts = urlsplit(url)
        assert parts.hostname in allowed_hosts and parts.scheme == "https"
        self.calls.append(url)
        query = parse_qs(parts.query)
        if parts.hostname == "suggestqueries.google.com":
            source = "youtube" if query.get("ds") == ["yt"] else "google"
            if source in self.blocked:
                raise http_error(429)
            items = self.google if source == "google" else ["정보처리기사 강의"]
            return json.dumps([query["q"][0], items]).encode(), url, "text/javascript; charset=UTF-8"
        if parts.hostname == "ac.search.naver.com":
            return json.dumps({"items": [[["정보처리기사 일정"], ["정보처리기사"]]]}).encode(), url, "application/json"
        if parts.hostname == "ko.wikipedia.org":
            return json.dumps(["정보처리기사", ["정보처리기사"], [""], ["https://ko.wikipedia.org/wiki/정보처리기사"]]).encode(), url, "application/json"
        views = [{"views": 5}] * 7 + [{"views": 20}] * 7
        return json.dumps({"items": views}).encode(), url, "application/json"


def configured(tmp_path, **values):
    store = Store(tmp_path)
    trend_signals.update_trend_settings(store, {"enabled": True, "seeds": ["정보처리기사"], **values}, actor="owner")
    return store


def test_collects_three_autocompletes_and_wikipedia_views_without_model_calls(tmp_path):
    store, web, pauses = configured(tmp_path), FakeWeb(), []
    result = trend_signals.collect_trends(store, fetch=web, pause=pauses.append, today=date(2026, 11, 27))
    assert result == {"rows": 4, "ok": 4, "empty": 0, "blocked": 0, "missing": 0, "error": 0, "paid_calls": 0}
    rows = {row["source"]: row for row in store.setting(trend_signals.REPORT)["rows"]}
    assert [i["text"] for i in rows["google"]["items"]] == ["정보처리기사 실기", "정보처리기사 필기"]
    assert [i["text"] for i in rows["naver"]["items"]] == ["정보처리기사 일정"]  # 씨앗과 같은 말은 뺀다
    assert rows["youtube"]["items"] == [{"text": "정보처리기사 강의"}]  # 처음 모은 날은 '새로' 표시가 없다
    views = rows["wikipedia"]["views"]
    assert (views["prev7"], views["last7"], views["change_pct"]) == (35, 140, None)  # 그 전 7일이 50회 미만이면 비율 없음
    assert "50회 미만" in rows["wikipedia"]["note"] and len(pauses) == 3


def test_blocked_source_stays_empty_and_new_suggestions_are_marked(tmp_path):
    store = configured(tmp_path, sources=["google", "youtube"])
    trend_signals.collect_trends(store, fetch=FakeWeb(), pause=lambda _: None, today=date(2026, 11, 27))
    later = FakeWeb(google=("정보처리기사 실기", "정보처리기사 2026 일정"), blocked={"youtube"})
    result = trend_signals.collect_trends(store, fetch=later, pause=lambda _: None, today=date(2026, 11, 28))
    rows = {row["source"]: row for row in store.setting(trend_signals.REPORT)["rows"]}
    assert result["blocked"] == 1 and rows["youtube"]["status"] == "blocked" and rows["youtube"]["items"] == []
    assert "있는 척하지 않고" in rows["youtube"]["note"]
    assert rows["google"]["items"] == [{"text": "정보처리기사 실기", "new": False}, {"text": "정보처리기사 2026 일정", "new": True}]


def test_wikipedia_change_rate_only_with_enough_views_and_missing_article(tmp_path):
    class Busy(FakeWeb):
        def __call__(self, url, **kw):
            if "wikimedia.org" in url:
                return json.dumps({"items": [{"views": 100}] * 7 + [{"views": 150}] * 7}).encode(), url, "application/json"
            return super().__call__(url, **kw)
    store = configured(tmp_path, sources=["wikipedia"])
    trend_signals.collect_trends(store, fetch=Busy(), pause=lambda _: None, today=date(2026, 11, 27))
    assert store.setting(trend_signals.REPORT)["rows"][0]["views"]["change_pct"] == 50

    class Missing(FakeWeb):
        def __call__(self, url, **kw):
            return json.dumps(["없는말", [], [], []]).encode(), url, "application/json"
    trend_signals.collect_trends(store, fetch=Missing(), pause=lambda _: None, today=date(2026, 11, 27))
    assert store.setting(trend_signals.REPORT)["rows"][0]["status"] == "missing"


@pytest.mark.parametrize("patch", [{"seeds": []}, {"seeds": ["https://a.example"]}, {"seeds": ["x"] * 9}, {"sources": ["x"]}, {"enabled": "yes"}])
def test_settings_reject_bad_values(tmp_path, patch):
    with pytest.raises(WorkflowError):
        trend_signals.update_trend_settings(Store(tmp_path), patch, actor="owner")


def test_worker_runs_the_queued_collection(tmp_path, monkeypatch):
    from office import worker
    store = configured(tmp_path)
    monkeypatch.setattr(trend_signals, "collect_trends", lambda s: {"rows": 1})
    task = trend_signals.queue_trends(store)
    assert task["kind"] == "trend_signals"
    assert worker.process_task(store, task) == {"rows": 1}


def test_api_reads_saves_and_queues(tmp_path):
    from fastapi.testclient import TestClient
    from office.api import create_app
    client = TestClient(create_app(Store(tmp_path)), base_url="http://localhost:8510")
    headers = {"Origin": "http://localhost:3110", "X-Office-CSRF": client.get("/api/session").json()["csrf"]}
    assert client.get("/api/trend-signals").json()["settings"]["enabled"] is False
    saved = client.put("/api/trend-signals", json={"enabled": True, "seeds": ["편입"], "sources": ["naver"]}, headers=headers)
    assert saved.status_code == 200 and saved.json()["settings"]["seeds"] == ["편입"]
    assert client.put("/api/trend-signals", json={"enabled": True, "seeds": [], "sources": ["naver"]}, headers=headers).status_code == 422
    assert client.put("/api/trend-signals", json={"enabled": True, "seeds": ["편입"], "sources": ["naver"]}).status_code == 403
    assert client.post("/api/trend-signals/refresh", headers=headers).json()["kind"] == "trend_signals"
