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


@pytest.mark.parametrize("state", ["failed", "running", "unknown"])
def test_selected_job_keeps_its_tasks_after_other_jobs_fill_dashboard_history(context, state):
    from office.store import canonical, now
    store, client, _ = context
    job = store.create_job(store.article("one"))
    task = store.enqueue("draft", {"job_id": job["id"], "source_hash": None}, key="selected-status")
    with store.connection(transaction=True) as db:
        db.execute("UPDATE tasks SET state=? WHERE id=?", (state, task["id"]))
    with store.connection(transaction=True) as db:
        stamp = now()
        db.executemany("INSERT INTO tasks VALUES(?,?,?,?,?,NULL,NULL,?,?)", [(f"task_other_{index}", "draft", canonical({"job_id": f"job_other_{index}"}), "completed", f"other:{index}", stamp, stamp) for index in range(105)])
    dashboard = client.get("/api/dashboard").json()
    assert len(dashboard["tasks"]) == 100 and task["id"] not in {row["id"] for row in dashboard["tasks"]}
    response = client.get(f"/api/jobs/{job['id']}")
    assert response.status_code == 200
    assert [(row["id"], row["state"]) for row in response.json()["tasks"]] == [(task["id"], state)]
    assert store.job(job["id"]) == job


def test_job_summaries_bound_metadata_and_preserve_detail_ids_with_smaller_payload(context):
    from office.store import canonical
    store, client, _ = context
    private = "PRIVATE_SUMMARY_SENTINEL"
    hostile_title = '<img src=x onerror="alert(1)"> 합성 제목'
    with store.connection(transaction=True) as db:
        for index in range(105):
            stamp = f"2026-10-29T00:{index // 60:02}:{index % 60:02}+00:00"
            job = {"id": f"job_{index:03}", "title": hostile_title, "state": "source_review", "updated_at": stamp,
                   "source_hash": "a" * 64, "source_packet": {"body": private + "." * 12000, "evidence": [private]},
                   "article": {"url": "https://example.com/" + private, "body": private}, "payload": private, "actor": private,
                   "source_approval": {"id": "approval_synthetic", "decision": "approved", "version": "a" * 64, "created_at": stamp, "actor": private},
                   "release_approval": {"decision": "rejected", "version": "b" * 64, "created_at": stamp, "outputs": ["blog"], "note": private},
                   "manifest": {"hash": "b" * 64, "source_hash": "a" * 64, "path": private, "files": [{"id": "asset_synthetic", "kind": "text", "sha256": "c" * 64, "outputs": ["blog"], "path": private, "url": private}]}}
            db.execute("INSERT INTO jobs VALUES(?,?,?)", (job["id"], canonical(job), stamp))
    dashboard = client.get("/api/dashboard")
    response = client.get("/api/jobs/summaries")
    assert dashboard.status_code == response.status_code == 200
    summaries = response.json()["jobs"]
    assert len(dashboard.json()["jobs"]) == 105 and len(summaries) == 80
    assert summaries[0]["id"] == "job_104" and summaries[-1]["id"] == "job_025"
    assert summaries[0]["title"] == hostile_title
    assert response.headers["content-type"].startswith("application/json")
    assert private not in response.text and len(response.content) < len(dashboard.content) / 5
    assert len(client.get("/api/jobs/summaries?limit=1").json()["jobs"]) == 1
    detail = client.get("/api/jobs/" + summaries[-1]["id"])
    assert detail.status_code == 200 and detail.json()["id"] == "job_025"
    assert private in detail.json()["source_packet"]["body"]
    for summary in summaries:
        assert set(summary) == {"id", "title", "state", "source_hash", "source_approval", "release_approval", "manifest"}
        assert set(summary["source_approval"]) == {"id", "decision", "version", "created_at"}
        assert set(summary["release_approval"]) == {"decision", "version", "created_at", "outputs"}
        assert set(summary["manifest"]) == {"hash", "source_hash", "files"}
        assert set(summary["manifest"]["files"][0]) == {"id", "kind", "sha256", "outputs"}


@pytest.mark.parametrize("limit", ["0", "81", "-1", "1.5", "wrong"])
def test_job_summaries_reject_invalid_limit_before_reading_jobs(context, monkeypatch, limit):
    store, client, _ = context

    def unexpected(*args, **kwargs):
        pytest.fail("잘못된 limit으로 작업을 조회했습니다")

    monkeypatch.setattr(store, "jobs", unexpected)
    assert client.get("/api/jobs/summaries?limit=" + limit).status_code == 422


