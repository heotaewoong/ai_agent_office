import pytest
from office.store import Store, WorkflowError


def packet(text="검증한 원고", critical=False):
    return {
        "title": "AI 뉴스", "body": text,
        "evidence": [{"id": "e1", "url": "https://example.com/news", "claim": "공식 발표"}],
        "quality": {"status": "blocked" if critical else "passed", "critical": critical},
    }


@pytest.fixture
def store(tmp_path):
    return Store(tmp_path)


def new_job(store):
    return store.create_job({"id": "article-1", "title": "AI 뉴스", "url": "https://example.com/news"})


def test_unapproved_source_cannot_start_production(store):
    job = new_job(store)
    store.save_source(job["id"], packet())
    with pytest.raises(WorkflowError, match="원고 승인"):
        store.require_source_approval(job["id"])


def test_approval_binds_current_source_and_survives_restart(store):
    job = new_job(store)
    first = store.save_source(job["id"], packet())
    store.review_source(job["id"], first["source_hash"], "approved", "operator")
    reopened = Store(store.root)
    assert reopened.require_source_approval(job["id"])["source_hash"] == first["source_hash"]


def test_source_change_invalidates_approval_and_derivatives(store):
    job = new_job(store)
    first = store.save_source(job["id"], packet())
    store.review_source(job["id"], first["source_hash"], "approved", "operator")
    store.update_job(job["id"], manifest={"source_hash": first["source_hash"], "files": []})
    second = store.save_source(job["id"], packet("수정한 원고"))
    assert second["source_hash"] != first["source_hash"]
    assert second["manifest"] is None
    with pytest.raises(WorkflowError, match="원고 승인"):
        store.require_source_approval(job["id"])
    with pytest.raises(WorkflowError, match="버전"):
        store.review_source(job["id"], first["source_hash"], "approved", "operator")


def test_critical_quality_issue_blocks_approval(store):
    job = new_job(store)
    draft = store.save_source(job["id"], packet(critical=True))
    with pytest.raises(WorkflowError, match="중대|검수"):
        store.review_source(job["id"], draft["source_hash"], "approved", "operator")


def test_source_rejection_blocks_production(store):
    job = new_job(store)
    draft = store.save_source(job["id"], packet())
    store.review_source(job["id"], draft["source_hash"], "rejected", "operator")
    with pytest.raises(WorkflowError):
        store.require_source_approval(job["id"])


def test_queue_claim_is_persistent_and_idempotent(store):
    first = store.enqueue("draft", {"job_id": "j1"}, key="draft-j1-v1")
    second = store.enqueue("draft", {"job_id": "j1"}, key="draft-j1-v1")
    assert first["id"] == second["id"]
    assert store.claim("worker-a")["id"] == first["id"]
    assert Store(store.root).claim("worker-b") is None
    store.finish_task(first["id"], "worker-a", {"status": "done"})
    assert store.task(first["id"])["state"] == "completed"


def test_wrong_worker_cannot_finish_a_claimed_task(store):
    task = store.enqueue("draft", {}, key="one")
    store.claim("worker-a")
    with pytest.raises(WorkflowError, match="소유"):
        store.finish_task(task["id"], "worker-b", {})


def test_manifest_cannot_attach_to_changed_source(store):
    job = new_job(store)
    first = store.save_source(job["id"], packet())
    store.review_source(job["id"], first["source_hash"], "approved", "operator")
    store.save_source(job["id"], packet("수정한 원고"))
    with pytest.raises(WorkflowError, match="버전|승인"):
        store.save_manifest_if_current(job["id"], first["source_hash"], job["selections"], {"files": []})


def test_old_evaluation_cannot_overwrite_a_new_editor_version(store):
    job = new_job(store)
    first = store.save_source(job["id"], packet())
    current = store.save_source(job["id"], packet("편집자가 바꾼 원고"))
    with pytest.raises(WorkflowError, match="버전"):
        store.save_source(job["id"], packet("느리게 끝난 옛 평가"), expected_hash=first["source_hash"])
    assert store.job(job["id"])["source_hash"] == current["source_hash"]


