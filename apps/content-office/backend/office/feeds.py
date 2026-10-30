"""Bounded RSS/Atom collection; feed delivery, freshness and editorial rank are separate."""
from __future__ import annotations

import email.utils
import hashlib
import html
import ipaddress
import json
import re
import socket
import xml.etree.ElementTree as ET
from concurrent.futures import ThreadPoolExecutor
from datetime import datetime, timedelta, timezone
from pathlib import Path
from urllib.parse import parse_qsl, urlencode, urljoin, urlsplit, urlunsplit

import requests

from .store import now
from .korean import clean_feed_summary

from .source_registry import classify_article, load_sources

MAX_BYTES = 3_000_000

DEFAULT_FEEDS = load_sources()


def normalize_url(url: str) -> str:
    p = urlsplit(url.strip())
    query = [(k, v) for k, v in parse_qsl(p.query, keep_blank_values=True) if not k.lower().startswith("utm_") and k.lower() not in ("ref", "source", "fbclid", "gclid")]
    return urlunsplit((p.scheme.lower(), p.netloc.lower(), p.path.rstrip("/") or "/", urlencode(query), ""))


def validate_public_url(url: str) -> str:
    p = urlsplit(url)
    if p.scheme != "https" or not p.hostname or p.username or p.password or p.port not in (None, 443):
        raise ValueError("공개 HTTPS 주소만 허용합니다")
    host = p.hostname.lower()
    if host == "localhost" or host.endswith((".localhost", ".local", ".internal")):
        raise ValueError("내부 주소는 허용하지 않습니다")
    try:
        addresses = [ipaddress.ip_address(host)]
    except ValueError:
        addresses = [ipaddress.ip_address(x[4][0]) for x in socket.getaddrinfo(host, 443, type=socket.SOCK_STREAM)]
    if not addresses or any(not address.is_global for address in addresses):
        raise ValueError("내부 네트워크 주소는 허용하지 않습니다")
    return url


def fetch_public(url: str, *, maximum=MAX_BYTES, allowed_hosts=None):
    current = url
    for _ in range(5):
        validate_public_url(current)
        if allowed_hosts and urlsplit(current).hostname not in allowed_hosts:
            raise ValueError("등록된 출처 범위 밖으로 이동했습니다")
        with requests.get(current, timeout=(8, 20), stream=True, allow_redirects=False, headers={"User-Agent": "HeoBrainContentOffice/1.0 (public RSS research)"}) as response:
            if response.status_code in (301, 302, 303, 307, 308):
                current = urljoin(current, response.headers.get("Location", ""))
                continue
            response.raise_for_status()
            parts, length = [], 0
            for chunk in response.iter_content(65536):
                length += len(chunk)
                if length > maximum:
                    raise ValueError("응답 크기 한도를 초과했습니다")
                parts.append(chunk)
            return b"".join(parts), current, response.headers.get("Content-Type", "")
    raise ValueError("리다이렉트 횟수 한도를 초과했습니다")


def clean_text(value: str) -> str:
    return re.sub(r"\s+", " ", html.unescape(re.sub(r"<[^>]*>", " ", value or ""))).strip()


def parse_date(value):
    if not value:
        return None
    try:
        date = email.utils.parsedate_to_datetime(value)
    except (ValueError, TypeError):
        try:
            date = datetime.fromisoformat(value.strip().replace("Z", "+00:00"))
        except (ValueError, TypeError):
            return None
    if date.tzinfo is None:
        return None
    return date.astimezone(timezone.utc)


class NoDoctypeTreeBuilder(ET.TreeBuilder):
    def doctype(self, name, pubid, system):
        raise ValueError('XML DOCTYPE 및 엔티티 선언은 허용하지 않습니다')


def parse_feed(xml: str | bytes, feed: dict, current: datetime | None = None) -> list[dict]:
    current = current or datetime.now(timezone.utc)
    raw = xml.encode() if isinstance(xml, str) else xml
    if len(raw) > MAX_BYTES:
        raise ValueError("안전한 크기의 일반 RSS/Atom만 허용합니다")
    root = ET.fromstring(raw, parser=ET.XMLParser(target=NoDoctypeTreeBuilder()))
    articles = []
    for item in root.iter():
        if item.tag.rsplit("}", 1)[-1] not in ("item", "entry"):
            continue
        fields, link = {}, None
        for child in item:
            key = child.tag.rsplit("}", 1)[-1]
            value = "".join(child.itertext()).strip()
            if key == "link":
                candidate = child.attrib.get("href") if child.attrib.get("rel", "alternate") == "alternate" else None
                link = candidate or link or value
            if key not in fields:
                fields[key] = value
        if not fields.get("title") or not link or urlsplit(link).scheme not in ("http", "https"):
            continue
        canonical_url = normalize_url(link)
        date = parse_date(fields.get("pubDate") or fields.get("published") or fields.get("date") or fields.get("updated"))
        status = "unknown" if date is None else "future" if date > current + timedelta(minutes=5) else "valid"
        articles.append({"id": hashlib.sha256(canonical_url.encode()).hexdigest()[:24], "title": clean_text(fields["title"]), "url": canonical_url, "feed_id": feed["id"], "feed_name": feed["name"], "published_at": date.isoformat() if date else None, "date_status": status, "summary": clean_feed_summary(clean_text(fields.get("description") or fields.get("summary") or fields.get("content") or ""))[:700], "retrieved_at": now()})
    return [classify_article({**article, **{key: feed[key] for key in ("segment", "topics", "language") if key in feed}}) for article in articles]


