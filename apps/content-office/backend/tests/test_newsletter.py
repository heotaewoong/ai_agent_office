"""뉴스레터 회차: 현재 원고·출고·동의에 결속된 사람 승인③과 수동 발송 기록. 이메일은 회차에 넣지 않는다."""
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
    return client.post("/api/leads", json={"email": email, "magnet_key": magnet, "source": "homepage", "consent_version": "v1", "consent_text": "뉴스레터 수신 동의", "consent_purpose": "newsletter"}, headers=headers).json()["lead"]


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
    fetched = client.get(f"/api/newsletters/{issue['id']}").json()
    assert fetched["hash"] == issue["hash"]
    assert len(issue["review_hash"]) == 64 and fetched["review_hash"] == issue["review_hash"] == listing[0]["review_hash"]
    export = client.get(f"/api/newsletters/{issue['id']}/export")
    assert export.status_code == 200 and export.headers["content-type"].startswith("text/markdown") and export.text == markdown
    assert client.get("/api/newsletters/issue_missing").status_code == 409


def test_review_is_human_recorded_and_never_sends(tmp_path):
    store, job_id = released_fixture(tmp_path)
    client, headers = api(store)
    lead(client, headers, "reader@example.com")
    issue = client.post(f"/api/jobs/{job_id}/newsletter", json={"issue_key": "2026-11-w2", "subject": "이번 주 복습"}, headers=headers).json()
    early = client.post(f"/api/newsletters/{issue['id']}/sent", json={"expected_hash": issue["review_hash"]}, headers=headers)
    assert early.status_code == 409
    rejected = client.post(f"/api/newsletters/{issue['id']}/review", json={"decision": "reject", "expected_hash": issue["review_hash"], "note": "제목 수정"}, headers=headers).json()
    assert rejected["state"] == "rejected" and rejected["approval"]["decision"] == "rejected" and rejected["approval"]["note"] == "제목 수정"
    approved = client.post(f"/api/newsletters/{issue['id']}/review", json={"decision": "approve", "expected_hash": issue["review_hash"], "note": None}, headers=headers)
    assert approved.status_code == 200
    body = approved.json()
    assert body["state"] == "approved" and body["sent_at"] is None
    assert body["approval"]["stage"] == "③" and body["approval"]["decision"] == "approved" and body["approval"]["actor"] == "local-operator" and body["approval"]["at"]
    assert body["approval"]["version"] == issue["hash"]
    kinds = [e["kind"] for e in store.events(job_id)]
    assert kinds.count("newsletter_reviewed") == 2 and "newsletter_sent_manual" not in kinds
    again = client.post(f"/api/newsletters/{issue['id']}/review", json={"decision": "approve", "expected_hash": issue["review_hash"], "note": None}, headers=headers)
    assert again.status_code == 409
    sent = client.post(f"/api/newsletters/{issue['id']}/sent", json={"expected_hash": issue["review_hash"]}, headers=headers)
    assert sent.status_code == 200 and sent.json()["state"] == "sent_manual" and sent.json()["sent_at"]
    event = next(e for e in store.events(job_id) if e["kind"] == "newsletter_sent_manual")
    assert event["data"]["recipient_count"] == 1 and event["data"]["issue_key"] == "2026-11-w2"
    assert client.post(f"/api/newsletters/{issue['id']}/sent", json={"expected_hash": issue["review_hash"]}, headers=headers).status_code == 409
    assert client.post(f"/api/newsletters/{issue['id']}/review", json={"decision": "reject", "expected_hash": issue["review_hash"], "note": None}, headers=headers).status_code == 409
    from office.newsletter import review_issue
    with pytest.raises(WorkflowError):
        review_issue(store, issue["id"], "approve", expected_hash=issue["review_hash"], actor="", note=None)


