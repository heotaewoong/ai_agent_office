import json
import time
from datetime import datetime

import pytest
from fastapi.testclient import TestClient

from office import stocks
from office.api import create_app
from office.store import Store


@pytest.fixture(autouse=True)
def fixed_clock(monkeypatch):
    monkeypatch.setattr(stocks, "_now", lambda: datetime.fromisoformat("2026-11-03T09:00:00+09:00"))

TARGETS = [{"type": "core", "label": "코어 지수", "target_pct": 50}, {"type": "dividend", "label": "배당·안전", "target_pct": 10},
           {"type": "sector", "label": "섹터·테마", "target_pct": 15}, {"type": "option", "label": "옵션 인컴", "target_pct": 5},
           {"type": "crypto", "label": "암호화폐", "target_pct": 10}, {"type": "stock", "label": "개별주", "target_pct": 10}]
HOLDINGS = [
    {"id": "us-voo", "account": "해외", "name": "VOO", "ticker": "VOO", "market": "US", "type": "core", "qty": 1, "qty_note": "시트",
     "value_krw": 1_000_000, "cost_krw": 900_000, "price_date": "2026-10-08"},
    {"id": "us-ethu", "account": "해외", "name": "ETHU", "ticker": "ETHU", "market": "US", "type": "crypto", "qty": 10, "qty_note": "시트",
     "value_krw": 600_000, "cost_krw": 800_000, "price_date": "2026-10-08"},
    {"id": "kr-kakao", "account": "ISA", "name": "카카오", "ticker": "035720", "market": "KR", "type": "stock", "qty": 4,
     "value_krw": 200_000, "cost_krw": 300_000},
    {"id": "kr-luni", "account": "ISA", "name": "루닛", "ticker": "328130", "market": "KR", "type": "stock", "qty": 2,
     "value_krw": 100_000, "cost_krw": 150_000},
    {"id": "kr-spac", "account": "종합", "name": "스팩", "ticker": "", "market": "KR", "type": "stock", "qty": 15,
     "value_krw": 100_000, "cost_krw": 100_000},
]


def portfolio(tmp_path, history=None):
    source = tmp_path / "source"
    source.mkdir()
    (source / "dashboard_holdings.json").write_text(json.dumps(HOLDINGS, ensure_ascii=False), encoding="utf-8")
    (source / "dashboard_targets.json").write_text(json.dumps(TARGETS, ensure_ascii=False), encoding="utf-8")
    (source / "dashboard_history.json").write_text(json.dumps(history or [{"date": "2026-10-09", "fx": 1300.0}]), encoding="utf-8")
    state = tmp_path / "state"
    stocks.import_portfolio(state, source)
    return state


def chart(price, prev, high=None, offset=0, stamp=1793390400, ccy="USD"):
    day = 86400
    return {"chart": {"result": [{"meta": {"regularMarketPrice": price, "regularMarketTime": stamp, "gmtoffset": offset,
                                            "currency": ccy, "fiftyTwoWeekHigh": high},
                                   "timestamp": [stamp - 2 * day, stamp - day, stamp],
                                   "indicators": {"quote": [{"close": [prev * 0.99, prev, price]}]}}]}}


def fake_fetch(prices):
    calls = []

    def fetch(url, timeout=8):
        calls.append(url)
        for key, payload in prices.items():
            if f"/chart/{key}?" in url or url.endswith(f"/stock/{key}/basic"):
                if isinstance(payload, Exception):
                    raise payload
                return payload
        raise OSError("not found")
    fetch.calls = calls
    return fetch


def by_id(status, item_id):
    return next(item for item in status["items"] if item["id"] == item_id)


def test_missing_portfolio_reports_not_connected(tmp_path):
    status = stocks.stocks_status(tmp_path)
    assert status["configured"] is False and status["items"] == []