def rank_articles(articles, current=None, days=7):
    current = current or datetime.now(timezone.utc)
    seen, ranked = set(), []
    for source in articles:
        article = dict(source)
        date = parse_date(article.get("published_at"))
        if date is None or date > current + timedelta(minutes=5) or date < current - timedelta(days=days):
            continue
        url = normalize_url(article["url"])
        if url in seen:
            previous = next((r for r in ranked if normalize_url(r['url']) == url), None)
            if previous is not None and article.get('signals'):
                previous['signals'] = {**previous.get('signals', {}), **article['signals']}
                previous['related_sources'] = [*previous.get('related_sources', []), {'url': article.get('discussion_url', article['url']), 'feed_name': article.get('feed_name'), 'reason': '같은 원문을 가리키는 공개 반응 지표'}]
            continue
        seen.add(url)
        text = (article["title"] + " " + article.get("summary", "")).lower()
        age_days = (current - date).total_seconds() / 86400
        freshness = max(0, 25 - age_days * 2)
        agent = any(word in text for word in ("agent", "workflow", "benchmark", "automation", "coding"))
        practical = any(word in text for word in ("api", "open source", "release", "ads", "training", "developer", "tool"))
        article["score"] = round(freshness + 20 + (25 if agent else 8) + (20 if practical else 10), 1)
        article["score_reasons"] = [f"최근 {age_days:.1f}일 이내 발표", "공식 RSS 출처", "에이전트·실무 자동화 관련" if agent else "AI 산업·활용 변화", "실행·영상 설명 소재가 구체적" if practical else "추가 원문 검토 필요"]
        source_note = {'community': 'HN 커뮤니티 제보 · 원문 검증 필요', 'youtube': 'YouTube 공개 채널 피드 · 영상 본문 미검증',
                       'news_aggregator': 'Google 뉴스 중개 · 원출처 확인 필요', 'search_trend': 'Google 급상승 검색 · 사실 검증 아님'}.get(article.get('source_kind'))
        if source_note:
            article['score_reasons'][1] = source_note
            event = {'community': 'HN 등록(원문 발행일 미확인)', 'youtube': '영상 게시', 'news_aggregator': '뉴스 목록 수록', 'search_trend': '검색 관심 관측'}[article['source_kind']]
            article['score_reasons'][0] = f'최근 {age_days:.1f}일 이내 {event}'
        article["score_note"] = "편집 규칙 점수이며 성과 측정치가 아닙니다"
        if article.get("segment") == "exam":
            article["score"] = round(freshness + 40, 1)
            article["score_reasons"] = [f"최근 {age_days:.1f}일 이내 공지", "교육부 공식 공지", "수험·대학·직업교육 관련 제목; 원문 확인 필요"]
        ranked.append(article)
    return deduplicate_events(sorted(ranked, key=lambda a: (a["score"], a["published_at"]), reverse=True))


def deduplicate_events(articles):
    result, seen = [], {}
    for source in sorted(articles, key=lambda article: (bool(article.get("selected")), article.get("score", 0)), reverse=True):
        article = dict(source)
        title = " ".join(re.findall(r"[a-z0-9가-힣]+", article["title"].lower()))
        curated = article.get("event_id")
        # Short titles such as "AI update" do not identify a common event.
        event_key = 'event:' + str(curated) if curated else 'title:' + title if len(title) >= 24 else 'url:' + normalize_url(article['url'])
        candidates = seen.get(event_key, [])
        date = parse_date(article.get('published_at'))
        previous = next((item for item in candidates if curated or (date and parse_date(item.get('published_at')) and abs(date - parse_date(item['published_at'])) <= timedelta(hours=48))), None)
        if previous is not None:
            related = previous.setdefault("related_sources", [])
            if article['url'] != previous['url'] and article['url'] not in {item['url'] for item in related}:
                related.append({"url": article["url"], "feed_name": article.get("feed_name"), "reason": "확인한 같은 이벤트 ID" if curated else "48시간 이내의 구체적인 동일 제목; 원문 검토 필요"})
            continue
        seen.setdefault(event_key, []).append(article)
        result.append(article)
    return result


def collect_feeds(root: Path, feeds=None):
    root = Path(root)
    raw_dir = root / "feeds"
    raw_dir.mkdir(parents=True, exist_ok=True)
    def collect(feed):
        record = {**feed, "checked_at": now()}
        try:
            raw, resolved, content_type = fetch_public(feed["url"])
            if feed.get("format") == "moe-board":
                from .education_sources import parse_moe
                articles = parse_moe(raw, feed)
            elif feed.get('format') == 'hn-api':
                from .public_sources import hn_articles
                articles = hn_articles(raw, feed, fetch_public)
            else:
                articles = parse_feed(raw, feed)
                if feed.get('format') in ('youtube', 'google-news', 'google-trends'):
                    from .public_sources import annotate_feed
                    original_count = len(articles)
                    articles = annotate_feed(raw, articles, feed)
                    record['raw_items'] = original_count
            path = raw_dir / f"{feed['id']}.xml"
            path.write_bytes(raw)
            record.update(state="ok", count=len(articles), resolved_url=resolved, content_type=content_type, sha256=hashlib.sha256(raw).hexdigest(), error=None)
            return record, articles
        except Exception as error:
            record.update(state="failed", count=None, error=f"{type(error).__name__}: 조회 실패. 원문과 연결 상태를 확인하세요")
            return record, []
    with ThreadPoolExecutor(max_workers=5) as pool:
        results = list(pool.map(collect, feeds or DEFAULT_FEEDS))
    articles = [article for _, rows in results for article in rows]
    ranked = rank_articles(articles)
    return {"checked_at": now(), "feeds": [r for r, _ in results], "articles": ranked, "total_items": len(articles), "eligible_items": len(ranked), "days": 7, "partial_failure": any(r["state"] != "ok" for r, _ in results)}