def test_rebuild_refreshes_consent_and_resets_approval_when_content_changes(tmp_path):
    store, job_id = released_fixture(tmp_path)
    client, headers = api(store)
    first = lead(client, headers, "first@example.com")
    issue = client.post(f"/api/jobs/{job_id}/newsletter", json={"issue_key": "2026-11-w3", "subject": None}, headers=headers).json()
    client.post(f"/api/newsletters/{issue['id']}/review", json={"decision": "approve", "expected_hash": issue["review_hash"], "note": None}, headers=headers)
    lead(client, headers, "second@example.com")
    client.post(f"/api/leads/{first['id']}/withdraw", json={}, headers=headers)
    rebuilt = client.post(f"/api/newsletters/{issue['id']}/rebuild", json={}, headers=headers).json()
    assert rebuilt["recipient_count"] == 1 and rebuilt["recipients_hash"] != issue["recipients_hash"]
    assert rebuilt["hash"] == issue["hash"] and rebuilt["state"] == "draft" and rebuilt["approval"] is None
    client.put(f"/api/jobs/{job_id}/offer", json={"expected_offer_hash": None, "product": "D-30 플래너", "price_krw": 9900, "url": "https://heobrain.kr/planner", "note": None}, headers=headers)
    from tests.test_offer import reapprove_campaign_fixture
    reapprove_campaign_fixture(store, job_id)
    changed = client.post(f"/api/newsletters/{issue['id']}/rebuild", json={}, headers=headers).json()
    assert changed["hash"] != issue["hash"] and changed["state"] == "draft" and changed["approval"] is None
    assert "D-30 플래너" in changed["markdown"] and "9,900원" in changed["markdown"] and "https://heobrain.kr/planner" in changed["markdown"]
    assert "newsletter_rebuilt" in [e["kind"] for e in store.events(job_id)]
    assert client.post(f"/api/newsletters/{issue['id']}/sent", json={"expected_hash": issue["review_hash"]}, headers=headers).status_code == 409
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
    auto_issue = client.post(f"/api/newsletters/{auto_issue['id']}/rebuild", json={}, headers=headers).json()
    client.post(f"/api/jobs/{job_id}/newsletter", json={"issue_key": "2026-11-w9", "subject": None}, headers=headers)
    client.post(f"/api/newsletters/{auto_issue['id']}/review", json={"decision": "approve", "expected_hash": auto_issue["review_hash"], "note": None}, headers=headers)
    dashboard = client.get("/api/dashboard").json()
    assert dashboard["leads"] == {"consented": 1}
    assert dashboard["newsletters"] == {"draft": 1, "approved": 1}
    assert "one@example.com" not in json.dumps(dashboard) and "two@example.com" not in json.dumps(dashboard)


@pytest.mark.parametrize("change", ["content", "recipients"])
@pytest.mark.parametrize("decision", ["approve", "reject"])
def test_review_rejects_stale_preview(tmp_path, change, decision):
    store, job_id = released_fixture(tmp_path)
    client, headers = api(store)
    issue = client.post(f"/api/jobs/{job_id}/newsletter", json={"issue_key": "stale-preview", "subject": None}, headers=headers).json()
    viewed_hash = issue["review_hash"]
    if change == "content":
        client.put(f"/api/jobs/{job_id}/offer", json={"expected_offer_hash": None, "product": "새 자료", "price_krw": 9900, "url": "https://heobrain.kr/new", "note": None}, headers=headers)
    else:
        lead(client, headers, "new-reader@example.com")
    if change == "content":
        from tests.test_offer import reapprove_campaign_fixture
        reapprove_campaign_fixture(store, job_id)
    rebuilt = client.post(f"/api/newsletters/{issue['id']}/rebuild", json={}, headers=headers).json()
    if change == "content":
        assert rebuilt["hash"] != issue["hash"]
    else:
        assert rebuilt["recipients_hash"] != issue["recipients_hash"]
    assert rebuilt["review_hash"] != viewed_hash
    response = client.post(f"/api/newsletters/{issue['id']}/review", json={"decision": decision, "expected_hash": viewed_hash, "note": None}, headers=headers)
    assert response.status_code == 409
    current = client.get(f"/api/newsletters/{issue['id']}").json()
    assert current["state"] == "draft" and current["approval"] is None
    assert not [event for event in store.events(job_id) if event["kind"] == "newsletter_reviewed"]


