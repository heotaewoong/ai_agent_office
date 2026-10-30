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
    compact = client.get("/api/dashboard?compact=true")
    assert compact.status_code == 200
    metadata = compact.json()["jobs"]
    assert len(metadata) == 105
    assert [item["id"] for item in metadata] == [item["id"] for item in dashboard.json()["jobs"]]
    assert metadata[-1]["id"] == "job_000" and metadata[-1]["title"] == hostile_title
    assert sum(item["state"] == "source_review" for item in metadata) == 105
    assert all(item["has_source"] is True and item["source_hash"] == "a" * 64 for item in metadata)
    assert all(set(item) == {"id", "title", "state", "source_hash", "updated_at", "has_source"} for item in metadata)
    assert private not in compact.text
    assert len(compact.content) < len(dashboard.content) / 5
    assert client.get("/api/dashboard?compact=false").json()["jobs"] == dashboard.json()["jobs"]
    assert {key: value for key, value in compact.json().items() if key != "jobs"} == {key: value for key, value in dashboard.json().items() if key != "jobs"}
    # 80개 요약 범위 밖의 오래된 ID도 목록과 상세 조회에 계속 존재한다.
    oldest = client.get("/api/jobs/" + metadata[-1]["id"])
    assert oldest.status_code == 200 and private in oldest.json()["source_packet"]["body"]
    print(f"dashboard bytes legacy={len(dashboard.content)} compact={len(compact.content)} jobs={len(metadata)}")


def test_compact_dashboard_bounds_scalar_metadata_without_body_or_nested_values(context):
    from office.store import canonical
    store, client, _ = context
    job = store.create_job(store.article("one"))
    store.update_job(job["id"], title="t" * 250, state="s" * 90, source_hash="not-a-hash",
                     source_packet={"body": {"private": "PRIVATE_COMPACT_NESTED"}})
    malformed = {**store.job(job["id"]), "updated_at": {"private": "PRIVATE_COMPACT_NESTED"}}
    with store.connection(transaction=True) as db:
        db.execute("UPDATE jobs SET data=? WHERE id=?", (canonical(malformed), job["id"]))
    response = client.get("/api/dashboard?compact=true")
    assert response.status_code == 200
    metadata = response.json()["jobs"][0]
    assert len(metadata["title"]) == 200 and len(metadata["state"]) == 60
    assert metadata["source_hash"] is None and metadata["has_source"] is False and metadata["updated_at"] == ""
    assert "PRIVATE_COMPACT_NESTED" not in response.text


def test_compact_dashboard_fails_explicitly_instead_of_silently_dropping_invalid_job_id(context):
    from office.store import canonical
    store, client, _ = context
    job = store.create_job(store.article("one"))
    with store.connection(transaction=True) as db:
        db.execute("UPDATE jobs SET data=? WHERE id=?", (canonical({**job, "id": "../invalid"}), job["id"]))
    assert len(client.get("/api/dashboard").json()["jobs"]) == 1
    response = client.get("/api/dashboard?compact=true")
    assert response.status_code == 409 and "전체 작업 목록" in response.json()["detail"]


def test_compact_dashboard_keeps_sidebar_title_fallback_without_returning_article(context):
    store, client, _ = context
    article = {**store.article("one"), "editorial_title": "운영자가 정리한 제목"}
    job = store.create_job(article)
    store.update_job(job["id"], title="")
    metadata = client.get("/api/dashboard?compact=true").json()["jobs"][0]
    assert metadata["title"] == article["editorial_title"] and "article" not in metadata
    assert metadata["has_source"] is False and metadata["source_hash"] is None


def test_compact_dashboard_rejects_bad_flag_before_job_read_and_keeps_read_origin_gate(context, monkeypatch):
    store, client, _ = context
    assert client.get("/api/dashboard?compact=true", headers={"Origin": "https://attacker.example"}).status_code == 403
    def unexpected(*args, **kwargs):
        pytest.fail("잘못된 compact 값으로 작업 목록을 조회했습니다")
    monkeypatch.setattr(store, "jobs", unexpected)
    assert client.get("/api/dashboard?compact=wrong").status_code == 422


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


