import json
from datetime import date

import pytest
from fastapi.testclient import TestClient

from office.api import create_app
from office.calendar import CONFIG_PATH, calendar_for, enrich_idea, load_calendar, next_exam, timeliness
from office.ideas import WEIGHTS, score_idea
from office.store import Store, WorkflowError

TODAY = date(2026, 10, 29)


@pytest.fixture
def calendar(tmp_path):
    data = {
        "exam-info-processing": {
            "note": "테스트용",
            "exams": [
                {"name": "지난 필기", "date": "2026-10-01", "kind": "필기", "source_url": "https://www.q-net.or.kr", "verified": True},
                {"name": "3회 실기", "date": "2026-11-28", "kind": "실기", "source_url": "https://www.q-net.or.kr", "verified": True, "note": "합성 확인 상태, 실제 일정 검증 아님"},
                {"name": "3회 발표", "date": "2026-12-20", "kind": "발표", "source_url": "https://www.q-net.or.kr", "verified": True},
                {"name": "1회 필기 원서접수", "date": "2027-01-18", "kind": "원서접수", "source_url": "https://www.q-net.or.kr", "verified": True},
            ],
        },
        "exam-opic": {"baseline": 0.6, "note": "상시 시험", "exams": []},
        "transfer-admission": {"exams": [{"name": "편입 시험", "date": "2027-04-01", "kind": "응시", "source_url": "https://example.invalid/official", "verified": True}]},
    }
    path = tmp_path / "exam_calendar.json"
    path.write_text(json.dumps(data, ensure_ascii=False), encoding="utf-8")
    return load_calendar(path)


def test_timeliness_curve_uses_nearest_upcoming_exam_type_event(calendar):
    assert timeliness("exam-info-processing", today=TODAY, calendar=calendar) == 1.0  # 30일 전
    # 실기가 지나면 발표(12-20)는 시험형이 아니므로 건너뛰고 원서접수(2027-01-18)가 다음 사건이다
    assert timeliness("exam-info-processing", today=date(2026, 12, 5), calendar=calendar) == 1.0  # 44일 전
    value = timeliness("exam-info-processing", today=date(2026, 12, 2), calendar=calendar)  # 47일 전 → 선형 구간
    assert 0.2 < value < 1.0
    assert timeliness("exam-info-processing", today=date(2026, 9, 20), calendar=calendar) == 1.0  # 필기 11일 전
    assert timeliness("transfer-admission", today=TODAY, calendar=calendar) == 0.2  # 154일 전 → 바닥값


def test_past_events_are_ignored_and_empty_calendar_scores_zero(calendar):
    assert next_exam("exam-info-processing", today=date(2027, 2, 1), calendar=calendar) is None
    assert timeliness("exam-info-processing", today=date(2027, 2, 1), calendar=calendar) == 0.0
    assert timeliness("ai-agent", today=TODAY, calendar=calendar) == 0.0
    assert next_exam("productivity-automation", today=TODAY, calendar=calendar) is None


def test_opic_uses_baseline_without_entries(calendar):
    result = calendar_for("exam-opic", today=TODAY, calendar=calendar)
    assert result["exams"] == [] and result["next"] is None and result["timeliness"] == 0.6


def test_next_exam_shape_and_unknown_preset(calendar):
    nxt = next_exam("exam-info-processing", today=TODAY, calendar=calendar)
    assert nxt == {"name": "3회 실기", "date": "2026-11-28", "kind": "실기", "days_left": 30,
                   "source_url": "https://www.q-net.or.kr", "verified": True, "note": "합성 확인 상태, 실제 일정 검증 아님"}
    with pytest.raises(WorkflowError, match="프리셋"):
        calendar_for("nope", today=TODAY, calendar=calendar)


def test_shipped_calendar_config_is_well_formed():
    calendar = load_calendar(CONFIG_PATH)
    assert {"exam-opic", "exam-info-processing", "transfer-admission"} <= set(calendar)
    for preset, entry in calendar.items():
        for exam in entry["exams"]:
            date.fromisoformat(exam["date"])
            assert exam["kind"] in ("필기", "실기", "응시", "원서접수", "발표")
            assert isinstance(exam["verified"], bool)
            if not exam["verified"]:
                assert "확인" in exam.get("note", "")
    assert calendar["exam-info-processing"]["exams"]


def test_enrich_idea_reads_brief_preset_or_nested_brief(calendar):
    card = enrich_idea({"title": "t", "brief": {"preset": "exam-info-processing"}}, today=TODAY, calendar=calendar)
    assert card["timeliness"] == 1.0 and card["next_exam"] == next_exam("exam-info-processing", today=TODAY, calendar=calendar)
    assert card["next_exam"]["verified"] is True and card["next_exam"]["source_url"] and card["next_exam"]["note"]
    flat = enrich_idea({"title": "t", "brief_preset": "exam-info-processing"}, today=TODAY, calendar=calendar)
    assert flat["timeliness"] == 1.0
    plain = enrich_idea({"title": "t"}, today=TODAY, calendar=calendar)
    assert plain["timeliness"] == 0.0 and plain["next_exam"] is None


def test_timeliness_adds_points_without_changing_cards_without_calendar(calendar):
    base = {"title": "D", "demand": 100, "primary_sources": 3, "fit": 1}
    plain = score_idea(base, today=TODAY, calendar=calendar)
    assert plain["score"] == 70.0 and plain["parts"]["timeliness"] == 0.0 and WEIGHTS["timeliness"] == 10  # 이상치 unknown=0, 나머지 만점
    half = score_idea({"title": "H", "primary_sources": 3, "fit": 0.5}, today=TODAY, calendar=calendar)
    timely = score_idea({"title": "H", "primary_sources": 3, "fit": 0.5, "brief": {"preset": "exam-info-processing"}}, today=TODAY, calendar=calendar)
    assert timely["parts"]["timeliness"] == 1.0
    assert timely["score"] == round(half["score"] + WEIGHTS["timeliness"], 1)
    assert score_idea({**base, "brief": {"preset": "exam-info-processing"}}, today=TODAY, calendar=calendar)["score"] == 80.0
    capped = score_idea({**base, "views": 20000, "channel_avg_views": 1000, "brief": {"preset": "exam-info-processing"}}, today=TODAY, calendar=calendar)
    assert capped["score"] == 100.0  # 100 + 10 가산점은 100으로 상한


