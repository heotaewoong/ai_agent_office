"""자동 보충 조사: 자료 창고 판정(맞음, 애매, 틀림)에 따라 바깥 조사를 대신 돌리고, 사람이 승인⓪에서 판정을 채점한다."""
from contextlib import closing

import pytest
import requests
from fastapi.testclient import TestClient

from office import external_research, research_auto
from office.external_research import VERDICTS, library_verdict, run_research
from office.research_auto import run_auto_research
from office.research_choices import (
    auto_tavily_today, load_auto, load_label, log_click, save_label, suggest_label, verdict_stats,
)
from office.source_library import _connect
from office.store import Store, WorkflowError

PLAN = {"kind": "W3", "area": "C", "kind_guessed": False, "area_guessed": False, "need": "required", "blocked": False}
FACT = {"key": "fact-1", "lane": "fact", "title": "공식 문서", "url": "https://docs.example.org/a", "snippet": ""}
BLOG = {"key": "blog-1", "lane": "example", "title": "블로그", "url": "https://blog.example.com/a", "snippet": "", "idea_only": True}


def verdict(key, score=0.5):
    return {"verdict": key, "label": VERDICTS[key], "top_score": score, "reason": ""}


def usage(calls=0):
    return {"month": "2026-11", "calls": calls, "cap": 900, "remaining": 900 - calls, "has_key": True}


def fakes(monkeypatch, key, candidates=(), tavily_rows=()):
    """창고 판정이 key인 조사와 Tavily를 흉내 낸다. 둘 다 밖으로 나가지 않는다."""
    research_calls, tavily_calls = [], []

    def research(root, title, **options):
        research_calls.append(options)
        return {"plan": dict(PLAN), "queries": {"english": "", "terms": [], "custom": False}, "library": {"fact_sources": 1, "sufficient": False},
                "candidates": list(candidates), "notes": [], "searched": key != "correct", "verdict": verdict(key) if key else None}

    def tavily(root, title, **options):
        tavily_calls.append(title)
        return {"queries": {"tavily": title}, "candidates": list(tavily_rows), "notes": ["Tavily 메모"], "searched": True, "tavily": usage(len(tavily_calls))}

    monkeypatch.setattr(research_auto, "tavily_usage", lambda root: usage(len(tavily_calls)))
    return research, tavily, research_calls, tavily_calls


def test_verdict_comes_from_the_top_library_score():
    assert library_verdict(None, 0.9) is None  # 창고를 못 봤으면 판정하지 않는다.
    assert library_verdict(0, 0.9)["verdict"] == "incorrect" and library_verdict(2, None)["verdict"] == "incorrect"
    assert library_verdict(2, 0.47)["verdict"] == "incorrect" and library_verdict(2, 0.48)["verdict"] == "ambiguous"
    assert library_verdict(2, 0.6199)["verdict"] == "ambiguous"
    assert library_verdict(2, 0.62) == {"verdict": "correct", "label": "맞음", "top_score": 0.62, "reason": "자료 창고에 이 주제와 아주 가까운 근거가 있어요."}


def test_correct_verdict_stays_inside_and_the_result_is_reused(tmp_path, monkeypatch):
    research, tavily, research_calls, tavily_calls = fakes(monkeypatch, "correct")
    first = run_auto_research(tmp_path, "idea-1", "간격 복습", research=research, tavily=tavily)
    assert first["cached"] is False and first["auto"] == {"ran": False, "tavily": False, "tavily_today": 0, "tavily_daily_cap": 30}
    assert research_calls[0]["auto"] is True and tavily_calls == [] and "hold" not in first
    again = run_auto_research(tmp_path, "idea-1", "간격 복습", research=research, tavily=tavily)
    assert again["cached"] is True and again["verdict"]["verdict"] == "correct" and len(research_calls) == 1


def test_ambiguous_verdict_adds_one_tavily_search_per_idea(tmp_path, monkeypatch):
    research, tavily, research_calls, tavily_calls = fakes(monkeypatch, "ambiguous", candidates=[FACT], tavily_rows=[FACT, BLOG])
    found = run_auto_research(tmp_path, "idea-1", "간격 복습", research=research, tavily=tavily)
    assert [row["key"] for row in found["candidates"]] == ["fact-1", "blog-1"] and "Tavily 메모" in found["notes"]
    assert found["auto"]["tavily"] is True and found["auto"]["tavily_today"] == 1 and tavily_calls == ["간격 복습"]
    assert load_auto(tmp_path, "idea-1")["tavily"] is True and auto_tavily_today(tmp_path) == 1
    # 글 유형을 바꾸면 창고와 무료 출처는 다시 보지만 Tavily는 다시 부르지 않는다.
    changed = run_auto_research(tmp_path, "idea-1", "간격 복습", kind="W1", research=research, tavily=tavily)
    assert changed["cached"] is False and len(research_calls) == 2 and len(tavily_calls) == 1
    assert any("이미 한 번" in note for note in changed["notes"]) and load_auto(tmp_path, "idea-1")["tavily"] is True


