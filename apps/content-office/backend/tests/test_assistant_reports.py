"""Synthetic receipts only; these tests do not claim a live model execution."""
import importlib.util
import pytest

from office.store import Store, WorkflowError, digest


def payload():
    return {"work_id": "work_02", "request_id": "request_02",
            "facts": ["역할 회신을 확인함"], "limitations": ["독립 원문 감사는 미확인"],
            "evidence": [{"id": "receipt_02", "sha256": "a" * 64}]}


def test_import_and_lookup_in_existing_settings(tmp_path):
    assert importlib.util.find_spec("office.assistant_reports") is not None, "report domain module missing"
    from office.assistant_reports import import_report, get_report
    store = Store(tmp_path)
    seen = []
    report = import_report(store, payload(), verify_evidence=lambda eid, sha: seen.append((eid, sha)) or True)
    assert seen == [("receipt_02", "a" * 64)]
    assert report["sha256"] == digest(payload())
    assert report["scope"] == "verified_reference_not_approval"
    assert get_report(store, "request_02") == report
    assert get_report(store, "missing") is None
    with store.connection() as db:
        rows = db.execute("SELECT key FROM settings WHERE key LIKE 'assistant_report:%'").fetchall()
    assert [r[0] for r in rows] == ["assistant_report:request:request_02"]


def test_verified_collaboration_metadata_is_explicit_not_inferred(tmp_path):
    from office.assistant_reports import import_report, get_report
    store = Store(tmp_path)
    data = {**payload(), "title": "비서 팀 검토", "collaboration_kind": "dm_review",
            "participants": ["lumi", "ethan", "ada"]}
    report = import_report(store, data, verify_evidence=lambda *_: True)
    assert report["title"] == data["title"]
    assert report["collaboration_kind"] == "dm_review"
    assert report["participants"] == data["participants"]
    assert report["scope"] == "verified_reference_not_approval"
    assert get_report(store, data["request_id"]) == report


@pytest.mark.parametrize("change", [
    {"body": "canonical chat"}, {"source_path": "/home/private"},
    {"facts": ["see /home/person/secret.md"]}, {"facts": [r"C:\Users\person\secret"]},
    {"facts": ["PRIVATE 강의 원문"]}, {"facts": ["canonical conversation transcript"]},
    {"facts": ["../secret"]}, {"facts": ["%2Fhome%2Fperson"]},
    {"facts": ["https://private.example/source"]}, {"facts": ["line\nbody"]},
    {"facts": ["x" * 301]}, {"facts": ["x"] * 21}, {"facts": []},
    {"limitations": "none"}, {"limitations": [None]}, {"limitations": ["\x00"]},
    {"request_id": "bad/id"}, {"work_id": True},
    {"evidence": []}, {"evidence": [{"id": "receipt", "sha256": "A" * 64}]},
    {"evidence": [{"id": "receipt", "sha256": "a" * 64, "body": "secret"}]},
    {"evidence": [{"id": "receipt", "sha256": "a" * 64}] * 2},
    {"job_id": "job_x"}, {"source_hash": "a" * 64},
])
def test_invalid_or_private_payload_is_rejected_without_write(tmp_path, change):
    from office.assistant_reports import import_report
    store = Store(tmp_path)
    with store.connection() as db:
        before = list(db.iterdump())
    with pytest.raises(WorkflowError):
        import_report(store, {**payload(), **change}, verify_evidence=lambda *_: True)
    with store.connection() as db:
        assert list(db.iterdump()) == before


@pytest.mark.parametrize("bad", [None, [], True, "text", {"work_id": "work"}])
def test_non_report_json_is_rejected(tmp_path, bad):
    from office.assistant_reports import import_report
    with pytest.raises(WorkflowError):
        import_report(Store(tmp_path), bad, verify_evidence=lambda *_: True)


@pytest.mark.parametrize("bad", ["../private", "a" * 97, None, True])
def test_lookup_rejects_bad_identifier(tmp_path, bad):
    from office.assistant_reports import get_report
    with pytest.raises(WorkflowError):
        get_report(Store(tmp_path), bad)


