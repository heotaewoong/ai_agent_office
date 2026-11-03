"""Offline, single-asset buy-signal replay; never an order or strategy approval.

Callers supply a JSON object prepared from their existing read-only data. This
module performs no I/O. Explicit signals are NOT proof of rule compliance.
Raw OHLC, no corporate actions, integer units and one currency only. Dividends
and taxes are excluded; Decimal precision is 28 with no currency/tick rounding.
Missing or unsupported inputs produce needs_data without performance numbers.
"""

import hashlib
import json
from datetime import date, datetime
from decimal import Context, Decimal, DecimalException, localcontext


class _Invalid(ValueError):
    pass


def _require(condition, reason):
    if not condition:
        raise _Invalid(reason)


def _text(value):
    return isinstance(value, str) and bool(value.strip())


def _day(value):
    _require(isinstance(value, str) and len(value) == 10, "date")
    parsed = date.fromisoformat(value)
    _require(parsed.isoformat() == value, "date")
    return parsed


def _stamp(value):
    _require(isinstance(value, str), "timestamp")
    parsed = datetime.fromisoformat(value)
    _require(parsed.tzinfo is not None and parsed.utcoffset() is not None, "timestamp")
    return parsed


def _number(value, positive=True, reason="number"):
    _require(isinstance(value, (str, int, float)) and not isinstance(value, bool), reason)
    _require(len(str(value)) <= 80, reason)
    number = Decimal(str(value))
    _require(number.is_finite(), reason)
    _require(Decimal("1e-12") <= number <= Decimal("1e18") if positive
             else Decimal(0) <= number <= Decimal("1e18"), reason)
    return number


def _units(value):
    _require(type(value) is int and 0 < value <= 1_000_000_000, "units")
    return value


def _money(value):
    return format(value, "f").rstrip("0").rstrip(".") if "." in format(value, "f") else format(value, "f")


def _hashed(value):
    return hashlib.sha256(json.dumps(value, sort_keys=True, ensure_ascii=False,
                                     separators=(",", ":"), allow_nan=False).encode("utf-8")).hexdigest()


def _finish(result):
    result["order_eligible"] = False
    result["result_hash"] = _hashed(result)
    return result


def _simulate(data, input_hash):
    _require(isinstance(data, dict), "request")
    _require(data.get("evidence_kind") in ("synthetic", "historical"), "evidence_kind")
    symbol = data.get("symbol")
    _require(_text(symbol), "symbol")
    rule, window, assumptions = data["rule"], data["window"], data["assumptions"]
    _require(isinstance(rule, dict) and rule.get("confirmed") is True, "rule_unconfirmed")
    _require(rule.get("kind") == "explicit_buy_signals", "rule_kind")
    _require(_text(rule.get("id")) and _text(rule.get("source")), "rule_source")
    start, end = _day(window["start"]), _day(window["end"])
    _require(start < end, "evaluation_window")
    _require(_day(rule["calibration_end"]) < start, "evaluation_not_held_out")
    frozen = _stamp(rule["frozen_at"])
    _require(frozen.date() < start, "rule_not_frozen")
    max_units = _units(rule["max_units"])
    snapshot = _stamp(data["data_as_of"])
    _require(assumptions["price_basis"] == "raw", "price_basis")
    _require(assumptions["corporate_actions"] == "none_in_window", "corporate_actions")
    _require(assumptions["dividends"] == "excluded", "dividends")
    _require(assumptions["taxes"] == "excluded", "taxes")
    currency = assumptions["currency"]
    _require(isinstance(currency, str) and len(currency) == 3 and currency.isascii()
             and currency.isalpha() and currency.isupper(), "currency")
    _require(assumptions["base_currency"] == currency
             and assumptions["fx"] == "same_currency_only", "fx_unsupported")
    fee_bps = _number(assumptions["fee_bps"], positive=False, reason="fee_bps")
    slippage_bps = _number(assumptions["slippage_bps"], positive=False, reason="slippage_bps")
    _require(fee_bps < 10000, "fee_bps")
    _require(slippage_bps < 10000, "slippage_bps")
    initial = _number(data["initial_cash"])
    bars, sessions = data["bars"], data["sessions"]
    _require(isinstance(bars, list) and len(bars) >= 2, "insufficient_bars")
    _require(isinstance(sessions, list) and _text(data.get("calendar_source")), "calendar_source")
    calendar = [_day(day) for day in sessions]
    _require(calendar == sorted(set(calendar)) and calendar
             and calendar[0] == start and calendar[-1] == end, "calendar_order_window")
    dates = [_day(bar["date"]) for bar in bars]
    _require(dates == sorted(set(dates)), "bar_order")
    _require(dates == calendar, "calendar_coverage")
    prices = []
    for bar, day in zip(bars, dates):
        _require(bar.get("final") is True, "unconfirmed_bar")
        _require(_text(bar.get("source")), "source")
        _require(_day(bar["as_of"]) == day, "bar_as_of")
        _require(bar["currency"] == currency, "currency")
        _require(bar["symbol"] == symbol, "symbol")
        _require(bar["price_basis"] == "raw", "price_basis")
        opening, closing, available = (_stamp(bar[key]) for key in ("open_at", "close_at", "available_at"))
        _require(opening.date() == closing.date() == day and opening < closing <= available,
                 "bar_time_order")
        _require(frozen < opening, "rule_not_frozen")
        _require(available <= snapshot, "snapshot_before_data")
        op, hi, lo, cl = (_number(bar[key]) for key in ("open", "high", "low", "close"))
        _require(lo <= min(op, cl) <= max(op, cl) <= hi, "ohlc")
        prices.append((op, cl, opening, closing, available))
    _require(all(prices[i][3] < prices[i + 1][2] for i in range(len(prices) - 1)), "bar_time_order")
    signals = data["signals"]
    _require(isinstance(signals, list), "signals")
    signal_days = [_day(signal["date"]) for signal in signals]
    _require(signal_days == sorted(set(signal_days)), "signal_order")
    cash, held, trades = initial, 0, []
    for signal, day in zip(signals, signal_days):
        _require(signal["side"] == "buy", "side")
        _require(signal["symbol"] == symbol, "symbol")
        _require(day in dates, "signal_outside_window")
        index = dates.index(day)
        _require(index + 1 < len(prices), "no_next_bar")
        decided = _stamp(signal["decided_at"])
        _require(prices[index][4] <= decided, "unavailable_at_decision")
        _require(decided < prices[index + 1][2], "late_signal")
        count = _units(signal["units"])
        _require(held + count <= max_units, "position_limit")
        raw_open = prices[index + 1][0]
        fill_price = raw_open * (1 + slippage_bps / 10000)
        notional = fill_price * count
        fee = notional * fee_bps / 10000
        _require(notional + fee <= cash, "insufficient_cash")
        cash -= notional + fee
        held += count
        trades.append({"signal_date": day.isoformat(), "decided_at": signal["decided_at"],
                       "execution_date": dates[index + 1].isoformat(), "units": count,
                       "raw_open": _money(raw_open), "fill_price": _money(fill_price),
                       "fee": _money(fee), "cash_after": _money(cash), "units_after": held})
    terminal = cash + held * prices[-1][1]
    return _finish({"status": "simulated", "evidence_kind": data["evidence_kind"],
                    "input_hash": input_hash, "rule": rule, "window": window,
                    "data_as_of": data["data_as_of"], "calendar_source": data["calendar_source"],
                    "sources": sorted({bar["source"] for bar in bars}), "assumptions": assumptions,
                    "symbol": symbol, "currency": currency, "trades": trades, "cash": _money(cash), "units": held,
                    "terminal_equity": _money(terminal), "pnl": _money(terminal - initial),
                    "return_pct": _money((terminal / initial - 1) * 100),
                    "rule_compliance": "not_verified", "human_hand_check": "pending",
                    "warnings": ["Explicit signals: strategy compliance and hindsight selection are not verified.",
                                 "Source authenticity, calendar completeness and corporate actions require independent review.",
                                 "No dividends, taxes, FX, selling or broker/currency tick rounding; not total or realized return.",
                                 "Decimal precision 28; positive amounts limited to 1e-12..1e18; integer units at most 1e9."]})


