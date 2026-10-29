

def test_task_activity_is_metadata_only_and_finds_active_beyond_global_history(tmp_path, monkeypatch):
    import office.store as module
    store = module.Store(tmp_path)
    private = module.canonical({"body": "PRIVATE_ACTIVITY_SENTINEL", "path": "private/source.md"})
    old, recent = "2020-01-01T00:00:00+00:00", "2026-10-29T00:00:00+00:00"
    with store.connection(transaction=True) as db:
        rows = [("task_old_active", "draft", private, "running", "active", "private-owner", private, old, old),
                ("task_old_unknown", "produce", private, "unknown", "unknown", "private-owner", private, old, old)]
        rows += [(f"task_other_{index:03}", "other", private, "completed", f"other:{index}", None, private, recent, recent) for index in range(105)]
        db.executemany("INSERT INTO tasks VALUES(?,?,?,?,?,?,?,?,?)", rows)
    assert len(store.tasks()) == 100 and not any(t["kind"] in ("draft", "produce") for t in store.tasks())
    with monkeypatch.context() as check:
        check.setattr(module.json, "loads", lambda value: (_ for _ in ()).throw(AssertionError("activity must not decode task bodies")))
        activity = store.task_activity(("draft", "produce", "draft", "refresh"))
        assert store.task_activity(()) == []
    assert {t["id"] for t in activity} == {"task_old_active", "task_old_unknown"}
    assert all(set(t) == {"id", "kind", "state", "created_at", "updated_at"} for t in activity)
    assert "PRIVATE_ACTIVITY_SENTINEL" not in module.canonical(activity)
    assert store.task("task_old_unknown")["state"] == "unknown"


def test_task_activity_prefers_active_then_latest_with_stable_id_ties(tmp_path):
    from office.store import Store
    store = Store(tmp_path)
    rows = [("task_draft_old", "draft", "unknown", "2020"), ("task_draft_new", "draft", "completed", "2021"),
            ("task_active_a", "produce", "running", "2019"), ("task_active_z", "produce", "claimed", "2019"),
            ("task_newer_completed", "produce", "completed", "2022"),
            ("task_eval_a", "evaluate", "failed", "2022"), ("task_eval_z", "evaluate", "unknown", "2022")]
    with store.connection(transaction=True) as db:
        db.executemany("INSERT INTO tasks VALUES(?,?,?, ?,?,NULL,NULL,?,?)", [(id_, kind, "{}", state, id_, stamp, stamp) for id_, kind, state, stamp in rows])
    selected = {task["kind"]: task for task in store.task_activity(("draft", "produce", "evaluate"))}
    assert len(selected) == 3
    assert selected["draft"]["id"] == "task_draft_new"  # Old unknown history is not a permanent priority.
    assert selected["produce"]["id"] == "task_active_z"  # Active precedes newer completed; ties use id.
    assert selected["evaluate"]["id"] == "task_eval_z"
    assert store.task("task_draft_old")["state"] == "unknown"


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


def test_task_history_filters_the_job_before_its_limit_and_keeps_global_history_bounded(tmp_path):
    from office.store import Store, canonical, now
    store = Store(tmp_path)
    selected = []
    for state in ("failed", "running", "unknown"):
        task = store.enqueue("draft", {"job_id": "job_selected", "source_hash": None}, key="selected:" + state)
        with store.connection(transaction=True) as db:
            db.execute("UPDATE tasks SET state=? WHERE id=?", (state, task["id"]))
        selected.append(task["id"])
    with store.connection(transaction=True) as db:
        stamp = now()
        db.executemany("INSERT INTO tasks VALUES(?,?,?,?,?,NULL,NULL,?,?)", [(f"task_other_{index}", "draft", canonical({"job_id": f"job_other_{index}"}), "completed", f"other:{index}", stamp, stamp) for index in range(105)])
    assert len(store.tasks()) == 100
    assert not set(selected).intersection(task["id"] for task in store.tasks())
    assert {task["id"] for task in store.tasks("job_selected")} == set(selected)
    assert {task["state"] for task in store.tasks("job_selected")} == {"failed", "running", "unknown"}
    with store.connection(transaction=True) as db:
        stamp = now()
        db.executemany("INSERT INTO tasks VALUES(?,?,?,?,?,NULL,NULL,?,?)", [(f"task_selected_{index}", "evaluate", canonical({"job_id": "job_selected"}), "completed", f"selected-new:{index}", stamp, stamp) for index in range(105)])
    history = store.tasks("job_selected")
    assert len(history) == 100 and all(task["payload"]["job_id"] == "job_selected" for task in history)
    assert not set(selected).intersection(task["id"] for task in history)
    assert [store.task(task_id)["state"] for task_id in selected] == ["failed", "running", "unknown"]


