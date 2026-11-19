from datetime import datetime, timedelta, timezone
from urllib.parse import urlsplit

from office import discovery, platform_news
from office.store import Store, digest
from office.benchmarks import DEFAULT as BENCHMARK_DEFAULT

NOW = datetime(2026, 11, 19, 5, 0, tzinfo=timezone.utc)


def result(identity, views, stamped=NOW, title="AI automation news", channel="Test channel"):
    return {"id": identity, "snippet": {"title": title, "channelTitle": channel,
            "publishedAt": stamped.isoformat(), "description": "Public metadata"},
            "statistics": {"viewCount": views}}


def test_youtube_custom_topic_candidates_use_fixed_scope_and_compare_valid_public_counts():
    ids = ("AA000000000", "BB000000000", "CC000000000", "DD000000000")
    requests = []
    rows = [result(ids[0], "9"), result(ids[1], "100", channel="Channel B"), result(ids[2], None),
            result(ids[3], "9999", NOW - timedelta(days=8))]

    def fetch(endpoint, params, key):
        requests.append((endpoint, params, key))
        if endpoint == "search":
            return {"items": [{"id": {"videoId": video_id}} for video_id in ids]}
        return {"items": rows}

    data = platform_news.youtube_candidates("key-fixture", "AI automation news", "KR", NOW, fetch=fetch)
    assert requests[0][1]["order"] == "viewCount"
    assert requests[0][1]["q"] == "AI automation news"
    assert len(requests) == 2
    assert requests[0][1]["publishedAfter"] == (NOW - timedelta(days=7)).isoformat()
    assert requests[0][1]["regionCode"] == "KR"
    assert requests[-1][1]["id"] == ",".join(ids)
    assert [row["id"] for row in data] == [ids[1], ids[0], ids[2]]
    assert [row["metrics"] for row in data] == [{"views": 100}, {"views": 9}, {}]
    assert all(urlsplit(row["url"]).hostname == "www.youtube.com" for row in data)


def test_read_only_platform_news_keeps_observations_on_real_platform_and_preserves_missing_counts(tmp_path, monkeypatch):
    store = Store(tmp_path)
    def row(pid, url, metrics):
        return {"id": pid, "title": "AI agent walkthrough", "platform": "instagram",
                "url": url, "source_id": "every-ai-instagram", "source_name": "Sample creator",
                "checked_at": NOW.isoformat(), "published_at": NOW.isoformat(), "metrics": metrics}
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
    legacy_path = platform_news._cache_path(store).with_name("platform-news.json")
    legacy_path.parent.mkdir(parents=True, exist_ok=True)
    legacy = '{"attempted_at":"' + NOW.isoformat() + '","youtube_attempted_at":"' + NOW.isoformat() + '"}'
    legacy_path.write_text(legacy, encoding="utf-8")
    monkeypatch.setenv("HEOBRAIN_YOUTUBE_DATA_API_KEY", "AI" + "a" * 37)
    monkeypatch.setenv("HEOBRAIN_PLATFORM_NEWS_SOURCES_DB", str(tmp_path / "missing.db"))
    calls = []
    def fetch(key, topic, region, current):
        calls.append((topic, region))
        return [{"id": "AA000000000", "title": "AI agent walkthrough", "url": "https://www.youtube.com/watch?v=AA000000000",
                 "source": "Public channel", "metrics": {"views": 40}, "published_at": NOW.isoformat(),
                 "observed_at": NOW.isoformat(), "summary": ""}]
    monkeypatch.setattr(platform_news, "youtube_candidates", fetch)
    monkeypatch.setattr(platform_news, "blog_candidates", lambda current, topic: {})
    assert platform_news.refresh(store, current=NOW)["status"] == "refreshed"
    assert platform_news.refresh(store, current=NOW + timedelta(hours=2))["status"] == "cached"
    assert calls == [(discovery.DEFAULT["topic"], "KR")]
    assert legacy_path.read_text(encoding="utf-8") == legacy
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
    monkeypatch.setattr(platform_news, "blog_candidates", lambda current, topic: {})
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


def test_broad_ai_search_runs_three_selective_queries_and_filters_noisy_high_view_titles():
    ids = ("AA000000000", "BB000000000", "CC000000000", "DD000000000", "EE000000000")
    requests = []
    rows = [
        result(ids[0], "80000", title="Weekend celebrity roundup #AI"),
        result(ids[1], "1000", title="생성형 AI 워크플로우", channel="Creator One"),
        result(ids[2], "900", title="AI 에이전트 실전", channel="Creator One"),
        result(ids[3], "800", title="OpenAI 모델 업데이트", channel="creator one"),
        result(ids[4], "700", title="Claude Code 업무 자동화", channel="Creator Two"),
    ]
    def fetch(endpoint, params, key):
        requests.append((endpoint, params))
        if endpoint == "search":
            return {"items": [{"id": {"videoId": identity}} for identity in ids]}
        return {"items": rows}

    data = platform_news.youtube_candidates("key-fixture", "AI", "KR", NOW, fetch=fetch)
    assert [params["q"] for endpoint, params in requests if endpoint == "search"] == [
        "AI 에이전트", "AI 자동화", "생성형 AI",
    ]
    assert requests[-1] == ("videos", {"part": "snippet,statistics", "id": ",".join(ids)})
    assert [row["id"] for row in data] == [ids[1], ids[2], ids[4]]


