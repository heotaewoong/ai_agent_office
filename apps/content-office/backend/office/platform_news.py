"""Public platform discovery through official data and existing observations."""
from __future__ import annotations

import argparse
import http.client
import json
import os
import re
import sqlite3
import stat
import tempfile
import unicodedata
from concurrent.futures import ThreadPoolExecutor
from datetime import datetime, timedelta, timezone
from pathlib import Path
from urllib.parse import parse_qs, unquote, urlencode, urlsplit
from xml.etree.ElementTree import ParseError

from requests import RequestException

from . import benchmarks, discovery
from .feeds import clean_text, fetch_public, normalize_url, parse_date, parse_feed
from .runtime import AlreadyRunning, ProcessLock
from .store import Store, digest

MAX_ITEMS = 8
MAX_PER_CREATOR = 2
MAX_STAT = 9007199254740991
MAX_BYTES = 1_000_000
OBSERVATION_BYTES = 256 * 1024
OBSERVATION_LIMIT = 128
FRESHNESS = timedelta(hours=30)
REFRESH_INTERVAL = timedelta(hours=12)
OBSERVATION_AGE = timedelta(days=7)
BLOG_AGE = timedelta(days=30)
VIDEO_ID = re.compile(r"[A-Za-z0-9_-]{11}")
COUNTERS = {"views": "viewCount", "likes": "likeCount", "comments": "commentCount"}
OBSERVED_COUNTERS = (*COUNTERS, "reactions", "reposts")
PLATFORMS = ("youtube", "naver_blog", "tistory", "instagram", "threads", "tiktok", "x", "linkedin")
AI_QUERIES = {
    "KR": ("AI 에이전트", "AI 자동화", "생성형 AI"),
    "JP": ("AI エージェント", "AI 自動化", "生成 AI"),
}
AI_SIGNALS = re.compile(
    r"(?<![a-z\d])(?:openai|anthropic|claude(?:\s+code)?|chatgpt|gpt(?:-\d+)?|codex|llms?|rag|mcp|"
    r"llama\.cpp|ollama|qwen\d*|langgraph|coding\s+agents?|"
    r"gemini\s+(?:\d|cli|pro|flash|advanced|ultra)|artificial intelligence|machine learning|"
    r"ai[-\s]+(?:agents?\b|automation\b|workflow|tools?\b|models?\b|coding\b|developer\b|news\b|"
    r"research\b|engineer|researcher|inference\b|training\b|updates?\b|에이전트|자동화|워크플로|"
    r"도구|모델|코딩|뉴스|개발|기술|연구|전략|생성|활용|비서|서비스|エージェント|自動化)|"
    r"ai(?:가|로|를|의|를|에서|에이전트|자동화)|(?:generative|agentic)\s+ai\b|agentic\s+(?:engineer|workflow|coding))(?![a-z\d])|"
    r"인공지능|코딩\s*에이전트|대형\s*언어\s*모델|생성형|챗GPT|머신\s*러닝|딥\s*러닝|제미나이|生成\s*AI|人工知能",
    re.IGNORECASE,
)
BLOG_FEEDS = {
    "naver_blog": (
        ("naver-cloud", "네이버클라우드", "https://rss.blog.naver.com/n_cloudplatform.xml"),
        ("naver-search", "NAVER Search & Tech", "https://rss.blog.naver.com/naver_search.xml"),
        ("naver-kcc", "한국저작권위원회", "https://rss.blog.naver.com/kcc_press.xml"),
    ),
    "tistory": (
        ("tistory-bcho", "조대협 티스토리", "https://bcho.tistory.com/rss"),
        ("tistory-learning", "러닝머신 티스토리", "https://lsjsj92.tistory.com/rss"),
        ("tistory-gillilab", "GilliLab", "https://rupijun.tistory.com/rss"),
        ("tistory-bilient", "Connecting HW and SW", "https://bilient.tistory.com/rss"),
        ("tistory-brainchaos", "brainchaos UnLoG", "https://brainchaos.tistory.com/rss"),
    ),
}
SIDECAR_SOURCES = {
    "instagram-every": ("instagram", "every._ai"),
    "threads-geeknews": ("threads", "GeekNews"),
    "tiktok-trends": ("tiktok", "TikTok Creative Center"),
    "linkedin-openai": ("linkedin", "OpenAI"),
    **{identity: (platform, name) for platform, feeds in BLOG_FEEDS.items() for identity, name, _ in feeds},
}
REFERENCE = {
    "tiktok": "https://ads.tiktok.com/creative/creativeCenter/trends/hashtag?period=7&region=KR",
    "linkedin": "https://www.linkedin.com/company/openai/",
}
LABELS = {"naver_blog": "네이버 블로그", "tistory": "티스토리", **{
    k: benchmarks.PLATFORMS[k] for k in PLATFORMS if k not in ("naver_blog", "tistory")
}}


