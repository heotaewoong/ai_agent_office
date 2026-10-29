import pytest
from fastapi.testclient import TestClient
from office.api import create_app
from office.store import Store


@pytest.fixture
def context(tmp_path):
    store = Store(tmp_path)
    client = TestClient(create_app(store), base_url="http://localhost:8510")
    token = client.get("/api/session").json()["csrf"]
    return store, client, {"Origin": "http://localhost:3110", "X-Office-CSRF": token}


def read_idea(client, idea_id):
    return {"expected_hash": next(card["edit_hash"] for card in client.get("/api/ideas").json()["ideas"] if card["id"] == idea_id)}


def test_idea_to_packaged_job(context):
    store, client, headers = context
    saved = client.post("/api/ideas", json={"title": "Claude 팀 블로그 자동화", "source_url": "https://example.com/claude-team", "primary_sources": 2, "demand": 70, "fit": 0.9}, headers=headers).json()
    assert saved["score"] > 0 and saved["blocked"] == []
    chosen = client.post(f"/api/ideas/{saved['id']}/select", json=read_idea(client, saved["id"]), headers=headers).json()
    job_id = chosen["job"]["id"]
    assert chosen["job"]["article"]["origin"] == "idea"
    bad = client.post(f"/api/jobs/{job_id}/packaging", json={"titles": ["하나"], "thumbnails": [], "hook": "", "logline": "", "reasons": []}, headers=headers)
    assert bad.status_code == 409
    good = {"titles": ["Claude 팀으로 블로그 자동화", "AI 팀 블로그", "자동화 3단계"], "thumbnails": [{"text": "AI 팀", "visual": "화면"}] * 3,
            "hook": "Claude 팀으로 블로그를 끝낸 결과부터 봅니다", "logline": "한 명이 팀처럼 일하는 법", "reasons": ["수요", "실제 화면"]}
    assert client.post(f"/api/jobs/{job_id}/packaging", json=good, headers=headers).status_code == 200
    assert store.job(job_id)["packaging"]["packaging_hash"]


def test_blocked_idea_cannot_be_selected(context):
    _, client, headers = context
    saved = client.post("/api/ideas", json={"title": "출처 없는 소문"}, headers=headers).json()
    assert saved["blocked"] == ["1차 출처 없음"]
    assert client.post(f"/api/ideas/{saved['id']}/select", json=read_idea(client, saved["id"]), headers=headers).status_code == 409


def test_idea_without_https_source_url_cannot_be_selected(context):
    _, client, headers = context
    saved = client.post("/api/ideas", json={"title": "URL 없는 기획", "primary_sources": 2, "demand": 70, "fit": 0.9}, headers=headers).json()
    assert saved["blocked"] == []
    assert client.post(f"/api/ideas/{saved['id']}/select", json=read_idea(client, saved["id"]), headers=headers).status_code == 409


def test_snapshot_creates_lesson_that_needs_review(context):
    _, client, headers = context
    for vid, ctr in (("b1", 5.0), ("b2", 6.0)):
        client.post("/api/analytics/snapshots", json={"channel": "youtube_long", "external_id": vid, "period": "7d", "metrics": {"ctr": ctr, "avp": 40}}, headers=headers)
    result = client.post("/api/analytics/snapshots", json={"channel": "youtube_long", "external_id": "vid-a", "period": "7d", "metrics": {"ctr": 2.0, "avp": 55}}, headers=headers).json()
    lesson = result["lessons"][0]
    assert lesson["kind"] == "packaging" and lesson["state"] == "proposed"
    reviewed = client.post(f"/api/lessons/{lesson['id']}/review", json={"decision": "approved"}, headers=headers).json()
    assert reviewed["state"] == "approved"


def packaged_idea_job(store, client, headers):
    saved = client.post("/api/ideas", json={"title": "Claude 팀 블로그 자동화", "source_url": "https://example.com/claude-team", "primary_sources": 2, "demand": 70, "fit": 0.9}, headers=headers).json()
    return client.post(f"/api/ideas/{saved['id']}/select", json=read_idea(client, saved["id"]), headers=headers).json()["job"]["id"]


GOOD_PACKAGING = {"titles": ["Claude 팀으로 블로그 자동화", "AI 팀 블로그", "자동화 3단계"], "thumbnails": [{"text": "AI 팀", "visual": "화면"}] * 3,
                  "hook": "Claude 팀으로 블로그를 끝낸 결과부터 봅니다", "logline": "한 명이 팀처럼 일하는 법", "reasons": ["수요", "실제 화면"]}