@pytest.mark.parametrize("expected", [None, "short", "g" * 64])
def test_review_requires_valid_preview_hash(tmp_path, expected):
    store, job_id = released_fixture(tmp_path)
    client, headers = api(store)
    issue = client.get("/api/newsletters").json()["issues"][0]
    payload = {"decision": "approve", "note": None}
    if expected is not None:
        payload["expected_hash"] = expected
    response = client.post(f"/api/newsletters/{issue['id']}/review", json=payload, headers=headers)
    assert response.status_code == 422
    assert client.get(f"/api/newsletters/{issue['id']}").json()["approval"] is None
    assert not [event for event in store.events(job_id) if event["kind"] == "newsletter_reviewed"]


def test_review_token_cannot_be_reused_for_another_issue(tmp_path):
    store, job_id = released_fixture(tmp_path)
    client, headers = api(store)
    first = client.post(f"/api/jobs/{job_id}/newsletter", json={"issue_key": "first", "subject": None}, headers=headers).json()
    second = client.post(f"/api/jobs/{job_id}/newsletter", json={"issue_key": "second", "subject": None}, headers=headers).json()
    assert first["hash"] == second["hash"] and first["recipients_hash"] == second["recipients_hash"]
    assert first["review_hash"] != second["review_hash"]
    response = client.post(f"/api/newsletters/{second['id']}/review", json={"decision": "approve", "expected_hash": first["review_hash"]}, headers=headers)
    assert response.status_code == 409
    assert client.get(f"/api/newsletters/{second['id']}").json()["approval"] is None


def test_unchanged_rebuild_preserves_preview_hash_and_content_approval_semantics(tmp_path):
    store, job_id = released_fixture(tmp_path)
    client, headers = api(store)
    issue = client.get("/api/newsletters").json()["issues"][0]
    rebuilt = client.post(f"/api/newsletters/{issue['id']}/rebuild", json={}, headers=headers).json()
    assert rebuilt["review_hash"] == issue["review_hash"]
    approved = client.post(f"/api/newsletters/{issue['id']}/review", json={"decision": "approve", "expected_hash": rebuilt["review_hash"]}, headers=headers)
    assert approved.status_code == 200
    assert approved.json()["approval"]["version"] == issue["hash"]
    unchanged = client.post(f"/api/newsletters/{issue['id']}/rebuild", json={}, headers=headers).json()
    assert unchanged["state"] == "approved" and unchanged["approval"] == approved.json()["approval"]


def test_review_compare_and_approval_remain_atomic_during_rebuild(tmp_path, monkeypatch):
    from contextlib import contextmanager
    from threading import Event, Thread, current_thread
    from office import newsletter

    store, job_id = released_fixture(tmp_path)
    issue = newsletter.issues(store)[0]
    store.set_offer(job_id, {"product": "새 자료", "price_krw": 9900, "url": "https://heobrain.kr/new", "note": None}, "op")
    from tests.test_offer import reapprove_campaign_fixture
    reapprove_campaign_fixture(store, job_id)
    held, release, waiting, acquired = (Event() for _ in range(4))
    original_connection, original_released = store.connection, newsletter._released_job
    errors = []

    @contextmanager
    def observed_connection(transaction=False):
        rebuilding = current_thread().name == "newsletter-rebuild" and transaction
        if rebuilding:
            waiting.set()
        with original_connection(transaction=transaction) as db:
            if rebuilding:
                acquired.set()
            yield db

    def paused_release(db, current_store, current_job):
        if current_thread().name == "newsletter-review":
            held.set()
            assert release.wait(5), "검토 트랜잭션을 풀지 못했습니다"
        return original_released(db, current_store, current_job)

    def run(function):
        try:
            function()
        except BaseException as error:
            errors.append(error)

    monkeypatch.setattr(store, "connection", observed_connection)
    monkeypatch.setattr(newsletter, "_released_job", paused_release)
    reviewer = Thread(name="newsletter-review", target=run, args=(lambda: newsletter.review_issue(store, issue["id"], "approve", expected_hash=issue["review_hash"], actor="op"),))
    rebuilder = Thread(name="newsletter-rebuild", target=run, args=(lambda: newsletter.rebuild_issue(store, issue["id"], actor="op"),))
    reviewer.start()
    try:
        assert held.wait(5), "검토 트랜잭션을 시작하지 못했습니다"
        rebuilder.start()
        assert waiting.wait(5), "재작성 트랜잭션이 대기하지 않았습니다"
        assert not acquired.is_set()
    finally:
        release.set()
        reviewer.join(5)
        if rebuilder.ident is not None:
            rebuilder.join(5)
    assert not reviewer.is_alive() and not rebuilder.is_alive()
    assert len(errors) == 1 and isinstance(errors[0], WorkflowError) and "판본" in str(errors[0])
    current = newsletter.issue(store, issue["id"])
    assert current["hash"] != issue["hash"] and current["state"] == "draft" and current["approval"] is None
    assert not [event for event in store.events(job_id) if event["kind"] == "newsletter_reviewed"]


