import hashlib
from datetime import datetime, timedelta, timezone
import pytest
from fastapi.testclient import TestClient
from office.api import create_app
from office.store import Store, digest


@pytest.fixture
def context(tmp_path):
    store = Store(tmp_path)
    article = {"id": "one", "title": "AI 발표", "url": "https://example.com/news", "summary": "공식 발표", "evidence": [], "published_at": datetime.now(timezone.utc).isoformat()}
    store.save_articles([article])
    client = TestClient(create_app(store), base_url="http://localhost:8510")
    token = client.get("/api/session").json()["csrf"]
    return store, client, {"Origin": "http://localhost:3110", "X-Office-CSRF": token}


def test_foreign_origin_cannot_create_or_review_jobs(context):
    store, client, headers = context
    response = client.post("/api/jobs", json={"article_ids": ["one"]}, headers={**headers, "Origin": "https://attacker.example"})
    assert response.status_code == 403
    assert store.jobs() == []


def test_mutation_requires_session_and_csrf(context):
    _, client, _ = context
    response = client.post("/api/jobs", json={"article_ids": ["one"]}, headers={"Origin": "http://localhost:3110"})
    assert response.status_code == 403


def test_create_job_and_refresh_detail_keep_same_id(context):
    _, client, headers = context
    first = client.post("/api/jobs", json={"article_ids": ["one"]}, headers=headers)
    assert first.status_code == 200
    job_id = first.json()["jobs"][0]["id"]
    second = client.post("/api/jobs", json={"article_ids": ["one"]}, headers=headers)
    assert second.json()["jobs"][0]["id"] == job_id
    assert client.get(f"/api/jobs/{job_id}").json()["id"] == job_id


def test_produce_cannot_bypass_source_approval(context):
    store, client, headers = context
    job = store.create_job(store.article("one"))
    response = client.post(f"/api/jobs/{job['id']}/produce", json={}, headers=headers)
    assert response.status_code == 409
    assert store.tasks(job["id"]) == []


def test_editor_cannot_forge_quality_passed(context):
    store, client, headers = context
    job = store.create_job(store.article("one"))
    response = client.put(f"/api/jobs/{job['id']}/source", json={"packet": {"title": "수정", "body": "본문", "quality": {"status": "passed", "critical": False}}}, headers=headers)
    assert response.status_code == 200
    assert response.json()["source_packet"]["quality"]["status"] == "unverified"
    attempted = client.post(f"/api/jobs/{job['id']}/reviews/source", json={"version": response.json()["source_hash"], "decision": "approved"}, headers=headers)
    assert attempted.status_code == 409


def test_artifact_id_is_not_a_file_path(context):
    _, client, _ = context
    response = client.get("/api/artifacts/not-an-artifact")
    assert response.status_code == 404


def approved_bundle(store, video=False):
    job = store.create_job(store.article("one"))
    source = store.save_source(job["id"], {"title": "검토 원고", "body": "완성 원고", "quality": {"status": "passed", "critical": False}})
    store.review_source(job["id"], source["source_hash"], "approved", "operator", {"blog": True, "video": video})
    (store.artifacts / "tistory.txt").write_bytes(b"demo")
    record = {"id": "asset_one", "name": "tistory.txt", "kind": "text", "path": "tistory.txt", "size": 4, "sha256": hashlib.sha256(b"demo").hexdigest(), "url": "/api/artifacts/asset_one"}
    manifest = {"source_hash": source["source_hash"], "files": [record], "thumbnail_candidates": [record] if video else [], "media": {"duration": 20} if video else {}}
    manifest["hash"] = digest(manifest)
    store.save_manifest_if_current(job["id"], source["source_hash"], store.job(job["id"])["selections"], manifest)
    return store.job(job["id"])


def test_release_does_not_apply_to_a_source_changed_during_file_validation(context, monkeypatch):
    store, client, headers = context
    job = approved_bundle(store)
    actual_sha256 = hashlib.sha256
    triggered = False
    def source_changed(data=b"", *args, **kwargs):
        nonlocal triggered
        if data == b"demo" and not triggered:
            triggered = True
            store.save_source(job["id"], {"title": "새 원고", "body": "수정", "quality": {"status": "passed", "critical": False}})
        return actual_sha256(data, *args, **kwargs)
    monkeypatch.setattr("office.api.hashlib.sha256", source_changed)
    response = client.post(f"/api/jobs/{job['id']}/reviews/release", json={"version": job["manifest"]["hash"], "decision": "approved"}, headers=headers)
    assert response.status_code == 409
    assert store.job(job["id"])["release_approval"] is None
    assert store.job(job["id"])["state"] == "source_review"