def _count(value):
    if isinstance(value, str) and value.isascii() and value.isdigit() and len(value) <= 16:
        value = int(value)
    return value if type(value) is int and 0 <= value <= MAX_STAT else None


def _public_text(value, maximum, *, max_words=None):
    value = clean_text(value) if isinstance(value, str) else ""
    return (" ".join(value.split()[:max_words]) if max_words else value)[:maximum]


def _youtube_get(endpoint, params, key):
    # Fixed destination; a redirect never carries the header to another host.
    conn = http.client.HTTPSConnection("www.googleapis.com", timeout=10)
    try:
        conn.request("GET", "/youtube/v3/" + endpoint + "?" + urlencode(params),
                     headers={"X-Goog-Api-Key": key, "Accept": "application/json"})
        response = conn.getresponse()
        if response.status != 200:
            raise RuntimeError("YouTube API HTTP " + str(response.status))
        payload = response.read(MAX_BYTES + 1)
        if len(payload) > MAX_BYTES:
            raise ValueError("응답 크기 한도를 초과했습니다")
        value = json.loads(payload)
        if not isinstance(value, dict) or not isinstance(value.get("items"), list):
            raise ValueError("YouTube 응답 구조가 예상과 다릅니다")
        return value
    finally:
        conn.close()


def _broad_ai(topic):
    return " ".join(topic.casefold().split()) in {"ai", "인공지능", "ai 자동화", "ai automation"}


def _matches_topic(text, topic):
    if _broad_ai(topic):
        return bool(AI_SIGNALS.search(text))
    terms = re.findall(r"[^\W_]+", topic.casefold())
    text = text.casefold()
    return bool(terms) and all(
        re.search(r"(?<![a-z0-9])" + re.escape(term) + r"(?![a-z0-9])", text) for term in terms
    )


def youtube_candidates(key, topic, region, current, *, fetch=_youtube_get):
    since = current - timedelta(days=7)
    queries = AI_QUERIES.get(region, ("AI agents", "AI automation", "generative AI")) if _broad_ai(topic) else (topic,)
    ids = {}
    for query in queries:
        search = fetch("search", {"part": "snippet", "fields": "items(id/videoId)", "type": "video",
                                 "q": query, "order": "viewCount", "publishedAfter": since.isoformat(),
                                 "regionCode": region, "relevanceLanguage": discovery.REGIONS[region][0].split("-")[0],
                                 "maxResults": MAX_ITEMS * 2}, key)
        for row in search["items"][:MAX_ITEMS * 2]:
            identity = row.get("id") if isinstance(row, dict) else None
            video_id = identity.get("videoId") if isinstance(identity, dict) else None
            if isinstance(video_id, str) and VIDEO_ID.fullmatch(video_id):
                ids[video_id] = None
    if not ids:
        return []
    rows = fetch("videos", {"part": "snippet,statistics", "id": ",".join(ids)}, key)
    candidates = []
    seen = set()
    for row in rows["items"][:len(ids)]:
        if not isinstance(row, dict):
            continue
        video_id, snippet = row.get("id"), row.get("snippet", {})
        if not isinstance(video_id, str) or video_id not in ids or video_id in seen or not isinstance(snippet, dict):
            continue
        published = _optional_date(snippet.get("publishedAt"))
        title = _public_text(snippet.get("title"), 180)
        if not published or not since <= published <= current + timedelta(minutes=5) or not _matches_topic(title, topic):
            continue
        seen.add(video_id)
        stats = row.get("statistics")
        stats = stats if isinstance(stats, dict) else {}
        metrics = {name: count for name, field in COUNTERS.items()
                   if (count := _count(stats.get(field))) is not None}
        candidates.append({"id": video_id, "title": title,
                           "url": "https://www.youtube.com/watch?v=" + video_id,
                           "source": _public_text(snippet.get("channelTitle"), 100) or "YouTube",
                           "summary": _public_text(snippet.get("description"), 180, max_words=20),
                           "published_at": published.isoformat(), "observed_at": current.isoformat(),
                           "metrics": metrics, "metric_precision": dict.fromkeys(metrics, "exact")})
    return _select("youtube", candidates, "views")


