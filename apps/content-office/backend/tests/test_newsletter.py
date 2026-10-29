"""뉴스레터 회차: 승인② 원고에서 회차 생성, 사람 승인③, 발송 직전 최신 동의 스냅샷, 수동 발송 기록. 이메일은 회차에 넣지 않는다."""
import json

import pytest
from fastapi.testclient import TestClient

from office.api import create_app
from office.store import WorkflowError
from tests.test_youtube_delivery import released_fixture


def api(store):
    client = TestClient(create_app(store), base_url="http://localhost:8510")
    token = client.get("/api/session").json()["csrf"]
    return client, {"Origin": "http://localhost:3110", "X-Office-CSRF": token}


def lead(client, headers, email, magnet="d30-planner"):
    return client.post("/api/leads", json={"email": email, "magnet_key": magnet, "source": "homepage", "consent_version": "v1", "consent_text": "뉴스레터 수신 동의"}, headers=headers).json()["lead"]


def test_issue_requires_release_approval(tmp_path):
    store, job_id = released_fixture(tmp_path, approve_release=False)
    client, headers = api(store)
    response = client.post(f"/api/jobs/{job_id}/newsletter", json={"issue_key": "2026-11-w1", "subject": None}, headers=headers)
    assert response.status_code == 409 and "승인②" in response.json()["detail"]
    assert client.get("/api/newsletters").json()["issues"] == []


def test_build_issue_snapshots_consent_without_emails(tmp_path):
    store, job_id = released_fixture(tmp_path)
    client, headers = api(store)
    active = lead(client, headers, "active@example.com")
    gone = lead(client, headers, "gone@example.com")
    client.post(f"/api/leads/{gone['id']}/withdraw", json={}, headers=headers)
    response = client.post(f"/api/jobs/{job_id}/newsletter", json={"issue_key": "2026-11-w1", "subject": None}, headers=headers)
    assert response.status_code == 201
    issue = response.json()
    assert issue["issue_key"] == "2026-11-w1" and issue["job_id"] == job_id and issue["state"] == "draft"
    assert issue["subject"] == "업로드 시험" and issue["approval"] is None and issue["sent_at"] is None
    assert issue["recipient_count"] == 1 and len(issue["recipients_hash"]) == 64 and issue["built_at"] and len(issue["hash"]) == 64
    markdown = issue["markdown"]
    assert "업로드 시험" in markdown and "합성 기능 시험입니다." in markdown
    assert "## 오늘 할 일" in markdown and "무료 AI 업무 적용 점검표 받기" in markdown and "[수신거부 링크]" in markdown
    blob = json.dumps(issue, ensure_ascii=False)
    assert "active@example.com" not in blob and "gone@example.com" not in blob and active["id"] not in blob
    duplicate = client.post(f"/api/jobs/{job_id}/newsletter", json={"issue_key": "2026-11-w1", "subject": "다른 제목"}, headers=headers)
    assert duplicate.status_code == 409
    assert client.post(f"/api/jobs/{job_id}/newsletter", json={"issue_key": "bad key!", "subject": None}, headers=headers).status_code == 409
    listing = client.get("/api/newsletters").json()["issues"]
    # 출고 승인② 때 자동으로 만든 초안(job_id-v1)과 방금 만든 회차, 최신순
    assert listing[0]["id"] == issue["id"] and {i["issue_key"] for i in listing} == {"2026-11-w1", f"{job_id}-v1"}
    assert client.get(f"/api/newsletters/{issue['id']}").json()["hash"] == issue["hash"]
    export = client.get(f"/api/newsletters/{issue['id']}/export")
    assert export.status_code == 200 and export.headers["content-type"].startswith("text/markdown") and export.text == markdown
    assert client.get("/api/newsletters/issue_missing").status_code == 409


def test_review_is_human_recorded_and_never_sends(tmp_path):
    store, job_id = released_fixture(tmp_path)
    client, headers = api(store)
    lead(client, headers, "reader@example.com")
    issue = client.post(f"/api/jobs/{job_id}/newsletter", json={"issue_key": "2026-11-w2", "subject": "이번 주 복습"}, headers=headers).json()
    early = client.post(f"/api/newsletters/{issue['id']}/sent", json={}, headers=headers)
    assert early.status_code == 409
    rejected = client.post(f"/api/newsletters/{issue['id']}/review", json={"decision": "reject", "note": "제목 수정"}, headers=headers).json()
    assert rejected["state"] == "rejected" and rejected["approval"]["decision"] == "rejected" and rejected["approval"]["note"] == "제목 수정"
    approved = client.post(f"/api/newsletters/{issue['id']}/review", json={"decision": "approve", "note": None}, headers=headers)
    assert approved.status_code == 200
    body = approved.json()
    assert body["state"] == "approved" and body["sent_at"] is None
    assert body["approval"]["stage"] == "③" and body["approval"]["decision"] == "approved" and body["approval"]["actor"] == "local-operator" and body["approval"]["at"]
    kinds = [e["kind"] for e in store.events(job_id)]
    assert kinds.count("newsletter_reviewed") == 2 and "newsletter_sent_manual" not in kinds
    again = client.post(f"/api/newsletters/{issue['id']}/review", json={"decision": "approve", "note": None}, headers=headers)
    assert again.status_code == 409
    sent = client.post(f"/api/newsletters/{issue['id']}/sent", json={}, headers=headers)
    assert sent.status_code == 200 and sent.json()["state"] == "sent_manual" and sent.json()["sent_at"]
    event = next(e for e in store.events(job_id) if e["kind"] == "newsletter_sent_manual")
    assert event["data"]["recipient_count"] == 1 and event["data"]["issue_key"] == "2026-11-w2"
    assert client.post(f"/api/newsletters/{issue['id']}/sent", json={}, headers=headers).status_code == 409
    assert client.post(f"/api/newsletters/{issue['id']}/review", json={"decision": "reject", "note": None}, headers=headers).status_code == 409
    from office.newsletter import review_issue
    with pytest.raises(WorkflowError):
        review_issue(store, issue["id"], "approve", actor="", note=None)


