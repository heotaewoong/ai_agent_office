from concurrent.futures import ThreadPoolExecutor
import pytest
from office.store import Store, WorkflowError


def test_parallel_reservations_do_not_overrun_cap(tmp_path):
    store = Store(tmp_path, budget_krw=100)
    def reserve(_):
        try:
            return store.reserve_cost("test", 60, {})["id"]
        except WorkflowError:
            return None
    with ThreadPoolExecutor(max_workers=2) as pool:
        ids = list(pool.map(reserve, range(2)))
    assert len([x for x in ids if x]) == 1
    assert store.budget()["reserved_krw"] == 60


def test_unknown_call_keeps_money_reserved(tmp_path):
    store = Store(tmp_path, budget_krw=100)
    reservation = store.reserve_cost("model", 80, {"model": "test"})
    store.unknown_cost(reservation["id"], "response_lost")
    assert store.budget()["reserved_krw"] == 80
    with pytest.raises(WorkflowError, match="예산"):
        store.reserve_cost("next", 30, {})


def test_settlement_releases_only_unused_reservation(tmp_path):
    store = Store(tmp_path, budget_krw=100)
    reservation = store.reserve_cost("model", 80, {})
    store.settle_cost(reservation["id"], 25, {"input_tokens": 100})
    budget = store.budget()
    assert budget["spent_krw"] == 25
    assert budget["reserved_krw"] == 0
    assert budget["remaining_krw"] == 75


def test_same_uncertain_model_call_cannot_reserve_again(tmp_path):
    store = Store(tmp_path)
    reservation = store.reserve_cost("model", 80, {"cache_key": "same-actual-request"})
    store.unknown_cost(reservation["id"], "response_lost")
    with pytest.raises(WorkflowError, match="대사|확인|호출"):
        store.reserve_cost("model", 80, {"cache_key": "same-actual-request"})
    assert store.budget()["reserved_krw"] == 80


def test_actual_overrun_is_recorded_and_new_calls_stay_blocked(tmp_path):
    store = Store(tmp_path, budget_krw=100)
    reservation = store.reserve_cost("model", 80, {})
    store.settle_cost(reservation["id"], 120, {"billing_observed": True})
    assert store.budget()["overrun_krw"] == 20
    assert store.budget()["spent_krw"] == 120
    with pytest.raises(WorkflowError):
        store.reserve_cost("next", 1, {})


def job_with_cap(store, article_id="capped"):
    job_id = store.create_job({"id": article_id, "title": "합성 예산 시험"})["id"]
    current = store.get_job_budget(job_id)
    return job_id, store.set_job_budget(job_id, 1000, "test-operator", expected_hash=current["hash"])


def test_job_cap_combines_all_cost_kinds_and_preserves_global_and_unknown(tmp_path):
    store = Store(tmp_path)
    prior = store.reserve_cost("legacy_model", 123, {"cache_key": "legacy-unknown"})
    store.unknown_cost(prior["id"], "unknown")
    before = store.budget()
    job_id, initial = job_with_cap(store)
    assert initial["spent_krw"] == initial["reserved_krw"] == 0
    assert initial["remaining_krw"] == 1000 and store.budget() == before
    text = store.reserve_cost("model", 400, {"job_id": job_id})
    store.settle_cost(text["id"], 250, {})
    voice = store.reserve_cost("speech_openai_tts", 500, {"job_id": job_id})
    store.unknown_cost(voice["id"], "unknown")
    store.reserve_cost("image", 250, {"job_id": job_id})
    with pytest.raises(WorkflowError, match="업무의 합산 예산"):
        store.reserve_cost("clip", 1, {"job_id": job_id})
    budget = store.get_job_budget(job_id)
    assert budget["spent_krw"] == 250 and budget["reserved_krw"] == 750 and budget["remaining_krw"] == 0
    assert budget["hash"] == initial["hash"]
    assert store.budget()["cap_krw"] == 10000 and store.budget()["reserved_krw"] == 873
    with store.connection() as db:
        assert db.execute("SELECT state,reserved_krw FROM costs WHERE id=?", (prior["id"],)).fetchone()[:] == ("unknown", 123)


