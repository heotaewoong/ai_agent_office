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