def test_calendar_api_contract(tmp_path):
    client = TestClient(create_app(Store(tmp_path)), base_url="http://localhost:8510")
    body = client.get("/api/calendar", params={"preset": "exam-info-processing"}).json()
    assert body["preset"] == "exam-info-processing" and 0 <= body["timeliness"] <= 1
    assert set(body["exams"][0]) >= {"name", "date", "kind", "source_url", "verified"}
    assert body["next"] is None or set(body["next"]) == {"name", "date", "kind", "days_left", "verified", "source_url", "note"}
    empty = client.get("/api/calendar", params={"preset": "ai-agent"}).json()
    assert empty == {"preset": "ai-agent", "exams": [], "next": None, "timeliness": 0.0}
    assert client.get("/api/calendar", params={"preset": "nope"}).status_code == 409


def test_idea_api_returns_timeliness_and_next_exam(tmp_path):
    client = TestClient(create_app(Store(tmp_path)), base_url="http://localhost:8510")
    headers = {"Origin": "http://localhost:3110", "X-Office-CSRF": client.get("/api/session").json()["csrf"]}
    body = {"title": "정처기 D-30 복습", "source_url": "https://example.com/ip", "primary_sources": 2, "fit": 0.8, "brief_preset": "exam-info-processing"}
    idea = client.post("/api/ideas", json=body, headers=headers).json()
    assert "timeliness" in idea and "next_exam" in idea and "timeliness" in idea["parts"]
    listed = client.get("/api/ideas").json()["ideas"][0]
    assert "timeliness" in listed and "next_exam" in listed


@pytest.mark.parametrize("verified", [False, None, "false", "true", 1])
def test_unverified_or_non_boolean_dates_remain_reference_only(tmp_path, verified):
    row = {"name": "미확인 추정 접수", "date": "2026-11-28", "kind": "원서접수", "source_url": "https://example.invalid/notice", "note": "공식 공고 확인 필요"}
    if verified is not None:
        row["verified"] = verified
    path = tmp_path / "calendar.json"
    path.write_text(json.dumps({"transfer-admission": {"exams": [row]}}), encoding="utf-8")
    calendar = load_calendar(path)
    result = calendar_for("transfer-admission", today=TODAY, calendar=calendar)
    assert result["next"]["verified"] is False and result["timeliness"] == 0
    card = enrich_idea({"brief_preset": "transfer-admission"}, today=TODAY, calendar=calendar)
    assert card["next_exam"] == result["next"]
    assert card["next_exam"]["note"] == row["note"] and card["next_exam"]["source_url"] == row["source_url"]


@pytest.mark.parametrize("url", ["", "http://example.invalid/notice", "https://localhost/notice", "https://127.0.0.1/notice", "https://10.0.0.1/notice", "https://user:pass@example.invalid/notice", "https://example.invalid/a b", "https://[invalid"])
def test_verified_flag_without_public_https_source_cannot_add_timeliness(url):
    calendar = {"transfer-admission": {"baseline": 0, "exams": [{"name": "불완전 확인", "date": "2026-11-28", "kind": "응시", "verified": True, "source_url": url}]}}
    assert timeliness("transfer-admission", today=TODAY, calendar=calendar) == 0
    reference = next_exam("transfer-admission", today=TODAY, calendar=calendar)
    assert reference["source_url"] == url and reference["note"] == ""


def test_nearest_unverified_event_does_not_borrow_a_later_verified_event_score():
    calendar = {"transfer-admission": {"baseline": 0, "note": "추정과 확정 구분", "exams": [
        {"name": "추정 접수", "date": "2026-11-01", "kind": "원서접수", "verified": False, "source_url": ""},
        {"name": "합성 확인 시험", "date": "2026-11-28", "kind": "응시", "verified": True, "source_url": "https://example.invalid/notice"}]}}
    result = calendar_for("transfer-admission", today=TODAY, calendar=calendar)
    assert result["next"]["name"] == "추정 접수" and result["next"]["note"] == "추정과 확정 구분"
    assert result["timeliness"] == 0
    assert timeliness("transfer-admission", today=date(2026, 11, 2), calendar=calendar) == 1


def test_shipped_unverified_transfer_dates_do_not_boost_real_idea_ranking():
    calendar = load_calendar(CONFIG_PATH)
    today = date(2026, 10, 30)
    base = {"title": "합성 순위 검증", "primary_sources": 3, "fit": 1, "demand": 100}
    plain = score_idea(base, today=today, calendar=calendar)
    transfer = score_idea({**base, "brief_preset": "transfer-admission"}, today=today, calendar=calendar)
    assert plain["score"] == transfer["score"] == 70
    assert transfer["next_exam"]["verified"] is False and transfer["next_exam"]["source_url"] == ""
    assert transfer["next_exam"]["kind"] == "원서접수" and transfer["next_exam"]["days_left"] == 59
    assert transfer["parts"]["timeliness"] == 0
    blocked = score_idea({**base, "brief_preset": "transfer-admission", "primary_sources": 0}, today=today, calendar=calendar)
    assert blocked["score"] == 0 and blocked["blocked"] and blocked["parts"]["timeliness"] == 0