@pytest.mark.parametrize("action", ["approve", "reject", "export", "sent"])
@pytest.mark.parametrize("change", ["source", "offer", "release", "release_rejected", "source_rejected", "file", "file_missing", "consent_text", "consent_version", "consent_granted", "consent_purpose", "email", "withdrawn", "new_recipient"])
def test_current_chain_is_required_for_review_export_and_sent(tmp_path, action, change):
    from office import leads, newsletter
    from office.store import canonical, digest
    from tests.test_offer import reapprove_campaign_fixture

    store, job_id = released_fixture(tmp_path)
    reader, _ = leads.register_lead(store, email="reader@example.com", magnet_key="one", source="homepage", consent_version="v1", consent_text="뉴스레터 수신 동의", consent_purpose="newsletter")
    current = newsletter.build_issue(store, job_id, issue_key="current-chain", subject=None, actor="op")
    if action == "sent":
        current = newsletter.review_issue(store, current["id"], "approve", expected_hash=current["review_hash"], actor="op")
    approvals_before = len([event for event in store.events(job_id) if event["kind"] == "newsletter_reviewed"])
    job = store.job(job_id)
    if change == "source":
        packet = {**job["source_packet"], "body": "새 원고 B입니다."}
        store.save_source(job_id, packet)
        reapprove_campaign_fixture(store, job_id)
    elif change == "offer":
        store.set_offer(job_id, {"product": "새 상품 B", "price_krw": 9900, "url": "https://heobrain.kr/new"}, "op")
        reapprove_campaign_fixture(store, job_id)
    elif change == "release":
        manifest = {**job["manifest"], "note": "새 출고 판본 B"}
        manifest["hash"] = digest({key: value for key, value in manifest.items() if key != "hash"})
        store.save_manifest_if_current(job_id, job["source_hash"], job["selections"], manifest)
        store.review_release(job_id, manifest["hash"], "approved", "op", media_reviewed=True, outputs=["video"])
    elif change == "release_rejected":
        store.review_release(job_id, job["manifest"]["hash"], "rejected", "op", outputs=["video"])
    elif change == "source_rejected":
        store.review_source(job_id, job["source_hash"], "rejected", "op")
    elif change in ("file", "file_missing"):
        path = store.artifacts / job["manifest"]["files"][0]["path"]
        if change == "file":
            path.write_bytes(b"changed after release")
        else:
            path.unlink()
    elif change == "withdrawn":
        leads.withdraw_lead(store, reader["id"])
    elif change == "new_recipient":
        leads.register_lead(store, email="new@example.com", magnet_key="two", source="homepage", consent_version="v1", consent_text="뉴스레터 수신 동의", consent_purpose="newsletter")
    else:
        with store.connection(transaction=True) as db:
            row = db.execute("SELECT data FROM leads WHERE id=?", (reader["id"],)).fetchone()
            data = json.loads(row["data"])
            if change == "email":
                db.execute("UPDATE leads SET email=? WHERE id=?", ("changed@example.com", reader["id"]))
            else:
                if change == "consent_text":
                    data["consent_text"] = "자료 전달에만 동의합니다"
                elif change == "consent_version":
                    data["consent"]["version"] = "v2"
                elif change == "consent_purpose":
                    data["consent"]["purpose"] = "lead_magnet_delivery"
                else:
                    data["consent"]["granted_at"] = "2026-10-30T01:00:00+00:00"
                db.execute("UPDATE leads SET data=? WHERE id=?", (canonical(data), reader["id"]))
    client, headers = api(store)
    if action == "export":
        response = client.get(f"/api/newsletters/{current['id']}/export")
    elif action == "sent":
        response = client.post(f"/api/newsletters/{current['id']}/sent", json={"expected_hash": current["review_hash"]}, headers=headers)
    else:
        response = client.post(f"/api/newsletters/{current['id']}/review", json={"decision": action, "expected_hash": current["review_hash"]}, headers=headers)
    assert response.status_code == 409, response.text
    saved = newsletter.issue(store, current["id"])
    assert saved["state"] == current["state"] and saved["approval"] == current["approval"] and saved["sent_at"] is None
    assert saved["recipients_hash"] == current["recipients_hash"] and saved["recipient_count"] == current["recipient_count"]
    assert len([event for event in store.events(job_id) if event["kind"] == "newsletter_reviewed"]) == approvals_before
    assert not [event for event in store.events(job_id) if event["kind"] == "newsletter_sent_manual"]


