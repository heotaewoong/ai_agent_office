"""Local staging projection and app-recording tests. No external API or real approval."""
import hashlib
import json

import pytest
from fastapi.testclient import TestClient

from office.api import create_app
from office.channels import update_channel
from office.staging import prepare_staging, staging_view
from office.store import Store, WorkflowError


@pytest.fixture(autouse=True)
def no_external_calls(monkeypatch):
    def forbidden(*args, **kwargs):
        raise AssertionError("Staging never sends network requests")
    monkeypatch.setattr("requests.sessions.Session.request", forbidden)


def released_blog(tmp_path, language="ko"):
    from office.media import produce
    store = Store(tmp_path)
    job = store.create_job({"id": "synthetic-staging", "title": "합성 안내", "url": "https://example.invalid/source"})
    packet = {"title": "합성 안내", "body": "실제 뉴스가 아닌 합성 안내입니다.", "quality": {"status": "passed", "critical": False}, "audience": {"language": language}}
    source = store.save_source(job["id"], packet)
    store.review_source(job["id"], source["source_hash"], "approved", "synthetic-operator", {"blog": True, "video": False})
    manifest = produce(store, job["id"])
    store.review_release(job["id"], manifest["hash"], "approved", "synthetic-operator", outputs=["blog"])
    return store, job["id"]


def row(view, key):
    return next(item for item in view["channels"] if item["channel_key"] == key)


def client(store):
    api = TestClient(create_app(store), base_url="http://localhost:8510")
    csrf = api.get("/api/session").json()["csrf"]
    return api, {"Origin": "http://localhost:3110", "X-Office-CSRF": csrf}


def test_unapproved_job_has_blockers_without_stale_files_or_writes(tmp_path):
    store = Store(tmp_path)
    job = store.create_job({"id": "not-reviewed", "title": "미승인"})
    before, events = store.job(job["id"]), store.events()
    view = staging_view(store, job["id"])
    assert not view["current_release"] and view["blockers"]
    assert len(view["channels"]) == 9 and all(not r["local_ready"] and not r["files"] for r in view["channels"])
    assert row(view, "x_main")["status"] == "paused"
    assert {r["platform"] for r in view["channels"]}.isdisjoint({"slack", "discord", "store"})
    assert store.job(job["id"]) == before and store.events() == events
    with pytest.raises(WorkflowError, match="승인"):
        prepare_staging(store, job["id"], view["stage_hash"], "op")


def test_release_automatically_projects_local_ready_but_not_external_drafts(tmp_path):
    store, job_id = released_blog(tmp_path)
    store.set_setting("work_window", {"status": "closed"})
    view = staging_view(store, job_id)
    assert view["current_release"] and not view["recorded_current"]
    assert row(view, "tistory_main")["local_ready"] and row(view, "naver_blog_main")["local_ready"]
    assert row(view, "threads_main")["local_ready"] and row(view, "linkedin_personal")["local_ready"]
    assert not row(view, "instagram_main")["local_ready"]  # caption alone is not ready media
    assert not row(view, "instagram_english")["local_ready"]
    assert row(view, "x_main")["status"] == "paused" and row(view, "x_main")["files"] == []
    assert all(not r["external_draft_created"] and not r["can_upload_private"] for r in view["channels"])
    assert "path" not in json.dumps(view) and "external_account_id" not in json.dumps(view)
    assert store.setting("deliveries", {}) == {} and store.budget()["spent_krw"] == 0


def test_http_stage_record_is_csrf_protected_idempotent_and_version_bound(tmp_path):
    store, job_id = released_blog(tmp_path)
    api, headers = client(store)
    path = f"/api/jobs/{job_id}/staging"
    viewed = api.get(path).json()
    assert api.post(path, json={"expected_hash": viewed["stage_hash"]}).status_code == 403
    assert api.post(path, json={"expected_hash": "bad"}, headers=headers).status_code == 422
    saved = api.post(path, json={"expected_hash": viewed["stage_hash"]}, headers=headers)
    assert saved.status_code == 200 and saved.json()["recorded_current"] and saved.json()["recorded_at"]
    assert store.job(job_id)["channel_staging"]["stage_hash"] == viewed["stage_hash"]
    assert api.post(path, json={"expected_hash": viewed["stage_hash"]}, headers=headers).status_code == 200
    assert len([e for e in store.events(job_id) if e["kind"] == "channel_staging_prepared"]) == 1
    store.set_offer(job_id, {"product": "합성 새 상품", "url": "https://example.invalid/item"}, "op")
    current = api.get(path).json()
    assert not current["current_release"] and not current["recorded_current"]
    assert all(not item["local_ready"] and item["files"] == [] for item in current["channels"])
    assert api.post(path, json={"expected_hash": viewed["stage_hash"]}, headers=headers).status_code == 409
    assert len([e for e in store.events(job_id) if e["kind"] == "channel_staging_prepared"]) == 1