def test_import_validates_and_keeps_user_files_unchanged(tmp_path):
    state = portfolio(tmp_path)
    folder = state / "stocks"
    assert json.loads((folder / "holdings.json").read_text(encoding="utf-8")) == HOLDINGS
    assert json.loads((folder / "meta.json").read_text(encoding="utf-8"))["holdings_date"] == "2026-10-09"
    bad = tmp_path / "bad"
    bad.mkdir()
    (bad / "holdings.json").write_text(json.dumps([{**HOLDINGS[0], "type": "gamble"}]), encoding="utf-8")
    (bad / "targets.json").write_text(json.dumps(TARGETS), encoding="utf-8")
    with pytest.raises(stocks.StocksError):
        stocks.import_portfolio(tmp_path / "other", bad)
    (bad / "holdings.json").write_text(json.dumps(HOLDINGS), encoding="utf-8")
    (bad / "targets.json").write_text(json.dumps(TARGETS[:3]), encoding="utf-8")
    with pytest.raises(stocks.StocksError, match="100%"):
        stocks.import_portfolio(tmp_path / "other", bad)


def test_status_flags_drift_and_concentration_without_won_amounts_or_trade_orders(tmp_path):
    status = stocks.stocks_status(portfolio(tmp_path))
    assert status["configured"] is True
    titles = " ".join(item["title"] + " " + item["stateLabel"] for item in status["items"])
    # 2,000,000 total: core 50%, crypto 30%, stock 20%
    assert by_id(status, "stocks-type-crypto")["needsHuman"] is True
    assert "목표보다 20.0%p 많아요" in by_id(status, "stocks-type-crypto")["stateLabel"]
    assert by_id(status, "stocks-concentration")["title"] == "가장 큰 종목 VOO 50.0%"
    assert "2배 레버리지" not in by_id(status, "stocks-concentration")["stateLabel"]
    assert "core" not in [i["id"].removeprefix("stocks-type-") for i in status["items"] if i["needsHuman"]]
    for banned in ("사세요", "파세요", "매수하세요", "매도하세요", "1,000,000", "2,000,000"):
        assert banned not in titles
    assert by_id(status, "stocks-quotes")["actions"] == [{"id": "stocks-refresh", "label": "시세 새로 확인"}]
    assert "2026-10-09" in by_id(status, "stocks-data")["title"]
    assert "티커가 없는 1종목" in by_id(status, "stocks-data")["stateLabel"]


def test_monthly_plan_splits_by_target_and_fills_gaps_first():
    types = [{"type": t["type"], "label": t["label"], "target_pct": t["target_pct"], "value_krw": v}
             for t, v in zip(TARGETS, [150_000, 73_000, 155_000, 61_000, 245_000, 316_000])]
    plan = stocks.monthly_plan(types, 1_000_000, 500_000)
    assert sum(p["krw"] for p in plan["by_target"]) == 500_000
    assert sum(p["krw"] for p in plan["fill_gap"]) == 500_000
    assert not {p["type"] for p in plan["fill_gap"]} & {"crypto", "stock"}  # 이미 목표보다 많은 유형은 채우지 않는다
    assert plan["fill_gap"][0]["type"] == "core" and plan["fill_gap"][0]["krw"] == 394_000
    assert all(p["krw"] % 1000 == 0 for p in plan["by_target"])


def test_refresh_reprices_with_sources_dates_and_never_edits_holdings(tmp_path):
    state = portfolio(tmp_path)
    before = (state / "stocks" / "holdings.json").read_bytes()
    fetch = fake_fetch({
        "KRW%3DX": chart(1400.0, 1390.0, ccy="KRW"),
        "VOO": chart(700.0, 710.0, high=720.0),
        "ETHU": chart(30.0, 33.0, high=100.0),
        "035720.KS": chart(40_000.0, 39_000.0, high=60_000.0, offset=32400, ccy="KRW"),
        "328130.KS": OSError("wrong exchange"),
        "328130.KQ": chart(20_000.0, 19_000.0, offset=32400, ccy="KRW"),
        "QQQ": chart(600.0, 606.0), "SCHD": chart(30.0, 29.7), "ETH-USD": chart(4000.0, 3900.0), "BTC-USD": chart(100_000.0, 99_000.0),
    })
    record = stocks.refresh_quotes(state, fetch)
    assert (state / "stocks" / "holdings.json").read_bytes() == before
    assert record["fx"]["rate"] == 1400.0 and record["fx"]["source"] == stocks.QUOTE_SOURCE
    assert record["quotes"]["328130.KS"]["symbol"] == "328130.KQ"
    assert record["failed"] == []
    assert not any("chart/%EC" in url for url in fetch.calls)
    detail = stocks.stocks_detail(state)
    rows = {r["id"]: r for r in detail["rows"]}
    assert rows["us-voo"]["value_krw"] == 980_000 and rows["us-voo"]["basis"] == "quote"
    assert rows["kr-kakao"]["value_krw"] == 160_000
    assert rows["kr-spac"]["basis"] == "file" and rows["kr-spac"]["value_krw"] == 100_000
    status = stocks.stocks_status(state)
    movers = by_id(status, "stocks-movers")
    assert "ETHU" in movers["title"] and "-9.09%" in movers["title"] and "확인 못 함" in movers["stateLabel"]
    draw = by_id(status, "stocks-drawdown")
    assert "ETHU -70%" in draw["title"] and "카카오 -33%" in draw["title"] and draw["needsHuman"] is True
    assert "원달러 1,400.00원" in by_id(status, "stocks-market")["title"]
    history = json.loads((state / "stocks" / "history.json").read_text(encoding="utf-8"))
    assert [r["date"] for r in history][0] == "2026-10-09" and len(history) == 2
    assert history[-1]["total_krw"] == sum(r["value_krw"] for r in detail["rows"])


