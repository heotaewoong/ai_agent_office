"""Synthetic arithmetic and refusal cases; no portfolio, network or broker."""

import copy
import json
from decimal import Inexact, getcontext, localcontext

import pytest

from office.stock_backtest import build_review_contract, run_backtest


@pytest.fixture
def request_data():
    days = ["2020-01-02", "2020-01-03", "2020-01-06", "2020-01-07"]
    bars = []
    for day, price in zip(days, [100, 110, 120, 130]):
        bars.append({"date": day, "as_of": day, "source": "synthetic-fixture", "symbol": "TEST",
                     "price_basis": "raw",
                     "open_at": f"{day}T09:00:00+00:00", "close_at": f"{day}T16:00:00+00:00",
                     "available_at": f"{day}T16:01:00+00:00", "final": True,
                     "open": price, "high": price + 10, "low": price - 10,
                     "close": price + 5, "currency": "USD"})
    return {"evidence_kind": "synthetic", "symbol": "TEST", "data_as_of": "2020-01-08T00:00:00+00:00",
            "rule": {"kind": "explicit_buy_signals", "id": "synthetic-only-v1",
                     "source": "synthetic-test-spec", "confirmed": True,
                     "calibration_end": "2019-12-30", "frozen_at": "2019-12-31T12:00:00+00:00",
                     "max_units": 4},
            "window": {"start": days[0], "end": days[-1]},
            "sessions": days, "calendar_source": "synthetic-test-calendar", "bars": bars,
            "signals": [{"date": day, "decided_at": f"{day}T17:00:00+00:00", "units": units,
                         "symbol": "TEST", "side": "buy"}
                        for day, units in zip(days, [2, 1, 1])],
            "initial_cash": "1000", "assumptions": {
                "currency": "USD", "base_currency": "USD", "fx": "same_currency_only",
                "price_basis": "raw", "corporate_actions": "none_in_window",
                "dividends": "excluded", "taxes": "excluded", "fee_bps": 100, "slippage_bps": 100}}


@pytest.mark.parametrize("data", [None, {}, {"bars": [], "signals": []}])
def test_absent_real_rule_and_prices_never_produce_a_return(data):
    result = run_backtest(data)
    assert result["status"] == "needs_data"
    assert result["reasons"]
    assert "return_pct" not in result
    assert result["order_eligible"] is False


def test_four_hand_calculated_points_use_next_open_and_separate_costs(request_data):
    result = run_backtest(request_data)
    assert result["status"] == "simulated"
    first, second, third = result["trades"]
    assert (first["signal_date"], first["execution_date"]) == ("2020-01-02", "2020-01-03")
    assert (first["raw_open"], first["fill_price"], first["fee"], first["cash_after"]) == (
        "110", "111.1", "2.222", "775.578")
    assert (second["cash_after"], second["units_after"]) == ("653.166", 3)
    assert (third["cash_after"], third["units_after"]) == ("520.553", 4)
    assert (result["terminal_equity"], result["pnl"], result["return_pct"]) == (
        "1060.553", "60.553", "6.0553")
    assert result["evidence_kind"] == "synthetic"
    assert result["rule_compliance"] == "not_verified"
    assert result["human_hand_check"] == "pending"
    assert result["order_eligible"] is False
    assert result["assumptions"] == request_data["assumptions"]


@pytest.mark.parametrize("field,value,reason", [
    ("available_at", "2020-01-03T10:00:00+00:00", "unavailable_at_decision"),
    ("available_at", "2020-01-02T15:59:00+00:00", "bar_time_order"),
    ("available_at", "2020-01-02T16:01:00", "timestamp"),
    ("as_of", "2020-01-01", "bar_as_of"),
    ("final", False, "unconfirmed_bar"),
    ("currency", "KRW", "currency"),
    ("symbol", "OTHER", "symbol"),
    ("price_basis", "split_adjusted", "price_basis"),
    ("source", "", "source"),
    ("close", None, "number"), ("open", 0, "number"),
    ("close", float("nan"), "json_input"), ("open", float("inf"), "json_input"),
    ("low", 200, "ohlc"), ("high", 1, "ohlc"), ("open", True, "number"),
])
def test_bad_price_rows_never_yield_partial_performance(request_data, field, value, reason):
    request_data["bars"][0][field] = value
    result = run_backtest(request_data)
    assert result["status"] == "needs_data"
    assert reason in " ".join(result["reasons"])
    assert "trades" not in result and "return_pct" not in result


