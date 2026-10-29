import pytest
from fastapi.testclient import TestClient

from office.api import create_app
from office.questions import convert_question, receive_question
from office.store import Store, digest


@pytest.fixture
def context(tmp_path):
    store = Store(tmp_path)
    client = TestClient(create_app(store), base_url="http://localhost:8510")
    headers = {"Origin": "http://localhost:3110", "X-Office-CSRF": client.get("/api/session").json()["csrf"]}
    question = receive_question(store, "homepage", "편입 영어와 모집 요강은 어디부터 확인해야 하나요?")
    idea = convert_question(store, question["id"], brief_preset="transfer-admission")
    return store, client, headers, idea


def payload(idea, **changes):
    return {"source_urls": ["https://admission.example.edu/transfer"], "operator_verified": True, "expected_hash": digest(idea), **changes}


def test_question_idea_sources_keep_identity_and_require_explicit_selection(context):
    store, client, headers, idea = context
    listed = client.get("/api/ideas").json()["ideas"][0]
    assert listed["edit_hash"] == digest(idea)
    response = client.put(f"/api/ideas/{idea['id']}/sources", json=payload(idea, source_urls=[
        "https://admission.example.edu/transfer",
        "https://admission.example.edu/transfer",
        "https://admission.example.edu/english",
    ]), headers=headers)
    assert response.status_code == 200
    saved = response.json()
    assert saved["id"] == idea["id"] and saved["state"] == "candidate" and not saved["blocked"]
    assert saved["source_url"] == "https://admission.example.edu/transfer"
    assert saved["source_urls"] == [saved["source_url"], "https://admission.example.edu/english"]
    assert saved["primary_sources"] == saved["operator_verified_sources"] == 2
    for key in ("brief", "question_group", "question_ids", "origin", "title", "demand", "fit"):
        assert saved[key] == idea[key]
    assert "edit_hash" not in store.ideas()[0]
    assert saved["edit_hash"] == digest(store.ideas()[0]) != listed["edit_hash"]
    assert store.jobs() == [] and store.tasks() == []
    with store.connection() as db:
        assert db.execute("SELECT COUNT(*) FROM approvals").fetchone()[0] == 0
    assert all(question["state"] == "converted" for question in store.questions())
    chosen = client.post(f"/api/ideas/{idea['id']}/select", json={"expected_hash": saved["edit_hash"]}, headers=headers)
    assert chosen.status_code == 200
    assert chosen.json()["job"]["brief"] == idea["brief"]
    assert chosen.json()["job"]["article"]["url"] == saved["source_url"]


def test_stale_or_selected_source_edit_fails_without_changes(context):
    store, client, headers, idea = context
    first = client.put(f"/api/ideas/{idea['id']}/sources", json=payload(idea), headers=headers)
    assert first.status_code == 200
    snapshot, events = store.ideas(), store.events()
    stale = client.put(f"/api/ideas/{idea['id']}/sources", json=payload(idea, source_urls=["https://example.edu/new"]), headers=headers)
    assert stale.status_code == 409 and store.ideas() == snapshot and store.events() == events
    store.select_idea(idea["id"], "fixture-operator")
    selected = store.ideas()[0]
    snapshot, events = store.ideas(), store.events()
    assert client.put(f"/api/ideas/{idea['id']}/sources", json=payload(selected), headers=headers).status_code == 409
    assert store.ideas() == snapshot and store.events() == events


def test_source_edit_does_not_merge_another_candidate(context):
    store, client, headers, idea = context
    other = store.save_idea({**idea, "source_url": "https://admission.example.edu/transfer"})
    assert other["id"] != idea["id"]
    snapshot, events = store.ideas(), store.events()
    response = client.put(f"/api/ideas/{idea['id']}/sources", json=payload(idea), headers=headers)
    assert response.status_code == 409
    assert store.ideas() == snapshot and store.events() == events


@pytest.mark.parametrize("url", ["http://example.edu/a", "https://localhost/a", "https://127.0.0.1/a", "https://user:password@example.edu/a", "https://example.edu:8080/a", "https://example.edu:invalid/a", "", "https:///missing"])
def test_invalid_source_urls_do_not_raise_count_or_mutate(context, url):
    store, client, headers, idea = context
    snapshot, events = store.ideas(), store.events()
    response = client.put(f"/api/ideas/{idea['id']}/sources", json=payload(idea, source_urls=[url]), headers=headers)
    assert response.status_code in (409, 422)
    assert store.ideas() == snapshot and store.events() == events


