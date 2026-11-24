"""글 유형(W1~W5) × 분야: 사람이 고른 값만 조사 칸을 바꾸고, 추측값은 기본값으로만 보여 준다."""
import sys
from types import SimpleNamespace

import pytest
from fastapi.testclient import TestClient

from office import external_research
from office.external_research import KINDS, _KIND_BLANKS, guess_kind, research_plan, run_research
from office.research_choices import click_stats, load_choice, load_choices, log_click, save_choice
from office.store import Store, WorkflowError, digest


def offline(url, *, maximum):
    raise AssertionError(f"밖으로 나가면 안 되는 요청: {url}")


def no_library(root, title):
    raise AssertionError("범위 밖 주제는 자료 창고도 찾지 않는다")


def client(tmp_path):
    from office.api import create_app
    api = TestClient(create_app(Store(tmp_path)), base_url="http://localhost:8510")
    api.headers.update({"Origin": "http://localhost:3110", "X-Office-CSRF": api.get("/api/session").json()["csrf"]})
    return api


def add_idea(api, title, slug):
    made = api.post("/api/ideas", json={"title": title, "source_url": f"https://primary.example.org/{slug}", "primary_sources": 1})
    assert made.status_code == 200
    return made.json()


@pytest.fixture(autouse=True)
def fresh_feed_cache():
    external_research._feed_cache.clear()


def test_kind_is_guessed_from_the_title_and_the_experience_switch_counts_as_a_choice():
    titles = ("Hermes와 OpenClaw 차이", "정보처리기사 실기 접수 일정", "간격 복습이 기억에 미치는 효과", "퇴사하고 느낀 것들",
              "석 달 만에 집중 시간이 30% 늘어난 내 방법", "문제가 생겼을 때 안내 문구 쓰기")
    assert [guess_kind(text) for text in titles] == ["W1", "W2", "W3", "W4", "W4", "W3"]
    assert list(KINDS) == ["W1", "W2", "W3", "W4", "W5"]
    switched = research_plan("간격 복습", area="C", experience_first=True)
    assert (switched["kind"], switched["kind_guessed"], switched["need"]) == ("W4", False, "none")


@pytest.mark.parametrize("title, kind, area", [
    ("ElevenLabs와 OpenAI TTS 무료 등급 비교", "W1", "B"), ("Gemini 새 모델 발표 해설", "W2", "B"),
    ("2027년 정보처리기사 시험 일정과 응시료", "W2", "A"), ("OPIc IM2에서 막힐 때 공부법", "W3", "A"),
    ("커피는 자기 몇 시간 전에 끊어야 하나", "W3", "C"), ("옵시디언 동기화가 안 될 때 해결 후기", "W4", "B"),
    ("이 약 먹어도 되나요", "W5", None), ("Claude로 HTML 발표자료를 제작한 사례", "W3", "B"),
])
def test_default_guesses_follow_the_examples_in_design_v2(title, kind, area):
    plan = research_plan(title)
    assert (plan["kind"], plan["kind_guessed"]) == (kind, True)
    assert area is None or plan["area"] == area


def test_the_coffee_question_follows_the_brain_science_rules_once_chosen():
    plan = research_plan("커피는 자기 몇 시간 전에 끊어야 하나", kind="W3", area="C")
    assert plan["fact"]["need"] == "required" and plan["fact"]["providers"] == ["pubmed", "openalex"] and not plan["blocked"]
    guessed_out_of_scope = research_plan("이 약 먹어도 되나요")
    assert guessed_out_of_scope["kind"] == "W5" and guessed_out_of_scope["blocked"] is False  # 추측만으로는 막지 않는다.


@pytest.mark.parametrize("title, area", [("퇴사하고 느낀 것들", "D"), ("정보처리기사 실기 접수 일정", None), ("Hermes와 OpenClaw 차이", None),
                                         ("아침 루틴 만드는 방법", None)])
