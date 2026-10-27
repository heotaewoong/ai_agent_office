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


def test_idea_to_packaged_job(context):
    store, client, headers = context
    saved = client.post("/api/ideas", json={"title": "Claude 팀 블로그 자동화", "source_url": "https://example.com/claude-team", "primary_sources": 2, "demand": 70, "fit": 0.9}, headers=headers).json()
    assert saved["score"] > 0 and saved["blocked"] == []
    chosen = client.post(f"/api/ideas/{saved['id']}/select", json={}, headers=headers).json()
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
    assert client.post(f"/api/ideas/{saved['id']}/select", json={}, headers=headers).status_code == 409


def test_idea_without_https_source_url_cannot_be_selected(context):
    _, client, headers = context
    saved = client.post("/api/ideas", json={"title": "URL 없는 기획", "primary_sources": 2, "demand": 70, "fit": 0.9}, headers=headers).json()
    assert saved["blocked"] == []
    assert client.post(f"/api/ideas/{saved['id']}/select", json={}, headers=headers).status_code == 409


def test_snapshot_creates_lesson_that_needs_review(context):
    _, client, headers = context
    for vid, ctr in (("b1", 5.0), ("b2", 6.0)):
        client.post("/api/analytics/snapshots", json={"channel": "youtube_long", "external_id": vid, "period": "7d", "metrics": {"ctr": ctr, "avp": 40}}, headers=headers)
    result = client.post("/api/analytics/snapshots", json={"channel": "youtube_long", "external_id": "vid-a", "period": "7d", "metrics": {"ctr": 2.0, "avp": 55}}, headers=headers).json()
    lesson = result["lessons"][0]
    assert lesson["kind"] == "packaging" and lesson["state"] == "proposed"
    reviewed = client.post(f"/api/lessons/{lesson['id']}/review", json={"decision": "approved"}, headers=headers).json()
    assert reviewed["state"] == "approved"