def test_file_tampering_invalidates_ready_and_record_without_network(tmp_path):
    store, job_id = released_blog(tmp_path)
    view = staging_view(store, job_id)
    prepare_staging(store, job_id, view["stage_hash"], "op")
    file = next(f for f in store.job(job_id)["manifest"]["files"] if f["name"] == "threads-main.txt")
    (store.artifacts / file["path"]).write_text("변경된 합성 파일", encoding="utf-8")
    current = staging_view(store, job_id)
    assert not current["current_release"] and not current["recorded_current"]
    assert all(not r["local_ready"] and not r["files"] for r in current["channels"])
    with pytest.raises(WorkflowError):
        prepare_staging(store, job_id, view["stage_hash"], "op")


def test_target_change_invalidates_channel_ready_without_relabelling_language(tmp_path):
    store, job_id = released_blog(tmp_path)
    view = staging_view(store, job_id)
    prepare_staging(store, job_id, view["stage_hash"], "op")
    update_channel(store, "threads_main", {"public_url": "https://www.threads.com/@new-synthetic"}, "op")
    current = staging_view(store, job_id)
    assert not row(current, "threads_main")["local_ready"] and not current["recorded_current"]
    job = store.job(job_id)
    store.set_brief(job_id, {**job["brief"], "language": "en"}, "op")
    current = staging_view(store, job_id)
    assert row(current, "instagram_english")["source_language"] == "ko"
    assert not row(current, "instagram_english")["local_ready"]


def test_current_youtube_delivery_is_distinct_from_local_readiness_and_secrets(tmp_path, monkeypatch):
    from tests.test_youtube_delivery import released_fixture
    store, job_id = released_fixture(tmp_path, allow_channels=True)
    for name in ("YOUTUBE_CLIENT_ID", "YOUTUBE_CLIENT_SECRET", "YOUTUBE_REFRESH_TOKEN"):
        monkeypatch.setenv(name, "PRIVATE_SECRET_SENTINEL")
    job = store.job(job_id)
    asset = next(f for f in job["manifest"]["files"] if f["name"] == "short.mp4")["sha256"]
    record = {"job_id": job_id, "channel_key": "youtube_main_ko", "manifest_hash": job["manifest"]["hash"], "asset_sha256": asset,
              "state": "unknown", "external_id": "synthetic-id", "session_uri": "PRIVATE_UPLOAD_SESSION_SENTINEL"}
    store.set_setting("deliveries", {"one": record})
    view = staging_view(store, job_id)
    youtube = row(view, "youtube_main_ko")
    assert youtube["local_ready"] and youtube["external_state"] == "unknown" and not youtube["can_upload_private"]
    assert not youtube["external_draft_created"] and "PRIVATE" not in json.dumps(view)
    record.update(state="private", privacy_status="private", upload_status="uploaded")
    store.set_setting("deliveries", {"one": record})
    current = row(staging_view(store, job_id), "youtube_main_ko")
    assert current["status"] == "private" and current["external_draft_created"] and current["external_id"] == "synthetic-id"
    assert not current["can_upload_private"]
    assert current["upload_status"] == "uploaded" and current["processing_status"] is None
    record["external_id"] = "not/an/external/id"
    store.set_setting("deliveries", {"one": record})
    invalid = row(staging_view(store, job_id), "youtube_main_ko")
    assert invalid["external_state"] == "unknown" and invalid["external_id"] is None and not invalid["external_draft_created"]
    record["external_id"] = "synthetic-id"
    record.pop("privacy_status")
    store.set_setting("deliveries", {"one": record})
    assert row(staging_view(store, job_id), "youtube_main_ko")["external_state"] == "unknown"
    record.update(state="failed", external_id=None)
    store.set_setting("deliveries", {"one": record})
    failed = row(staging_view(store, job_id), "youtube_main_ko")
    assert failed["external_state"] == "needs_review" and not failed["can_upload_private"]