def _exact_post(platform, url):
    if not isinstance(url, str) or len(url) > 2000 or any(c in url for c in "\r\n<>\\"):
        return False
    try:
        p = urlsplit(url)
        host, path = p.hostname or "", p.path
        if p.scheme != "https" or p.username or p.password or p.port not in (None, 443):
            return False
    except ValueError:
        return False
    if platform == "youtube":
        return bool(
            host in ("youtu.be", "www.youtu.be") and VIDEO_ID.fullmatch(path.strip("/"))
            or host in ("youtube.com", "www.youtube.com", "m.youtube.com") and
            (path == "/watch" and VIDEO_ID.fullmatch(parse_qs(p.query).get("v", [""])[0])
             or re.fullmatch(r"/(?:shorts|live)/[A-Za-z0-9_-]{11}/?", path))
        )
    if platform == "naver_blog":
        return host in ("blog.naver.com", "m.blog.naver.com") and bool(
            re.fullmatch(r"/[A-Za-z0-9_.-]+/\d+/?", path) or
            path == "/PostView.naver" and parse_qs(p.query).get("logNo", [""])[0].isdigit()
            and re.fullmatch(r"[A-Za-z0-9_.-]+", parse_qs(p.query).get("blogId", [""])[0]))
    if platform == "tistory":
        return host.endswith(".tistory.com") and bool(re.fullmatch(r"/(?:[0-9]+|entry/[^/]+)/?", path))
    if platform == "instagram":
        return host in ("www.instagram.com", "instagram.com") and bool(re.fullmatch(
            r"/(?:[A-Za-z0-9._]+/)?(?:p|reel)/[A-Za-z0-9_-]+/?", path))
    if platform == "threads":
        return host in ("www.threads.com", "threads.com", "www.threads.net", "threads.net") and bool(
            re.fullmatch(r"/@[A-Za-z0-9._]+/post/[A-Za-z0-9_-]+/?", path))
    if platform == "tiktok":
        return host in ("www.tiktok.com", "tiktok.com") and bool(re.fullmatch(r"/@[^/]+/video/\d+/?", path))
    if platform == "x":
        return host in ("www.x.com", "x.com", "www.twitter.com", "twitter.com") and bool(
            re.fullmatch(r"/[^/]+/status/\d+/?", path))
    return host in ("www.linkedin.com", "linkedin.com") and bool(
        re.fullmatch(r"/posts/[^/]+/?", path)
        or re.fullmatch(r"/feed/update/urn:li:(?:activity|ugcPost|share):[0-9]+/?", unquote(path))
    )


def _optional_date(value):
    return parse_date(value) if isinstance(value, str) else None


def _recent(value, current, age):
    parsed = _optional_date(value)
    return bool(parsed and -timedelta(minutes=5) <= current - parsed <= age)


def _date_string(value, current):
    parsed = _optional_date(value)
    return parsed.isoformat() if parsed and parsed <= current + timedelta(minutes=5) else None


def _candidate(row, platform, current, *, observed=None):
    url = row.get("url")
    if not _exact_post(platform, url):
        return None
    observed_at = _date_string(observed or row.get("checked_at") or row.get("observed_at"), current)
    metrics, precision = {}, {}
    if _recent(observed_at, current, OBSERVATION_AGE):
        for name, metric in (row.get("metrics") or {}).items():
            if name not in OBSERVED_COUNTERS or not isinstance(metric, dict) or metric.get("availability") != "observed":
                continue
            count = _count(metric.get("value"))
            exactness = metric.get("precision")
            if count is not None and exactness in ("exact", "approximate"):
                metrics[name], precision[name] = count, exactness
    return {"id": row.get("id") or "platform-" + digest(url)[:24], "url": url,
            "title": clean_text(row.get("title"))[:180] or LABELS[platform] + " 공개 게시물",
            "source": clean_text(row.get("source_name") or row.get("feed_name"))[:100] or LABELS[platform],
            "summary": clean_text(row.get("summary"))[:250],
            "published_at": _date_string(row.get("published_at"), current), "observed_at": observed_at,
            "metrics": metrics, "metric_precision": precision}


