"""Bounded public discovery metadata. Popularity is not evidence or publishing permission."""
import hashlib
import json
import re
from concurrent.futures import ThreadPoolExecutor
from datetime import datetime, timezone
from urllib.parse import urlsplit
from xml.etree import ElementTree as ET

from .store import now

AI_TERMS = r'\b(ai|llms?|gpt|openai|anthropic|claude|gemini|chatgpt|agents?|automation|robotics)\b|artificial intelligence|machine learning|인공지능|자동화|생성형'


def relevant(text, topic='AI 자동화'):
    if topic.strip().lower() in ('ai', 'ai 자동화', 'ai automation'):
        return bool(re.search(AI_TERMS, text, re.I))
    return any(term.casefold() in text.casefold() for term in topic.split() if term.strip())


def hn_articles(raw, feed, fetcher):
    ids = json.loads(raw)
    if not isinstance(ids, list) or len(ids) > 1000 or any(type(i) is not int or not 0 < i < 10**12 for i in ids):
        raise ValueError('Invalid HN story list')
    def story(identity):
        body, _, _ = fetcher(f'https://hacker-news.firebaseio.com/v0/item/{identity}.json',
                             allowed_hosts={'hacker-news.firebaseio.com'})
        row = json.loads(body)
        if not isinstance(row, dict) or row.get('type') != 'story' or row.get('dead') or row.get('deleted'):
            return None
        title = str(row.get('title', ''))[:500]
        if not title or not relevant(title, feed.get('topic', 'AI 자동화')):
            return None
        stamp = row.get('time')
        if type(stamp) is not int or stamp <= 0:
            return None
        url = str(row.get('url') or f'https://news.ycombinator.com/item?id={identity}')
        parsed = urlsplit(url)
        if parsed.scheme not in ('http', 'https') or not parsed.hostname or parsed.username or parsed.password:
            return None
        return {'id': hashlib.sha256(url.encode()).hexdigest()[:24], 'title': title, 'url': url,
                'feed_id': feed['id'], 'feed_name': feed['name'], 'segment': 'ai', 'language': 'en',
                'topics': feed['topics'], 'summary': '', 'published_at': datetime.fromtimestamp(stamp, timezone.utc).isoformat(),
                'date_status': 'valid', 'retrieved_at': now(), 'source_kind': 'community',
                'date_note': 'HN 등록일입니다. 연결된 원문 발행일은 확인하지 않았습니다',
                'discussion_url': f'https://news.ycombinator.com/item?id={identity}',
                'signals': {'hn_points': row.get('score') if type(row.get('score')) is int else None,
                            'hn_comments': row.get('descendants') if type(row.get('descendants')) is int else None},
                'signal_note': 'HN 게시물 반응이며 원문의 사실 검증·전체 시장 수요가 아닙니다'}
    # Partial item failures remain visible, rather than silently reporting a successful full scan.
    with ThreadPoolExecutor(max_workers=4) as pool:
        rows = list(pool.map(story, ids[:24]))
    return [r for r in rows if r]


def annotate_feed(raw, articles, feed):
    """Attach measured counters without mistaking observation time for publication time."""
    root = ET.fromstring(raw)
    kind = feed.get('format')
    if kind == 'youtube':
        by_url = {r['url']: r for r in articles}
        for entry in root.findall('{http://www.w3.org/2005/Atom}entry'):
            link = entry.find('{http://www.w3.org/2005/Atom}link')
            row = by_url.get(link.get('href')) if link is not None else None
            if row is None:
                continue
            stats = entry.find('.//{http://search.yahoo.com/mrss/}statistics')
            views = stats.get('views', '') if stats is not None else ''
            row.update(source_kind='youtube', signals={'youtube_views': int(views) if views.isdigit() else None},
                       date_note='공개 피드의 영상 게시일입니다',
                       signal_note='공개 피드 조회 시점의 누적 조회수입니다. 증가율·영상 전사·전체 시청 검증이 아닙니다')
    elif kind == 'google-trends':
        namespace = '{https://trends.google.com/trending/rss}'
        by_title = {r['title']: r for r in articles}
        for item in root.findall('./channel/item'):
            row = by_title.get(item.findtext('title'))
            if row is None:
                continue
            row.update(source_kind='search_trend', signals={'search_volume_label': item.findtext(namespace + 'approx_traffic')},
                       date_note='검색 관심 급상승 항목의 관측일이며 원문 발행일이 아닙니다',
                       signal_note='지역별 급상승 검색의 근사 표시입니다. 플랫폼 조회수·정확한 검색량·사실 검증이 아닙니다')
        articles = [r for r in articles if relevant(r['title'] + ' ' + r.get('summary', ''), feed.get('topic', 'AI 자동화'))]
    elif kind == 'google-news':
        for row in articles:
            row.update(source_kind='news_aggregator', date_note='Google 뉴스 목록의 날짜입니다. 발행사 원문 날짜를 확인하세요', signal_note='Google 뉴스 중개 목록입니다. 발행사 원문과 독립 출처를 확인하세요')
    return articles