def test_failed_quotes_keep_file_values_and_are_counted(tmp_path):
    state = portfolio(tmp_path)
    record = stocks.refresh_quotes(state, fake_fetch({"VOO": chart(700.0, 710.0)}))
    assert record["fx"] is None and "ETHU" in record["failed"]
    rows = {r["id"]: r for r in stocks.stocks_detail(state)["rows"]}
    assert rows["us-voo"]["basis"] == "file" and rows["us-voo"]["value_krw"] == 1_000_000  # 환율이 없으면 다시 계산하지 않는다
    assert "확인 못 함" in by_id(stocks.stocks_status(state), "stocks-quotes")["stateLabel"]


def test_refresh_api_requires_operator_session_and_space_carries_stocks(tmp_path, monkeypatch):
    state = portfolio(tmp_path)
    store = Store(state)
    client = TestClient(create_app(store), base_url="http://localhost:8510")
    token = client.get("/api/session").json()["csrf"]
    headers = {"Origin": "http://localhost:3110", "X-Office-CSRF": token}
    space = client.get("/api/space").json()
    assert space["stocks"]["configured"] is True and space["stocks"]["version"] == 1
    assert "value_krw" not in json.dumps(space["stocks"])
    assert client.post("/api/stocks/refresh", headers={"Origin": "http://localhost:3110"}).status_code == 403
    monkeypatch.setattr(stocks, "_http_json", fake_fetch({"VOO": chart(700.0, 710.0)}))
    response = client.post("/api/stocks/refresh", headers=headers)
    assert response.status_code == 202 and response.json()["started"] is True
    for _ in range(50):
        if json.loads((state / "stocks" / "quotes.json").read_text(encoding="utf-8")).get("status") == "done":
            break
        time.sleep(0.05)
    assert client.get("/api/stocks").json()["quotes"]["status"] == "done"
    assert any(e["kind"] == "stocks_refresh_requested" for e in store.events(limit=5))


def test_refresh_api_without_portfolio_is_a_clear_conflict(tmp_path):
    client = TestClient(create_app(Store(tmp_path)), base_url="http://localhost:8510")
    token = client.get("/api/session").json()["csrf"]
    response = client.post("/api/stocks/refresh", headers={"Origin": "http://localhost:3110", "X-Office-CSRF": token})
    assert response.status_code == 409 and "포트폴리오" in response.json()["detail"]
    assert client.get("/api/space").json()["stocks"]["configured"] is False


def quality_portfolio(*, quote_changes=None, fx_changes=None):
    quote = {"price": 700.0, "ccy": "USD", "as_of": "2026-11-02", "at": "2026-11-03T06:00:00+09:00",
             "source": "synthetic public quote", "change_pct": -1.0, "high52": 720.0}
    fx = {"rate": 1400.0, "ccy": "KRW", "as_of": "2026-11-03T06:00:00+09:00", "source": "synthetic FX"}
    return {"holdings": [HOLDINGS[0]], "targets": TARGETS, "history": [{"date": "2026-10-09", "fx": 1300}],
            "meta": {"holdings_date": "2026-10-09"}, "settings": dict(stocks.DEFAULT_SETTINGS),
            "quotes": {"status": "done", "refreshed_at": "2026-11-03T08:29:34+09:00",
                       "fx": {**fx, **(fx_changes or {})}, "quotes": {"VOO": {**quote, **(quote_changes or {})}}, "failed": []}}