def _post_key(platform, url):
    parsed = urlsplit(url)
    if platform in ("instagram", "threads", "tiktok", "x"):
        return parsed.path.strip("/").split("/")[-1]
    if platform == "naver_blog":
        fields = parse_qs(parsed.query)
        if parsed.path == "/PostView.naver":
            return (fields.get("blogId", [""])[0].casefold(), fields["logNo"][0])
        creator, identity = parsed.path.strip("/").split("/")
        return (creator.casefold(), identity)
    return normalize_url(url)


def _unique(platform, rows):
    items = {}
    for row in rows:
        key = _post_key(platform, row["url"])
        previous = items.get(key)
        if previous is None or (not previous["metrics"] and row["metrics"]):
            items[key] = row
    return list(items.values())


def _sort_key(row, metric=None):
    return row["metrics"].get(metric, -1), row["published_at"] or row["observed_at"] or ""


def _creator_key(platform, row):
    parsed = urlsplit(row["url"])
    path = parsed.path.strip("/").split("/")
    if platform == "tistory":
        name = parsed.hostname
    elif platform == "naver_blog":
        name = parse_qs(parsed.query).get("blogId", [""])[0] if parsed.path == "/PostView.naver" else path[0]
    elif platform in ("threads", "tiktok", "x") or platform == "instagram" and len(path) == 3:
        name = path[0]
    else:
        name = row["source"]
    return " ".join(unicodedata.normalize("NFKC", name or row["source"]).casefold().lstrip("@").split())


def _select(platform, rows, metric=None):
    ranked = sorted(_unique(platform, rows), key=lambda row: _sort_key(row, metric), reverse=True)
    result, creators = [], {}
    for row in ranked:
        creator = _creator_key(platform, row)
        count = creators.get(creator, 0)
        if count >= MAX_PER_CREATOR:
            continue
        result.append(row)
        creators[creator] = count + 1
        if len(result) == MAX_ITEMS:
            break
    return result


def _topic_rows(rows, topic):
    if not _broad_ai(topic):
        return rows
    return [row for row in rows if _matches_topic(row["title"], topic)]


def _recent_blogs(rows, current):
    return [row for row in rows if _recent(row["published_at"] or row["observed_at"], current, BLOG_AGE)]


def blog_candidates(current, topic=discovery.DEFAULT["topic"]):
    def collect(platform, feed):
        identity, label, url = feed
        try:
            # The configured feeds are fixed public URLs. No returned link is fetched.
            raw, _, _ = fetch_public(url, allowed_hosts={urlsplit(url).hostname})
            rows = parse_feed(raw, {"id": identity, "name": label, "segment": "ai",
                                  "topics": ["AI·기술"], "language": "ko"}, current)
            items = [_candidate(r, platform, current, observed=current.isoformat()) for r in rows[:40]
                     if r.get("date_status") != "future"]
            return platform, label, True, [r for r in items if r]
        except (RequestException, ValueError, OSError, ParseError):
            return platform, label, False, []

    with ThreadPoolExecutor(max_workers=4) as pool:
        futures = [pool.submit(collect, platform, feed) for platform, feeds in BLOG_FEEDS.items() for feed in feeds]
        reports = [future.result() for future in futures]
    groups = {}
    for platform in BLOG_FEEDS:
        own = [(label, ok, items) for code, label, ok, items in reports if code == platform]
        rows = _recent_blogs([r for _, _, items in own for r in items], current)
        groups[platform] = {"checked_at": current.isoformat(), "sources_checked": len(own),
                            "sources_succeeded": sum(ok for _, ok, _ in own),
                            "failed_sources": [label for label, ok, _ in own if not ok],
                            "items": _select(platform, _topic_rows(rows, topic))}
    return groups