@pytest.mark.parametrize("action", ["approve", "reject", "export", "sent"])
def test_coupon_expiry_blocks_review_export_and_sent(tmp_path, monkeypatch, action):
    from datetime import datetime, timedelta, timezone
    from office import newsletter, offers
    from tests.test_offer import coupon_offer, reapprove_campaign_fixture

    store, job_id = released_fixture(tmp_path)
    future = datetime.now(timezone.utc) + timedelta(days=1)
    store.set_offer(job_id, coupon_offer(code="SAVE10", discount_percent=10, expires_at=future.isoformat(), terms="합성 시험", verified=True), "op")
    reapprove_campaign_fixture(store, job_id)
    current = newsletter.build_issue(store, job_id, issue_key="expiry", subject=None, actor="op")
    if action == "sent":
        current = newsletter.review_issue(store, current["id"], "approve", expected_hash=current["review_hash"], actor="op")

    class AfterExpiry(datetime):
        @classmethod
        def now(cls, tz=None):
            return future + timedelta(seconds=1)

    monkeypatch.setattr(offers, "datetime", AfterExpiry)
    client, headers = api(store)
    if action == "export":
        response = client.get(f"/api/newsletters/{current['id']}/export")
    elif action == "sent":
        response = client.post(f"/api/newsletters/{current['id']}/sent", json={"expected_hash": current["review_hash"]}, headers=headers)
    else:
        response = client.post(f"/api/newsletters/{current['id']}/review", json={"decision": action, "expected_hash": current["review_hash"]}, headers=headers)
    assert response.status_code == 409 and "기간" in response.json()["detail"]
    assert newsletter.issue(store, current["id"])["sent_at"] is None