def test_job_snapshot_guard_rejects_stale_even_on_replay(tmp_path):
    from office.assistant_reports import import_report, get_report
    store = Store(tmp_path)
    job = store.create_job({"id": "article_fixture", "title": "Synthetic"})
    linked = {**payload(), "job_id": job['id'], "source_hash": None}
    report = import_report(store, linked, verify_evidence=lambda *_: True)
    store.save_source(job['id'], {"title": "Synthetic", "body": "Fixture only"})
    for request_id in ("request_02", "request_new"):
        with pytest.raises(WorkflowError, match="stale"):
            import_report(store, {**linked, "request_id": request_id}, verify_evidence=lambda *_: True)
    assert get_report(store, "request_02") == report  # historical read remains honest
    assert get_report(store, "request_new") is None
    with pytest.raises(WorkflowError):
        import_report(store, {**linked, "job_id": "job_missing"}, verify_evidence=lambda *_: True)


@pytest.mark.parametrize("verified", [False, None, 1, "true"])
def test_unverified_receipt_never_imports(tmp_path, verified):
    from office.assistant_reports import import_report, get_report
    store = Store(tmp_path)
    with pytest.raises(WorkflowError, match="verified"):
        import_report(store, payload(), verify_evidence=lambda *_: verified)
    assert get_report(store, "request_02") is None


def test_verifier_failure_rolls_back_and_never_stores_exception_text(tmp_path):
    from office.assistant_reports import import_report, get_report
    store = Store(tmp_path)
    def unavailable(*_):
        raise RuntimeError("private verifier detail")
    with pytest.raises(WorkflowError, match="verification unavailable"):
        import_report(store, payload(), verify_evidence=unavailable)
    assert get_report(store, "request_02") is None


def test_stable_request_is_idempotent_and_conflict_is_workflow_error(tmp_path):
    from office.assistant_reports import import_report, get_report
    store = Store(tmp_path)
    report = import_report(store, payload(), verify_evidence=lambda *_: True)
    assert import_report(store, payload(), verify_evidence=lambda *_: False) == report
    for change in ({"facts": ["다른 보고"]}, {"work_id": "work_other"}):
        with pytest.raises(WorkflowError, match="conflict"):
            import_report(store, {**payload(), **change}, verify_evidence=lambda *_: True)
    assert get_report(store, "request_02") == report


def test_report_only_changes_one_settings_row_and_preserves_all_assets(tmp_path):
    from office.assistant_reports import import_report, get_report
    from office.store import canonical, now
    store = Store(tmp_path)
    job = store.create_job({"id": "article_preserved", "title": "Synthetic preservation fixture"})
    job = store.save_source(job['id'], {"title": "Synthetic", "body": "Fixture only",
                                      "quality": {"status": "passed", "critical": False}})
    store.review_source(job['id'], job['source_hash'], 'approved', 'fixture operator')
    store.update_job(job['id'], manifest={"hash": "fixture_manifest", "artifacts": ["keep.txt"]})
    store.add_draft(job['id'], {"title": "Fixture", "body": "Unapproved fixture"})
    store.enqueue('draft', {'job_id': job['id']}, key='preserve')
    with store.connection() as db:
        stamp = now()
        db.execute("INSERT INTO costs VALUES(?,?,?,?,?,?,?,?)", ('cost_fixture', 'fixture', 'reserved', 10, None, canonical({'fixture': True}), stamp, stamp))
    keep = store.artifacts / 'keep.txt'
    keep.write_text('preserved fixture asset')
    with store.connection() as db:
        before = list(db.iterdump())
    file_before = {str(p.relative_to(store.root)): p.read_bytes() for p in store.artifacts.rglob('*') if p.is_file()}
    linked = {**payload(), 'job_id': job['id'], 'source_hash': job['source_hash']}
    first = import_report(store, linked, verify_evidence=lambda *_: True)
    assert get_report(store, linked['request_id']) == first
    assert import_report(store, linked, verify_evidence=lambda *_: True) == first
    with store.connection() as db:
        after = [line for line in db.iterdump() if not line.startswith('INSERT INTO "settings" VALUES(\'assistant_report:')]
    assert after == before
    assert {str(p.relative_to(store.root)): p.read_bytes() for p in store.artifacts.rglob('*') if p.is_file()} == file_before


def test_same_request_concurrent_import_creates_one_record(tmp_path):
    from concurrent.futures import ThreadPoolExecutor
    from office.assistant_reports import import_report
    store = Store(tmp_path)
    with ThreadPoolExecutor(max_workers=4) as pool:
        results = list(pool.map(lambda _: import_report(store, payload(), verify_evidence=lambda *_: True), range(8)))
    assert all(result == results[0] for result in results)
    with store.connection() as db:
        assert db.execute("SELECT count(*) FROM settings WHERE key LIKE 'assistant_report:%'").fetchone()[0] == 1
