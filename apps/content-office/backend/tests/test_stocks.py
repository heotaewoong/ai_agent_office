import json
import time

import pytest
from fastapi.testclient import TestClient

from office import stocks
from office.api import create_app
from office.store import Store

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


def chart(price, prev, high=None, offset=0, stamp=1793390400):
    day = 86400
    return {"chart": {"result": [{"meta": {"regularMarketPrice": price, "regularMarketTime": stamp, "gmtoffset": offset,
                                            "currency": "USD", "fiftyTwoWeekHigh": high},
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
        "KRW%3DX": chart(1400.0, 1390.0),
        "VOO": chart(700.0, 710.0, high=720.0),
        "ETHU": chart(30.0, 33.0, high=100.0),
        "035720.KS": chart(40_000.0, 39_000.0, high=60_000.0, offset=32400),
        "328130.KS": OSError("wrong exchange"),
        "328130.KQ": chart(20_000.0, 19_000.0, offset=32400),
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