def test_withdrawal_requires_rebuild_and_explicit_reapproval_without_ledger_migration(tmp_path):
    from office import leads, newsletter

    store, job_id = released_fixture(tmp_path)
    reader, _ = leads.register_lead(store, email="reader@example.com", magnet_key="one", source="homepage", consent_version="v1", consent_text="뉴스레터 수신 동의", consent_purpose="newsletter")
    current = newsletter.build_issue(store, job_id, issue_key="withdrawal", subject=None, actor="op")
    approved = newsletter.review_issue(store, current["id"], "approve", expected_hash=current["review_hash"], actor="human")
    leads.withdraw_lead(store, reader["id"])
    with pytest.raises(WorkflowError, match="동의"):
        newsletter.mark_sent(store, current["id"], expected_hash=current["review_hash"], actor="op")
    assert newsletter.issue(store, current["id"]) == approved
    rebuilt = newsletter.rebuild_issue(store, current["id"], actor="op")
    assert rebuilt["recipient_count"] == 0 and rebuilt["state"] == "draft" and rebuilt["approval"] is None
    with store.connection() as db:
        reviews = db.execute("SELECT * FROM approvals WHERE kind='newsletter'").fetchall()
        assert len(reviews) == 1 and reviews[0]["actor"] == "human"
    fresh = newsletter.review_issue(store, current["id"], "approve", expected_hash=rebuilt["review_hash"], actor="human")
    sent = newsletter.mark_sent(store, current["id"], expected_hash=fresh["review_hash"], actor="op")
    assert sent["recipient_count"] == 0 and sent["recipients_hash"] == fresh["recipients_hash"] and sent["state"] == "sent_manual"


def test_rejected_issue_cannot_export_or_mark_sent(tmp_path):
    from office import newsletter

    store, job_id = released_fixture(tmp_path)
    current = newsletter.issues(store)[0]
    rejected = newsletter.review_issue(store, current["id"], "reject", expected_hash=current["review_hash"], actor="human")
    client, headers = api(store)
    assert client.get(f"/api/newsletters/{current['id']}/export").status_code == 409
    assert client.post(f"/api/newsletters/{current['id']}/sent", json={"expected_hash": current["review_hash"]}, headers=headers).status_code == 409
    assert newsletter.issue(store, current["id"]) == rejected


def test_legacy_snapshot_and_approval_are_readable_but_need_rebuild_and_reapproval(tmp_path):
    from office import newsletter
    from office.store import canonical, digest

    store, job_id = released_fixture(tmp_path)
    current = newsletter.issues(store)[0]
    legacy = {key: value for key, value in current.items() if key not in ("id", "issue_key", "job_id", "state", "created_at", "updated_at", "review_hash", "release_outputs")}
    legacy["recipients_hash"] = digest([])
    legacy["hash"] = digest({key: legacy[key] for key in ("subject", "markdown", "source_hash", "release_version")})
    legacy["approval"] = {"stage": "③", "decision": "approved", "actor": "legacy-human", "version": legacy["hash"]}
    with store.connection(transaction=True) as db:
        db.execute("UPDATE newsletter_issues SET state='approved',data=? WHERE id=?", (canonical(legacy), current["id"]))
    before = newsletter.issue(store, current["id"])
    assert before["approval"]["actor"] == "legacy-human"
    with pytest.raises(WorkflowError):
        newsletter.mark_sent(store, current["id"], expected_hash=before["review_hash"], actor="op")
    with pytest.raises(WorkflowError):
        newsletter.export_issue(store, current["id"])
    assert newsletter.issue(store, current["id"]) == before
    rebuilt = newsletter.rebuild_issue(store, current["id"], actor="op")
    assert rebuilt["state"] == "draft" and rebuilt["approval"] is None and rebuilt["release_outputs"] == ["video"]


@pytest.mark.parametrize("change", ["content", "recipients"])
def test_sent_requires_the_exact_approved_issue_seen_by_the_operator(tmp_path, change):
    from office import newsletter
    from tests.test_offer import reapprove_campaign_fixture
    store, job_id = released_fixture(tmp_path)
    client, headers = api(store)
    first = newsletter.issues(store)[0]
    viewed_a = newsletter.review_issue(store, first["id"], "approve", expected_hash=first["review_hash"], actor="human-a")
    if change == "content":
        store.set_offer(job_id, {"product": "새 상품 B", "price_krw": 9900, "url": "https://heobrain.kr/new"}, "human-b")
        reapprove_campaign_fixture(store, job_id)
    else:
        lead(client, headers, "new-recipient@example.com")
    rebuilt = newsletter.rebuild_issue(store, first["id"], actor="human-b")
    current_b = newsletter.review_issue(store, first["id"], "approve", expected_hash=rebuilt["review_hash"], actor="human-b")
    assert current_b["review_hash"] != viewed_a["review_hash"]
    stale = client.post(f"/api/newsletters/{first['id']}/sent", json={"expected_hash": viewed_a["review_hash"]}, headers=headers)
    assert stale.status_code == 409 and "변경" in stale.json()["detail"]
    assert newsletter.issue(store, first["id"]) == current_b
    assert not [event for event in store.events(job_id) if event["kind"] == "newsletter_sent_manual"]
    sent = client.post(f"/api/newsletters/{first['id']}/sent", json={"expected_hash": current_b["review_hash"]}, headers=headers)
    assert sent.status_code == 200 and sent.json()["hash"] == current_b["hash"] and sent.json()["state"] == "sent_manual"