def test_job_budget_routes_preserve_global_ledger_and_approval_with_versioned_cap(context):
    store, client, headers = context
    job = store.create_job(store.article("one"))
    path = f"/api/jobs/{job['id']}/budget"
    before_job = store.job(job["id"])
    initial = client.get(path)
    assert initial.status_code == 200
    snapshot = initial.json()
    assert snapshot["job_id"] == job["id"] and snapshot["cap_krw"] is None and snapshot["remaining_krw"] is None
    assert snapshot["spent_krw"] == snapshot["reserved_krw"] == 0
    paid = store.reserve_cost("synthetic-paid", 300, {"job_id": job["id"]})
    store.settle_cost(paid["id"], 150, {})
    unknown = store.reserve_cost("synthetic-unknown", 400, {"job_id": job["id"]})
    store.unknown_cost(unknown["id"], "synthetic-only")
    current = client.get(path).json()
    assert current["hash"] == snapshot["hash"] and current["spent_krw"] == 150 and current["reserved_krw"] == 400
    global_before = store.budget()
    body = {"cap_krw": 1000, "expected_hash": snapshot["hash"]}
    assert client.put(path, json=body).status_code == 403
    updated = client.put(path, json=body, headers=headers)
    assert updated.status_code == 200
    assert updated.json()["cap_krw"] == 1000 and updated.json()["remaining_krw"] == 450
    assert updated.json()["hash"] != snapshot["hash"] and updated.json()["configured_by"] == "local-operator"
    assert store.budget() == global_before and store.job(job["id"]) == before_job and store.tasks() == []
    stale = client.put(path, json={"cap_krw": 2000, "expected_hash": snapshot["hash"]}, headers=headers)
    assert stale.status_code == 409 and client.get(path).json()["cap_krw"] == 1000
    excessive = client.put(path, json={"cap_krw": global_before["cap_krw"] + 1, "expected_hash": updated.json()["hash"]}, headers=headers)
    assert excessive.status_code == 409 and store.budget() == global_before


@pytest.mark.parametrize("patch", [{"cap_krw": value} for value in (None, "1000", True, False, 1.5, 0, -1)] + [{"expected_hash": None}, {"expected_hash": "bad"}])
def test_job_budget_api_rejects_non_integer_or_unversioned_settings_without_mutation(context, patch):
    store, client, headers = context
    job = store.create_job(store.article("one"))
    path = f"/api/jobs/{job['id']}/budget"
    initial = client.get(path).json()
    events = store.events()
    result = client.put(path, json={"cap_krw": 1000, "expected_hash": initial["hash"], **patch}, headers=headers)
    assert result.status_code == 422
    assert client.get(path).json() == initial and store.events() == events
    assert client.put(path, json={"cap_krw": 1000}, headers=headers).status_code == 422


@pytest.mark.parametrize("mode", ["omitted", False])
def test_source_input_keeps_summary_as_default_and_explicit_false(context, mode):
    store, client, headers = context
    job = store.create_job(store.article("one"))
    original = "기존 요약 입력 방식을 검증하는 합성 본문입니다. " * 30
    body = {"source_text": original, "version": job["source_hash"]}
    if mode != "omitted":
        body["preserve_original"] = mode
    result = client.post(f"/api/jobs/{job['id']}/evidence", json=body, headers=headers)
    assert result.status_code == 200
    saved = result.json()
    assert saved["article"]["preserve_original"] is False
    assert saved["article"]["operator_source_text"] == original
    assert saved["source_packet"].get("preserve_original") is not True
    assert saved["source_packet"]["body"] != original
    assert saved["source_packet"]["source_input_hash"] == digest(original)


@pytest.mark.parametrize("invalid", ["true", "false", 1, 0, None, [], {}])
def test_preserve_original_requires_strict_boolean_without_mutation(context, invalid):
    store, client, headers = context
    job = store.create_job(store.article("one"))
    before, events, tasks = store.job(job["id"]), store.events(), store.tasks()
    result = client.post(f"/api/jobs/{job['id']}/evidence", json={"source_text": "원문 보존 입력 검증용 본문입니다. " * 30, "preserve_original": invalid}, headers=headers)
    assert result.status_code == 422
    assert store.job(job["id"]) == before and store.events() == events and store.tasks() == tasks


def test_long_original_markdown_is_passed_through_with_hash_and_no_approval(context):
    store, client, headers = context
    job = store.create_job(store.article("one"))
    original = "# 직접 쓴 합성 원문\n\n" + ("## 본문\n\n문장과 **강조** 및 [출처](https://example.com/source)를 그대로 둡니다.\n\n```python\nprint('원문 보존')\n```\n\n" * 120) + "마지막 줄과 공백  \n"
    assert 10000 < len(original) <= 20000
    result = client.post(f"/api/jobs/{job['id']}/evidence", json={"source_text": original, "version": job["source_hash"], "preserve_original": True}, headers=headers)
    assert result.status_code == 200
    saved = result.json()
    assert saved["article"]["operator_source_text"] == saved["source_packet"]["body"] == original
    assert saved["article"]["preserve_original"] is saved["source_packet"]["preserve_original"] is True
    assert saved["source_packet"]["source_input_hash"] == digest(original)
    assert saved["source_approval"] is None and saved["release_approval"] is None and saved["manifest"] is None
    assert saved["source_packet"]["quality"]["status"] == "unverified"
    assert store.tasks(job["id"])[0]["kind"] == "draft"
    assert store.tasks(job["id"])[0]["payload"]["source_hash"] == saved["source_hash"]
    stale = client.post(f"/api/jobs/{job['id']}/evidence", json={"source_text": original, "version": job["source_hash"], "preserve_original": False}, headers=headers)
    assert stale.status_code == 409 and store.job(job["id"])["article"]["preserve_original"] is True