def test_sources_require_confirmation_hash_session_and_bounded_list(context):
    store, client, headers, idea = context
    route = f"/api/ideas/{idea['id']}/sources"
    assert client.put(route, json=payload(idea)).status_code == 403
    assert client.put(route, json=payload(idea, operator_verified=False), headers=headers).status_code == 409
    assert client.put(route, json=payload(idea, operator_verified="true"), headers=headers).status_code == 422
    missing = payload(idea)
    del missing["expected_hash"]
    assert client.put(route, json=missing, headers=headers).status_code == 422
    assert client.put(route, json=payload(idea, source_urls=[f"https://example.edu/{n}" for n in range(11)]), headers=headers).status_code == 422
    assert store.ideas() == [idea]


def test_source_edit_keeps_unrelated_policy_block(context):
    store, client, headers, idea = context
    blocked = store.save_idea({**idea, "policy_flags": ["templated_series"]})
    response = client.put(f"/api/ideas/{idea['id']}/sources", json=payload(blocked), headers=headers)
    assert response.status_code == 200
    assert response.json()["blocked"] == ["같은 템플릿 반복 위험(YouTube 비진정성 콘텐츠)"]
    assert client.post(f"/api/ideas/{idea['id']}/select", json={"expected_hash": response.json()["edit_hash"]}, headers=headers).status_code == 409


def test_source_edit_preserves_resource_query_and_does_not_fetch_pages(context, monkeypatch):
    import socket
    from office import feeds
    store, client, headers, idea = context
    def no_network(*args, **kwargs):
        raise AssertionError("출처 등록은 외부 요청이나 DNS 조회를 하지 않습니다")
    monkeypatch.setattr(socket, "getaddrinfo", no_network)
    monkeypatch.setattr(feeds, "fetch_public", no_network)
    urls = ["https://example.edu/guide/?source=2026#section", "https://example.edu/guide/?source=2025#section"]
    response = client.put(f"/api/ideas/{idea['id']}/sources", json=payload(idea, source_urls=urls), headers=headers)
    assert response.status_code == 200
    assert response.json()["source_urls"] == urls and response.json()["source_url"] == urls[0]
    assert response.json()["operator_verified_sources"] == 2 and store.jobs() == []


def test_selection_rejects_unread_source_revision_without_job_or_audit_change(context):
    store, client, headers, idea = context
    route = f"/api/ideas/{idea['id']}/select"
    updated = client.put(f"/api/ideas/{idea['id']}/sources", json=payload(idea), headers=headers).json()
    before, events = store.ideas(), store.events()
    assert client.post(route, json={"expected_hash": digest(idea)}, headers=headers).status_code == 409
    assert store.ideas() == before and store.jobs() == [] and store.events() == events
    assert client.post(route, json={}, headers=headers).status_code == 422
    assert client.post(route, json={"expected_hash": updated["edit_hash"]}, headers=headers).status_code == 200
    assert len(store.ideas()) == 1 and store.ideas()[0]["id"] == idea["id"]


def test_source_edits_with_same_read_hash_have_only_one_winner(context):
    from concurrent.futures import ThreadPoolExecutor
    from threading import Barrier
    from office.ideas import set_idea_sources
    from office.store import WorkflowError
    store, _, _, idea = context
    barrier = Barrier(2)

    def edit(number):
        barrier.wait(timeout=5)
        try:
            return set_idea_sources(store, idea["id"], [f"https://example.edu/{number}"], expected_hash=digest(idea), operator_verified=True)["source_url"]
        except WorkflowError:
            return "conflict"

    with ThreadPoolExecutor(max_workers=2) as pool:
        results = list(pool.map(edit, [1, 2]))
    assert results.count("conflict") == 1
    assert len(store.ideas()) == 1 and store.ideas()[0]["source_url"] in results
    assert len([event for event in store.events() if event["kind"] == "idea_sources_updated"]) == 1