def test_platform_status_keeps_multiple_observed_creators_without_unrelated_or_overview_rows(tmp_path, monkeypatch):
    import json

    store = Store(tmp_path)
    monkeypatch.setenv("HEOBRAIN_PLATFORM_NEWS_SOURCES_DB", str(tmp_path / "missing.db"))
    baseline = {
        "platform": "threads", "title": "Agentic AI workflow", "source": "@Mixed.Name",
        "observed_at": NOW.isoformat(), "published_at": NOW.isoformat(), "metric_precision": {"likes": "exact"},
    }
    observations = [
        {**baseline, "url": "https://www.threads.com/@mixed.name/post/A1", "metrics": {"likes": 60}},
        {**baseline, "url": "https://www.threads.com/@mixed.name/post/A2", "metrics": {"likes": 50}},
        {**baseline, "source": "Mixed.Name", "url": "https://www.threads.net/@Mixed.Name/post/A3",
         "metrics": {"likes": 40}},
        {**baseline, "url": "https://www.threads.net/@mixed.name/post/A1", "metrics": {"likes": 60}},
        {**baseline, "source": "Different creator", "url": "https://www.threads.com/@different/post/B2"},
        {**baseline, "source": "Different creator", "url": "https://www.threads.com/@different/post/B5",
         "metrics": {"likes": 12}},
        {**baseline, "source": "Unrelated", "title": "Weekend entertainment #AI",
         "url": "https://www.threads.com/@different/post/B3", "metrics": {"likes": 999}},
        {**baseline, "source": "Unrelated", "url": "https://www.threads.com/search?q=AI"},
        {**baseline, "url": "https://www.threads.com/@different/post/B4",
         "observed_at": (NOW + timedelta(days=1)).isoformat()},
        {**baseline, "platform": "linkedin", "source": "LLM Co", "title": "LLM 인프라",
         "url": "https://www.linkedin.com/posts/llm-activity-123", "metrics": {"reactions": 51},
         "metric_precision": {"reactions": "exact"}},
        {**baseline, "platform": "tistory", "source": "AI Journal", "title": "LLM의 추론",
         "url": "https://aijournal.tistory.com/42", "published_at": NOW.isoformat()},
        {**baseline, "platform": "tistory", "source": "AI Journal", "title": "LLM 카테고리",
         "url": "https://aijournal.tistory.com/category/LLM"},
    ]
    observation_file = platform_news._cache_path(store).with_name("public-platform-observations.json")
    observation_file.parent.mkdir(parents=True, exist_ok=True)
    observation_file.write_text(json.dumps(observations), encoding="utf-8")
    groups = {row["id"]: row for row in platform_news.status(store, current=NOW)["platforms"]}
    threads = groups["threads"]
    assert threads["source_status"] == "observed"
    assert threads["criteria"]["metric"] == "likes"
    assert [row["url"].split("/")[-1] for row in threads["items"]] == ["A1", "A2", "B5"]
    assert threads["items"][-1]["metrics"] == {"likes": 12}
    linkedin = groups["linkedin"]
    assert linkedin["criteria"]["metric"] == "reactions"
    assert linkedin["items"][0]["metrics"] == {"reactions": 51}
    assert [row["url"] for row in groups["tistory"]["items"]] == ["https://aijournal.tistory.com/42"]


def test_tistory_keeps_recent_topical_rows_from_several_publishers(tmp_path, monkeypatch):
    store = Store(tmp_path)
    monkeypatch.setenv("HEOBRAIN_PLATFORM_NEWS_SOURCES_DB", str(tmp_path / "missing.db"))

    def row(host, identity, title, age=0):
        return {"url": f"https://{host}.tistory.com/{identity}", "title": title,
                "source": host.upper(), "summary": "", "published_at": (NOW - timedelta(days=age)).isoformat(),
                "observed_at": NOW.isoformat(), "metrics": {}}

    platform_news._write_cache(store, {"blogs": {"tistory": {
        "checked_at": NOW.isoformat(), "sources_succeeded": 2, "items": [
            row("aijournal", 10, "OpenAI 모델"),
            row("aijournal", 11, "인공지능 챗봇"),
            row("aijournal", 12, "Claude Code 사용법", 1),
            row("different", 42, "AI 에이전트 실전", 2),
            row("noise", 12, "축구 국가대표 경기"),
            row("reference", 43, "AI 에이전트 기본", 8),
            row("old", 44, "생성형 AI 개론", 31),
        ],
    }}})
    groups = {row["id"]: row for row in platform_news.status(store, current=NOW)["platforms"]}
    assert [row["url"].split("/")[-1] for row in groups["tistory"]["items"]] == ["10", "11", "42"]
    assert groups["tistory"]["criteria"]["kind"] == "latest"
    assert [r["url"].split("/")[-1] for r in groups["tistory"]["reference_items"]] == ["43"]