def test_a_guessed_kind_is_only_a_default_and_never_changes_what_to_search(title, area):
    guessed = research_plan(title, area=area)
    chosen = research_plan(title, area=area, kind="W3")  # W3은 주장 기준 그대로라 추측값과 조사 칸이 같아야 한다.
    assert guessed["kind_guessed"] is True and chosen["kind_guessed"] is False
    same = ("need", "fact", "example", "summary", "blocked", "experience_first", "needs_experience_source")
    assert {key: guessed[key] for key in same} == {key: chosen[key] for key in same}
    assert guessed["blanks"] == list(_KIND_BLANKS[guessed["kind"]])


def test_out_of_scope_topics_are_blocked_even_when_forced(tmp_path):
    plan = research_plan("연예인 열애설 정리", kind="W5", area="E")
    assert plan["blocked"] is True and plan["need"] == "none" and plan["fact"]["providers"] == [] and plan["blanks"] == []
    assert plan["summary"].startswith("외부 조사 안 함")
    result = run_research(tmp_path, "연예인 열애설 정리", kind="W5", area="E", force=True, fetch=offline, fact_sources=no_library,
                          translate=lambda title: pytest.fail("범위 밖 주제는 검색어도 만들지 않는다"))
    assert result["searched"] is False and result["candidates"] == [] and any("밖으로 찾지 않았어요" in note for note in result["notes"])


def test_experience_reviews_skip_outside_search_and_ask_for_my_own_source():
    plan = research_plan("석 달 만에 집중 시간이 30% 늘어난 방법", area="D", kind="W4")
    assert plan["need"] == "none" and plan["needs_experience_source"] is True and plan["experience_first"] is True
    assert "수치" in plan["warning"]
    guessed = research_plan("석 달 만에 집중 시간이 30% 늘어난 내 방법", area="D")
    assert guessed["kind"] == "W4" and guessed["needs_experience_source"] is False and guessed["need"] == "required"


def test_announcements_read_official_sources_first_and_skip_other_peoples_examples():
    plan = research_plan("수면 연구 새 지침 발표", area="C", kind="W2")
    assert plan["fact"]["need"] == "required" and plan["fact"]["providers"] == ["official", "pubmed", "openalex"]
    assert plan["example"]["need"] == "none" and plan["need"] == "required" and "원문" in plan["summary"]


def test_comparisons_always_check_official_pages_and_examples():
    plan = research_plan("자취방 청소기 고르기", area="E", kind="W1")
    assert plan["fact"]["need"] == "recommended" and plan["fact"]["providers"] == ["official"]
    assert plan["example"]["need"] == "recommended" and plan["need"] == "recommended"
    assert research_plan("노트 앱 고르기", area="B", kind="W1")["fact"]["providers"][:2] == ["official", "github"]


def test_choices_are_saved_per_idea_and_checked(tmp_path):
    assert load_choices(tmp_path) == {} and load_choice(tmp_path, "idea-1") is None
    saved = save_choice(tmp_path, "idea-1", kind="W1", area="B")
    assert (saved["kind"], saved["area"], saved["kind_label"]) == ("W1", "B", "비교·벤치마킹") and saved["updated_at"]
    save_choice(tmp_path, "idea-1", kind="W2", area="B")
    assert load_choices(tmp_path) == {"idea-1": {"kind": "W2", "area": "B"}} and load_choice(tmp_path, "idea-1") == {"kind": "W2", "area": "B"}
    for bad in ({"kind": "W9", "area": "B"}, {"kind": "W1", "area": "Z"}):
        with pytest.raises(WorkflowError):
            save_choice(tmp_path, "idea-1", **bad)
    with pytest.raises(WorkflowError):
        save_choice(tmp_path, "../idea", kind="W1", area="B")


def test_click_log_keeps_only_counts_and_never_breaks_a_search(tmp_path):
    assert click_stats(tmp_path)["clicks"] == 0
    assert log_click(tmp_path, "idea-1", {"kind": "W1", "kind_guessed": False, "area": "B", "area_guessed": True, "need": "required"},
                     forced=False, searched=True, candidates=3) is True
    assert log_click(tmp_path, "bad id", {}, forced=False, searched=False, candidates=0) is False
    assert click_stats(tmp_path) == {"clicks": 1, "by_need": {"required": 1, "recommended": 0, "none": 0}, "chosen_kind": 1, "forced": 0,
                                     "found_any": 1}