def test_preserved_body_cannot_be_edited_but_title_video_and_server_contract_are_kept(context):
    store, client, headers = context
    job = store.create_job(store.article("one"))
    original = "# 합성 원문\n\n본인이 쓴 원문 보존 API 검사입니다.  \n" * 20
    saved = store.register_source_input(job["id"], original, job["source_hash"], preserve_original=True)
    packet = {**saved["source_packet"], "reference_evidence_ids": ["E1"]}
    saved = store.save_source(job["id"], packet)
    before, events, tasks = store.job(job["id"]), store.events(), store.tasks()
    changed = client.put(f"/api/jobs/{job['id']}/source", json={"version": saved["source_hash"], "packet": {**packet, "body": original + "변경"}}, headers=headers)
    assert changed.status_code == 409 and "원문 입력" in changed.json()["detail"]
    assert store.job(job["id"]) == before and store.events() == events and store.tasks() == tasks
    edited = {**packet, "title": "제목만 수정", "video": {"title": "별도 영상", "scenes": []},
              "preserve_original": False, "source_input_hash": "forged", "reference_evidence_ids": ["FORGED"]}
    accepted = client.put(f"/api/jobs/{job['id']}/source", json={"version": saved["source_hash"], "packet": edited}, headers=headers)
    assert accepted.status_code == 200
    result = accepted.json()["source_packet"]
    assert result["body"] == original and result["title"] == "제목만 수정" and result["video"] == edited["video"]
    assert result["preserve_original"] is True and result["source_input_hash"] == digest(original)
    assert result["reference_evidence_ids"] == ["E1"] and result["quality"]["status"] == "unverified"
    assert store.tasks(job["id"])[0]["kind"] == "evaluate"


def test_summary_source_edit_cannot_inject_original_preservation_contract(context):
    store, client, headers = context
    job = store.create_job(store.article("one"))
    body = "요약 원고의 입력 본문입니다."
    response = client.put(f"/api/jobs/{job['id']}/source", json={"version": job["source_hash"], "packet": {
        "title": "수정 원고", "body": body, "preserve_original": True,
        "source_input_hash": digest(body), "reference_evidence_ids": ["FORGED"]}}, headers=headers)
    assert response.status_code == 200
    packet = response.json()["source_packet"]
    assert packet["body"] == body and packet["quality"]["status"] == "unverified"
    assert not any(field in packet for field in ("preserve_original", "source_input_hash", "reference_evidence_ids"))
    assert store.tasks(job["id"])[0]["kind"] == "evaluate"


def test_both_preview_routes_allow_only_the_two_image_hosts_and_keep_script_blocked(context):
    store, client, _ = context
    job = approved_bundle(store)
    draft = store.add_draft(job["id"], {"title": "합성 미리보기", "body": "공개 원문 미리보기입니다."})
    manifest = job["manifest"]
    record = manifest["files"][0]
    record.update(name="tistory.html", outputs=["blog"])
    manifest["completed_outputs"] = ["blog"]
    manifest["hash"] = digest(manifest)
    store.save_manifest_if_current(job["id"], job["source_hash"], job["selections"], manifest)
    for path in (f"/api/jobs/{job['id']}/drafts/{draft['id']}/preview", f"/api/jobs/{job['id']}/blog-preview"):
        result = client.get(path)
        assert result.status_code == 200
        directives = {parts[0]: parts[1:] for directive in result.headers["Content-Security-Policy"].split(";") if (parts := directive.strip().split())}
        assert directives == {"default-src": ["'none'"], "script-src": ["'none'"], "style-src": ["'unsafe-inline'"],
                              "img-src": ["'self'", "https://blog.kakaocdn.net", "https://t1.daumcdn.net"], "base-uri": ["'none'"], "form-action": ["'none'"]}
        assert result.headers["Cache-Control"] == "no-store"