def test_changing_production_choices_invalidates_derivatives_and_release(store):
    job = new_job(store)
    draft = store.save_source(job["id"], packet())
    store.review_source(job["id"], draft["source_hash"], "approved", "operator", {"blog": True, "video": False})
    store.update_job(job["id"], manifest={"source_hash": draft["source_hash"], "hash": "old", "files": []}, release_approval={"decision": "approved", "version": "old"})
    changed = store.review_source(job["id"], draft["source_hash"], "approved", "operator", {"blog": True, "video": True})
    assert changed["manifest"] is None
    assert changed["release_approval"] is None


def test_source_approval_requires_at_least_one_output(store):
    job = new_job(store)
    draft = store.save_source(job["id"], packet())
    with pytest.raises(WorkflowError, match="제작물|선택"):
        store.review_source(job["id"], draft["source_hash"], "approved", "operator", {})


def test_source_input_updates_atomically_and_rejects_an_old_editor_snapshot(store):
    job = new_job(store)
    first = store.register_source_input(job["id"], "처음 등록한 본문", expected_hash=None)
    with pytest.raises(WorkflowError, match="버전"):
        store.register_source_input(job["id"], "늦게 도착한 옛 탭의 본문", expected_hash=None)
    current = store.job(job["id"])
    assert current["article"]["operator_source_text"] == "처음 등록한 본문"
    assert current["source_hash"] == first["source_hash"]
    assert current["source_approval"] is None


def test_preservation_mode_is_bound_to_source_hash_and_compare_and_swap(store):
    from office.store import digest
    job = new_job(store)
    original = "  ## 저자가 직접 제공한 원문\r\n\r\n| 하나 | 둘 |\r\n|---|---|\r\n| 보존 | 확인 |  \r\n"
    summary = store.register_source_input(job["id"], original, expected_hash=None)
    assert summary["article"]["preserve_original"] is False
    saved = store.register_source_input(job["id"], original, expected_hash=summary["source_hash"], preserve_original=True)
    assert saved["source_hash"] != summary["source_hash"]
    assert saved["article"]["operator_source_text"] == saved["source_packet"]["body"] == original
    assert saved["article"]["preserve_original"] is saved["source_packet"]["preserve_original"] is True
    assert saved["source_packet"]["source_input_hash"] == digest(original)
    with pytest.raises(WorkflowError, match="버전"):
        store.register_source_input(job["id"], "늦은 탭의 변경", expected_hash=summary["source_hash"], preserve_original=False)
    assert store.job(job["id"]) == saved
    toggled = store.register_source_input(job["id"], original, expected_hash=saved["source_hash"])
    assert toggled["source_hash"] != saved["source_hash"] and toggled["article"]["preserve_original"] is False
    assert "preserve_original" not in toggled["source_packet"]


@pytest.mark.parametrize("value", [None, "true", "false", 0, 1, [], {}])
def test_source_preservation_requires_a_strict_boolean_before_mutating_state(store, value):
    job = new_job(store)
    before, events = store.job(job["id"]), store.events(job["id"])
    with pytest.raises(WorkflowError, match="true.*false"):
        store.register_source_input(job["id"], "제공한 본문", expected_hash=None, preserve_original=value)
    assert store.job(job["id"]) == before and store.events(job["id"]) == events


@pytest.mark.parametrize("text", [None, "", " \r\n\t", 123])
def test_source_preservation_requires_supplied_markdown_before_mutating_state(store, text):
    job = new_job(store)
    before, events = store.job(job["id"]), store.events(job["id"])
    with pytest.raises(WorkflowError, match="직접 제공"):
        store.register_source_input(job["id"], text, expected_hash=None, preserve_original=True)
    assert store.job(job["id"]) == before and store.events(job["id"]) == events