def test_job_summaries_sanitize_malformed_nested_metadata_and_bound_every_list(context):
    store, client, _ = context
    private = "PRIVATE_NESTED_SENTINEL"
    job = store.create_job(store.article("one"))
    file = {"id": "../invalid", "kind": {"body": private}, "sha256": "not-a-hash", "outputs": ["x" * 90] * 30 + [{"body": private}], "arbitrary": private}
    store.update_job(job["id"], title="t" * 250, state="s" * 90, source_hash="not-a-hash",
                     source_approval={"id": "../invalid", "decision": "d" * 70, "version": "A" * 64, "created_at": "t" * 90, "actor": private},
                     release_approval=[private], manifest={"hash": {"body": private}, "source_hash": "A" * 64, "files": [file] * 100, "unknown": private})
    response = client.get("/api/jobs/summaries?limit=80")
    assert response.status_code == 200
    summary = response.json()["jobs"][0]
    assert len(summary["title"]) == 200 and len(summary["state"]) == 60
    assert summary["source_hash"] is None and summary["release_approval"] is None
    assert summary["source_approval"] == {"id": None, "decision": "d" * 40, "version": "a" * 64, "created_at": "t" * 60}
    assert summary["manifest"]["hash"] is None and summary["manifest"]["source_hash"] == "a" * 64
    assert len(summary["manifest"]["files"]) == 80
    for metadata in summary["manifest"]["files"]:
        assert metadata["id"] is None and metadata["sha256"] is None and isinstance(metadata["kind"], str)
        assert len(metadata["outputs"]) == 20 and all(len(output) == 60 for output in metadata["outputs"])
    assert private not in response.text


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


def test_idea_source_text_requires_packaging_before_any_mutation(context):
    from office.packaging import attach_packaging
    store, client, headers = context
    job = store.create_job({"id": "idea-fixture", "title": "편입 준비", "url": "https://example.edu/transfer", "origin": "idea", "evidence": []})
    snapshot, events, tasks = store.job(job["id"]), store.events(), store.tasks()
    body = {"source_text": "운영자가 확인한 공개 모집 요강 본문입니다. " * 20}
    response = client.post(f"/api/jobs/{job['id']}/evidence", json=body, headers=headers)
    assert response.status_code == 409 and "패키징" in response.json()["detail"]
    assert store.job(job["id"]) == snapshot and store.events() == events and store.tasks() == tasks
    attach_packaging(store, job["id"], {"titles": ["편입 준비 첫걸음", "편입 준비 순서", "편입 준비 체크"], "thumbnails": [{"text": "편입 준비", "visual": "직접 제작한 도형"}] * 3, "hook": "편입 준비를 시작할 때 모집 요강부터 확인해요.", "logline": "모집 요강을 읽는 순서", "reasons": ["독자 질문", "공식 요강"]}, "fixture-operator")
    assert client.post(f"/api/jobs/{job['id']}/evidence", json=body, headers=headers).status_code == 200
    assert store.job(job["id"])["source_approval"] is None
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
    for key in ('YOUTUBE_CLIENT_ID', 'YOUTUBE_CLIENT_SECRET', 'YOUTUBE_REFRESH_TOKEN', 'YOUTUBE_MAIN_KO_REFRESH_TOKEN', 'YOUTUBE_ENGLISH_REFRESH_TOKEN'):
        monkeypatch.delenv(key, raising=False)
    job = store.create_job({'id': 'delivery-route', 'title': '업로드 경로'})
    assert client.get(f"/api/jobs/{job['id']}/deliveries").json() == {'deliveries': [], 'youtube_configured': False}
    response = client.post(f"/api/jobs/{job['id']}/deliveries/youtube", headers=headers)
    assert response.status_code == 409 and '출고 승인②' in response.json()['detail']
    assert client.get('/api/dashboard').json()['provider']['youtube'] == {'configured': False, 'channels': [], 'visibility': 'private', 'automatic_retry': False}
    assert client.post(f"/api/jobs/{job['id']}/deliveries/missing/reconcile", headers=headers).status_code == 409
    unknown = client.post(f"/api/jobs/{job['id']}/deliveries/youtube", json={'channel_key': 'tistory_main'}, headers=headers)
    assert unknown.status_code == 409 and '채널' in unknown.json()['detail']


def test_channel_routes_expose_registry_and_accept_operator_settings_only(context):
    store, client, headers = context
    rows = client.get('/api/channels').json()['channels']
    by_key = {row['key']: row for row in rows}
    assert by_key['youtube_english']['external_account_id'] == 'UCc2CaOrPo-1dezowe7kklZA' and by_key['youtube_main_ko']['publication_enabled'] is False
    assert 'refresh_token' not in by_key['youtube_main_ko'] and by_key['youtube_main_ko']['credentials_configured'] in (True, False)
    assert client.put('/api/channels/youtube_main_ko', json={'publication_enabled': True}).status_code == 403
    updated = client.put('/api/channels/youtube_main_ko', json={'external_account_id': 'UCmainko0000000000000000', 'publication_enabled': True}, headers=headers)
    assert updated.status_code == 200 and updated.json()['external_account_id'] == 'UCmainko0000000000000000' and updated.json()['publication_enabled'] is True
    assert client.put('/api/channels/youtube_main_ko', json={'external_account_id': 'bad'}, headers=headers).status_code == 409
    assert client.put('/api/channels/tiktok_main', json={'publication_enabled': True}, headers=headers).status_code == 409
    assert client.put('/api/channels/youtube_main_ko', json={'refresh_token': 'abc'}, headers=headers).status_code == 409
    assert any(e['kind'] == 'channel_updated' for e in store.events(limit=5))


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