def _sidecar_groups(current):
    path = Path(os.environ.get("HEOBRAIN_PLATFORM_NEWS_SOURCES_DB") or
                Path.home() / ".local/share/heobrain-content-source-connect/sources.sqlite3")
    if not path.is_file():
        return {}
    groups = {}
    try:
        with sqlite3.connect(path.resolve().as_uri() + "?mode=ro", uri=True, timeout=1) as db:
            for identity, (platform, label) in SIDECAR_SOURCES.items():
                rows = db.execute("SELECT title, url, published, observed_at FROM items WHERE source_id=? "
                                  "ORDER BY COALESCE(published, observed_at, '') DESC, observed_at DESC LIMIT 16", (identity,))
                for title, url, published, observed in rows:
                    row = _candidate({"title": title, "url": url, "published_at": published,
                                      "source_name": label}, platform, current, observed=observed)
                    if row:
                        groups.setdefault(platform, []).append(row)
    except (sqlite3.Error, OSError):
        return {}
    return groups


def _benchmark_groups(store, current):
    registry = store.setting("benchmark_registry", benchmarks.DEFAULT)
    snapshot = store.setting("benchmark_snapshot", {})
    if snapshot.get("registry_hash") != digest(registry):
        return {}
    active = {row.get("id") for row in registry.get("sources", [])}
    groups = {}
    for row in snapshot.get("items", []):
        platform = row.get("platform")
        if platform not in PLATFORMS or row.get("source_id") not in active:
            continue
        candidate = _candidate(row, platform, current, observed=(row.get("provenance") or {}).get("observed_at"))
        if candidate:
            groups.setdefault(platform, []).append(candidate)
    return groups


def _cache_path(store):
    return store.root / "runtime" / "platform-news-v2.json"


def _supplemental_groups(store, current):
    path = _cache_path(store).with_name("public-platform-observations.json")
    try:
        with path.open("rb") as file:
            raw = file.read(OBSERVATION_BYTES + 1)
        rows = json.loads(raw) if len(raw) <= OBSERVATION_BYTES else []
    except (OSError, ValueError, RecursionError):
        return {}
    if not isinstance(rows, list) or len(rows) > OBSERVATION_LIMIT:
        return {}

    groups = {}
    for row in rows:
        if not isinstance(row, dict):
            continue
        platform = row.get("platform")
        title = _public_text(row.get("title"), 180)
        source = _public_text(row.get("source"), 100)
        if platform not in PLATFORMS[1:] or not title or not source:
            continue
        observed = row.get("observed_at")
        published = row.get("published_at")
        if not _recent(observed, current, OBSERVATION_AGE) or (published is not None and not _date_string(published, current)):
            continue
        counters, precision = row.get("metrics"), row.get("metric_precision")
        metrics = {}
        if isinstance(counters, dict) and isinstance(precision, dict):
            metrics = {name: {"value": counters.get(name), "availability": "observed", "precision": precision.get(name)}
                       for name in OBSERVED_COUNTERS if name in counters}
        candidate = _candidate({"url": row.get("url"), "title": title, "source_name": source,
                                "summary": _public_text(row.get("summary"), 250),
                                "published_at": published, "metrics": metrics},
                               platform, current, observed=observed)
        if candidate:
            groups.setdefault(platform, []).append(candidate)
    return groups


def _read_cache(store):
    path = _cache_path(store)
    try:
        with path.open("rb") as file:
            raw = file.read(MAX_BYTES + 1)
        data = json.loads(raw) if len(raw) <= MAX_BYTES else {}
        return data if isinstance(data, dict) else {}
    except (OSError, ValueError):
        return {}


def _write_cache(store, data):
    path = _cache_path(store)
    path.parent.mkdir(parents=True, exist_ok=True)
    with tempfile.NamedTemporaryFile("w", dir=path.parent, encoding="utf-8", delete=False) as temporary:
        name = Path(temporary.name)
        try:
            json.dump(data, temporary, ensure_ascii=False)
            temporary.close()
            os.replace(name, path)
        finally:
            name.unlink(missing_ok=True)


def _key_path():
    value = os.environ.get("HEOBRAIN_YOUTUBE_DATA_API_KEY_FILE")
    return Path(value).expanduser() if value else Path.home() / ".config/heobrain/platform-news-youtube.key"