def test_rebuild_refreshes_consent_and_resets_approval_when_content_changes(tmp_path):
    store, job_id = released_fixture(tmp_path)
    client, headers = api(store)
    first = lead(client, headers, "first@example.com")
    issue = client.post(f"/api/jobs/{job_id}/newsletter", json={"issue_key": "2026-11-w3", "subject": None}, headers=headers).json()
    client.post(f"/api/newsletters/{issue['id']}/review", json={"decision": "approve", "note": None}, headers=headers)
    lead(client, headers, "second@example.com")
    client.post(f"/api/leads/{first['id']}/withdraw", json={}, headers=headers)
    rebuilt = client.post(f"/api/newsletters/{issue['id']}/rebuild", json={}, headers=headers).json()
    assert rebuilt["recipient_count"] == 1 and rebuilt["recipients_hash"] != issue["recipients_hash"]
    assert rebuilt["hash"] == issue["hash"] and rebuilt["state"] == "approved" and rebuilt["approval"]["stage"] == "③"
    client.put(f"/api/jobs/{job_id}/offer", json={"product": "D-30 플래너", "price_krw": 9900, "url": "https://heobrain.store/planner", "note": None}, headers=headers)
    changed = client.post(f"/api/newsletters/{issue['id']}/rebuild", json={}, headers=headers).json()
    assert changed["hash"] != issue["hash"] and changed["state"] == "draft" and changed["approval"] is None
    assert "D-30 플래너" in changed["markdown"] and "9,900원" in changed["markdown"] and "https://heobrain.store/planner" in changed["markdown"]
    assert "newsletter_rebuilt" in [e["kind"] for e in store.events(job_id)]
    assert client.post(f"/api/newsletters/{issue['id']}/sent", json={}, headers=headers).status_code == 409
    store.update_job(job_id, release_approval=None)
    assert client.post(f"/api/newsletters/{issue['id']}/rebuild", json={}, headers=headers).status_code == 409


def test_release_approval_auto_builds_one_draft_issue_without_approving(tmp_path):
    from office.newsletter import issues
    store, job_id = released_fixture(tmp_path)
    drafts = issues(store)
    assert len(drafts) == 1
    auto = drafts[0]
    assert auto["job_id"] == job_id and auto["issue_key"] == f"{job_id}-v1" and auto["state"] == "draft" and auto["approval"] is None
    assert auto["recipient_count"] == 0 and "[수신거부 링크]" in auto["markdown"]
    built = next(e for e in store.events(job_id) if e["kind"] == "newsletter_built")
    assert built["data"]["auto"] is True
    assert "newsletter_reviewed" not in [e["kind"] for e in store.events(job_id)]
    # 같은 제작물을 다시 승인②해도 같은 내용의 회차가 또 생기지 않는다
    job = store.job(job_id)
    store.review_release(job_id, job["manifest"]["hash"], "approved", "op", media_reviewed=True, outputs=["video"])
    assert [i["issue_key"] for i in issues(store)] == [f"{job_id}-v1"]
    # 거절②는 회차를 만들지 않는다
    store2, job2 = released_fixture(tmp_path / "rejected", approve_release=False)
    manifest_hash = store2.job(job2)["manifest"]["hash"]
    store2.review_release(job2, manifest_hash, "rejected", "op", media_reviewed=True, outputs=["video"])
    assert issues(store2) == []


def test_auto_build_failure_never_blocks_release_approval(tmp_path, monkeypatch):
    from office import newsletter
    store, job_id = released_fixture(tmp_path, approve_release=False)

    def broken(*args, **kwargs):
        raise WorkflowError("회차 생성 실패 시뮬레이션")
    monkeypatch.setattr(newsletter, "build_issue", broken)
    job = store.review_release(job_id, store.job(job_id)["manifest"]["hash"], "approved", "op", media_reviewed=True, outputs=["video"])
    assert job["release_approval"]["decision"] == "approved" and job["state"] == "release_approved"
    skipped = next(e for e in store.events(job_id) if e["kind"] == "newsletter_auto_build_skipped")
    assert "시뮬레이션" in skipped["data"]["reason"]
    assert newsletter.issues(store) == []


def test_dashboard_counts_leads_and_newsletters(tmp_path):
    store, job_id = released_fixture(tmp_path)
    client, headers = api(store)
    first = lead(client, headers, "one@example.com")
    lead(client, headers, "two@example.com")
    client.post(f"/api/leads/{first['id']}/withdraw", json={}, headers=headers)
    auto_issue = client.get("/api/newsletters").json()["issues"][0]
    client.post(f"/api/jobs/{job_id}/newsletter", json={"issue_key": "2026-11-w9", "subject": None}, headers=headers)
    client.post(f"/api/newsletters/{auto_issue['id']}/review", json={"decision": "approve", "note": None}, headers=headers)
    dashboard = client.get("/api/dashboard").json()
    assert dashboard["leads"] == {"consented": 1}
    assert dashboard["newsletters"] == {"draft": 1, "approved": 1}
    assert "one@example.com" not in json.dumps(dashboard) and "two@example.com" not in json.dumps(dashboard)