def test_source_edit_and_selection_serialize_without_duplicate_or_unread_selection(context):
    from concurrent.futures import ThreadPoolExecutor
    from threading import Barrier
    from office.ideas import score_idea, select_reviewed_idea, set_idea_sources
    from office.store import WorkflowError
    store, _, _, idea = context
    valid = store.save_idea(score_idea({**idea, "primary_sources": 1}))
    # Same ID, with a valid pre-edit source; no second candidate is introduced.
    current = set_idea_sources(store, valid["id"], ["https://example.edu/old"], expected_hash=digest(valid), operator_verified=True)
    token = current["edit_hash"]
    barrier = Barrier(2)

    def run(action):
        barrier.wait(timeout=5)
        try:
            if action == "edit":
                set_idea_sources(store, idea["id"], ["https://example.edu/new"], expected_hash=token, operator_verified=True)
            else:
                select_reviewed_idea(store, idea["id"], expected_hash=token, actor="fixture-operator")
            return action
        except WorkflowError:
            return "conflict"

    with ThreadPoolExecutor(max_workers=2) as pool:
        results = list(pool.map(run, ["edit", "select"]))
    assert results.count("conflict") == 1
    assert len(store.ideas()) == 1
    final = store.ideas()[0]
    assert final["id"] == idea["id"]
    if "select" in results:
        assert final["state"] == "selected" and final["source_url"] == "https://example.edu/old"
        assert len(store.jobs()) == 1 and store.jobs()[0]["article"]["url"] == final["source_url"]
    else:
        assert final["state"] == "candidate" and final["source_url"] == "https://example.edu/new"
        assert store.jobs() == []


def test_job_creation_failure_rolls_back_selection_job_and_both_events(context, monkeypatch):
    from office.store import WorkflowError
    store, client, headers, idea = context
    ready = client.put(f"/api/ideas/{idea['id']}/sources", json=payload(idea), headers=headers).json()
    ideas_before, events_before = store.ideas(), store.events()
    original = store._event

    def fail_after_job_event(db, kind, data, job_id=None):
        original(db, kind, data, job_id)
        if kind == "job_created":
            raise WorkflowError("fixture job creation failed")

    monkeypatch.setattr(store, "_event", fail_after_job_event)
    response = client.post(f"/api/ideas/{idea['id']}/select", json={"expected_hash": ready["edit_hash"]}, headers=headers)
    assert response.status_code == 409
    assert store.ideas() == ideas_before and store.events() == events_before and store.jobs() == []
    monkeypatch.setattr(store, "_event", original)
    retry = client.post(f"/api/ideas/{idea['id']}/select", json={"expected_hash": ready["edit_hash"]}, headers=headers)
    assert retry.status_code == 200 and len(store.jobs()) == 1
    assert len([event for event in store.events() if event["kind"] == "idea_selected"]) == 1
    assert len([event for event in store.events() if event["kind"] == "job_created"]) == 1


def test_job_helper_failure_after_insert_rolls_back_everything(context, monkeypatch):
    from office.store import WorkflowError
    store, client, headers, idea = context
    ready = client.put(f"/api/ideas/{idea['id']}/sources", json=payload(idea), headers=headers).json()
    ideas_before, events_before = store.ideas(), store.events()
    original = store._create_job

    def fail_after_insert(db, article, brief=None):
        original(db, article, brief)
        raise WorkflowError("fixture failure after helper writes")

    monkeypatch.setattr(store, "_create_job", fail_after_insert)
    response = client.post(f"/api/ideas/{idea['id']}/select", json={"expected_hash": ready["edit_hash"]}, headers=headers)
    assert response.status_code == 409
    assert store.ideas() == ideas_before and store.events() == events_before and store.jobs() == []


def test_selection_reuses_existing_job_without_overwriting_its_content(context):
    store, client, headers, idea = context
    ready = client.put(f"/api/ideas/{idea['id']}/sources", json=payload(idea), headers=headers).json()
    article = {"id": idea["id"], "title": idea["title"], "url": ready["source_url"], "origin": "idea", "evidence": []}
    existing = store.create_job(article, brief=idea["brief"])
    packet = {"title": "기존에 저장한 원고", "body": "보존해야 하는 원고 본문"}
    existing = store.save_source(existing["id"], packet)
    assert store.create_job({**article, "title": "덮어쓰면 안 되는 제목"}) == existing
    before = [event for event in store.events() if event["kind"] == "job_created"]
    response = client.post(f"/api/ideas/{idea['id']}/select", json={"expected_hash": ready["edit_hash"]}, headers=headers)
    assert response.status_code == 200 and response.json()["job"] == existing
    assert store.jobs() == [existing] and len(store.ideas()) == 1
    assert response.json()["idea"]["state"] == "selected"
    assert [event for event in store.events() if event["kind"] == "job_created"] == before