def test_incorrect_verdict_without_fact_candidates_is_held(tmp_path, monkeypatch):
    research, tavily, _, tavily_calls = fakes(monkeypatch, "incorrect", tavily_rows=[BLOG])
    found = run_auto_research(tmp_path, "idea-1", "아무도 안 쓴 주제", research=research, tavily=tavily)
    assert found["hold"] is True and any("근거 부족" in note for note in found["notes"]) and len(tavily_calls) == 1
    research, tavily, _, _ = fakes(monkeypatch, "incorrect", tavily_rows=[FACT])
    assert "hold" not in run_auto_research(tmp_path, "idea-2", "공식 자료가 있는 주제", research=research, tavily=tavily)


def test_daily_cap_stops_automatic_tavily(tmp_path, monkeypatch):
    monkeypatch.setattr(research_auto, "AUTO_TAVILY_DAILY_CAP", 2)
    research, tavily, _, tavily_calls = fakes(monkeypatch, "incorrect", tavily_rows=[FACT])
    results = [run_auto_research(tmp_path, f"idea-{n}", f"주제 {n}", research=research, tavily=tavily) for n in range(3)]
    assert len(tavily_calls) == 2 and auto_tavily_today(tmp_path) == 2
    assert results[2]["auto"]["tavily"] is False and any("다 썼어요" in note for note in results[2]["notes"])


def test_no_verdict_means_no_automatic_tavily(tmp_path, monkeypatch):
    research, tavily, _, tavily_calls = fakes(monkeypatch, None)
    found = run_auto_research(tmp_path, "idea-1", "회사를 그만두고 배운 것", experience_first=True, research=research, tavily=tavily)
    assert found["verdict"] is None and tavily_calls == [] and "hold" not in found


def offline(url, *, maximum):
    raise requests.ConnectionError("offline")


def test_run_research_follows_the_library_verdict_only_when_auto(tmp_path, monkeypatch):
    monkeypatch.setattr(external_research, "library_judgement", lambda root, title, area=None: {"fact_sources": 2, "top_score": 0.7})
    kept = run_research(tmp_path, "간격 복습이 기억에 미치는 효과", auto=True, fetch=offline)
    assert kept["verdict"]["verdict"] == "correct" and kept["searched"] is False and any("밖으로 찾지 않았어요" in note for note in kept["notes"])
    # 발표·공고 글은 창고에 있어도 최신 원문을 확인한다.
    news = run_research(tmp_path, "간격 복습이 기억에 미치는 효과", kind="W2", auto=True, fetch=offline)
    assert news["verdict"]["verdict"] == "correct" and not any("밖으로 찾지 않았어요" in note for note in news["notes"])
    # 사람이 누른 조사는 판정을 보여 주기만 하고 예전 기준대로 찾는다.
    manual = run_research(tmp_path, "간격 복습이 기억에 미치는 효과", fetch=offline)
    assert manual["verdict"]["verdict"] == "correct" and not any("밖으로 찾지 않았어요" in note for note in manual["notes"])
    mine = run_research(tmp_path, "회사를 그만두고 배운 것", area="D", experience_first=True, auto=True, fetch=offline)
    assert mine["verdict"] is None and mine["searched"] is False
    monkeypatch.setattr(external_research, "library_judgement", lambda root, title, area=None: {"fact_sources": 0, "top_score": 0.0})
    empty = run_research(tmp_path, "우리 동네 산책길 이야기", area="E", auto=True, fetch=offline)
    assert empty["verdict"]["verdict"] == "incorrect" and empty["plan"]["blocked"] is False


def test_person_marks_the_verdict_and_practice_is_left_out(tmp_path, monkeypatch):
    assert suggest_label("correct", 0) == "correct" and suggest_label("correct", 2) == "wrong"
    assert suggest_label("incorrect", 1) == "correct" and suggest_label("ambiguous", 0) == "wrong" and suggest_label(None, 3) is None
    assert load_label(tmp_path, "idea-1")["verdict"] is None  # 아직 표가 없는 창고
    for idea, key in (("idea-1", "correct"), ("idea-2", "incorrect"), ("idea-3", "ambiguous")):
        research, tavily, _, _ = fakes(monkeypatch, key, tavily_rows=[FACT])
        run_auto_research(tmp_path, idea, f"주제 {idea}", research=research, tavily=tavily)
    state = load_label(tmp_path, "idea-1")
    assert state == {"idea_id": "idea-1", "verdict": "correct", "verdict_label": "맞음", "top_score": 0.5, "label": None,
                     "suggested": "correct", "saved_external": 0}
    assert save_label(tmp_path, "idea-1", "correct")["label"] == "correct"
    assert save_label(tmp_path, "idea-2", "wrong")["label"] == "wrong"  # 미리 골라 둔 값(틀림)과 같다.
    assert save_label(tmp_path, "idea-3", "practice")["label"] == "practice"
    assert save_label(tmp_path, "idea-1", "wrong")["label"] == "wrong" and load_label(tmp_path, "idea-1")["label"] == "wrong"
    stats = verdict_stats(tmp_path)
    assert stats["labeled"] == 2 and stats["practice"] == 1 and stats["agreement"] == 0.0
    assert stats["by_verdict"]["correct"] == {"correct": 0, "wrong": 1} and stats["changed_from_suggestion"] == 1
    with pytest.raises(WorkflowError):
        save_label(tmp_path, "idea-1", "maybe")
    with pytest.raises(WorkflowError):
        save_label(tmp_path, "bad id!", "correct")