@pytest.mark.parametrize("changes, reason", [
    ({"as_of": "2024-07-20", "at": "2024-07-20T05:00:00+09:00"}, "stale"),
    ({"at": "2026-11-03T09:03:00+09:00"}, "future"),
    ({"at": None}, "timestamp_missing"),
    ({"at": "2026-11-03T06:00:00"}, "timestamp_invalid"),
    ({"as_of": None}, "date_invalid"),
    ({"as_of": "2026-11-04"}, "future"),
    ({"as_of": "2026-10-01"}, "date_mismatch"),
    ({"ccy": "KRW"}, "currency_mismatch"),
    ({"ccy": ""}, "currency_mismatch"),
    ({"price": 0}, "price_invalid"),
    ({"price": float("nan")}, "price_invalid"),
    ({"price": "700"}, "price_invalid"),
    ({"source": ""}, "source_missing"),
])
def test_untrusted_quote_keeps_file_value_and_reports_reason(changes, reason):
    data = quality_portfolio(quote_changes=changes)
    before = json.dumps(data, sort_keys=True)
    view = stocks.evaluate(data)
    assert view["rows"][0]["basis"] == "file"
    assert view["rows"][0]["value_krw"] == 1_000_000
    assert reason in view["rows"][0]["valuation_reasons"]
    assert view["data_quality"]["status"] == "invalid"
    assert view["data_quality"]["current_count"] == 0
    assert json.dumps(data, sort_keys=True) == before


def test_fresh_quote_uses_cross_day_us_date_and_exact_fx_without_mutation():
    data = quality_portfolio()
    before = json.dumps(data, sort_keys=True)
    view = stocks.evaluate(data)
    assert view["rows"][0]["value_krw"] == 980_000
    assert view["data_quality"]["status"] == "current"
    assert view["data_quality"]["current_count"] == 1
    assert view["data_quality"]["fallback_count"] == 0
    assert view["rows"][0]["quote_quality"]["as_of"] == "2026-11-02"
    assert view["rows"][0]["quote_quality"]["available_at"] == "2026-11-03T08:29:34+09:00"
    assert json.dumps(data, sort_keys=True) == before


@pytest.mark.parametrize("changes, reason", [
    ({"as_of": "2024-07-20T05:00:00+09:00"}, "fx_stale"),
    ({"as_of": "2026-11-03T09:03:00+09:00"}, "fx_future"),
    ({"as_of": None}, "fx_timestamp_missing"),
    ({"ccy": "USD"}, "fx_currency_mismatch"),
    ({"ccy": None}, "fx_currency_mismatch"),
    ({"rate": -1400}, "fx_price_invalid"),
])
def test_invalid_fx_never_reprices_us_holding(changes, reason):
    view = stocks.evaluate(quality_portfolio(fx_changes=changes))
    assert view["total_krw"] == 1_000_000
    assert view["rows"][0]["basis"] == "file"
    assert reason in view["rows"][0]["valuation_reasons"]


def test_weekend_quote_within_seven_day_policy_is_usable():
    data = quality_portfolio(quote_changes={"as_of": "2026-10-30", "at": "2026-10-31T05:00:00+09:00"})
    assert stocks.evaluate(data)["data_quality"]["status"] == "current"


def test_clock_skew_allows_two_minutes_but_not_three():
    data = quality_portfolio(quote_changes={"as_of": "2026-11-03", "at": "2026-11-03T09:02:00+09:00"})
    data["quotes"]["refreshed_at"] = "2026-11-03T09:00:00+09:00"
    assert stocks.evaluate(data)["rows"][0]["basis"] == "quote"


def test_two_minute_clock_skew_also_allows_crossing_midnight(monkeypatch):
    monkeypatch.setattr(stocks, "_now", lambda: datetime.fromisoformat("2026-11-03T23:59:00+09:00"))
    data = quality_portfolio(quote_changes={"as_of": "2026-11-04", "at": "2026-11-04T00:00:00+09:00"})
    data["quotes"]["refreshed_at"] = "2026-11-03T23:59:00+09:00"
    assert stocks.evaluate(data)["rows"][0]["basis"] == "quote"


