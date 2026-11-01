"""Which news candidates can actually be drafted.

2026-11-02 evidence (EC2, 165 candidates): Google News RSS links are encrypted wrappers (11 characters of
text), YouTube pages carry no article, and openai.com answers 403 to automated reads. Selecting any of them
always ended in an error after the job was created. Here we mark them at collection time, the screen hides
them and job creation refuses them up front. No model call is made; drafting still never uses RSS titles
alone (evidence.collect_article_evidence).
"""
from __future__ import annotations

from datetime import datetime, timedelta, timezone
from urllib.parse import urlsplit

import requests

STRUCTURAL = {
    "news_aggregator": "구글 뉴스 중계 주소라 원문을 자동으로 열 수 없어요",
    "youtube": "영상 페이지라 원고로 쓸 글이 없어요",
    "search_trend": "검색 관심 지표라 원문 기사가 없어요",
}
REUSE = timedelta(hours=24)
MINIMUM_TEXT = 200


def host(url):
    return (urlsplit(url or "").hostname or "").lower()


def _fresh(record, current):
    try:
        return current - datetime.fromisoformat(record["checked_at"]) < REUSE
    except (KeyError, TypeError, ValueError):
        return False


def probe(articles, previous=None, *, fetch=None, extract=None, current=None):
    """One read per host. Only a definite answer is recorded: an HTTP refusal or a page without article text.
    Network errors are not recorded, so the host stays selectable and is checked again next collection."""
    if fetch is None:
        from .feeds import fetch_public as fetch
    if extract is None:
        from .evidence import extract_article_text as extract
    current = current or datetime.now(timezone.utc)
    previous = previous or {}
    samples = {}
    for article in articles:
        if article.get("source_kind") in STRUCTURAL or article.get("operator_source_text"):
            continue
        samples.setdefault(host(article.get("url")), article)
    result = {}
    for name, article in samples.items():
        if not name:
            continue
        old = previous.get(name)
        if old and _fresh(old, current):
            result[name] = old
            continue
        try:
            raw, _, _ = fetch(article["url"], maximum=2_000_000)
            text = extract(raw.decode("utf-8", errors="replace"))
            readable = len(text) >= MINIMUM_TEXT
            reason = "" if readable else "원문 본문이 거의 없어 원고 근거로 쓸 수 없어요"
        except requests.HTTPError as error:
            code = getattr(getattr(error, "response", None), "status_code", None)
            readable, reason = False, f"사이트가 자동 열기를 막았어요(HTTP {code})" if code else "사이트가 자동 열기를 막았어요"
        except Exception:
            continue
        result[name] = {"readable": readable, "reason": reason, "checked_at": current.isoformat(), "sample_url": article["url"]}
    return result


def status(article, access):
    """(selectable, reason). Unknown hosts stay selectable; the draft step still reads the page itself."""
    if article.get("operator_source_text"):
        return True, ""
    reason = STRUCTURAL.get(article.get("source_kind"))
    if reason:
        return False, reason
    record = (access or {}).get(host(article.get("url")))
    if record and record.get("readable") is False:
        return False, record.get("reason") or "원문을 자동으로 열 수 없어요"
    return True, ""


def annotate(articles, access):
    rows = []
    for article in articles:
        readable, reason = status(article, access)
        rows.append({**article, "source_readable": readable, **({"source_unreadable_reason": reason} if reason else {})})
    return rows
