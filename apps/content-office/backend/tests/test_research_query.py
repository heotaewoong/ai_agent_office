"""외부 조사 검색어: 한글 주제를 영어 검색어로 바꾸는 소액 유료 호출. 한도, 저장한 결과 재사용, 실패 때의 동작을 지킨다."""
import json
import sqlite3
from contextlib import closing

import pytest
import requests

from office import research_query
from office.research_query import english_queries, month_spent_krw
from office.source_library import library_path
from office.store import Store

TITLE = "간격 복습이 기억에 미치는 효과"


class Reply:
    def __init__(self, queries=("spaced repetition memory retention", "distributed practice learning", "spacing effect"), status=200, usage=True):
        self.status_code = status
        self._data = {"id": "resp_1", "choices": [{"finish_reason": "stop", "message": {"content": json.dumps({"queries": list(queries)})}}]}
        if usage:
            self._data["usage"] = {"prompt_tokens": 150, "completion_tokens": 60}

    def json(self):
        return self._data


def sender(reply):
    calls = []

    def post(url, *, headers, json, timeout):
        calls.append({"url": url, "headers": headers, "json": json, "timeout": timeout})
        if isinstance(reply, Exception):
            raise reply
        return reply
    post.calls = calls
    return post


@pytest.fixture
def store(tmp_path, monkeypatch):
    monkeypatch.setenv("OPENAI_API_KEY", "test-key")
    for name in ("OFFICE_RESEARCH_QUERY_CAP_KRW", "OFFICE_RESEARCH_QUERY_MODEL", "GEMINI_API_KEY"):
        monkeypatch.delenv(name, raising=False)
    made = Store(tmp_path)
    made.set_setting("price_valid_until", "2099-01-01T00:00:00+00:00")
    return made


def rows(store):
    with closing(sqlite3.connect(library_path(store.root))) as db:
        return db.execute("SELECT title, queries, model, krw, state FROM research_query_calls ORDER BY id").fetchall()


def test_korean_topic_is_translated_once_recorded_and_then_reused(store):
    post = sender(Reply())
    made = english_queries(store, TITLE, transport=post)
    assert made == {"queries": ["spaced repetition memory retention", "distributed practice learning", "spacing effect"], "source": "model", "note": None}
    [call] = post.calls
    assert call["url"] == "https://api.openai.com/v1/chat/completions" and call["json"]["model"] == "gpt-5.4-nano"
    assert call["json"]["messages"][-1] == {"role": "user", "content": TITLE} and call["json"]["max_completion_tokens"] == 400
    assert call["headers"]["Authorization"] == "Bearer test-key" and call["timeout"] == (3, 6)
    [(title, queries, model, krw, state)] = rows(store)
    assert (title, model, state) == (TITLE, "gpt-5.4-nano", "settled") and json.loads(queries)[0] == "spaced repetition memory retention"
    assert krw == pytest.approx((150 * 0.20 + 60 * 1.25) / 1_000_000 * 2000) and krw < 1
    event = store.events(limit=1)[0]
    assert event["kind"] == "research_query_translated" and event["data"]["paid_calls"] == 1 and event["data"]["estimated_krw"] < 1
    assert TITLE not in json.dumps(event["data"], ensure_ascii=False)
    again = english_queries(store, f"  {TITLE} ", transport=sender(AssertionError("저장한 결과를 다시 써야 한다")))
    assert again["source"] == "saved" and again["queries"] == made["queries"] and len(rows(store)) == 1
    assert store.budget()["spent_krw"] == 0  # 전체 제작 예산 장부는 건드리지 않는다.


def test_english_topics_and_switched_off_setups_never_call_the_model(store, monkeypatch):
    never = sender(AssertionError("부르면 안 된다"))
    assert english_queries(store, "Hermes vs OpenClaw", transport=never) == {"queries": [], "source": None, "note": None}
    monkeypatch.setenv("OFFICE_RESEARCH_QUERY_CAP_KRW", "0")
    assert "꺼져 있어서" in english_queries(store, TITLE, transport=never)["note"]
    monkeypatch.delenv("OFFICE_RESEARCH_QUERY_CAP_KRW")
    monkeypatch.delenv("OPENAI_API_KEY")
    assert "꺼져 있어서" in english_queries(store, TITLE, transport=never)["note"]
    monkeypatch.setenv("OPENAI_API_KEY", "test-key")
    store.set_setting("price_valid_until", "2020-01-01T00:00:00+00:00")
    assert "단가를 다시 확인" in english_queries(store, TITLE, transport=never)["note"]
    assert never.calls == [] and rows(store) == []