@pytest.mark.parametrize("mutation,reason", [
    (lambda r: r["bars"].reverse(), "bar_order"),
    (lambda r: r["bars"].append(copy.deepcopy(r["bars"][-1])), "bar_order"),
    (lambda r: r["bars"].pop(1), "calendar_coverage"),
    (lambda r: r["bars"].clear(), "insufficient_bars"),
    (lambda r: r["signals"].reverse(), "signal_order"),
    (lambda r: r["signals"].append(copy.deepcopy(r["signals"][-1])), "signal_order"),
    (lambda r: r["rule"].update(confirmed=False), "rule_unconfirmed"),
    (lambda r: r["rule"].update(calibration_end="2020-01-02"), "evaluation_not_held_out"),
    (lambda r: r["rule"].update(frozen_at="2020-01-02T08:00:00+00:00"), "rule_not_frozen"),
    (lambda r: r.update(data_as_of="2020-01-07T16:00:00+00:00"), "snapshot_before_data"),
    (lambda r: r["signals"][0].update(decided_at="2020-01-03T09:00:00+00:00"), "late_signal"),
    (lambda r: r["signals"][-1].update(date="2020-01-07"), "no_next_bar"),
    (lambda r: r["signals"][0].update(units=0), "units"),
    (lambda r: r["signals"][0].update(units=1.5), "units"),
    (lambda r: r["signals"][0].update(side="sell"), "side"),
    (lambda r: r["signals"][0].update(symbol="OTHER"), "symbol"),
    (lambda r: r["rule"].update(max_units=3), "position_limit"),
    (lambda r: r.update(initial_cash="224.421"), "insufficient_cash"),
    (lambda r: r["assumptions"].update(base_currency="KRW"), "fx_unsupported"),
    (lambda r: r["assumptions"].update(corporate_actions="unknown"), "corporate_actions"),
    (lambda r: r["assumptions"].update(price_basis="split_adjusted"), "price_basis"),
    (lambda r: r["assumptions"].update(dividends="included"), "dividends"),
    (lambda r: r["assumptions"].update(fee_bps=-1), "fee_bps"),
    (lambda r: r["assumptions"].update(slippage_bps=10000), "slippage_bps"),
])
def test_invalid_contracts_refuse_without_repairing_inputs(request_data, mutation, reason):
    mutation(request_data)
    before = copy.deepcopy(request_data)
    result = run_backtest(request_data)
    assert result["status"] == "needs_data"
    assert reason in " ".join(result["reasons"])
    assert "return_pct" not in result
    assert request_data == before


def test_all_missing_prices_are_not_zero_filled(request_data):
    for row in request_data["bars"]:
        row["open"] = row["close"] = None
    assert run_backtest(request_data)["status"] == "needs_data"


def test_unchanged_input_replays_identically_even_with_different_decimal_context(request_data):
    before = copy.deepcopy(request_data)
    first = run_backtest(request_data)
    previous = getcontext().prec
    try:
        getcontext().prec = 4
        second = run_backtest(json.loads(json.dumps(request_data)))
    finally:
        getcontext().prec = previous
    assert first == second
    assert request_data == before
    request_data["assumptions"]["fee_bps"] = 0
    changed = run_backtest(request_data)
    assert first["input_hash"] != changed["input_hash"]
    assert first["result_hash"] != changed["result_hash"]


def test_explicit_no_buy_run_preserves_cash(request_data):
    request_data["signals"] = []
    result = run_backtest(request_data)
    assert result["status"] == "simulated"
    assert result["trades"] == []
    assert (result["terminal_equity"], result["return_pct"]) == ("1000", "0")


def test_caller_decimal_traps_and_exponents_cannot_change_replay(request_data):
    first = run_backtest(request_data)
    with localcontext() as context:
        context.Emax = 2
        context.traps[Inexact] = True
        second = run_backtest(request_data)
    assert second == first


@pytest.mark.parametrize("valid", [True, False])
def test_review_contract_keeps_same_evidence_pending_and_cannot_authorize_orders(request_data, valid):
    result = run_backtest(request_data if valid else {})
    contract = build_review_contract(result)
    assert contract["input_hash"] == result["input_hash"]
    assert contract["result_hash"] == result["result_hash"]
    assert [role["role"] for role in contract["roles"]] == ["data", "risk", "opposition", "chair"]
    assert all(role["status"] == "pending" for role in contract["roles"])
    assert all(role["input_hash"] == result["input_hash"] for role in contract["roles"])
    assert contract["human_decision"] == "pending"
    assert contract["independent_source_verification"] == "not_performed"
    assert contract["model_execution"] == "not_performed"
    assert contract["order_eligible"] is False
    assert contract["state"] == ("review_required" if valid else "needs_data")


@pytest.mark.parametrize("mutation", [
    lambda report: report.update(pnl="999999"),
    lambda report: report.update(input_hash=None),
    lambda report: report.update(result_hash="broken"),
    lambda report: report.clear(),
])
def test_changed_or_missing_evidence_is_not_a_complete_review_package(request_data, mutation):
    result = run_backtest(request_data)
    mutation(result)
    contract = build_review_contract(result)
    assert contract["state"] == "needs_data"
    assert contract["result_integrity"] == "invalid"
    assert contract["human_decision"] == "pending"
    assert contract["order_eligible"] is False


def test_bare_simulated_label_does_not_substitute_for_evidence():
    contract = build_review_contract({"status": "simulated"})
    assert contract["state"] == "needs_data"
    assert contract["order_eligible"] is False
