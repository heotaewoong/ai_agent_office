"""외부 조사 검색어: 한글 주제를 논문·저장소 검색용 영어 낱말로 바꾼다. 외부 조사에서 유료 모델을 부르는 곳은 여기 하나다.

- 운영자가 허락한 소액 호출이다(한 번에 1원 미만). 같은 주제는 저장해 둔 결과를 다시 쓰고, 달마다 쓸 수 있는 금액에 한도를 둔다.
- 전체 제작 예산(budget_cap)과 작업 시간 설정은 읽지도 바꾸지도 않는다. 대신 호출마다 운영 기록 이벤트와 자료 창고 DB에 금액을 남긴다.
- 검증한 단가의 유효기간(price_valid_until)이 지나면 부르지 않는다. 실패하면 호출한 쪽이 낱말표 검색어를 그대로 쓴다.
- 키가 있는 가장 싼 모델부터 쓴다. 키가 만료되거나 거절되면(401·403, 과금 없음) 다음 모델로 한 번 넘어간다.
"""
from __future__ import annotations

import hashlib
import json
import os
import re
import unicodedata
from contextlib import closing
from datetime import datetime, timezone

import requests

from .providers import DEFAULT_PRICE_VALID_UNTIL, FX_RESERVATION_KRW, Provider, price_for, provider_for
from .source_library import _connect, _now
from .store import canonical

MODELS = ("gemini-3.5-flash-lite", "gpt-5.4-nano")
DEFAULT_MONTHLY_CAP_KRW = 300
_KEYS = {"gemini": "GEMINI_API_KEY", "openai": "OPENAI_API_KEY"}
_MAX_TOKENS = 400
_SCHEMA = """
CREATE TABLE IF NOT EXISTS research_query_calls(
  id INTEGER PRIMARY KEY AUTOINCREMENT, title_hash TEXT NOT NULL, title TEXT NOT NULL, queries TEXT,
  model TEXT NOT NULL, krw REAL NOT NULL, state TEXT NOT NULL, created_at TEXT NOT NULL);
CREATE INDEX IF NOT EXISTS research_query_title ON research_query_calls(title_hash);
"""
_RESULT = {"type": "object", "additionalProperties": False, "required": ["queries"],
           "properties": {"queries": {"type": "array", "minItems": 1, "maxItems": 3, "items": {"type": "string"}}}}
_SYSTEM = ("You turn a Korean content topic into English search keywords for finding supporting sources. "
           "Return up to 3 keyword queries, the most specific first. Each query is 2 to 5 English words with no quotes and no boolean operators. "
           "Keep product names and proper names unchanged. The first query should suit an academic paper search such as PubMed.")


def monthly_cap_krw() -> int:
    try:
        return max(0, int(os.environ.get("OFFICE_RESEARCH_QUERY_CAP_KRW", DEFAULT_MONTHLY_CAP_KRW)))
    except ValueError:
        return DEFAULT_MONTHLY_CAP_KRW


def usable_models() -> list[str]:
    """키가 설정된 모델만, 싼 순서로. OFFICE_RESEARCH_QUERY_MODEL로 먼저 쓸 모델을 바꿀 수 있다."""
    first = os.environ.get("OFFICE_RESEARCH_QUERY_MODEL")
    ordered = ([first] if first in MODELS else []) + [model for model in MODELS if model != first]
    return [model for model in ordered if os.environ.get(_KEYS[provider_for(model)])]


def _clean_queries(values) -> list[str]:
    cleaned = []
    for value in values if isinstance(values, list) else []:
        text = re.sub(r"\s+", " ", re.sub(r"[^A-Za-z0-9 .+#-]", " ", str(value))).strip()[:80]
        if len(text) >= 3 and text.casefold() not in {item.casefold() for item in cleaned}:
            cleaned.append(text)
    return cleaned[:3]


def _record(root, title_hash, title, model, queries, krw, state) -> None:
    with closing(_connect(root)) as db, db:
        db.execute("INSERT INTO research_query_calls(title_hash, title, queries, model, krw, state, created_at) VALUES (?,?,?,?,?,?,?)",
                   (title_hash, title, json.dumps(queries) if queries else None, model, krw, state, _now()))


def month_spent_krw(root) -> float:
    with closing(_connect(root)) as db:
        db.executescript(_SCHEMA)
        return db.execute("SELECT COALESCE(SUM(krw), 0) FROM research_query_calls WHERE created_at LIKE ?",
                          (datetime.now(timezone.utc).strftime("%Y-%m") + "%",)).fetchone()[0]