def run_backtest(request: dict | None) -> dict:
    """Replay explicit buys or return needs_data; never load or change state.

    Required JSON fields are demonstrated by the synthetic test fixture. A
    declaration such as rule.confirmed is caller metadata, not human approval.
    Historical input authenticity and rule-derived signals remain unverified.
    """
    input_hash = None
    try:
        input_hash = _hashed(request)
        data = json.loads(json.dumps(request, allow_nan=False))
    except (TypeError, ValueError, OverflowError):
        return _finish({"status": "needs_data", "input_hash": None, "reasons": ["json_input"]})
    try:
        with localcontext(Context(prec=28)):
            return _simulate(data, input_hash)
    except _Invalid as exc:
        reason = str(exc)
    except (KeyError, TypeError, ValueError, IndexError, DecimalException, OverflowError):
        reason = "missing_or_malformed_input"
    return _finish({"status": "needs_data", "input_hash": input_hash, "reasons": [reason]})


def build_review_contract(result: dict) -> dict:
    """Prepare questions for existing reviewers; no council/model is executed."""
    result = result if isinstance(result, dict) else {}
    input_hash, result_hash = result.get("input_hash"), result.get("result_hash")
    try:
        integrity = (isinstance(input_hash, str) and len(input_hash) == 64
                     and all(char in "0123456789abcdef" for char in input_hash)
                     and _hashed({key: value for key, value in result.items() if key != "result_hash"}) == result_hash)
    except (TypeError, ValueError, OverflowError):
        integrity = False
    roles = [
        ("data", "Check as_of/available_at, OHLC, calendar, independent sources and corporate actions."),
        ("risk", "Check product risk, units/cash limits, fees, dividends, FX and omitted cases."),
        ("opposition", "Read prior reviews; challenge leakage, rule compliance and candidate selection."),
        ("chair", "Summarize adopt/hold/more evidence options; wait for the human decision."),
    ]
    return {"state": "review_required" if integrity and result.get("status") == "simulated" else "needs_data",
            "result_integrity": "valid" if integrity else "invalid",
            "input_hash": input_hash, "result_hash": result_hash,
            "roles": [{"role": role, "question": question, "status": "pending",
                       "input_hash": input_hash, "result_hash": result_hash} for role, question in roles],
            "human_decision": "pending", "independent_source_verification": "not_performed",
            "model_execution": "not_performed", "order_eligible": False}