def test_jobs_limit_is_applied_before_json_loading_and_default_still_returns_all(tmp_path, monkeypatch):
    import office.store as module
    store = module.Store(tmp_path)
    with store.connection(transaction=True) as db:
        for index in range(105):
            job = {"id": f"job_{index:03}", "title": "합성 작업", "updated_at": f"2026-10-29T00:{index // 60:02}:{index % 60:02}+00:00"}
            db.execute("INSERT INTO jobs VALUES(?,?,?)", (job["id"], module.canonical(job), job["updated_at"]))
    original = module.json.loads
    loaded = []

    def count_loads(value):
        loaded.append(1)
        return original(value)

    monkeypatch.setattr(module.json, "loads", count_loads)
    assert [job["id"] for job in store.jobs(limit=3)] == ["job_104", "job_103", "job_102"]
    assert len(loaded) == 3
    loaded.clear()
    assert len(store.jobs()) == len(loaded) == 105


def test_optional_unknown_guard_is_scoped_and_old_callers_keep_their_contract(tmp_path):
    import pytest
    from office.store import Store, WorkflowError
    store = Store(tmp_path)
    payload = {"job_id": "job_x", "source_hash": None}
    first = store.enqueue("quiz", payload, key="previous")
    with store.connection(transaction=True) as db:
        db.execute("UPDATE tasks SET state='unknown' WHERE id=?", (first["id"],))
    with pytest.raises(WorkflowError, match="결과 불명"):
        store.enqueue("quiz", payload, key="new-key", guard_unknown_scope=True)
    assert store.enqueue("quiz", {**payload, "job_id": "job_y"}, key="other-job", guard_unknown_scope=True)["state"] == "queued"
    assert store.enqueue("cards", payload, key="other-kind", guard_unknown_scope=True)["state"] == "queued"
    assert store.enqueue("quiz", {**payload, "source_hash": "a" * 64}, key="new-source", guard_unknown_scope=True)["state"] == "queued"
    assert store.enqueue("quiz", payload, key="previous")["id"] == first["id"]
    assert store.enqueue("quiz", payload, key="legacy-new-key")["state"] == "queued"
    assert store.task(first["id"])["state"] == "unknown"


def test_unknown_guard_reads_after_the_enqueue_transaction_acquires_its_lock(tmp_path, monkeypatch):
    from concurrent.futures import ThreadPoolExecutor
    from contextlib import contextmanager
    from threading import Event, current_thread
    import pytest
    from office.store import Store, WorkflowError
    store = Store(tmp_path)
    payload = {"job_id": "job_x", "source_hash": "a" * 64}
    first = store.enqueue("quiz", payload, key="previous")
    original, attempting = store.connection, Event()

    @contextmanager
    def connection(transaction=False):
        if transaction and current_thread().name.startswith("guard-admission"):
            attempting.set()
        with original(transaction=transaction) as db:
            yield db

    monkeypatch.setattr(store, "connection", connection)
    with ThreadPoolExecutor(max_workers=1, thread_name_prefix="guard-admission") as pool:
        with original(transaction=True) as writer:
            writer.execute("UPDATE tasks SET state='unknown' WHERE id=?", (first["id"],))
            future = pool.submit(store.enqueue, "quiz", payload, key="new-key", guard_unknown_scope=True)
            assert attempting.wait(5)
            assert not future.done()
        with pytest.raises(WorkflowError, match="결과 불명"):
            future.result(timeout=5)
    assert len(store.tasks("job_x")) == 1 and store.task(first["id"])["state"] == "unknown"