def test_api_saves_a_choice_and_the_idea_list_plans_with_it_without_touching_the_idea(tmp_path):
    api = client(tmp_path)
    idea = add_idea(api, "퇴사하고 느낀 것들", "quit")

    def listed():
        return next(row for row in api.get("/api/ideas").json()["ideas"] if row["id"] == idea["id"])
    before = listed()
    assert (before["research"]["kind"], before["research"]["kind_guessed"], before["research"]["need"]) == ("W4", True, "recommended")
    saved = api.put(f"/api/source-library/research/choices/{idea['id']}", json={"kind": "W4", "area": "D"})
    assert saved.status_code == 200 and saved.json()["choice"]["kind"] == "W4"
    after = listed()
    assert after["research"]["kind_guessed"] is False and after["research"]["area_guessed"] is False
    assert after["research"]["need"] == "none" and after["research"]["needs_experience_source"] is True
    assert {key: value for key, value in after.items() if key != "research"} == {key: value for key, value in before.items() if key != "research"}
    assert api.put(f"/api/source-library/research/choices/{idea['id']}", json={"kind": "W9", "area": "D"}).status_code == 422
    assert api.put(f"/api/source-library/research/choices/{idea['id']}", json={"kind": "W1", "area": "Z"}).status_code == 409
    assert api.put("/api/source-library/research/choices/bad%20id", json={"kind": "W1", "area": "D"}).status_code == 409
    plans = api.post("/api/source-library/research/plans", json={"topics": [{"id": idea["id"], "title": idea["title"], "kind": "W5", "area": "D"}]})
    assert plans.status_code == 200 and plans.json()["plans"][0]["blocked"] is True


def test_api_counts_research_clicks_from_idea_cards_only(tmp_path, monkeypatch):
    api = client(tmp_path)
    monkeypatch.setattr(external_research, "fetch_public", offline)
    blocked = api.post("/api/source-library/research", json={"id": "idea-7", "title": "연예인 열애설 정리", "kind": "W5", "area": "E", "force": True})
    assert blocked.status_code == 200 and blocked.json()["searched"] is False
    monkeypatch.setattr("office.api_source_library.run_research", lambda root, title, **options: {
        "plan": {"kind": "W3", "kind_guessed": True, "area": "C", "area_guessed": True, "need": "required"},
        "candidates": [{"key": "a"}], "searched": True})
    assert api.post("/api/source-library/research", json={"id": "idea-8", "title": "간격 복습"}).status_code == 200
    assert api.post("/api/source-library/research", json={"title": "간격 복습"}).status_code == 200
    assert api.get("/api/source-library/research/clicks").json() == {
        "clicks": 2, "by_need": {"required": 1, "recommended": 0, "none": 1}, "chosen_kind": 1, "forced": 1, "found_any": 1}


def test_public_evidence_uses_the_chosen_area_instead_of_the_guess(tmp_path, monkeypatch):
    scopes = []

    def find(query, *, limit, **scope):
        scopes.append(scope)
        return []
    monkeypatch.setitem(sys.modules, "office.public_evidence", SimpleNamespace(
        find_public_evidence=find, public_evidence_id=lambda *parts: "0" * 64,
        PublicEvidenceUnavailable=type("PublicEvidenceUnavailable", (RuntimeError,), {})))
    api = client(tmp_path)
    exam = add_idea(api, "토익 900점 공부 순서", "toeic")
    tool = add_idea(api, "MCP 서버 만들기", "mcp")
    guess = add_idea(api, "오픽 등급 올리기", "opic")
    assert api.put(f"/api/source-library/research/choices/{exam['id']}", json={"kind": "W3", "area": "C"}).status_code == 200
    assert api.put(f"/api/source-library/research/choices/{tool['id']}", json={"kind": "W3", "area": "A"}).status_code == 200
    for idea in (exam, tool, guess):
        assert api.post(f"/api/ideas/{idea['id']}/public-evidence", json={"expected_hash": digest(idea)}).status_code == 200
    assert scopes == [{}, {"area": "A"}, {"area": "A"}]
