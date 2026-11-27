"""트렌드 신호(2026-11-27 사용자 결정, connect-ai-writer lib/trends.mjs 방식을 Python으로 다시 씀).

씨앗 단어마다 구글, 유튜브, 네이버 자동완성과 위키백과 조회수를 모은다. 모델 호출이 없어 0원이다.
신호마다 읽은 주소와 시각을 붙이고, 막히거나 비면 그렇다고 적는다. 숫자가 받쳐 주지 않는 말(폭발, 급등)은 만들지 않는다.
요청 사이에 쉬고, 씨앗은 8개까지만 쓴다. 씨앗은 운영자가 정한 공개 단어만 쓰며 책이나 개인 자료 글은 밖으로 보내지 않는다.
"""
from __future__ import annotations

import json
import re
import time
from datetime import datetime, timedelta, timezone
from urllib.parse import quote, urlencode

import requests

from .feeds import fetch_public
from .store import WorkflowError, now

SETTING = "trend_signals"
REPORT = "trend_signals_report"
SOURCES = ("google", "youtube", "naver", "wikipedia")
LABELS = {"google": "구글 자동완성", "youtube": "유튜브 자동완성", "naver": "네이버 자동완성", "wikipedia": "위키백과 조회수"}
DEFAULT = {"enabled": False, "seeds": ["정보처리기사", "오픽", "편입", "AI 자동화", "공부법"], "sources": list(SOURCES)}
MAX_SEEDS = 8
MAX_ITEMS = 8
PAUSE_SECONDS = 1.0
MIN_VIEWS = 50  # 그 전 7일 조회수가 이보다 적으면 변화율을 쓰지 않는다(작은 수의 비율은 흔들린다)
HOSTS = {"google": {"suggestqueries.google.com"}, "youtube": {"suggestqueries.google.com"},
         "naver": {"ac.search.naver.com"}, "wikipedia": {"ko.wikipedia.org", "wikimedia.org"}}


def trend_settings(store):
    saved = store.setting(SETTING) or {}
    return {**DEFAULT, **{key: saved[key] for key in DEFAULT if key in saved}}


def _validate(values):
    if not isinstance(values.get("enabled"), bool):
        raise WorkflowError("켜기 여부는 참이나 거짓이어야 해요")
    seeds = values.get("seeds")
    if not isinstance(seeds, list) or not 1 <= len(seeds) <= MAX_SEEDS:
        raise WorkflowError(f"씨앗 단어는 1~{MAX_SEEDS}개예요")
    clean = []
    for seed in seeds:
        if not isinstance(seed, str) or not 1 <= len(seed.strip()) <= 30 or any(ord(c) < 32 for c in seed) or re.search(r"https?://|[<>]", seed):
            raise WorkflowError("씨앗 단어는 1~30자의 공개 단어만 넣어요(주소나 기호 없이)")
        if seed.strip() not in clean:
            clean.append(seed.strip())
    sources = values.get("sources")
    if not isinstance(sources, list) or not sources or any(source not in SOURCES for source in sources):
        raise WorkflowError("모을 곳을 하나 이상 고르세요")
    return {"enabled": values["enabled"], "seeds": clean, "sources": [s for s in SOURCES if s in sources]}


def update_trend_settings(store, patch, *, actor):
    values = _validate({**trend_settings(store), **(patch or {})})
    saved = {**values, "updated_by": str(actor)[:120], "updated_at": now()}
    store.set_setting(SETTING, saved)
    store.event("trend_signals_settings", {key: saved[key] for key in ("enabled", "seeds", "sources")})
    return trend_settings(store)


def _json(fetch, url, source):
    body, _, content_type = fetch(url, maximum=400_000, allowed_hosts=HOSTS[source])
    charset = (re.search(r"charset=([\w-]+)", content_type or "") or [None, "utf-8"])[1]
    try:
        return json.loads(body.decode(charset, errors="replace"))
    except (LookupError, ValueError):
        return json.loads(body.decode("utf-8", errors="replace"))


def suggest_url(source, seed):
    if source in ("google", "youtube"):
        params = {"client": "firefox", "hl": "ko", "gl": "kr", "ie": "UTF-8", "oe": "UTF-8", "q": seed}
        if source == "youtube":
            params["ds"] = "yt"
        return "https://suggestqueries.google.com/complete/search?" + urlencode(params)
    return "https://ac.search.naver.com/nx/ac?" + urlencode({"q": seed, "con": 1, "frm": "nv", "ans": 2, "r_format": "json",
                                                            "r_enc": "UTF-8", "r_unicode": 0, "t_koreng": 1, "run": 2, "rev": 4,
                                                            "q_enc": "UTF-8", "st": 100})


def parse_suggestions(source, data, seed):
    if source in ("google", "youtube"):
        values = data[1] if isinstance(data, list) and len(data) > 1 and isinstance(data[1], list) else []
    else:
        groups = data.get("items") if isinstance(data, dict) else None
        first = groups[0] if isinstance(groups, list) and groups and isinstance(groups[0], list) else []
        values = [entry[0] if isinstance(entry, list) and entry else entry for entry in first]
    out = []
    for value in values:
        if isinstance(value, str) and value.strip() and value.strip() != seed and value.strip() not in out:
            out.append(value.strip()[:80])
    return out[:MAX_ITEMS]