def english_queries(store, title: str, *, transport=None) -> dict:
    """{"queries": [...], "source": "saved"|"model"|None, "note": 못 만든 이유|None}. 예외를 올리지 않는다."""
    title = re.sub(r"\s+", " ", unicodedata.normalize("NFKC", title or "")).strip()[:300]
    if not re.search(r"[가-힣]", title):
        return {"queries": [], "source": None, "note": None}
    title_hash = hashlib.sha256(title.casefold().encode("utf-8")).hexdigest()
    with closing(_connect(store.root)) as db:
        db.executescript(_SCHEMA)
        saved = db.execute("SELECT queries FROM research_query_calls WHERE title_hash=? AND queries IS NOT NULL ORDER BY id DESC LIMIT 1",
                           (title_hash,)).fetchone()
    if saved:
        return {"queries": _clean_queries(json.loads(saved[0])), "source": "saved", "note": None}

    def skipped(note):
        return {"queries": [], "source": None, "note": note}

    cap, models = monthly_cap_krw(), usable_models()
    if cap <= 0 or not models:
        return skipped("영어 검색어 자동 만들기가 꺼져 있어서 낱말표로 찾았어요.")
    if datetime.now(timezone.utc) >= datetime.fromisoformat(store.setting("price_valid_until", DEFAULT_PRICE_VALID_UNTIL)):
        return skipped("모델 단가를 다시 확인해야 해서 영어 검색어 자동 만들기를 쉬고 낱말표로 찾았어요.")
    failed = "영어 검색어를 자동으로 만들지 못해 낱말표로 찾았어요."
    messages = [{"role": "system", "content": _SYSTEM}, {"role": "user", "content": title}]
    options = {"max_tokens": _MAX_TOKENS, "temperature": 0.2}
    for model in models:
        openai = provider_for(model) == "openai"
        client = Provider(store, model=model)
        build = client._openai_request if openai else client._gemini_request
        url, headers, payload = build(os.environ[_KEYS[provider_for(model)]], messages, _RESULT, options)
        price = price_for(model)
        maximum = (len(canonical(payload).encode("utf-8")) * price["input_usd_million"] + _MAX_TOKENS * price["output_usd_million"]) / 1_000_000 * FX_RESERVATION_KRW * 1.2
        if month_spent_krw(store.root) + maximum > cap:
            return skipped(f"이번 달 영어 검색어 자동 만들기 한도({cap:,}원)를 다 써서 낱말표로 찾았어요.")
        try:
            response = (transport or requests.post)(url, headers=headers, json=payload, timeout=(3, 6))
        except requests.RequestException:
            _record(store.root, title_hash, title, model, None, maximum, "unknown")  # 처리됐는지 알 수 없어 최대 금액으로 적어 둔다.
            return skipped(failed)
        if response.status_code in (401, 403):
            _record(store.root, title_hash, title, model, None, 0, "rejected")
            continue  # 키가 만료됐거나 권한이 없다. 과금이 없으니 다음 모델로 넘어간다.
        if response.status_code >= 400:
            unknown = response.status_code >= 500
            _record(store.root, title_hash, title, model, None, maximum if unknown else 0, "unknown" if unknown else "rejected")
            return skipped(failed)
        try:
            data = response.json()
            input_tokens, output_tokens, _, _ = Provider._openai_usage(data) if openai else Provider._gemini_usage(data)
            actual = (input_tokens * price["input_usd_million"] + output_tokens * price["output_usd_million"]) / 1_000_000 * FX_RESERVATION_KRW
        except (ValueError, KeyError, TypeError):
            _record(store.root, title_hash, title, model, None, maximum, "unknown")
            return skipped(failed)
        try:
            text = Provider._openai_text(data) if openai else Provider._gemini_text(data)
            queries = _clean_queries(json.loads(text).get("queries"))
        except (ValueError, KeyError, TypeError, IndexError, AttributeError):
            queries = []
        _record(store.root, title_hash, title, model, queries, actual, "settled")
        store.event("research_query_translated", {"model": model, "input_tokens": input_tokens, "output_tokens": output_tokens,
                                                  "estimated_krw": round(actual, 3), "queries": len(queries), "paid_calls": 1})
        return {"queries": queries, "source": "model", "note": None} if queries else skipped(failed)
    return skipped("모델 키가 만료됐거나 거절돼서 영어 검색어를 자동으로 만들지 못했어요. 낱말표로 찾았어요.")