def test_native_popularity_separates_publication_and_observation_uses_fixed_metric_and_preserves_unknown(tmp_path, monkeypatch):
    import json

    store = Store(tmp_path)
    monkeypatch.setenv("HEOBRAIN_PLATFORM_NEWS_SOURCES_DB", str(tmp_path / "missing.db"))

    def row(identity, author, published_days, observed_days, metrics):
        return {"platform": "instagram", "source": author, "title": "AI agent workflow",
                "url": "https://www.instagram.com/p/" + identity + "/",
                "published_at": (NOW - timedelta(days=published_days)).isoformat()
                if published_days is not None else None,
                "observed_at": (NOW - timedelta(days=observed_days)).isoformat(),
                "metrics": metrics, "metric_precision": dict.fromkeys(metrics, "exact")}

    observations = [
        row("zero", "Zero", 1, 0, {"likes": 0, "views": 90000}),
        row("top", "High", 1, 0, {"likes": 27}),
        row("newer_measurement", "Same", 1, 0, {"likes": 15}),
        row("newer_measurement", "Same", 1, 2, {"likes": 17}),
        row("old", "Old", 8, 0, {"likes": 10000}),
        row("unknown_date", "Undated", None, 0, {"likes": 20000}),
        row("stale_measurement", "Stale", 7, 8, {"likes": 20000}),
        row("views_only", "Views", 1, 0, {"views": 25000}),
        row("beyond_window", "Archives", 31, 0, {"likes": 99999}),
    ]
    observation_file = platform_news._cache_path(store).with_name("public-platform-observations.json")
    observation_file.parent.mkdir(parents=True, exist_ok=True)
    observation_file.write_text(json.dumps(observations), encoding="utf-8")
    groups = {row["id"]: row for row in platform_news.status(store, current=NOW)["platforms"]}
    instagram = groups["instagram"]
    assert instagram["criteria"] == {
        "kind": "popularity", "metric": "likes", "published_days": 7, "observation_days": 7,
        "reference_days": 30, "source": "browser_observation", "scope": instagram["criteria"]["scope"],
    }
    assert [r["url"].split("/")[-2] for r in instagram["items"]] == ["top", "newer_measurement", "zero"]
    assert [r["metrics"]["likes"] for r in instagram["items"]] == [27, 15, 0]
    refs = {r["url"].split("/")[-2]: r for r in instagram["reference_items"]}
    assert set(refs) == {"old", "unknown_date", "stale_measurement", "views_only"}
    assert "likes" not in refs["views_only"]["metrics"]
    assert "likes" not in refs["stale_measurement"]["metrics"]


def test_youtube_registered_rss_fallback_uses_published_date_while_api_popularity_requires_views(tmp_path, monkeypatch):
    store = Store(tmp_path)
    monkeypatch.setenv("HEOBRAIN_PLATFORM_NEWS_SOURCES_DB", str(tmp_path / "missing.db"))
    creator = next(row for row in BENCHMARK_DEFAULT["sources"] if row["platform"] == "youtube")
    listed = [
        {"id": "older", "title": "AI agent guide", "platform": "youtube", "source_id": creator["id"],
         "url": "https://www.youtube.com/watch?v=AA000000000", "source_name": "Example",
         "published_at": (NOW - timedelta(days=2)).isoformat(), "checked_at": NOW.isoformat(),
         "metrics": {"views": {"availability": "observed", "precision": "exact", "value": 9999}}},
        {"id": "newer", "title": "AI agent news", "platform": "youtube", "source_id": creator["id"],
         "url": "https://www.youtube.com/watch?v=BB000000000", "source_name": "Example",
         "published_at": NOW.isoformat(), "checked_at": NOW.isoformat()},
    ]
    store.set_setting("benchmark_snapshot", {"registry_hash": digest(BENCHMARK_DEFAULT), "items": listed})
    data = platform_news.status(store, current=NOW)["platforms"][0]
    assert data["criteria"]["source"] == "public_rss"
    assert data["criteria"]["kind"] == "latest"
    assert data["criteria"]["metric"] is None
    assert [r["id"] for r in data["items"]] == ["newer", "older"]

    api_items = {r["id"]: r for r in data["items"]}
    platform_news._write_cache(store, {"youtube": {
        "state": "available", "topic": discovery.DEFAULT["topic"], "region": "KR",
        "checked_at": NOW.isoformat(), "items": list(api_items.values()),
    }})
    data = platform_news.status(store, current=NOW)["platforms"][0]
    assert data["criteria"]["source"] == "youtube_api"
    assert data["criteria"]["metric"] == "views"
    assert [r["id"] for r in data["items"]] == ["older"]
    assert [r["id"] for r in data["reference_items"]] == ["newer"]