@pytest.mark.parametrize("available_at, reason", [
    (None, "availability_missing"),
    ("not-a-time", "availability_invalid"),
    ("2026-11-03T08:29:34", "availability_invalid"),
    ("2026-11-04T08:29:34+09:00", "availability_future"),
    ("2026-11-03T05:00:00+09:00", "availability_before_quote"),
])
def test_contradictory_or_unverifiable_availability_never_claims_current(available_at, reason):
    data = quality_portfolio()
    data["quotes"]["refreshed_at"] = available_at
    before = json.dumps(data, sort_keys=True)
    view = stocks.evaluate(data)
    assert view["rows"][0]["basis"] == "file"
    assert reason in view["rows"][0]["valuation_reasons"]
    assert "fx_" + reason in view["rows"][0]["valuation_reasons"]
    assert view["data_quality"]["status"] == "invalid"
    assert json.dumps(data, sort_keys=True) == before


@pytest.mark.parametrize("stamp, basis", [("2026-10-27T09:00:00+09:00", "quote"), ("2026-10-27T08:59:59+09:00", "file")])
def test_seven_day_age_boundary_is_not_silently_extended(stamp, basis):
    data = quality_portfolio(quote_changes={"as_of": "2026-10-27", "at": stamp})
    assert stocks.evaluate(data)["rows"][0]["basis"] == basis


def test_mixed_total_and_monthly_plan_are_explicit_estimates_and_gets_preserve_files(tmp_path):
    state = portfolio(tmp_path)
    data = quality_portfolio()
    data["quotes"]["quotes"]["ETHU"] = {**data["quotes"]["quotes"]["VOO"], "as_of": "2024-07-20", "at": "2024-07-20T05:00:00+09:00"}
    (state / "stocks" / "quotes.json").write_text(json.dumps(data["quotes"]), encoding="utf-8")
    before = {p.name: p.read_bytes() for p in (state / "stocks").glob("*.json")}
    detail = stocks.stocks_detail(state)
    assert detail["data_quality"]["status"] == "partial"
    assert detail["data_quality"]["current_count"] == 1
    assert detail["data_quality"]["fallback_count"] == 4
    assert detail["total_krw"] == 1_980_000
    status = stocks.stocks_status(state)
    summary = by_id(status, "stocks-summary")
    assert "혼합 기준 추정" in summary["stateLabel"] and "최신 평가액 미확인" in summary["stateLabel"]
    assert "추정" in by_id(status, "stocks-monthly")["stateLabel"]
    quality = by_id(status, "stocks-data-quality")
    assert "오래된 시세" in quality["stateLabel"]
    assert "1,980,000" not in json.dumps(status, ensure_ascii=False)
    client = TestClient(create_app(Store(state)), base_url="http://localhost:8510")
    assert client.get("/api/stocks").json()["data_quality"]["status"] == "partial"
    assert any(i["id"] == "stocks-data-quality" for i in client.get("/api/space").json()["stocks"]["items"])
    assert {p.name: p.read_bytes() for p in (state / "stocks").glob("*.json")} == before


def test_old_watchlist_quote_is_not_presented_as_current_market_summary(tmp_path):
    state = portfolio(tmp_path)
    data = quality_portfolio()
    data["quotes"]["quotes"]["BTC-USD"] = {**data["quotes"]["quotes"]["VOO"], "as_of": "2024-07-20", "at": "2024-07-20T05:00:00+09:00"}
    (state / "stocks" / "quotes.json").write_text(json.dumps(data["quotes"]), encoding="utf-8")
    assert "비트코인" not in by_id(stocks.stocks_status(state), "stocks-market")["title"]


def test_nontext_collection_time_is_a_warning_in_status_and_space_api(tmp_path):
    state = portfolio(tmp_path)
    data = quality_portfolio()
    data["quotes"]["refreshed_at"] = 42
    (state / "stocks" / "quotes.json").write_text(json.dumps(data["quotes"]), encoding="utf-8")
    before = (state / "stocks" / "quotes.json").read_bytes()
    assert "수집 시각 미확인" in by_id(stocks.stocks_status(state), "stocks-quotes")["stateLabel"]
    client = TestClient(create_app(Store(state)), base_url="http://localhost:8510")
    response = client.get("/api/space")
    assert response.status_code == 200
    assert "수집 시각 미확인" in by_id(response.json()["stocks"], "stocks-quotes")["stateLabel"]
    assert (state / "stocks" / "quotes.json").read_bytes() == before