def _key():
    value = os.environ.get("HEOBRAIN_YOUTUBE_DATA_API_KEY", "").strip()
    if not value:
        try:
            path = _key_path()
            flags = os.O_RDONLY | getattr(os, "O_NOFOLLOW", 0) | getattr(os, "O_NONBLOCK", 0)
            with os.fdopen(os.open(path, flags), "rb") as source:
                info = os.fstat(source.fileno())
                if not stat.S_ISREG(info.st_mode) or (os.name != "nt" and info.st_mode & 0o077):
                    return ""
                value = source.read(256).decode("ascii").strip()
        except (OSError, UnicodeError):
            return ""
    return value if re.fullmatch(r"[A-Za-z0-9_-]{20,100}", value) else ""


def _settings(store):
    value = discovery.config(store)
    topic = value.get("topic") or discovery.DEFAULT["topic"]
    region = value.get("region")
    return topic, region if region in discovery.REGIONS else discovery.DEFAULT["region"]


def refresh(store, *, current=None):
    current = current or datetime.now(timezone.utc)
    topic, region = _settings(store)
    try:
        with ProcessLock(_cache_path(store).with_name("platform-news.lock")):
            cached = _read_cache(store)
            key = _key()
            recent = _recent(cached.get("attempted_at"), current, REFRESH_INTERVAL)
            youtube_attempt = bool(key) and not _recent(cached.get("youtube_attempted_at"), current, REFRESH_INTERVAL)
            if recent and not youtube_attempt:
                return {"status": "cached", "checked_at": cached.get("checked_at")}
            stamp = current.isoformat()
            prior_youtube = cached.get("youtube", {})
            # Save the attempt before network I/O. A crashed refresh cannot consume quota on retry.
            cached = {**cached, "attempted_at": stamp}
            if youtube_attempt:
                cached["youtube_attempted_at"] = stamp
            if not _recent(prior_youtube.get("checked_at"), current, FRESHNESS):
                cached.pop("youtube", None)
            _write_cache(store, cached)
            current_youtube = {"state": "waiting", "message": "YouTube 조회 키 설정 대기"}
            if key and not youtube_attempt:
                current_youtube = cached.get("youtube") or {"state": "waiting", "message": "다음 YouTube 검색 대기"}
            if youtube_attempt:
                try:
                    current_youtube = {"state": "available", "checked_at": stamp, "topic": topic,
                                       "region": region, "items": youtube_candidates(key, topic, region, current)}
                except (ValueError, TypeError, KeyError, OSError, RuntimeError, http.client.HTTPException):
                    current_youtube = {"state": "error", "message": "YouTube 공개 검색 확인 실패"}
                    if (prior_youtube.get("state") == "available" and
                            _recent(prior_youtube.get("checked_at"), current, FRESHNESS)):
                        current_youtube = {**prior_youtube, "state": "stale",
                                           "message": "YouTube 재조회에 실패했습니다. 이전 검색 결과입니다."}
            snapshot = {"attempted_at": stamp, "checked_at": stamp, "youtube": current_youtube,
                        "youtube_attempted_at": cached.get("youtube_attempted_at"),
                        "blogs": cached.get("blogs", {}) if recent else blog_candidates(current, topic)}
            _write_cache(store, snapshot)
            return {"status": "refreshed", "checked_at": stamp,
                    "youtube_status": current_youtube["state"],
                    "blog_status": {p: r["sources_succeeded"] for p, r in snapshot["blogs"].items()}}
    except AlreadyRunning:
        return {"status": "running"}


def _panel(platform, state, method, ranking, rows, *, checked_at=None, message=""):
    seen = max((row["observed_at"] or "" for row in rows), default="")
    value = {"id": platform, "label": LABELS[platform], "source_status": state, "method": method,
             "ranking_basis": ranking, "message": message, "checked_at": checked_at or seen or None,
             "items": rows[:MAX_ITEMS]}
    if platform in REFERENCE:
        value["reference_url"] = REFERENCE[platform]
    return value