def test_parallel_job_reservations_are_atomic_and_other_jobs_are_independent(tmp_path):
    store = Store(tmp_path)
    job_id, _ = job_with_cap(store)
    other_job, _ = job_with_cap(store, "other")

    def reserve(_):
        try:
            return store.reserve_cost("model", 600, {"job_id": job_id})["id"]
        except WorkflowError:
            return None

    with ThreadPoolExecutor(max_workers=2) as pool:
        ids = list(pool.map(reserve, range(2)))
    assert sum(cost is not None for cost in ids) == 1
    store.reserve_cost("speech_tts", 600, {"job_id": other_job})
    assert store.get_job_budget(job_id)["reserved_krw"] == store.get_job_budget(other_job)["reserved_krw"] == 600


def test_job_cap_cas_rejects_stale_hash_and_reconfiguration_never_resets_costs(tmp_path):
    store = Store(tmp_path)
    job_id = store.create_job({"id": "cas", "title": "예산"})["id"]
    unset = store.get_job_budget(job_id)
    assert unset["cap_krw"] is unset["remaining_krw"] is None
    configured = store.set_job_budget(job_id, 1000, "first", expected_hash=unset["hash"])
    reservation = store.reserve_cost("model", 200, {"job_id": job_id})
    store.settle_cost(reservation["id"], 150, {})
    with pytest.raises(WorkflowError, match="설정이 변경"):
        store.set_job_budget(job_id, 1000, "stale", expected_hash=unset["hash"])
    again = store.set_job_budget(job_id, 1000, "second", expected_hash=configured["hash"])
    assert again["spent_krw"] == 150 and again["remaining_krw"] == 850
    assert again["configured_by"] == "second" and again["hash"] != configured["hash"]


@pytest.mark.parametrize("cap", [True, False, -1, 0, 1.5, float("nan"), float("inf"), "1000", None, 10001])
def test_invalid_job_caps_are_rejected_without_mutation(tmp_path, cap):
    store = Store(tmp_path)
    job_id = store.create_job({"id": "invalid", "title": "예산"})["id"]
    before = store.get_job_budget(job_id)
    with pytest.raises(WorkflowError, match="예산"):
        store.set_job_budget(job_id, cap, "test", expected_hash=before["hash"])
    assert store.get_job_budget(job_id) == before


@pytest.mark.parametrize("actor,expected_hash", [("", "0" * 64), ("op", None), ("op", "bad")])
def test_job_cap_requires_actor_and_current_hash(tmp_path, actor, expected_hash):
    store = Store(tmp_path)
    job_id = store.create_job({"id": "invalid-review", "title": "예산"})["id"]
    with pytest.raises(WorkflowError):
        store.set_job_budget(job_id, 1000, actor, expected_hash=expected_hash)
    assert store.get_job_budget(job_id)["cap_krw"] is None


def test_job_without_cap_and_jobless_rss_keep_global_budget_behavior(tmp_path):
    store = Store(tmp_path)
    capped, _ = job_with_cap(store)
    plain = store.create_job({"id": "plain", "title": "기존 업무"})["id"]
    store.reserve_cost("model", 1000, {"job_id": capped})
    store.reserve_cost("model", 2000, {"job_id": plain})
    store.reserve_cost("rss_model", 2000, {})
    assert store.get_job_budget(plain)["reserved_krw"] == 2000
    assert store.get_job_budget(plain)["cap_krw"] is None
    assert store.budget()["reserved_krw"] == 5000


def test_job_settlement_records_real_overrun_and_blocks_further_calls(tmp_path):
    store = Store(tmp_path)
    job_id, _ = job_with_cap(store)
    reservation = store.reserve_cost("model", 900, {"job_id": job_id})
    store.settle_cost(reservation["id"], 1100, {"billing_observed": True})
    budget = store.get_job_budget(job_id)
    assert budget["spent_krw"] == 1100 and budget["overrun_krw"] == 100 and budget["remaining_krw"] == -100
    with pytest.raises(WorkflowError, match="업무의 합산 예산"):
        store.reserve_cost("speech_tts", 1, {"job_id": job_id})