def photo_preview_fixture(store, html=None, photo_location="current"):
    import base64
    from office.media import artifact_record
    job = store.create_job(store.article("one"))
    original = "# 합성 사진 원문\n\n" + "사진 원문 보존 검사입니다. " * 20
    job = store.register_source_input(job["id"], original, job["source_hash"], preserve_original=True)
    job = store.save_source(job["id"], {**job["source_packet"], "quality": {"status": "passed", "critical": False}})
    store.review_source(job["id"], job["source_hash"], "approved", "synthetic-operator", {"blog": True})
    folder = store.artifacts / job["id"] / job["source_hash"] / "production-photo-fixture"
    folder.mkdir(parents=True)
    picture = folder / "source-photo-01.png"
    if photo_location == "other-job":
        other = store.create_job({"id": "synthetic-other-job", "title": "다른 작업"})
        picture = store.artifacts / other["id"] / job["source_hash"] / "production-photo-fixture" / picture.name
        picture.parent.mkdir(parents=True)
    elif photo_location == "outside":
        picture = store.root / picture.name
    picture.write_bytes(base64.b64decode("iVBORw0KGgoAAAANSUhEUgAAAAEAAAABCAQAAAC1HAwCAAAAC0lEQVR42mP8/x8AAwMCAO+a5H8AAAAASUVORK5CYII="))
    records = []
    for name, text in {"tistory.html": html or '<figure><a href="source-photo-01.png"><img src="source-photo-01.png" alt="합성 사진"></a></figure>',
                       "tistory.md": "# 변하지 않는 Markdown\n\n원문 텍스트입니다.", "naver.txt": "변하지 않는 네이버 본문"}.items():
        file = folder / name
        file.write_text(text, encoding="utf-8")
        records.append({**artifact_record(store.artifacts, file), "outputs": ["blog"]})
    if photo_location == "outside":
        checksum = hashlib.sha256(picture.read_bytes()).hexdigest()
        photo = {"id": "asset_outside", "name": picture.name, "path": str(picture), "sha256": checksum, "outputs": ["blog"]}
    else:
        photo = {**artifact_record(store.artifacts, picture), "outputs": ["blog"]}
    records.append(photo)
    manifest = {"source_hash": job["source_hash"], "files": records, "completed_outputs": ["blog"]}
    manifest["hash"] = digest(manifest)
    store.save_manifest_if_current(job["id"], job["source_hash"], store.job(job["id"])["selections"], manifest)
    return job, picture, photo


def test_blog_preview_maps_verified_local_photos_to_artifact_ids_and_keeps_text_formats(context):
    store, client, _ = context
    job, picture, photo = photo_preview_fixture(store)
    path = f"/api/jobs/{job['id']}/blog-preview"
    preview = client.get(path)
    assert preview.status_code == 200
    artifact_url = "/api/artifacts/" + photo["id"]
    assert f'src="{artifact_url}"' in preview.text and f'href="{artifact_url}"' in preview.text
    assert 'src="source-photo-' not in preview.text and str(picture.parent) not in preview.text
    image = client.get(artifact_url)
    assert image.status_code == 200 and image.content == picture.read_bytes()
    assert "image/png" in image.headers["Content-Type"]
    assert "변하지 않는 Markdown" in client.get(path + "?format=markdown").text
    assert "변하지 않는 네이버 본문" in client.get(path + "?format=naver").text


@pytest.mark.parametrize("change", ["missing", "tampered"])
def test_blog_preview_blocks_missing_or_modified_manifest_photos(context, change):
    store, client, _ = context
    job, picture, _ = photo_preview_fixture(store)
    if change == "missing":
        picture.unlink()
    else:
        picture.write_bytes(b"changed synthetic bytes")
    response = client.get(f"/api/jobs/{job['id']}/blog-preview")
    assert response.status_code == 409 and "사진" in response.json()["detail"]


@pytest.mark.parametrize("location", ["other-job", "outside"])
def test_blog_preview_rejects_foreign_job_and_absolute_local_picture_paths(context, location):
    store, client, _ = context
    job, _, _ = photo_preview_fixture(store, photo_location=location)
    assert client.get(f"/api/jobs/{job['id']}/blog-preview").status_code == 409


@pytest.mark.parametrize("src", ["file:///C:/private/photo.png", "../other-job/source-photo-01.png", "/api/artifacts/asset_other_job", "https://blog.kakaocdn.net/photo.png?SECRET_QUERY=never-expose", "source-photo-02.png"])
def test_blog_preview_rejects_unmapped_or_remote_picture_references_without_leaking_url(context, src):
    store, client, _ = context
    job, _, _ = photo_preview_fixture(store, html=f'<figure><img src="{src}"></figure>')
    response = client.get(f"/api/jobs/{job['id']}/blog-preview")
    assert response.status_code == 409 and "SECRET_QUERY" not in response.text and src not in response.text


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
    store.set_setting("channel_registry", {"youtube_main_ko": {"publication_enabled": True}})
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
