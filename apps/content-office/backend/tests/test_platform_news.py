from datetime import datetime, timedelta, timezone
from urllib.parse import urlsplit

from office import discovery, platform_news
from office.store import Store, digest
from office.benchmarks import DEFAULT as BENCHMARK_DEFAULT

NOW = datetime(2026, 11, 19, 5, 0, tzinfo=timezone.utc)


def result(identity, views, stamped=NOW):
    return {"id": identity, "snippet": {"title": identity, "channelTitle": "Test channel",
            "publishedAt": stamped.isoformat(), "description": "Public metadata"},
            "statistics": {"viewCount": views}}


def test_youtube_candidates_use_fixed_scope_and_compare_valid_public_counts():
    ids = ("AA000000000", "BB000000000", "CC000000000", "DD000000000")
    requests = []
    rows = [result(ids[0], "9"), result(ids[1], "100"), result(ids[2], None),
            result(ids[3], "9999", NOW - timedelta(days=8))]

    def fetch(endpoint, params, key):
        requests.append((endpoint, params, key))
        if endpoint == "search":
            return {"items": [{"id": {"videoId": video_id}} for video_id in ids]}
        return {"items": rows}

    data = platform_news.youtube_candidates("key-fixture", "AI 자동화", "KR", NOW, fetch=fetch)
    assert requests[0][1]["order"] == "viewCount"
    assert requests[0][1]["publishedAfter"] == (NOW - timedelta(days=7)).isoformat()
    assert requests[0][1]["regionCode"] == "KR"
    assert requests[1][1]["id"] == ",".join(ids)
    assert [row["id"] for row in data] == [ids[1], ids[0], ids[2]]
    assert [row["metrics"] for row in data] == [{"views": 100}, {"views": 9}, {}]
    assert all(urlsplit(row["url"]).hostname == "www.youtube.com" for row in data)


def test_read_only_platform_news_keeps_observations_on_real_platform_and_preserves_missing_counts(tmp_path, monkeypatch):
    store = Store(tmp_path)
    def row(pid, url, metrics):
        return {"id": pid, "title": "verified item", "platform": "instagram",
                "url": url, "source_id": "every-ai-instagram", "source_name": "Sample creator",
                "checked_at": NOW.isoformat(), "metrics": metrics}
    store.set_setting("benchmark_snapshot", {"registry_hash": digest(BENCHMARK_DEFAULT), "items": [
        row("example", "https://www.instagram.com/p/test_public_/", {"likes": {"value": 7, "availability": "observed", "precision": "approximate"},
            "comments": {"value": None, "availability": "not_visible", "precision": "unknown"}}),
        row("mismatch", "https://www.youtube.com/watch?v=A0A0A0A0A0A", {}),
    ]})
    monkeypatch.setenv("HEOBRAIN_PLATFORM_NEWS_SOURCES_DB", str(tmp_path / "missing.db"))
    monkeypatch.setattr(platform_news, "youtube_candidates", lambda *_: (_ for _ in ()).throw(AssertionError("GET must not fetch")))
    data = platform_news.status(store, current=NOW)
    groups = {row["id"]: row for row in data["platforms"]}
    assert groups["youtube"]["source_status"] == "waiting"
    assert groups["instagram"]["source_status"] == "observed"
    assert [row["id"] for row in groups["instagram"]["items"]] == ["example"]
    assert groups["instagram"]["items"][0]["metrics"] == {"likes": 7}
    assert groups["instagram"]["items"][0]["metric_precision"] == {"likes": "approximate"}
    assert groups["threads"]["items"] == []


def test_platform_refresh_reuses_cache_then_hides_expired_stats(tmp_path, monkeypatch):
    store = Store(tmp_path)
    monkeypatch.setenv("HEOBRAIN_YOUTUBE_DATA_API_KEY", "AI" + "a" * 37)
    monkeypatch.setenv("HEOBRAIN_PLATFORM_NEWS_SOURCES_DB", str(tmp_path / "missing.db"))
    calls = []
    def fetch(key, topic, region, current):
        calls.append((topic, region))
        return [{"id": "AA000000000", "title": "video title", "url": "https://www.youtube.com/watch?v=AA000000000",
                 "source": "Public channel", "metrics": {"views": 40}, "published_at": NOW.isoformat(),
                 "observed_at": NOW.isoformat(), "summary": ""}]
    monkeypatch.setattr(platform_news, "youtube_candidates", fetch)
    monkeypatch.setattr(platform_news, "blog_candidates", lambda current: {})
    assert platform_news.refresh(store, current=NOW)["status"] == "refreshed"
    assert platform_news.refresh(store, current=NOW + timedelta(hours=2))["status"] == "cached"
    assert calls == [(discovery.DEFAULT["topic"], "KR")]
    assert platform_news.status(store, current=NOW)["platforms"][0]["items"][0]["metrics"]["views"] == 40
    stale = platform_news.status(store, current=NOW + timedelta(hours=31))["platforms"][0]
    assert stale["source_status"] == "stale"
    assert not stale["items"]



def test_route_preserves_private_cache_and_keyless_setup_can_later_start_a_real_search(tmp_path, monkeypatch):
    from fastapi.testclient import TestClient
    from office.api import create_app

    store = Store(tmp_path)
    monkeypatch.delenv("HEOBRAIN_YOUTUBE_DATA_API_KEY", raising=False)
    monkeypatch.setenv("HEOBRAIN_YOUTUBE_DATA_API_KEY_FILE", str(tmp_path / "missing.key"))
    monkeypatch.setenv("HEOBRAIN_PLATFORM_NEWS_SOURCES_DB", str(tmp_path / "missing.db"))
    monkeypatch.setattr(platform_news, "blog_candidates", lambda current: {})
    assert platform_news.refresh(store, current=NOW)["youtube_status"] == "waiting"
    assert platform_news.status(store, current=NOW)["platforms"][0]["items"] == []
    calls = []
    def fetch(key, topic, region, current):
        calls.append((topic, region))
        return []
    monkeypatch.setattr(platform_news, "youtube_candidates", fetch)
    monkeypatch.setenv("HEOBRAIN_YOUTUBE_DATA_API_KEY", "AI" + "a" * 37)
    assert platform_news.refresh(store, current=NOW + timedelta(minutes=1))["youtube_status"] == "available"

    response = TestClient(create_app(store)).get("/api/platform-news")
    assert response.status_code == 200
    assert "no-store" in response.headers["cache-control"]
    assert [row["id"] for row in response.json()["platforms"]] == list(platform_news.PLATFORMS)
    assert calls == [(discovery.DEFAULT["topic"], "KR")]