def test_record_compare_remains_atomic_if_source_changes_before_write(tmp_path, monkeypatch):
    from contextlib import contextmanager
    store, job_id = released_blog(tmp_path)
    view = staging_view(store, job_id)
    original = store.connection
    changed = False
    @contextmanager
    def racing(transaction=False):
        nonlocal changed
        if transaction and not changed:
            changed = True
            store.set_offer(job_id, {"product": "합성 변경", "url": "https://example.invalid/changed"}, "op")
        with original(transaction=transaction) as db:
            yield db
    monkeypatch.setattr(store, "connection", racing)
    with pytest.raises(WorkflowError, match="바뀌"):
        prepare_staging(store, job_id, view["stage_hash"], "op")
    assert "channel_staging" not in store.job(job_id)
    assert not any(e["kind"] == "channel_staging_prepared" for e in store.events(job_id))


def test_files_are_rechecked_inside_record_transaction(tmp_path, monkeypatch):
    from contextlib import contextmanager
    store, job_id = released_blog(tmp_path)
    view = staging_view(store, job_id)
    path = store.artifacts / next(f["path"] for f in store.job(job_id)["manifest"]["files"] if f["name"] == "threads-main.txt")
    original = store.connection
    changed = False
    @contextmanager
    def racing(transaction=False):
        nonlocal changed
        if transaction and not changed:
            changed = True
            path.write_text("검사와 기록 사이에 바뀐 합성 파일", encoding="utf-8")
        with original(transaction=transaction) as db:
            yield db
    monkeypatch.setattr(store, "connection", racing)
    with pytest.raises(WorkflowError, match="파일이 변경"):
        prepare_staging(store, job_id, view["stage_hash"], "op")
    assert "channel_staging" not in store.job(job_id)
    assert not any(e["kind"] == "channel_staging_prepared" for e in store.events(job_id))


def test_http_release_automatically_records_local_staging_without_sending(tmp_path):
    store, job_id = released_blog(tmp_path)
    api, headers = client(store)
    job = store.job(job_id)
    reviewed = api.post(f"/api/jobs/{job_id}/reviews/release", json={"version": job["manifest"]["hash"], "decision": "approved", "outputs": ["blog"]}, headers=headers)
    assert reviewed.status_code == 200
    assert reviewed.json()["release_approval"]["decision"] == "approved"
    view = api.get(f"/api/jobs/{job_id}/staging").json()
    assert view["recorded_current"] and view["recorded_at"]
    assert row(view, "threads_main")["local_ready"] and not row(view, "threads_main")["external_draft_created"]
    assert len([e for e in store.events(job_id) if e["kind"] == "channel_staging_prepared"]) == 1
    assert store.setting("deliveries", {}) == {} and store.budget()["spent_krw"] == 0


def test_auto_staging_failure_keeps_successful_approval_and_reports_skip(tmp_path, monkeypatch):
    from office import staging
    store, job_id = released_blog(tmp_path)
    api, headers = client(store)
    job = store.job(job_id)
    def failed(*args, **kwargs):
        raise OSError("private-internal-detail-must-not-be-exposed")
    monkeypatch.setattr(staging, "_record_staging", failed)
    result = api.post(f"/api/jobs/{job_id}/reviews/release", json={"version": job["manifest"]["hash"], "decision": "approved", "outputs": ["blog"]}, headers=headers)
    assert result.status_code == 200 and result.json()["release_approval"]["decision"] == "approved"
    assert "channel_staging" not in store.job(job_id)
    event = next(e for e in store.events(job_id) if e["kind"] == "channel_staging_prepare_skipped")
    assert "private-internal-detail" not in json.dumps(event)
    assert not event["data"]["external_sent"]


def test_youtube_upload_eligibility_requires_channel_permission_and_open_window(tmp_path, monkeypatch):
    from tests.test_youtube_delivery import released_fixture
    store, job_id = released_fixture(tmp_path, allow_channels=False)
    for name in ("YOUTUBE_CLIENT_ID", "YOUTUBE_CLIENT_SECRET", "YOUTUBE_REFRESH_TOKEN"):
        monkeypatch.setenv(name, "synthetic-credential")
    initial = row(staging_view(store, job_id), "youtube_main_ko")
    assert initial["local_ready"] and not initial["can_upload_private"]
    assert any("전송 허용" in reason for reason in initial["blockers"])
    store.set_setting("channel_registry", {"youtube_main_ko": {"publication_enabled": "false"}})
    assert not row(staging_view(store, job_id), "youtube_main_ko")["can_upload_private"]
    update_channel(store, "youtube_main_ko", {"publication_enabled": True}, "synthetic-operator")
    assert row(staging_view(store, job_id), "youtube_main_ko")["can_upload_private"]
    store.set_setting("work_window", {"status": "closed"})
    assert not row(staging_view(store, job_id), "youtube_main_ko")["can_upload_private"]