def pageviews(seed, fetch, today):
    """위키백과에서 씨앗과 가장 가까운 문서를 찾고 최근 7일과 그 전 7일 조회수를 비교한다(공식 공개 API)."""
    search = "https://ko.wikipedia.org/w/api.php?" + urlencode({"action": "opensearch", "search": seed, "limit": 1, "namespace": 0, "format": "json"})
    found = _json(fetch, search, "wikipedia")
    titles = found[1] if isinstance(found, list) and len(found) > 1 and isinstance(found[1], list) else []
    if not titles:
        return {"status": "missing", "note": "맞는 위키백과 문서가 없어요", "url": search}
    title = titles[0]
    end = today - timedelta(days=1)
    start = end - timedelta(days=13)
    url = ("https://wikimedia.org/api/rest_v1/metrics/pageviews/per-article/ko.wikipedia.org/all-access/user/"
           f"{quote(title.replace(' ', '_'), safe='')}/daily/{start:%Y%m%d}00/{end:%Y%m%d}00")
    data = _json(fetch, url, "wikipedia")
    views = [int(item.get("views") or 0) for item in data.get("items", []) if isinstance(item, dict)][-14:]
    prev7, last7 = sum(views[:-7]) if len(views) > 7 else 0, sum(views[-7:])
    metric = {"title": title, "last7": last7, "prev7": prev7, "change_pct": None}
    note = f"'{title}' 문서"
    if prev7 >= MIN_VIEWS:
        metric["change_pct"] = round((last7 - prev7) * 100 / prev7)
    else:
        note += f". 그 전 7일 조회수가 {MIN_VIEWS}회 미만이라 변화율은 쓰지 않아요"
    return {"status": "ok", "views": metric, "note": note, "url": f"https://ko.wikipedia.org/wiki/{quote(title.replace(' ', '_'))}"}


def _one(source, seed, fetch, today):
    try:
        if source == "wikipedia":
            return pageviews(seed, fetch, today)
        url = suggest_url(source, seed)
        items = parse_suggestions(source, _json(fetch, url, source), seed)
        return {"status": "ok" if items else "empty", "items": [{"text": text} for text in items], "url": url,
                "note": "" if items else "자동완성이 비었어요"}
    except requests.HTTPError as error:
        code = getattr(error.response, "status_code", None)
        if code in (403, 429):
            return {"status": "blocked", "note": f"{LABELS[source]}이 요청을 막았어요({code}). 있는 척하지 않고 비워 둬요"}
        if code == 404:
            return {"status": "missing", "note": "자료가 없어요(404)"}
        return {"status": "error", "note": f"응답 오류 {code}"}
    except Exception as error:  # 신호 하나가 실패해도 나머지는 계속 모은다
        return {"status": "error", "note": type(error).__name__}


def collect_trends(store, *, fetch=fetch_public, pause=time.sleep, today=None):
    settings = trend_settings(store)
    today = today or datetime.now(timezone.utc).date()
    previous = store.setting(REPORT) or {}
    seen = {(row.get("seed"), row.get("source")): {item.get("text") for item in row.get("items") or []}
            for row in previous.get("rows") or [] if row.get("status") == "ok"}
    rows, first = [], True
    for seed in settings["seeds"][:MAX_SEEDS]:
        for source in settings["sources"]:
            if not first:
                pause(PAUSE_SECONDS)
            first = False
            row = {"seed": seed, "source": source, "label": LABELS[source], "checked_at": now(), "items": [], **_one(source, seed, fetch, today)}
            old = seen.get((seed, source))
            if old is not None:  # 지난번에 없던 자동완성만 '새로'로 표시한다. 처음 모은 날은 표시하지 않는다
                for item in row["items"]:
                    item["new"] = item["text"] not in old
            rows.append(row)
    counts = {status: sum(1 for row in rows if row["status"] == status) for status in ("ok", "empty", "blocked", "missing", "error")}
    report = {"checked_at": now(), "seeds": settings["seeds"], "sources": settings["sources"], "rows": rows, "counts": counts,
              "paid_calls": 0, "method": "공개 자동완성과 위키백과 공식 조회수 API를 그대로 옮긴 표예요. 순위나 예측이 아니고, 막힌 곳은 비워 둬요"}
    store.set_setting(REPORT, report)
    store.event("trend_signals_collected", {"rows": len(rows), **counts, "paid_call_made": False})
    return {"rows": len(rows), **counts, "paid_calls": 0}


def trend_status(store):
    return {"settings": trend_settings(store), "report": store.setting(REPORT), "labels": LABELS,
            "limits": {"max_seeds": MAX_SEEDS, "pause_seconds": PAUSE_SECONDS, "min_views": MIN_VIEWS},
            "not_connected": ["네이버 데이터랩: API HUB 키를 받으면 붙여요", "유튜브 최근 2주 벤치마크: YouTube Data API 키를 받으면 붙여요"]}


def queue_trends(store):
    bucket = int(time.time()) // 900
    return store.enqueue("trend_signals", {"requested_at": now()}, key=f"trend_signals:{bucket}")
