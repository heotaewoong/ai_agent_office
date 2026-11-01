"""2026-11-02: 82% of the news candidates (Google News wrappers, YouTube pages, a 403 site) could never be
drafted, so selecting them always ended in an error. Unreadable sources are marked at collection time,
hidden/unselectable on screen and refused before a job is created. No model call is made."""
import pytest
import requests

from office.source_access import probe, status
from office.store import Store, WorkflowError


def article(url, kind=None, **extra):
    return {"id": url[-6:], "title": "기사", "url": url, **({"source_kind": kind} if kind else {}), **extra}


def test_structural_wrappers_are_unreadable_without_any_network_call():
    for kind in ("news_aggregator", "youtube", "search_trend"):
        readable, reason = status(article("https://news.google.com/rss/articles/abc", kind), {})
        assert readable is False and reason
    assert status(article("https://news.google.com/x", "news_aggregator", operator_source_text="본문" * 200), {})[0] is True


def test_probe_marks_refusing_and_empty_hosts_but_never_guesses_on_network_errors():
    def fetch(url, maximum=None):
        if "blocked" in url:
            response = requests.Response()
            response.status_code = 403
            raise requests.HTTPError("403 Forbidden", response=response)
        if "offline" in url:
            raise requests.ConnectionError("dns")
        if "short" in url:
            return b"<p>tiny</p>", url, {}
        return ("<article>" + "<p>충분히 긴 원문 문단입니다.</p>" * 40 + "</article>").encode(), url, {}
    rows = [article("https://blocked.example/a"), article("https://offline.example/b"), article("https://short.example/c"),
            article("https://good.example/d"), article("https://news.google.com/rss/x", "news_aggregator")]
    calls = []
    access = probe(rows, {}, fetch=lambda url, maximum=None: (calls.append(url), fetch(url))[1])
    assert access["blocked.example"]["readable"] is False and "403" in access["blocked.example"]["reason"]
    assert access["short.example"]["readable"] is False
    assert access["good.example"]["readable"] is True
    assert "offline.example" not in access  # unknown → still selectable, retried next collection
    assert not any("news.google.com" in url for url in calls)  # structural kinds are never fetched
    assert status(rows[0], access)[0] is False and status(rows[1], access)[0] is True and status(rows[3], access)[0] is True


def test_recent_probe_results_are_reused_without_refetching():
    previous = {"good.example": {"readable": True, "reason": "", "checked_at": "2999-01-01T00:00:00+00:00"}}
    def fetch(*args, **kwargs):
        raise AssertionError("fresh result must be reused")
    assert probe([article("https://good.example/d")], previous, fetch=fetch)["good.example"]["readable"] is True


def test_job_creation_refuses_unreadable_articles_before_creating_anything(tmp_path):
    from fastapi.testclient import TestClient
    from office.api import create_app
    from datetime import datetime, timezone
    store = Store(tmp_path)
    now = datetime.now(timezone.utc).isoformat()
    good = {"id": "goodart", "title": "읽을 수 있는 기사", "url": "https://good.example/a", "summary": "요약", "published_at": now}
    bad = {"id": "badart", "title": "구글 뉴스 기사", "url": "https://news.google.com/rss/articles/x", "summary": "요약", "published_at": now, "source_kind": "news_aggregator"}
    store.save_articles([good, bad])
    store.set_setting("feed_report", {"active_article_ids": ["goodart", "badart"], "source_access": {}})
    client = TestClient(create_app(store), base_url="http://localhost:8510")
    headers = {"Origin": "http://localhost:3110", "X-Office-CSRF": client.get("/api/session").json()["csrf"]}
    refused = client.post("/api/jobs", json={"article_ids": ["badart"]}, headers=headers)
    assert refused.status_code == 409 and "다른 기사" in refused.json()["detail"]
    assert store.jobs() == []
    dashboard = client.get("/api/dashboard?compact=true").json()
    marks = {row["id"]: row.get("source_readable") for row in dashboard["articles"]}
    assert marks == {"goodart": True, "badart": False}
