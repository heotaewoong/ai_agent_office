"""주식 팀: 내 포트폴리오를 사용자 원칙대로 점검한다.

사용자가 정한 규칙(주식 폴더 인계 문서 2-3~2-6)을 코드로 지킨다.
- 모든 수치에 출처와 기준일을 붙이고, 못 구한 값은 '확인 못 함'으로 둔다.
- '사세요', '파세요' 같은 단정이나 주문은 하지 않는다. 비중 차이와 위험 정보만 보여 준다.
- 보유 내역(수량·원금)과 목표 비중은 사용자 파일이 정본이다. 앱은 holdings.json·targets.json을 고치지 않는다.
- 포트폴리오는 공개 저장소가 아니라 서버 상태 폴더 `OFFICE_STATE_DIR/stocks/`에만 둔다.
- 시세 확인은 사람이 버튼을 누를 때만 무료 공개 시세를 읽는다. 유료 모델·API를 부르지 않는다.

파일(모두 `<상태 폴더>/stocks/`):
- holdings.json  종목별 1행. 인계 문서 7-2의 대시보드 스키마 그대로(id, account, name, ticker, market, type, qty, ...).
- targets.json   유형별 목표 비중 [{type, label, target_pct}]
- settings.json  선택. {"monthly_krw": 500000, "monthly_note": "...", "drift_pp": 5, "concentration_pct": 20, "tolerance_pct": [20, 30]}
- history.json   날짜별 기록. 시세 확인 때 오늘(한국 날짜) 행을 덧쓴다. 기존 행은 지우지 않는다.
- quotes.json    마지막 시세 확인 결과(앱이 쓴다).
"""
from __future__ import annotations

import argparse
import json
import math
import os
import shutil
import sys
import threading
from concurrent.futures import ThreadPoolExecutor
from collections import Counter
from datetime import date, datetime, timedelta, timezone
from pathlib import Path
from urllib.parse import quote

KST = timezone(timedelta(hours=9))
TYPES = ("core", "dividend", "sector", "option", "crypto", "stock")
TYPE_LABELS = {"core": "코어 지수", "dividend": "배당·안전", "sector": "섹터·테마", "option": "옵션 인컴", "crypto": "암호화폐", "stock": "개별주"}
DEFAULT_SETTINGS = {
    "monthly_krw": 500000,
    "monthly_note": "취업 후 월 적립액은 아직 미정(50만 원 또는 200만 원)",
    "drift_pp": 5.0,
    "concentration_pct": 20.0,
    "tolerance_pct": [20, 30],
}
# 사용자가 아침 브리핑 대상으로 고른 시장 지표(인계 문서 6-4)
WATCHLIST = [("QQQ", "QQQ"), ("VOO", "VOO"), ("SCHD", "SCHD"), ("ETH-USD", "이더리움"), ("BTC-USD", "비트코인")]
FX_SYMBOL = "KRW=X"
QUOTE_SOURCE = "Yahoo Finance 공개 시세"
NAVER_SOURCE = "네이버 증권 공개 시세"
LEVERAGED = {"ETHU": 2}
REFRESH_STALE_SECONDS = 180
# 대시보드 신뢰 정책이며 거래소 달력이나 매매 규칙이 아니다. 긴 휴장도 보수적으로 표시한다.
QUOTE_MAX_AGE_DAYS = 7
QUOTE_CLOCK_SKEW_SECONDS = 120
_LOCK = threading.Lock()


class StocksError(ValueError):
    pass


def folder(root) -> Path:
    return Path(root) / "stocks"