def test_draft_requires_packaging_for_idea_job(context):
    store, client, headers = context
    job_id = packaged_idea_job(store, client, headers)
    assert client.post(f"/api/jobs/{job_id}/draft", headers=headers).status_code == 409
    assert store.tasks(job_id) == []
    assert client.post(f"/api/jobs/{job_id}/packaging", json=GOOD_PACKAGING, headers=headers).status_code == 200
    assert client.post(f"/api/jobs/{job_id}/draft", headers=headers).status_code == 202


def test_new_mutating_routes_require_csrf(context):
    store, client, headers = context
    origin_only = {"Origin": headers["Origin"]}
    assert client.post("/api/ideas", json={"title": "CSRF 없는 기획"}, headers=origin_only).status_code == 403
    assert store.ideas() == []
    for vid, ctr in (("b1", 5.0), ("b2", 6.0)):
        client.post("/api/analytics/snapshots", json={"channel": "youtube_long", "external_id": vid, "period": "7d", "metrics": {"ctr": ctr, "avp": 40}}, headers=headers)
    lesson = client.post("/api/analytics/snapshots", json={"channel": "youtube_long", "external_id": "vid-a", "period": "7d", "metrics": {"ctr": 2.0, "avp": 55}}, headers=headers).json()["lessons"][0]
    assert client.post(f"/api/lessons/{lesson['id']}/review", json={"decision": "approved"}, headers=origin_only).status_code == 403
    assert [item["state"] for item in store.lessons() if item["id"] == lesson["id"]] == ["proposed"]


def test_invalid_packaging_and_snapshot_inputs_return_422(context):
    store, client, headers = context
    job_id = packaged_idea_job(store, client, headers)
    bad = {**GOOD_PACKAGING, "thumbnails": [{"text": 5, "visual": "x"}] * 3}
    assert client.post(f"/api/jobs/{job_id}/packaging", json=bad, headers=headers).status_code == 422
    assert not store.job(job_id).get("packaging")
    body = '{"channel":"shorts","external_id":"s","period":"24h","metrics":{"views":NaN}}'
    nan = client.post("/api/analytics/snapshots", content=body, headers={**headers, "Content-Type": "application/json"})
    assert nan.status_code == 422
    assert store.snapshots() == []
    assert client.post("/api/ideas", json={"title": "긴 URL", "source_url": "https://e.com/" + "a" * 2000}, headers=headers).status_code == 422
    assert client.post("/api/ideas", json={"title": "큰 조회수", "views": 10**13}, headers=headers).status_code == 422


def test_studio_csv_upload_saves_snapshots_and_counts(context):
    store, client, headers = context
    csv = "Content,Views,Impressions click-through rate (%),Average percentage viewed (%)\nvid1,1000,5.0%,40%\nvid2,500,2.0%,45%\nTotal,1500,,\n"
    r = client.post("/api/analytics/studio-csv", json={"channel": "youtube_long", "period": "7d", "csv": csv}, headers=headers)
    assert r.status_code == 200
    body = r.json()
    assert [s["external_id"] for s in body["snapshots"]] == ["vid1", "vid2"]
    assert len(store.snapshots("youtube_long")) == 2


def test_studio_csv_without_rows_is_409(context):
    _, client, headers = context
    r = client.post("/api/analytics/studio-csv", json={"channel": "shorts", "period": "24h", "csv": "Content,Views\nTotal,1\n"}, headers=headers)
    assert r.status_code == 409


def test_packaging_with_blank_titles_is_409(context):
    store, client, headers = context
    saved = client.post("/api/ideas", json={"title": "빈 제목 기획", "source_url": "https://example.com/blank", "primary_sources": 2, "demand": 70, "fit": 0.9}, headers=headers).json()
    job_id = client.post(f"/api/ideas/{saved['id']}/select", json=read_idea(client, saved["id"]), headers=headers).json()["job"]["id"]
    body = {"titles": ["", "", ""], "thumbnails": [{"text": "AI 팀", "visual": "화면"}] * 3, "hook": "블로그를 끝낸 결과", "logline": "한 줄", "reasons": ["수요", "화면"]}
    assert client.post(f"/api/jobs/{job_id}/packaging", json=body, headers=headers).status_code == 409


def test_studio_csv_duplicate_external_id_keeps_last_row(context):
    store, client, headers = context
    csv = "Content,Views\nvid1,100\nvid1,900\nTotal,1000\n"
    r = client.post("/api/analytics/studio-csv", json={"channel": "youtube_long", "period": "7d", "csv": csv}, headers=headers)
    assert r.status_code == 200
    assert [s["external_id"] for s in r.json()["snapshots"]] == ["vid1"]
    assert len(store.snapshots("youtube_long")) == 1