def test_monthly_cap_stops_new_calls(store, monkeypatch):
    assert english_queries(store, TITLE, transport=sender(Reply()))["source"] == "model"
    spent = month_spent_krw(store.root)
    assert 0 < spent < 1
    with closing(sqlite3.connect(library_path(store.root))) as db, db:
        db.execute("UPDATE research_query_calls SET krw=299")
    spent = month_spent_krw(store.root)
    blocked = english_queries(store, "미루는 습관을 고치는 방법", transport=sender(AssertionError("한도를 넘으면 부르지 않는다")))
    assert blocked["queries"] == [] and "한도(300원)를 다 써서" in blocked["note"] and month_spent_krw(store.root) == spent


def test_failures_fall_back_and_unknown_outcomes_count_against_the_cap(store):
    lost = english_queries(store, TITLE, transport=sender(requests.ConnectionError("down")))
    assert lost["queries"] == [] and "낱말표로 찾았어요" in lost["note"]
    refused = english_queries(store, TITLE, transport=sender(Reply(status=429)))
    broken = english_queries(store, TITLE, transport=sender(Reply(status=502)))
    unmetered = english_queries(store, TITLE, transport=sender(Reply(usage=False)))
    assert refused["queries"] == broken["queries"] == unmetered["queries"] == []
    assert [(state, krw > 0) for _, _, _, krw, state in rows(store)] == [("unknown", True), ("rejected", False), ("unknown", True), ("unknown", True)]
    assert all(queries is None for _, queries, _, _, _ in rows(store))


def test_model_output_is_reduced_to_plain_search_words(store):
    made = english_queries(store, TITLE, transport=sender(Reply(queries=['"spaced repetition" AND (memory)', "간격 복습", "Spacing effect  learning", "a"])))
    assert made["queries"] == ["spaced repetition AND memory", "Spacing effect learning"]
    empty = english_queries(store, "수면이 학습에 주는 영향", transport=sender(Reply(queries=["한글만"])))
    assert empty["queries"] == [] and "낱말표로 찾았어요" in empty["note"] and rows(store)[-1][4] == "settled"


def test_cap_setting_ignores_bad_values(monkeypatch):
    monkeypatch.setenv("OFFICE_RESEARCH_QUERY_CAP_KRW", "많이")
    assert research_query.monthly_cap_krw() == 300
    monkeypatch.setenv("OFFICE_RESEARCH_QUERY_CAP_KRW", "-5")
    assert research_query.monthly_cap_krw() == 0


class GeminiReply:
    def __init__(self, status=200):
        self.status_code = status

    def json(self):
        return {"responseId": "g_1", "usageMetadata": {"promptTokenCount": 76, "candidatesTokenCount": 35},
                "candidates": [{"content": {"parts": [{"text": json.dumps({"queries": ["desk height posture", "ergonomic desk posture"]})}]}}]}


def by_host(gemini, openai):
    calls = []

    def post(url, *, headers, json, timeout):
        calls.append("gemini" if "generativelanguage.googleapis.com" in url else "openai")
        return gemini if calls[-1] == "gemini" else openai
    post.calls = calls
    return post


def test_cheapest_model_with_a_key_goes_first(store, monkeypatch):
    monkeypatch.setenv("GEMINI_API_KEY", "g-key")
    post = by_host(GeminiReply(), Reply())
    made = english_queries(store, "책상 높이가 자세에 주는 영향", transport=post)
    assert made["queries"] == ["desk height posture", "ergonomic desk posture"] and post.calls == ["gemini"]
    [(_, _, model, krw, state)] = rows(store)
    assert (model, state) == ("gemini-3.5-flash-lite", "settled") and krw == pytest.approx((76 * 0.30 + 35 * 2.50) / 1_000_000 * 2000)
    monkeypatch.setenv("OFFICE_RESEARCH_QUERY_MODEL", "gpt-5.4-nano")
    chosen = by_host(GeminiReply(), Reply())
    assert english_queries(store, "수면이 학습에 주는 영향", transport=chosen)["source"] == "model" and chosen.calls == ["openai"]


def test_an_expired_key_stops_without_trying_another_provider(store, monkeypatch):
    monkeypatch.setenv("GEMINI_API_KEY", "g-key")
    post = by_host(GeminiReply(status=401), Reply())
    refused = english_queries(store, TITLE, transport=post)
    assert refused["queries"] == [] and refused["source"] is None and post.calls == ["gemini"]
    assert "gemini-3.5-flash-lite" in refused["note"] and "다른 모델로 넘어가지 않고" in refused["note"]
    assert [(model, state, krw) for _, _, model, krw, state in rows(store)] == [("gemini-3.5-flash-lite", "rejected", 0)]
    monkeypatch.setenv("OFFICE_RESEARCH_QUERY_MODEL", "gpt-5.4-nano")  # 다른 모델은 운영자가 직접 고를 때만 쓴다
    chosen = by_host(GeminiReply(status=401), Reply())
    assert english_queries(store, "미루는 습관을 고치는 방법", transport=chosen)["source"] == "model" and chosen.calls == ["openai"]