def _read(path, default):
    try:
        return json.loads(Path(path).read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return default


def _write(path, value):
    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    temp = path.with_name(path.name + ".tmp")
    temp.write_text(json.dumps(value, ensure_ascii=False, indent=2), encoding="utf-8")
    temp.chmod(0o600)
    os.replace(temp, path)


def _num(value):
    if isinstance(value, bool) or value is None:
        return None
    try:
        out = float(value)
    except (TypeError, ValueError):
        return None
    return out if math.isfinite(out) else None


def _now():
    return datetime.now(KST)


# ---------------------------------------------------------------- 입력 검증

def validate_holdings(rows):
    if not isinstance(rows, list) or not rows:
        raise StocksError("holdings.json은 종목 목록이어야 합니다")
    seen, out = set(), []
    for i, row in enumerate(rows):
        if not isinstance(row, dict):
            raise StocksError(f"{i + 1}번째 종목 형식이 잘못됐습니다")
        hid = str(row.get("id") or "").strip()
        if not hid or hid in seen:
            raise StocksError(f"{i + 1}번째 종목의 id가 비었거나 겹칩니다")
        seen.add(hid)
        if row.get("market") not in ("KR", "US"):
            raise StocksError(f"{hid}: market은 KR 또는 US여야 합니다")
        if row.get("type") not in TYPES:
            raise StocksError(f"{hid}: type은 {', '.join(TYPES)} 중 하나여야 합니다")
        for key in ("value_krw", "cost_krw"):
            value = _num(row.get(key))
            if value is None or value < 0:
                raise StocksError(f"{hid}: {key}가 0 이상의 숫자가 아닙니다")
        qty = row.get("qty")
        if qty is not None and (_num(qty) is None or _num(qty) < 0):
            raise StocksError(f"{hid}: qty가 0 이상의 숫자가 아닙니다")
        out.append(row)
    return out


def validate_targets(rows):
    if not isinstance(rows, list):
        raise StocksError("targets.json은 목록이어야 합니다")
    by_type = {}
    for row in rows:
        if not isinstance(row, dict) or row.get("type") not in TYPES:
            raise StocksError("targets.json에 알 수 없는 유형이 있습니다")
        pct = _num(row.get("target_pct"))
        if pct is None or pct < 0:
            raise StocksError(f"{row.get('type')}: target_pct가 0 이상의 숫자가 아닙니다")
        by_type[row["type"]] = {"type": row["type"], "label": str(row.get("label") or TYPE_LABELS[row["type"]]), "target_pct": pct}
    total = sum(r["target_pct"] for r in by_type.values())
    if abs(total - 100) > 0.5:
        raise StocksError(f"목표 비중 합계가 100%가 아닙니다({total:g}%)")
    return [by_type[t] for t in TYPES if t in by_type]


def load(root):
    base = folder(root)
    holdings = _read(base / "holdings.json", None)
    targets = _read(base / "targets.json", None)
    if holdings is None or targets is None:
        return None
    settings = {**DEFAULT_SETTINGS, **{k: v for k, v in (_read(base / "settings.json", {}) or {}).items() if k in DEFAULT_SETTINGS}}
    meta = _read(base / "meta.json", {}) or {}
    return {
        "meta": meta,
        "holdings": validate_holdings(holdings),
        "targets": validate_targets(targets),
        "settings": settings,
        "history": [r for r in (_read(base / "history.json", []) or []) if isinstance(r, dict) and r.get("date")],
        "quotes": _read(base / "quotes.json", {}) or {},
    }


def import_portfolio(root, source_dir):
    """사용자가 가진 대시보드 JSON(holdings·targets·history)을 상태 폴더로 복사한다. 내용은 바꾸지 않는다."""
    source_dir = Path(source_dir)
    names = {"holdings.json": ("holdings.json", "dashboard_holdings.json"),
             "targets.json": ("targets.json", "dashboard_targets.json"),
             "history.json": ("history.json", "dashboard_history.json")}
    found = {}
    for target, candidates in names.items():
        for name in candidates:
            if (source_dir / name).is_file():
                found[target] = source_dir / name
                break
    if "holdings.json" not in found or "targets.json" not in found:
        raise StocksError("holdings와 targets 파일을 찾지 못했습니다")
    validate_holdings(_read(found["holdings.json"], None))
    validate_targets(_read(found["targets.json"], None))
    base = folder(root)
    base.mkdir(parents=True, exist_ok=True)
    source_history = _read(found["history.json"], []) if "history.json" in found else []
    dates = sorted(str(r.get("date")) for r in source_history if isinstance(r, dict) and r.get("date"))
    holdings_date = dates[-1] if dates else datetime.fromtimestamp(found["holdings.json"].stat().st_mtime, KST).date().isoformat()
    for target, path in found.items():
        if target == "history.json" and (base / target).is_file():
            continue  # 서버에 쌓인 기록은 덮어쓰지 않는다
        shutil.copyfile(path, base / target)
        try:
            (base / target).chmod(0o600)
        except OSError:
            pass
    _write(base / "meta.json", {"holdings_date": holdings_date, "imported_at": _now().isoformat(timespec="seconds")})
    return sorted(found)


# ---------------------------------------------------------------- 시세 읽기

def _yahoo_symbol(row):
    """시세 저장 키. 한국 종목은 거래소를 모르면 코스피(.KS)로 두고, 읽을 때 코스닥(.KQ)도 시도한다."""
    ticker = str(row.get("ticker") or "").strip()
    if not ticker:
        return None
    if row.get("market") == "US":
        return ticker
    suffix = str(row.get("exchange") or "").upper()
    if suffix in ("KS", "KQ"):
        return f"{ticker}.{suffix}"
    return f"{ticker}.KS"


def _candidates(symbol, row):
    if row is not None and row.get("market") == "KR" and not str(row.get("exchange") or "") and symbol.endswith(".KS"):
        return [symbol, symbol[:-3] + ".KQ"]
    return [symbol]


def _http_json(url, timeout=8):
    import requests

    response = requests.get(url, timeout=timeout, headers={"User-Agent": "Mozilla/5.0 (HeoBrain office stocks team)", "Accept": "application/json"})
    response.raise_for_status()
    return response.json()


def yahoo_quote(symbol, fetch=None):
    """Yahoo Finance 차트 API의 마지막 가격·직전 종가·기준 시각·52주 고점."""
    fetch = fetch or _http_json
    data = fetch(f"https://query1.finance.yahoo.com/v8/finance/chart/{quote(symbol)}?range=5d&interval=1d")
    result = ((data or {}).get("chart") or {}).get("result") or []
    if not result:
        raise StocksError("결과 없음")
    meta = result[0].get("meta") or {}
    price = _num(meta.get("regularMarketPrice"))
    stamp = _num(meta.get("regularMarketTime"))
    if price is None or price <= 0 or stamp is None:
        raise StocksError("가격 없음")
    offset = _num(meta.get("gmtoffset")) or 0
    local_day = datetime.fromtimestamp(stamp + offset, timezone.utc).date()
    times = result[0].get("timestamp") or []
    closes = (((result[0].get("indicators") or {}).get("quote") or [{}])[0].get("close")) or []
    bars = [(datetime.fromtimestamp(t + offset, timezone.utc).date(), _num(c)) for t, c in zip(times, closes)]
    earlier = [c for day, c in bars if c and day < local_day]
    prev = earlier[-1] if earlier else None
    change = round((price / prev - 1) * 100, 2) if prev else None
    return {
        "symbol": symbol, "price": price, "prev_close": prev, "change_pct": change,
        "ccy": meta.get("currency") or "", "as_of": local_day.isoformat(),
        "at": datetime.fromtimestamp(stamp, timezone.utc).astimezone(KST).isoformat(timespec="minutes"),
        "high52": _num(meta.get("fiftyTwoWeekHigh")), "source": QUOTE_SOURCE,
    }


def naver_quote(code, fetch=None):
    """한국 종목 예비 경로: 네이버 증권 모바일 공개 시세."""
    fetch = fetch or _http_json
    data = fetch(f"https://m.stock.naver.com/api/stock/{quote(code)}/basic")
    price = _num(str((data or {}).get("closePrice") or "").replace(",", ""))
    if price is None or price <= 0:
        raise StocksError("가격 없음")
    change = _num(data.get("fluctuationsRatio"))
    traded = str(data.get("localTradedAt") or "")
    return {"symbol": code, "price": price, "prev_close": None, "change_pct": change, "ccy": "KRW",
            "as_of": traded[:10] or None, "at": traded or None, "high52": None, "source": NAVER_SOURCE}


def refresh_quotes(root, fetch=None, workers=6):
    """보유 종목·관심 지표·환율 시세를 읽어 quotes.json과 오늘 history 행을 쓴다. holdings·targets는 고치지 않는다."""
    fetch = fetch or _http_json
    portfolio = load(root)
    if portfolio is None:
        raise StocksError("포트폴리오 파일이 아직 서버에 없습니다")
    symbols = {}
    for row in portfolio["holdings"]:
        symbol = _yahoo_symbol(row)
        if symbol:
            symbols.setdefault(symbol, row)
    wanted = [FX_SYMBOL, *symbols, *(s for s, _ in WATCHLIST if s not in symbols)]

    def one(symbol):
        row, errors = symbols.get(symbol), []
        for candidate in _candidates(symbol, row):
            try:
                return symbol, yahoo_quote(candidate, fetch), None
            except Exception as error:  # noqa: BLE001 - 시세 하나 실패가 전체를 막지 않게 한다
                errors.append(type(error).__name__)
        if row is not None and row.get("market") == "KR":
            try:
                return symbol, naver_quote(str(row.get("ticker")), fetch), None
            except Exception as error:  # noqa: BLE001
                errors.append(type(error).__name__)
        return symbol, None, "/".join(errors)

    started = _now()
    with ThreadPoolExecutor(max_workers=max(1, workers)) as pool:
        results = list(pool.map(one, wanted))
    quotes = {symbol: q for symbol, q, _ in results if q}
    failed = sorted(symbol for symbol, q, _ in results if not q)
    fx = quotes.pop(FX_SYMBOL, None)
    record = {
        "status": "done", "started_at": started.isoformat(timespec="seconds"),
        "refreshed_at": _now().isoformat(timespec="seconds"),
        "fx": {"rate": fx["price"], "ccy": fx["ccy"], "as_of": fx["at"], "source": fx["source"]} if fx else None,
        "quotes": quotes, "failed": failed,
    }
    _write(folder(root) / "quotes.json", record)
    if quotes:
        _record_history(root)
    return record


def _record_history(root):
    portfolio = load(root)
    view = evaluate(portfolio)
    row = {"date": _now().date().isoformat(), "fx": view["fx"]["rate"], "total_krw": view["total_krw"],
           "cost_krw": view["cost_krw"], "pnl_krw": view["total_krw"] - view["cost_krw"],
           **{t["type"]: t["value_krw"] for t in view["types"]}, "source": "시세 확인(앱)",
           "data_quality": view["data_quality"]}
    history = [r for r in portfolio["history"] if r.get("date") != row["date"]] + [row]
    history.sort(key=lambda r: r["date"])
    _write(folder(root) / "history.json", history)


def start_refresh(root, fetch=None):
    """시세 확인을 뒤에서 시작한다. 화면 응답은 바로 돌려주고 결과는 /api/space 다음 조회에 나타난다."""
    if load(root) is None:
        raise StocksError("포트폴리오 파일이 아직 서버에 없습니다. 먼저 보유 종목 파일을 올려 주세요")
    path = folder(root) / "quotes.json"
    with _LOCK:
        current = _read(path, {}) or {}
        begun = current.get("started_at")
        if current.get("status") == "running" and begun:
            try:
                age = (_now() - datetime.fromisoformat(begun)).total_seconds()
            except ValueError:
                age = REFRESH_STALE_SECONDS + 1
            if age < REFRESH_STALE_SECONDS:
                return {"started": False, "message": "이미 시세를 확인하고 있어요. 잠시 뒤 패널이 바뀝니다"}
        _write(path, {**current, "status": "running", "started_at": _now().isoformat(timespec="seconds"), "error": None})

    def run():
        try:
            refresh_quotes(root, fetch)
        except Exception as error:  # noqa: BLE001
            latest = _read(path, {}) or {}
            _write(path, {**latest, "status": "failed", "error": type(error).__name__})

    threading.Thread(target=run, name="stocks-refresh", daemon=True).start()
    return {"started": True, "message": "시세 확인을 시작했어요. 30초쯤 뒤 패널에 반영됩니다"}


# ---------------------------------------------------------------- 계산

def _aware_stamp(value):
    try:
        stamp = datetime.fromisoformat(value)
        return stamp if stamp.utcoffset() is not None else None
    except (TypeError, ValueError):
        return None


def _quote_reasons(q, expected_ccy, now, *, available_at, fx=False):
    """원본은 보존하고 현재 평가에 쓸 수 없는 이유만 반환한다."""
    if not isinstance(q, dict) or not q:
        return ["missing"]
    reasons = []
    raw_price = q.get("rate" if fx else "price")
    price = _num(raw_price)
    if not isinstance(raw_price, (int, float)) or price is None or price <= 0:
        reasons.append("price_invalid")
    if q.get("ccy") != expected_ccy:
        reasons.append("currency_mismatch")
    if not isinstance(q.get("source"), str) or not q["source"].strip():
        reasons.append("source_missing")
    raw_at = q.get("as_of" if fx else "at")
    stamp = _aware_stamp(raw_at)
    if not raw_at:
        reasons.append("timestamp_missing")
    elif stamp is None:
        reasons.append("timestamp_invalid")
    try:
        raw_day = str(q.get("as_of") or "")
        day = date.fromisoformat(raw_day[:10] if fx else raw_day)
    except ValueError:
        reasons.append("date_invalid")
        day = None
    if day and day > (now + timedelta(seconds=QUOTE_CLOCK_SKEW_SECONDS)).date():
        reasons.append("future")
    if stamp:
        age = (now - stamp).total_seconds()
        if age < -QUOTE_CLOCK_SKEW_SECONDS:
            reasons.append("future")
        if age > QUOTE_MAX_AGE_DAYS * 86400:
            reasons.append("stale")
        # 미국 거래일은 같은 시각의 한국 날짜보다 하루 앞설 수 있다.
        if day and (stamp.astimezone(KST).date() - day).days not in (0, 1):
            reasons.append("date_mismatch")
    available = _aware_stamp(available_at)
    if not available_at:
        reasons.append("availability_missing")
    elif available is None:
        reasons.append("availability_invalid")
    if available:
        if (available - now).total_seconds() > QUOTE_CLOCK_SKEW_SECONDS:
            reasons.append("availability_future")
        if stamp and (stamp - available).total_seconds() > QUOTE_CLOCK_SKEW_SECONDS:
            reasons.append("availability_before_quote")
    return list(dict.fromkeys(reasons))


def evaluate(portfolio):
    """현재 평가: 새 시세가 있으면 수량×시세(×환율), 없으면 사용자 파일의 평가금액을 그대로 쓴다."""
    holdings, quotes = portfolio["holdings"], portfolio["quotes"] or {}
    live = quotes.get("quotes") or {}
    now = _now()
    fx_q = quotes.get("fx") or None
    fx_q = fx_q if isinstance(fx_q, dict) else None
    available_at = quotes.get("refreshed_at")
    fx_reasons = _quote_reasons(fx_q, "KRW", now, available_at=available_at, fx=True)
    valid_fx = fx_q if not fx_reasons else None
    last = portfolio["history"][-1] if portfolio["history"] else {}
    base_fx = _num(last.get("fx")) if not valid_fx else None
    fx = {"rate": valid_fx["rate"], "as_of": valid_fx["as_of"], "source": valid_fx["source"]} if valid_fx else \
         {"rate": base_fx, "as_of": last.get("date"), "source": "보유 파일 기록"}
    rows = []
    for h in holdings:
        qty, cost = _num(h.get("qty")), _num(h.get("cost_krw")) or 0
        symbol = _yahoo_symbol(h)
        q = live.get(symbol) if symbol else None
        reasons = _quote_reasons(q, "USD" if h["market"] == "US" else "KRW", now, available_at=available_at)
        if qty is None:
            reasons.append("quantity_missing")
        if h["market"] == "US":
            reasons.extend("fx_" + reason for reason in fx_reasons)
        value, basis = _num(h.get("value_krw")) or 0, "file"
        if not reasons:
            if h.get("market") == "US":
                value, basis = qty * q["price"] * valid_fx["rate"], "quote"
            elif h.get("market") == "KR":
                value, basis = qty * q["price"], "quote"
        rows.append({
            "id": h["id"], "name": h.get("name") or h["id"], "ticker": str(h.get("ticker") or ""), "market": h["market"],
            "account": h.get("account") or "", "type": h["type"], "value_krw": round(value), "cost_krw": round(cost),
            "basis": basis, "quote": q if basis == "quote" else None,
            "valuation_reasons": reasons,
            "quote_quality": {**{key: q.get(key) if isinstance(q, dict) else None for key in ("source", "as_of", "at")},
                              "available_at": quotes.get("refreshed_at")},
            "estimated_qty": "추정" in str(h.get("qty_note") or ""),
            "file_price_date": h.get("price_date"),
        })
    total = sum(r["value_krw"] for r in rows)
    cost_total = sum(r["cost_krw"] for r in rows)
    targets = {t["type"]: t for t in portfolio["targets"]}
    types = []
    for t in TYPES:
        value = sum(r["value_krw"] for r in rows if r["type"] == t)
        pct = value / total * 100 if total else 0.0
        target = targets.get(t, {}).get("target_pct", 0.0)
        types.append({"type": t, "label": targets.get(t, {}).get("label", TYPE_LABELS[t]), "value_krw": value,
                      "pct": round(pct, 1), "target_pct": target, "diff_pp": round(pct - target, 1)})
    groups = {}
    for r in rows:
        key = r["ticker"] or r["name"]
        g = groups.setdefault(key, {"name": r["name"], "ticker": r["ticker"], "value_krw": 0})
        g["value_krw"] += r["value_krw"]
    ranked = sorted(groups.values(), key=lambda g: g["value_krw"], reverse=True)
    for g in ranked:
        g["pct"] = round(g["value_krw"] / total * 100, 1) if total else 0.0
    current_count = sum(r["basis"] == "quote" for r in rows)
    quality = {
        "status": "current" if current_count == len(rows) else "partial" if current_count else "invalid",
        "current_count": current_count, "fallback_count": len(rows) - current_count,
        "reason_counts": dict(Counter(reason for r in rows for reason in r["valuation_reasons"])),
        "available_at": quotes.get("refreshed_at"), "max_age_days": QUOTE_MAX_AGE_DAYS,
        "clock_skew_seconds": QUOTE_CLOCK_SKEW_SECONDS,
        "sources": sorted({r["quote_quality"]["source"] for r in rows if isinstance(r["quote_quality"]["source"], str)}),
        "as_of_dates": sorted({r["quote_quality"]["as_of"] for r in rows if isinstance(r["quote_quality"]["as_of"], str)}),
        "fx": {"reasons": fx_reasons, "source": (fx_q or {}).get("source"), "as_of": (fx_q or {}).get("as_of")},
    }
    return {"rows": rows, "total_krw": total, "cost_krw": cost_total, "types": types, "ranked": ranked, "fx": fx,
            "data_quality": quality,
            "return_pct": round((total / cost_total - 1) * 100, 1) if cost_total else None}


def monthly_plan(types, total, amount):
    """이번 달 적립금을 유형별 금액으로만 나눈다(종목 선택은 사용자). 인계 문서 7-1의 계산기 두 방식."""
    amount = max(0, int(amount or 0))
    unit = 1000

    def rounded(shares):
        out = {k: int(v // unit * unit) for k, v in shares.items()}
        rest = amount - sum(out.values())
        if out and rest:
            key = max(shares, key=lambda k: shares[k] - out[k])
            out[key] += rest
        return out

    by_target = rounded({t["type"]: amount * t["target_pct"] / 100 for t in types})
    after = total + amount
    gaps = {t["type"]: max(0.0, t["target_pct"] / 100 * after - t["value_krw"]) for t in types}
    gap_sum = sum(gaps.values())
    if gap_sum <= 0:
        fill = dict(by_target)
    elif gap_sum <= amount:
        extra = amount - gap_sum
        fill = rounded({k: gaps[k] + extra * next(t["target_pct"] for t in types if t["type"] == k) / 100 for k in gaps})
    else:
        fill = rounded({k: amount * g / gap_sum for k, g in gaps.items()})
    labels = {t["type"]: t["label"] for t in types}
    pick = lambda plan: [{"type": k, "label": labels[k], "krw": v} for k, v in plan.items() if v > 0]
    return {"amount_krw": amount, "by_target": pick(by_target), "fill_gap": pick(fill)}


def _won(value):
    value = int(round(value))
    if value >= 10000 and value % 10000 == 0:
        return f"{value // 10000:,}만 원"
    if value >= 10000:
        return f"{value / 10000:,.1f}만 원"
    return f"{value:,}원"


def _sign(value, digits=1):
    return f"{value:+.{digits}f}"


def stocks_status(root):
    """오피스 월드 주식 팀 투영. 비중·수익률(%)과 출처·기준일만 담고 보유 평가금액(원)은 넣지 않는다."""
    try:
        portfolio = load(root)
    except StocksError as error:
        return {"version": 1, "configured": False, "error": str(error), "items": [], "approval": "포트폴리오 파일 확인 필요"}
    if portfolio is None:
        return {"version": 1, "configured": False, "error": None, "items": [], "approval": "포트폴리오 파일 연결 전"}
    view = evaluate(portfolio)
    quality = view["data_quality"]
    quality_label = {"current": "시세 기준 추정", "partial": "혼합 기준 추정 · 최신 평가액 미확인",
                     "invalid": "파일 기준 추정 · 최신 평가액 미확인"}[quality["status"]]
    settings = portfolio["settings"]
    quotes = portfolio["quotes"] or {}
    refreshed_stamp = _aware_stamp(quotes.get("refreshed_at"))
    refreshed_label = refreshed_stamp.isoformat(timespec="minutes")[5:16].replace("T", " ") \
        if refreshed_stamp and (refreshed_stamp - _now()).total_seconds() <= QUOTE_CLOCK_SKEW_SECONDS else None
    rows = view["rows"]
    priced = [r for r in rows if r["basis"] == "quote"]
    kept = [r for r in rows if r["basis"] == "file"]
    holdings_day = portfolio["meta"].get("holdings_date") or (portfolio["history"][0].get("date") if portfolio["history"] else None) or "확인 못 함"
    status = quotes.get("status")
    items = []

    def item(id_, title, label, state="info", needs=False, actions=()):
        items.append({"id": id_, "title": title, "stateLabel": label, "state": state, "needsHuman": needs, "actions": list(actions)})

    # 1) 한 줄 요약
    ret = view["return_pct"]
    drift = sorted((t for t in view["types"] if abs(t["diff_pp"]) > settings["drift_pp"]), key=lambda t: -abs(t["diff_pp"]))
    summary = f"{len(rows)}종목 · 원금 대비 {_sign(ret)}%" if ret is not None else f"{len(rows)}종목 · 수익률 확인 못 함"
    summary += f" · 목표와 {settings['drift_pp']:g}%p 넘게 다른 유형 {len(drift)}개" if drift else " · 유형 비중 모두 허용 범위 안"
    basis = f"{quality_label} · 보유 수량·원금은 {holdings_day} 내 시트 기준"
    if priced and refreshed_label:
        basis += f" · {len(priced)}종목은 {refreshed_label} 확인한 시세로 다시 계산"
    else:
        basis += " · 시세는 파일에 적힌 값"
    item("stocks-summary", summary, basis)
    reason_labels = {"missing": "시세 없음", "price_invalid": "가격 미확인", "currency_mismatch": "통화 미확인",
                     "source_missing": "출처 미확인", "timestamp_missing": "시각 없음", "timestamp_invalid": "시각 미확인",
                     "date_invalid": "기준일 미확인", "date_mismatch": "기준일·시각 불일치", "future": "미래 시각",
                     "availability_missing": "수집 시각 없음", "availability_invalid": "수집 시각 미확인",
                     "availability_future": "미래 수집 시각", "availability_before_quote": "가격·수집 시각 불일치",
                     "stale": "오래된 시세", "quantity_missing": "수량 미확인"}
    reason_text = " · ".join(f"{'환율 ' if reason.startswith('fx_') else ''}{reason_labels.get(reason.removeprefix('fx_'), reason)} {count}종목"
                             for reason, count in quality["reason_counts"].items())
    item("stocks-data-quality", f"데이터 품질: {quality_label}",
         f"시세 적용 {quality['current_count']}종목 · 파일 값 유지 {quality['fallback_count']}종목"
         + (f" · {reason_text}" if reason_text else "")
         + f" · 최근 {QUOTE_MAX_AGE_DAYS}일 신뢰 정책(거래소 달력 아님)",
         state="info" if quality["status"] == "current" else "drift", needs=quality["status"] != "current")

    # 2) 시세 확인 버튼(사람이 누를 때만 무료 공개 시세를 읽는다)
    if status == "running":
        label = "시세를 확인하는 중이에요. 잠시 뒤 자동으로 바뀝니다"
    elif status == "failed":
        label = "마지막 시세 확인 실패 · 이전 값 유지 · 다시 눌러 보세요"
    elif quotes.get("refreshed_at"):
        miss = len(quotes.get("failed") or [])
        label = (f"마지막 확인 {refreshed_label} · {QUOTE_SOURCE}" if refreshed_label else "수집 시각 미확인 · 시세 새로 확인 필요") \
            + (f" · {miss}개 확인 못 함" if miss else "")
    else:
        label = "아직 새 시세를 확인하지 않았어요 · 버튼을 누를 때만 무료 공개 시세를 읽고 비용은 없어요"
    item("stocks-quotes", "시세·환율 새로 확인", label, state="research" if status == "running" else "info",
         actions=[] if status == "running" else [{"id": "stocks-refresh", "label": "시세 새로 확인"}])

    # 3) 유형 비중 점검: 벗어난 유형은 하나씩, 범위 안 유형은 한 줄로
    for t in drift:
        direction = "많아요" if t["diff_pp"] > 0 else "적어요"
        item(f"stocks-type-{t['type']}", f"{t['label']} {t['pct']:.1f}% · 목표 {t['target_pct']:g}%",
             f"목표보다 {abs(t['diff_pp']):.1f}%p {direction} · 조정할지는 직접 판단", state="drift", needs=True)
    inside = [t for t in view["types"] if abs(t["diff_pp"]) <= settings["drift_pp"]]
    if inside:
        item("stocks-type-ok", "허용 범위 안: " + " · ".join(f"{t['label']} {t['pct']:.1f}%(목표 {t['target_pct']:g})" for t in inside),
             f"목표와 차이 {settings['drift_pp']:g}%p 이하")

    # 4) 한 종목 쏠림
    head = view["ranked"][0] if view["ranked"] else None
    if head:
        over = head["pct"] > settings["concentration_pct"]
        lev = LEVERAGED.get(head["ticker"])
        label = f"한 종목 기준 {settings['concentration_pct']:g}% {'초과' if over else '이하'}"
        if lev:
            label += f" · {lev}배 레버리지라 기초자산이 10% 움직이면 약 {lev * 10}% 움직여요"
        item("stocks-concentration", f"가장 큰 종목 {head['name']} {head['pct']:.1f}%", label, state="drift" if over else "info", needs=over)

    # 5) 이번 달 적립 배분(유형별 금액만, 종목 선택은 사용자)
    plan = monthly_plan(view["types"], view["total_krw"], settings["monthly_krw"])
    fill = " · ".join(f"{p['label']} {_won(p['krw'])}" for p in plan["fill_gap"]) or "배분할 금액 없음"
    item("stocks-monthly", f"이번 달 {_won(plan['amount_krw'])} 나누기, 부족한 유형부터: {fill}",
         quality_label + " · 목표 비중대로면 " + " · ".join(f"{p['label']} {_won(p['krw'])}" for p in plan["by_target"])
         + f" · {settings['monthly_note']} · 종목 선택은 직접")

    # 6) 하락 감내 범위(52주 고점 대비)
    low, high = settings["tolerance_pct"]
    falls, seen = [], set()
    for r in sorted(priced, key=lambda r: (r["quote"]["price"] / r["quote"]["high52"]) if r["quote"].get("high52") else 9):
        q = r["quote"]
        if not q.get("high52") or q["high52"] <= 0 or r["ticker"] in seen:
            continue
        seen.add(r["ticker"])
        falls.append((r, round((q["price"] / q["high52"] - 1) * 100, 1)))
    if falls:
        deep = [(r, f) for r, f in falls if f <= -low]
        source = f"{falls[0][0]['quote']['source']} 52주 고가 · {falls[0][0]['quote']['as_of']} 기준"
        if deep:
            text = " · ".join(f"{r['name']} {f:.0f}%" for r, f in deep[:4])
            item("stocks-drawdown", f"52주 고점보다 {low}% 넘게 내려간 종목 {len(deep)}개: {text}",
                 f"내 감내 범위 {low}~{high}%와 비교 · {source}", state="drift", needs=any(f <= -high for _, f in deep))
        else:
            item("stocks-drawdown", f"52주 고점보다 {low}% 넘게 내려간 보유 종목 없음", f"내 감내 범위 {low}~{high}%와 비교 · {source}")

    # 7) 직전 거래일 움직임
    shown, uniq = [], set()
    for r in sorted((r for r in priced if r["quote"].get("change_pct") is not None), key=lambda r: -abs(r["quote"]["change_pct"])):
        if r["ticker"] not in uniq:
            uniq.add(r["ticker"])
            shown.append(r)
    if shown:
        text = " · ".join(f"{r['name']} {_sign(r['quote']['change_pct'], 2)}%" for r in shown[:4])
        dates = sorted({r["quote"]["as_of"] for r in shown[:4] if r["quote"].get("as_of")})
        item("stocks-movers", f"직전 거래일 큰 움직임: {text}", f"직전 종가 대비 · {' / '.join(dates)} 기준 · 움직인 이유는 확인 못 함")

    # 8) 시장 한 줄(아침 브리핑 대상)
    live = quotes.get("quotes") or {}
    market = [(name, live.get(symbol)) for symbol, name in WATCHLIST]
    market = [(name, q) for name, q in market if not _quote_reasons(q, "USD", _now(), available_at=quotes.get("refreshed_at")) and q.get("change_pct") is not None]
    fx = quotes.get("fx") if not quality["fx"]["reasons"] else None
    if market or fx:
        parts = [f"{name} {_sign(q['change_pct'], 2)}%" for name, q in market]
        if fx:
            parts.append(f"원달러 {fx['rate']:,.2f}원")
        item("stocks-market", "시장 한 줄: " + " · ".join(parts),
             f"{QUOTE_SOURCE} · 환율 {str((fx or {}).get('as_of') or '확인 못 함')[:16].replace('T', ' ')} 기준 · 코인은 24시간 시장")

    # 9) 데이터 한계
    no_ticker = [r for r in kept if not r["ticker"]]
    estimated = [r for r in rows if r["estimated_qty"]]
    limits = []
    if no_ticker:
        limits.append(f"티커가 없는 {len(no_ticker)}종목은 시트 평가금액 그대로")
    if estimated:
        limits.append(f"수량을 평가금액에서 추정한 {len(estimated)}종목")
    missing = len(kept) - len(no_ticker)
    if missing and quotes.get("refreshed_at"):
        limits.append(f"시세를 못 읽은 {missing}종목은 파일 값 유지")
    item("stocks-data", f"보유 내역은 {holdings_day} 시트 그대로예요",
         "그 뒤 매수·매도는 반영 안 됨 · 시트를 고치면 다시 올려 주세요" + (" · " + " · ".join(limits) if limits else ""))

    flagged = sum(1 for i in items if i["needsHuman"])
    return {
        "version": 1, "configured": True, "error": None, "items": items,
        "holdingsDate": holdings_day, "refreshedAt": quotes.get("refreshed_at"), "refreshing": status == "running",
        "approval": f"포트폴리오 점검 · 직접 확인할 것 {flagged}개" if flagged else "포트폴리오 점검 · 확인할 것 없음",
    }


def stocks_detail(root):
    """운영자 화면용 상세(원화 금액 포함). /api/stocks에서만 돌려준다."""
    portfolio = load(root)
    if portfolio is None:
        return {"version": 1, "configured": False}
    view = evaluate(portfolio)
    plan = monthly_plan(view["types"], view["total_krw"], portfolio["settings"]["monthly_krw"])
    return {"version": 1, "configured": True, "total_krw": view["total_krw"], "cost_krw": view["cost_krw"],
            "data_quality": view["data_quality"],
            "return_pct": view["return_pct"], "fx": view["fx"], "types": view["types"], "top": view["ranked"][:5],
            "monthly": plan, "rows": view["rows"],
            "quotes": {k: portfolio["quotes"].get(k) for k in ("status", "refreshed_at", "failed")}}


def main(argv=None):
    parser = argparse.ArgumentParser(description="주식 팀 포트폴리오 가져오기·시세 확인")
    parser.add_argument("--state", default=os.environ.get("OFFICE_STATE_DIR", str(Path.home() / ".local/state/heobrain-content-office")))
    sub = parser.add_subparsers(dest="command", required=True)
    imp = sub.add_parser("import", help="대시보드 JSON 폴더를 상태 폴더로 복사")
    imp.add_argument("source")
    sub.add_parser("refresh", help="시세를 지금 한 번 확인")
    sub.add_parser("status", help="오피스 월드에 보일 항목 출력")
    args = parser.parse_args(argv)
    try:
        if args.command == "import":
            print(json.dumps({"imported": import_portfolio(args.state, args.source)}, ensure_ascii=False))
        elif args.command == "refresh":
            record = refresh_quotes(args.state)
            print(json.dumps({"quotes": len(record["quotes"]), "failed": record["failed"], "fx": record["fx"]}, ensure_ascii=False))
        else:
            status = stocks_status(args.state)
            for it in status["items"]:
                print(("[확인] " if it["needsHuman"] else "- ") + it["title"] + " | " + it["stateLabel"])
    except StocksError as error:
        print(str(error), file=sys.stderr)
        return 2
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