def status(store, *, current=None):
    current = current or datetime.now(timezone.utc)
    topic, region = _settings(store)
    cache = _read_cache(store)
    saved_youtube = cache.get("youtube", {})
    benchmark = _benchmark_groups(store, current)
    sidecar = _sidecar_groups(current)
    additional = _supplemental_groups(store, current)
    freshness = saved_youtube.get("checked_at")
    official = saved_youtube.get("state") in ("available", "stale")
    same_query = saved_youtube.get("topic") == topic and saved_youtube.get("region") == region
    youtube_rank = "최근 7일 관련 영상의 공개 누적 조회수순 · 채널별 최대 2건"
    if official and same_query and _recent(freshness, current, FRESHNESS):
        rows = [row for row in saved_youtube["items"] if _matches_topic(row["title"], topic)]
        youtube = _panel("youtube", saved_youtube["state"], "YouTube Data API v3",
                         youtube_rank, _select("youtube", rows, "views"), checked_at=freshness,
                         message=saved_youtube.get("message") or f"{region} 지역 · {topic} 검색 표본")
    else:
        fallback = _select("youtube", _topic_rows(benchmark.get("youtube", []), topic), "views")
        state = "stale" if official else "observed" if fallback else saved_youtube.get("state", "waiting")
        message = ("저장된 검색 결과의 조건 또는 유효 기간이 달라 새 조회를 기다립니다." if official else
                   saved_youtube.get("message", "정기 검색 결과를 기다립니다."))
        youtube = _panel("youtube", state, "등록 채널 공개 RSS" if fallback else "YouTube Data API v3",
                         "등록 채널에서 확인한 누적 조회수·날짜순" if fallback else youtube_rank,
                         fallback, message=message)
    panels = [youtube]
    blogs = cache.get("blogs", {})
    for platform in ("naver_blog", "tistory"):
        feed = blogs.get(platform, {})
        reviews = feed.get("items") or []
        rows = _recent_blogs(reviews + additional.get(platform, []) + benchmark.get(platform, []) +
                             sidecar.get(platform, []), current)
        rows = _select(platform, _topic_rows(rows, topic))
        state = ("available" if feed.get("sources_succeeded") and _recent(feed.get("checked_at"), current, FRESHNESS)
                 else "stale" if feed.get("sources_succeeded")
                 else "observed" if rows else "error" if feed.get("failed_sources") else "waiting")
        message = "수집이 지연된 피드: " + ", ".join(feed["failed_sources"]) if feed.get("failed_sources") else ""
        if not message and state == "available" and not rows:
            message = "최근 30일 이내 조건에 맞는 공개 글이 확인되지 않았습니다."
        method = "공개 RSS 및 게시물 관측" if additional.get(platform) else "등록 블로그의 공개 RSS"
        panels.append(_panel(platform, state, method, "최근 30일 발행일·관측일순 · 작성자별 최대 2건",
                             rows, checked_at=feed.get("checked_at"), message=message))
    for platform in PLATFORMS[3:]:
        rows = _topic_rows(additional.get(platform, []) + benchmark.get(platform, []) + sidecar.get(platform, []), topic)
        metric = next((name for name in ("views", "likes", "reactions") if any(name in row["metrics"] for row in rows)), None)
        if metric:
            rows = [row for row in rows if metric in row["metrics"]]
        current_rows = any(_recent(row["observed_at"], current, OBSERVATION_AGE) for row in rows)
        state = "observed" if current_rows else "stale" if rows else "waiting"
        ranking = {"views": "공개 표본의 관측 조회수순", "likes": "공개 표본의 관측 좋아요순",
                   "reactions": "공개 표본의 관측 반응수순"}.get(
            metric, "확인된 공개 게시물의 발행일·관측일순")
        message = {
            "instagram": "확인한 공개 게시물 표본입니다.",
            "threads": "확인한 공개 게시물 표본입니다.",
            "tiktok": ("확인한 틱톡 공개 영상 표본입니다." if rows else
                       "크리에이티브 센터에서 공개 해시태그 동향을 확인할 수 있습니다."),
            "x": "확인한 공개 게시물 표본입니다." if rows else "확인된 공개 게시물 수집을 기다립니다.",
            "linkedin": "공개 기업·작성자 게시물 표본과 참고 기업 페이지입니다.",
        }[platform]
        panels.append(_panel(platform, state, "공개 게시물 관측", ranking,
                             _select(platform, rows, metric), message=message))
    return {"checked_at": cache.get("checked_at"), "topic": topic, "region": region, "platforms": panels}


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("action", choices=("refresh", "status"))
    parser.add_argument("--root", type=Path, default=Path(os.environ.get("OFFICE_STATE_DIR") or
                        Path.home() / ".local/state/heobrain-content-office"))
    args = parser.parse_args()
    store = Store(args.root)
    output = refresh(store) if args.action == "refresh" else status(store)
    print(json.dumps(output, ensure_ascii=False))


if __name__ == "__main__":
    main()