def test_click_log_keeps_the_verdict_and_upgrades_an_old_table(tmp_path):
    with closing(_connect(tmp_path)) as db, db:
        db.execute("CREATE TABLE research_clicks(id INTEGER PRIMARY KEY AUTOINCREMENT, idea_id TEXT NOT NULL, at TEXT NOT NULL, kind TEXT NOT NULL, "
                   "area TEXT NOT NULL, kind_guessed INTEGER NOT NULL, area_guessed INTEGER NOT NULL, need TEXT NOT NULL, forced INTEGER NOT NULL, "
                   "searched INTEGER NOT NULL, candidates INTEGER NOT NULL)")
        db.execute("INSERT INTO research_clicks(idea_id,at,kind,area,kind_guessed,area_guessed,need,forced,searched,candidates) "
                   "VALUES ('old','2026-11-24T00:00:00+00:00','W3','C',0,0,'required',0,1,2)")
    assert log_click(tmp_path, "idea-1", PLAN, forced=False, searched=True, candidates=3, verdict=verdict("ambiguous", 0.55), auto=True)
    assert log_click(tmp_path, "idea-2", PLAN, forced=True, searched=True, candidates=0)
    with closing(_connect(tmp_path)) as db:
        rows = [tuple(row) for row in db.execute("SELECT idea_id, verdict, auto, top_score FROM research_clicks ORDER BY id")]
    assert rows == [("old", None, 0, None), ("idea-1", "ambiguous", 1, 0.55), ("idea-2", None, 0, None)]


def client(tmp_path):
    from office.api import create_app
    api = TestClient(create_app(Store(tmp_path)), base_url="http://localhost:8510")
    api.headers.update({"Origin": "http://localhost:3110", "X-Office-CSRF": api.get("/api/session").json()["csrf"]})
    return api


def test_api_runs_the_automatic_search_and_saves_the_label(tmp_path, monkeypatch):
    api = client(tmp_path)
    seen = []

    def auto(root, idea_id, title, **options):
        seen.append((idea_id, title, options["kind"], callable(options["translate"])))
        return {"plan": dict(PLAN), "candidates": [FACT], "notes": [], "searched": True, "verdict": verdict("ambiguous", 0.55), "cached": False}

    monkeypatch.setattr("office.api_source_library.run_auto_research", auto)
    monkeypatch.setattr("office.api_source_library.run_research", lambda root, title, **options: {"candidates": [], "manual": True})
    run = api.post("/api/source-library/research", json={"id": "idea-1", "title": "간격 복습", "kind": "W3", "auto": True})
    assert run.status_code == 200 and run.json()["verdict"]["verdict"] == "ambiguous" and seen == [("idea-1", "간격 복습", "W3", True)]
    # 검색어를 적었거나 '그래도 찾기'면 사람이 누른 조사다. 기획 ID가 없어도 자동 조사를 하지 않는다.
    assert api.post("/api/source-library/research", json={"id": "idea-1", "title": "간격 복습", "auto": True, "query": "spacing"}).json()["manual"] is True
    assert api.post("/api/source-library/research", json={"title": "간격 복습", "auto": True}).json()["manual"] is True
    assert api.post("/api/source-library/research", json={"title": "간격 복습", "auto": "yes"}).status_code == 422 and len(seen) == 1
    with closing(_connect(tmp_path)) as db:
        assert [tuple(row) for row in db.execute("SELECT idea_id, verdict, auto FROM research_clicks ORDER BY id")][0] == ("idea-1", "ambiguous", 1)
    assert api.get("/api/source-library/research/labels/idea-1").json()["label"] is None
    saved = api.put("/api/source-library/research/labels/idea-1", json={"label": "practice"})
    assert saved.status_code == 200 and saved.json()["label"] == "practice"
    assert api.get("/api/source-library/research/labels/idea-1").json()["label"] == "practice"
    assert api.put("/api/source-library/research/labels/idea-1", json={"label": "maybe"}).status_code == 422
    assert api.get("/api/source-library/research/labels").json()["practice"] == 1