@pytest.mark.parametrize("payload", [{}, {"expected_hash": None}, {"expected_hash": "short"}, {"expected_hash": "g" * 64}])
def test_sent_requires_a_valid_preview_token_before_any_state_or_event_changes(tmp_path, payload):
    from office import newsletter
    store, job_id = released_fixture(tmp_path)
    client, headers = api(store)
    first = newsletter.issues(store)[0]
    approved = newsletter.review_issue(store, first["id"], "approve", expected_hash=first["review_hash"], actor="human")
    events = store.events(job_id)
    response = client.post(f"/api/newsletters/{first['id']}/sent", json=payload, headers=headers)
    assert response.status_code == 422
    assert newsletter.issue(store, first["id"]) == approved and store.events(job_id) == events


def test_sent_token_cannot_be_reused_for_another_approved_issue(tmp_path):
    from office import newsletter
    store, job_id = released_fixture(tmp_path)
    client, headers = api(store)
    first = newsletter.issues(store)[0]
    second = newsletter.build_issue(store, job_id, issue_key="another-issue", subject=None, actor="human")
    approved_a = newsletter.review_issue(store, first["id"], "approve", expected_hash=first["review_hash"], actor="human")
    approved_b = newsletter.review_issue(store, second["id"], "approve", expected_hash=second["review_hash"], actor="human")
    assert approved_a["hash"] == approved_b["hash"] and approved_a["review_hash"] != approved_b["review_hash"]
    response = client.post(f"/api/newsletters/{second['id']}/sent", json={"expected_hash": approved_a["review_hash"]}, headers=headers)
    assert response.status_code == 409 and newsletter.issue(store, second["id"]) == approved_b


def test_new_explicit_newsletter_grant_changes_snapshot_and_requires_new_issue_approval(tmp_path):
    from office import leads, newsletter
    store, job_id = released_fixture(tmp_path)
    reader, _ = leads.register_lead(store, email="reader@example.com", magnet_key="same-material", source="homepage",
                                    consent_version="delivery-v1", consent_text="자료 전달에 동의합니다", consent_purpose="lead_magnet_delivery")
    current = newsletter.build_issue(store, job_id, issue_key="purpose-bound", subject=None, actor="human")
    assert current["recipient_count"] == 0
    approved = newsletter.review_issue(store, current["id"], "approve", expected_hash=current["review_hash"], actor="human")
    changed, created = leads.register_lead(store, email="reader@example.com", magnet_key="same-material", source="homepage",
                                          consent_version="newsletter-v1", consent_text="별도 뉴스레터 수신에 동의합니다", consent_purpose="newsletter")
    assert not created and changed["id"] == reader["id"] and changed["delivery"] == reader["delivery"]
    assert changed["consent_history"][0]["consent"]["purpose"] == "lead_magnet_delivery"
    with pytest.raises(WorkflowError, match="동의"):
        newsletter.mark_sent(store, current["id"], expected_hash=approved["review_hash"], actor="human")
    assert newsletter.issue(store, current["id"]) == approved
    rebuilt = newsletter.rebuild_issue(store, current["id"], actor="human")
    assert rebuilt["recipient_count"] == 1 and rebuilt["state"] == "draft" and rebuilt["approval"] is None
    assert rebuilt["recipients_hash"] != approved["recipients_hash"]