@pytest.mark.parametrize("malformed_fx", [[1], "invalid", 42, True, None])
def test_nondict_fx_keeps_file_value_and_status_available(tmp_path, malformed_fx):
    state = portfolio(tmp_path)
    data = quality_portfolio()
    data["quotes"]["fx"] = malformed_fx
    (state / "stocks" / "quotes.json").write_text(json.dumps(data["quotes"]), encoding="utf-8")
    before = (state / "stocks" / "quotes.json").read_bytes()
    view = stocks.evaluate(stocks.load(state))
    assert view["rows"][0]["basis"] == "file"
    assert view["rows"][0]["value_krw"] == 1_000_000
    assert "fx_missing" in view["rows"][0]["valuation_reasons"]
    assert stocks.stocks_status(state)["configured"] is True
    client = TestClient(create_app(Store(state)), base_url="http://localhost:8510")
    assert client.get("/api/space").status_code == 200
    assert (state / "stocks" / "quotes.json").read_bytes() == before


def test_new_cache_and_history_writes_are_private_on_posix(tmp_path):
    import os
    import stat
    if os.name != "posix":
        pytest.skip("POSIX file mode is verified on Linux")
    state = portfolio(tmp_path)
    stocks.refresh_quotes(state, fake_fetch({"VOO": chart(700, 710), "KRW%3DX": chart(1400, 1390, ccy="KRW")}))
    for name in ("quotes.json", "history.json"):
        assert stat.S_IMODE((state / "stocks" / name).stat().st_mode) == 0o600


@pytest.mark.parametrize("second_high,expected", [(None, "partial"), (720.0, "current"), (1000.0, "partial_drift")])
def test_drawdown_reports_coverage_and_never_clears_unchecked_holdings(tmp_path, monkeypatch, second_high, expected):
    data = quality_portfolio(quote_changes={"high52": None if expected == "partial_drift" else 720.0})
    data["holdings"].append({**data["holdings"][0], "id": "second-position", "ticker": "QQQ"})
    data["quotes"]["quotes"]["QQQ"] = {**data["quotes"]["quotes"]["VOO"], "high52": second_high}
    assert stocks.evaluate(data)["data_quality"]["status"] == "current"
    before = json.dumps(data, sort_keys=True)
    monkeypatch.setattr(stocks, "load", lambda _root: data)
    client = TestClient(create_app(Store(tmp_path)), base_url="http://localhost:8510")
    response = client.get("/api/space")
    assert response.status_code == 200
    card = by_id(response.json()["stocks"], "stocks-drawdown")
    if expected == "current":
        assert "보유 종목 없음" in card["title"]
        assert card["needsHuman"] is False
        assert "2/2" in card["stateLabel"]
    else:
        assert "미확인 1종목" in card["stateLabel"]
        assert "1/2" in card["stateLabel"]
        assert card["needsHuman"] is True
        assert "보유 종목 없음" not in card["title"]
        assert card["state"] == ("drift" if expected == "partial_drift" else "info")
    assert json.dumps(data, sort_keys=True) == before


@pytest.mark.parametrize("quote_changes", [{"high52": None}, {"as_of": "2024-07-20", "at": "2024-07-20T05:00:00+09:00"}])
def test_drawdown_missing_all_data_is_unknown_not_absent(tmp_path, monkeypatch, quote_changes):
    data = quality_portfolio(quote_changes=quote_changes)
    before = json.dumps(data, sort_keys=True)
    monkeypatch.setattr(stocks, "load", lambda _root: data)
    card = by_id(stocks.stocks_status(tmp_path), "stocks-drawdown")
    assert "확인 못 함" in card["title"]
    assert "미확인 1종목" in card["stateLabel"]
    assert "0/1" in card["stateLabel"]
    assert card["needsHuman"] is True
    assert json.dumps(data, sort_keys=True) == before