def test_video_release_requires_thumbnail_choice_and_media_review(context):
    store, client, headers = context
    job = approved_bundle(store, video=True)
    response = client.post(f"/api/jobs/{job['id']}/reviews/release", json={"version": job["manifest"]["hash"], "decision": "approved"}, headers=headers)
    assert response.status_code == 409
    chosen = client.post(f"/api/jobs/{job['id']}/thumbnail", json={"artifact_id": "asset_one"}, headers=headers)
    assert chosen.status_code == 200
    version = chosen.json()["manifest"]["hash"]
    without_review = client.post(f"/api/jobs/{job['id']}/reviews/release", json={"version": version, "decision": "approved"}, headers=headers)
    assert without_review.status_code == 409
    approved = client.post(f"/api/jobs/{job['id']}/reviews/release", json={"version": version, "decision": "approved", "media_reviewed": True}, headers=headers)
    assert approved.status_code == 200


def test_refresh_with_no_active_items_does_not_show_archived_news_as_current(context):
    store, client, _ = context
    old = {**store.article("one"), "published_at": (datetime.now(timezone.utc) - timedelta(days=30)).isoformat(), "score": 99}
    store.save_articles([old])
    store.create_job(old)
    store.set_setting("feed_report", {"active_article_ids": [], "eligible_items": 0, "feeds": []})
    dashboard = client.get("/api/dashboard").json()
    assert dashboard["articles"] == []
    assert len(dashboard["jobs"]) == 1


def test_public_source_text_is_registered_without_forging_evidence_or_approval(context):
    store, client, headers = context
    job = store.create_job(store.article("one"))
    response = client.post(f"/api/jobs/{job['id']}/evidence", json={"source_text": "제공한 공개 본문입니다. " * 30}, headers=headers)
    assert response.status_code == 200
    updated = response.json()
    assert updated["article"]["operator_source_text"]
    assert updated["article"]["evidence"] == []
    assert updated["source_approval"] is None
    assert store.tasks(job["id"])[0]["kind"] == "draft"


def test_retry_superseded_failed_draft_does_not_regenerate_current_source(context):
    store, client, headers = context
    job = store.create_job(store.article("one"))
    task = store.enqueue("draft", {"job_id": job["id"], "source_hash": None}, key="failed-old")
    store.claim("old-worker")
    store.finish_task(task["id"], "old-worker", {"error": "failed"}, state="failed")
    store.save_source(job["id"], {"title": "새 원고", "body": "검토 중", "quality": {"status": "passed", "critical": False}})
    response = client.post(f"/api/tasks/{task['id']}/retry", json={}, headers=headers)
    assert response.status_code == 409
    assert not any(task["state"] == "queued" for task in store.tasks())


def test_expired_article_cannot_be_selected_as_a_new_current_job(context):
    store, client, headers = context
    old = {**store.article("one"), "published_at": (datetime.now(timezone.utc) - timedelta(days=30)).isoformat()}
    store.save_articles([old])
    response = client.post("/api/jobs", json={"article_ids": ["one"]}, headers=headers)
    assert response.status_code == 409
    assert store.jobs() == []


def test_renderer_change_queues_new_production_instead_of_returning_old_finished_task(context, monkeypatch):
    from office import media
    store, client, headers = context
    job = approved_bundle(store)
    first = client.post(f"/api/jobs/{job['id']}/produce", json={}, headers=headers).json()
    claimed = store.claim('test-worker')
    assert claimed['id'] == first['id']
    store.finish_task(first['id'], 'test-worker', {}, state='completed')
    monkeypatch.setattr(media, 'RENDER_VERSION', 'new-render-version')
    second = client.post(f"/api/jobs/{job['id']}/produce", json={}, headers=headers)
    assert second.status_code == 202
    assert second.json()['id'] != first['id']
    assert second.json()['state'] == 'queued'


