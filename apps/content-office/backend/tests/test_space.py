import json
import pytest
from fastapi.testclient import TestClient
from office.api import AGENTS, create_app
from office.space import project_space
from office.store import Store

FORBIDDEN = ("게시됨", "자동")


def test_empty_store_still_has_five_stages(tmp_path):
    space = project_space(Store(tmp_path), agents=AGENTS)
    assert [s["id"] for s in space["stages"]] == ["inbox", "scripts", "creative", "outbox", "ops"]
    assert all(s["items"] == [] for s in space["stages"][:4])
    assert space["stages"][4]["items"][0]["id"] == "budget"
    assert space["version"] == 1 and len(space["agents"]) == 9


def test_jobs_and_ideas_land_in_their_rooms(tmp_path):
    store = Store(tmp_path)
    store.save_idea({"id": "idea-1", "title": "후보 기획", "score": 82, "blocked": [], "state": "candidate", "reasons": []})
    store.save_idea({"id": "idea-2", "title": "막힌 기획", "score": 10, "blocked": ["1차 출처 없음"], "state": "candidate", "reasons": []})
    job = store.create_job({"id": "a1", "title": "원고 작업", "url": "https://ex.com", "evidence": []})
    store.update_job(job["id"], state="source_approved")
    space = project_space(store)
    inbox = {i["title"]: i for i in space["stages"][0]["items"]}
    assert inbox["후보 기획"]["needsHuman"] is True and "82" in inbox["후보 기획"]["stateLabel"]
    assert inbox["막힌 기획"]["state"] == "blocked"
    creative = space["stages"][2]["items"]
    assert creative[0]["id"] == job["id"] and creative[0]["actions"] == [{"id": "produce", "label": "제작 시작"}] and creative[0]["view"] == "delivery"


def test_projection_has_no_private_data_or_forbidden_words(tmp_path):
    store = Store(tmp_path)
    store.create_job({"id": "b1", "title": "제목만", "url": "https://ex.com", "body": "본문 database/learning-private/secret.md",
                      "operator_source_text": "SECRETTEXT",
                      "evidence": [{"id": "e1", "excerpt": "EVIDENCETEXT", "url": "https://ex.com/private"}]})
    dumped = json.dumps(project_space(store), ensure_ascii=False)
    assert "learning-private" not in dumped and "본문" not in dumped
    assert not any(w in dumped for w in ("SECRETTEXT", "EVIDENCETEXT", "ex.com/private"))
    assert not any(w in dumped for w in FORBIDDEN)


def test_space_endpoint_is_public_read(tmp_path):
    client = TestClient(create_app(Store(tmp_path)), base_url="http://localhost:8510")
    r = client.get("/api/space")
    assert r.status_code == 200 and r.headers["cache-control"] == "no-store"
    assert r.json()["office"]["url"].startswith("http")


def test_running_draft_task_marks_editor_running(tmp_path):
    store = Store(tmp_path)
    store.enqueue("draft", {}, key="k1")
    with store.connection(transaction=True) as db:
        db.execute("UPDATE tasks SET state='running'")
    editor = next(a for a in project_space(store, agents=AGENTS)["agents"] if a["id"] == "editor")
    assert editor["status"] == "running"


@pytest.mark.parametrize(("kind", "agent_id", "state", "expected"), [
    ("draft", "editor", "running", "running"), ("evaluate", "critique", "claimed", "running"),
    ("produce", "video", "unknown", "unknown"), ("refresh", "research", "failed", "error"),
])
def test_agent_activity_survives_105_newer_tasks_of_other_kinds(tmp_path, kind, agent_id, state, expected):
    store = Store(tmp_path)
    old, recent = "2020-01-01T00:00:00+00:00", "2026-10-29T00:00:00+00:00"
    with store.connection(transaction=True) as db:
        rows = [("task_selected", kind, '{"body":"PRIVATE_ACTIVITY_SENTINEL"}', state, "selected", "private-owner", '{"result":"PRIVATE_RESULT"}', old, old)]
        rows += [(f"task_other_{index:03}", "other", "{}", "completed", f"other:{index}", None, None, recent, recent) for index in range(105)]
        db.executemany("INSERT INTO tasks VALUES(?,?,?,?,?,?,?,?,?)", rows)
    assert all(task["id"] != "task_selected" for task in store.tasks())
    space = project_space(store, agents=AGENTS)
    agent = next(a for a in space["agents"] if a["id"] == agent_id)
    assert agent["status"] == expected
    if state == "unknown":
        assert "결과 불명" in agent["task"] and "대사" in agent["task"]
    dumped = json.dumps(space, ensure_ascii=False)
    assert not any(value in dumped for value in ("PRIVATE_ACTIVITY_SENTINEL", "PRIVATE_RESULT", "private-owner"))


def test_latest_completed_stops_prioritizing_old_unknown_and_preserves_human_waiting(tmp_path):
    store = Store(tmp_path)
    job = store.create_job({"id": "needs-review", "title": "검토할 원고", "url": "https://example.com"})
    store.update_job(job["id"], state="source_review")
    with store.connection(transaction=True) as db:
        db.executemany("INSERT INTO tasks VALUES(?,?,?, ?,?,NULL,NULL,?,?)", [
            ("task_unknown", "draft", "{}", "unknown", "unknown", "2020", "2020"),
            ("task_completed", "draft", "{}", "completed", "completed", "2021", "2021"),
        ])
    def editor():
        return next(a for a in project_space(store, agents=AGENTS)["agents"] if a["id"] == "editor")
    assert editor()["status"] == "waiting"
    store.update_job(job["id"], state="research_ready")
    assert editor()["status"] == "idle"
    assert store.task("task_unknown")["state"] == "unknown"


def test_event_time_is_kst(tmp_path):
    store = Store(tmp_path)
    store.event("lesson_proposed", {})
    with store.connection(transaction=True) as db:
        db.execute("UPDATE events SET created_at='2026-10-28T00:05:00+00:00'")
    assert project_space(store)["events"][0]["time"] == "09:05"


def test_unscored_idea_is_pending(tmp_path):
    store = Store(tmp_path)
    store.save_idea({"title": "미채점"})
    item = project_space(store)["stages"][0]["items"][0]
    assert item["state"] == "pending" and item["needsHuman"] is False


def test_idea_job_without_packaging_offers_no_draft_action(tmp_path):
    store = Store(tmp_path)
    job = store.create_job({"id": "i1", "title": "기획", "url": "https://ex.com", "origin": "idea"})
    store.update_job(job["id"], state="research_ready")
    assert project_space(store)["stages"][1]["items"][0]["actions"] == []
    store.update_job(job["id"], packaging={"packaging_hash": "h"})
    assert project_space(store)["stages"][1]["items"][0]["actions"] == [{"id": "draft", "label": "원고 생성"}]
