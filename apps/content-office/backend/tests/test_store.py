

def test_failed_task_does_not_block_a_fresh_request_with_the_same_key(tmp_path):
    """The operator's second '원고 생성 시작' after a provider failure must queue new work, not echo the failed task."""
    from office.store import Store
    store = Store(tmp_path)
    first = store.enqueue("draft", {"job_id": "job_x", "source_hash": None}, key="draft:job_x:initial")
    assert store.enqueue("draft", {"job_id": "job_x"}, key="draft:job_x:initial")["id"] == first["id"]
    claimed = store.claim("worker-1")
    assert claimed["id"] == first["id"]
    store.finish_task(first["id"], "worker-1", {"error": "HTTP 503"}, state="failed")
    second = store.enqueue("draft", {"job_id": "job_x", "source_hash": None}, key="draft:job_x:initial")
    assert second["id"] != first["id"] and second["state"] == "queued"
    assert store.enqueue("draft", {"job_id": "job_x"}, key="draft:job_x:initial")["id"] == second["id"]
    store.claim("worker-1")
    store.finish_task(second["id"], "worker-1", {"error": "unknown"}, state="unknown")
    # 결과 불명은 대사 전까지 그대로 막는다(새 작업을 만들지 않는다)
    assert store.enqueue("draft", {"job_id": "job_x"}, key="draft:job_x:initial")["id"] == second["id"]
    assert [t["state"] for t in store.tasks("job_x")] == ["unknown", "failed"]