def test_blog_only_release_does_not_require_video_review_or_export_video_assets(context):
    import io
    import zipfile
    store, client, headers = context
    job = approved_bundle(store, video=True)
    manifest = job['manifest']
    manifest['files'][0]['outputs'] = ['blog']
    (store.artifacts / 'video-only.txt').write_bytes(b'video-only')
    manifest['files'].append({'id': 'asset_video', 'name': 'video-only.txt', 'path': 'video-only.txt', 'size': 10, 'sha256': hashlib.sha256(b'video-only').hexdigest(), 'outputs': ['video']})
    manifest['completed_outputs'] = ['blog', 'video']
    manifest['hash'] = digest(manifest)
    store.save_manifest_if_current(job['id'], job['source_hash'], job['selections'], manifest)
    response = client.post(f"/api/jobs/{job['id']}/reviews/release", json={'version': manifest['hash'], 'decision': 'approved', 'outputs': ['blog']}, headers=headers)
    assert response.status_code == 200
    assert response.json()['release_approval']['outputs'] == ['blog']
    package = client.get(f"/api/jobs/{job['id']}/package")
    assert package.status_code == 200
    with zipfile.ZipFile(io.BytesIO(package.content)) as archive:
        assert 'tistory.txt' in archive.namelist()
        assert 'video-only.txt' not in archive.namelist()


def two_output_bundle(store):
    job = approved_bundle(store)
    store.review_source(job['id'], job['source_hash'], 'approved', 'fixture-operator', {'blog': True, 'pdf': True})
    manifest = job['manifest']
    manifest['files'][0]['outputs'] = ['blog']
    (store.artifacts / 'summary.pdf').write_bytes(b'pdf-data')
    manifest['files'].append({'id': 'asset_pdf', 'name': 'summary.pdf', 'path': 'summary.pdf', 'size': 8, 'sha256': hashlib.sha256(b'pdf-data').hexdigest(), 'outputs': ['pdf']})
    manifest['completed_outputs'] = ['blog', 'pdf']
    manifest['hash'] = digest(manifest)
    current = store.job(job['id'])
    return store.save_manifest_if_current(job['id'], job['source_hash'], current['selections'], manifest)


def test_changing_release_outputs_cannot_overwrite_an_inflight_package(context):
    import zipfile
    store, client, _ = context
    job = two_output_bundle(store)
    manifest_hash = job['manifest']['hash']
    endpoint = next(route.endpoint for route in client.app.routes if route.path == '/api/jobs/{job_id}/package')
    store.review_release(job['id'], manifest_hash, 'approved', 'fixture-operator', outputs=['blog'])
    first = endpoint(job['id'])
    store.review_release(job['id'], manifest_hash, 'approved', 'fixture-operator', outputs=['pdf'])
    second = endpoint(job['id'])
    assert first.path != second.path
    with zipfile.ZipFile(first.path) as archive:
        assert 'tistory.txt' in archive.namelist() and 'summary.pdf' not in archive.namelist()


def test_unselected_missing_output_does_not_block_selected_blog_release(context):
    store, client, headers = context
    job = two_output_bundle(store)
    (store.artifacts / 'summary.pdf').unlink()
    approved = client.post(f"/api/jobs/{job['id']}/reviews/release", json={'version': job['manifest']['hash'], 'decision': 'approved', 'outputs': ['blog']}, headers=headers)
    assert approved.status_code == 200
    assert client.get(f"/api/jobs/{job['id']}/package").status_code == 200


def test_delivery_routes_require_release_and_report_ledger(context, monkeypatch):
    store, client, headers = context
    for key in ('YOUTUBE_CLIENT_ID', 'YOUTUBE_CLIENT_SECRET', 'YOUTUBE_REFRESH_TOKEN'):
        monkeypatch.delenv(key, raising=False)
    job = store.create_job({'id': 'delivery-route', 'title': '업로드 경로'})
    assert client.get(f"/api/jobs/{job['id']}/deliveries").json() == {'deliveries': [], 'youtube_configured': False}
    response = client.post(f"/api/jobs/{job['id']}/deliveries/youtube", headers=headers)
    assert response.status_code == 409 and '출고 승인②' in response.json()['detail']
    assert client.get('/api/dashboard').json()['provider']['youtube'] == {'configured': False, 'visibility': 'private', 'automatic_retry': False}
    assert client.post(f"/api/jobs/{job['id']}/deliveries/missing/reconcile", headers=headers).status_code == 409


def test_public_origin_is_opt_in_https_only_and_marks_cookie_secure(tmp_path, monkeypatch):
    from office.store import WorkflowError
    store = Store(tmp_path)
    store.save_articles([{"id": "one", "title": "AI 발표", "url": "https://example.com/news", "summary": "공식 발표", "evidence": [], "published_at": datetime.now(timezone.utc).isoformat()}])
    public = "https://office.example.com"
    monkeypatch.delenv("OFFICE_PUBLIC_ORIGIN", raising=False)
    local = TestClient(create_app(store), base_url="http://localhost:8510")
    token = local.get("/api/session").json()["csrf"]
    assert local.post("/api/jobs", json={"article_ids": ["one"]}, headers={"Origin": public, "X-Office-CSRF": token}).status_code == 403
    for bad in ("http://office.example.com", "https://office.example.com/path", "https://*.example.com", "https://user@office.example.com", "office.example.com"):
        monkeypatch.setenv("OFFICE_PUBLIC_ORIGIN", bad)
        with pytest.raises(WorkflowError, match="OFFICE_PUBLIC_ORIGIN"):
            create_app(store)
    monkeypatch.setenv("OFFICE_PUBLIC_ORIGIN", public + "/")
    # The browser reaches the proxy over HTTPS, so the Secure cookie is returned.
    client = TestClient(create_app(store), base_url="https://localhost:8510")
    session = client.get("/api/session")
    assert "secure" in session.headers["set-cookie"].lower()
    headers = {"Origin": public, "X-Office-CSRF": session.json()["csrf"]}
    created = client.post("/api/jobs", json={"article_ids": ["one"]}, headers=headers)
    assert created.status_code in (200, 201), created.text
    assert client.post("/api/jobs", json={"article_ids": ["one"]}, headers={**headers, "Origin": "https://attacker.example"}).status_code == 403
    assert client.post("/api/jobs", json={"article_ids": ["one"]}, headers={"Origin": public}).status_code == 403


def test_profile_settings_route_selects_without_cost_and_rejects_unknown(context):
    store, client, headers = context
    before = store.budget()
    response = client.post("/api/settings/profiles", json={"kind": "image", "profile": "openai-gpt-image"}, headers=headers)
    assert response.status_code == 200 and response.json()["image"]["id"] == "openai-gpt-image"
    assert client.post("/api/settings/profiles", json={"kind": "clip", "profile": "runway-gen4-turbo"}, headers=headers).json()["clip"]["id"] == "runway-gen4-turbo"
    assert client.post("/api/settings/profiles", json={"kind": "voice", "profile": "gemini-kore"}, headers=headers).json()["voice"]["id"] == "gemini-kore"
    assert store.budget() == before
    assert client.post("/api/settings/profiles", json={"kind": "image", "profile": "midjourney"}, headers=headers).status_code == 409
    assert client.post("/api/settings/profiles", json={"kind": "font", "profile": "x"}, headers=headers).status_code == 422
    assert client.post("/api/settings/profiles", json={"kind": "image", "profile": "none"}, headers={"Origin": "http://localhost:3110"}).status_code == 403
    selected = [e for e in store.events(limit=10) if e["kind"] == "image_profile_selected"]
    assert selected and selected[0]["data"]["selected_by"] == "local-operator-ui"


def test_work_window_route_opens_window_and_reports_services(context, monkeypatch):
    store, client, headers = context
    from office import services
    monkeypatch.setattr(services, "start_window_services", lambda store, **kw: {"started": [], "running": [], "note": "fixture"})
    assert client.post("/api/session/window", json={"minutes": 0}, headers=headers).status_code in (409, 422)
    response = client.post("/api/session/window", json={"minutes": 90}, headers=headers)
    assert response.status_code == 200, response.text
    body = response.json()
    assert body["work_window"]["authorization_source"] == "local_operator_ui" and body["services"]["note"] == "fixture"
    assert store.setting("work_window")["authorization_source"] == "local_operator_ui"
    assert client.post("/api/session/window", json={"minutes": 30}, headers=headers).status_code == 409
