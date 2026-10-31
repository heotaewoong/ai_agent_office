"""Platform-aware, metadata-only research; no model, approval or budget mutation."""
import re
import time
import json
from datetime import datetime, timezone
from urllib.parse import urlencode

from .source_registry import load_sources
from .store import WorkflowError, canonical, digest, now
from .public_sources import relevant
from .runtime import window_open


def can_collect(store):
    window = store.setting('work_window', {})
    return bool(window.get('authorized_end') and window.get('user_confirmed') is True and window_open(store))

DEFAULT = {'platforms': ['youtube', 'naver_blog', 'tistory'], 'topic': 'AI 자동화', 'region': 'KR',
           'youtube_channels': ['UCXZCJLdBC09xxGZ6gcdrc6A', 'UC_x5XG1OV2P6uZZ5FSM9Ttw']}
REGIONS = {'KR': ('ko', 'KR:ko'), 'US': ('en-US', 'US:en'), 'GB': ('en-GB', 'GB:en'), 'JP': ('ja', 'JP:ja')}
PLATFORMS = {'youtube': 'YouTube·Shorts', 'naver_blog': '네이버 블로그', 'tistory': '티스토리·검색형 블로그',
             'instagram': 'Instagram', 'threads': 'Threads', 'x': 'X', 'linkedin': 'LinkedIn'}
ROUTES = {'youtube': ['youtube', 'community', 'search_trend'], 'instagram': ['youtube', 'search_trend'],
          'naver_blog': ['search_trend', 'news_aggregator'], 'tistory': ['search_trend', 'news_aggregator'],
          'threads': ['community', 'news_aggregator', 'search_trend'], 'x': ['community', 'news_aggregator'],
          'linkedin': ['community', 'news_aggregator', 'official']}


def config(store):
    return store.setting('discovery_config', DEFAULT)


def validate(value):
    if not isinstance(value, dict) or set(value) != set(DEFAULT):
        raise WorkflowError('조사 조건의 항목을 확인하세요')
    platforms, topic, region, channels = (value[k] for k in ('platforms', 'topic', 'region', 'youtube_channels'))
    if (not isinstance(platforms, list) or not 1 <= len(platforms) <= 7
            or any(not isinstance(p, str) or p not in PLATFORMS for p in platforms)
            or len(set(platforms)) != len(platforms)):
        raise WorkflowError('게시 대상을 한 개 이상 선택하세요')
    if not isinstance(topic, str) or not 1 <= len(topic.strip()) <= 80 or any(ord(c) < 32 for c in topic):
        raise WorkflowError('조사 주제는 1~80자로 입력하세요')
    if not isinstance(region, str) or region not in REGIONS:
        raise WorkflowError('지원하는 조사 지역을 선택하세요')
    if not isinstance(channels, list) or not 1 <= len(channels) <= 6 or any(not isinstance(c, str) or not re.fullmatch(r'UC[A-Za-z0-9_-]{22}', c) for c in channels):
        raise WorkflowError('공개 YouTube 채널 ID를 1~6개 입력하세요')
    return {**value, 'platforms': list(platforms), 'topic': topic.strip(), 'youtube_channels': list(dict.fromkeys(channels))}


def feeds_for(value):
    language, ceid = REGIONS[value['region']]
    wanted = {kind for platform in value['platforms'] for kind in ROUTES[platform]}
    optional = {'google-news': 'news_aggregator', 'google-trends': 'search_trend'}
    rows = [dict(r) for r in load_sources() if r.get('format') != 'youtube'
            and (r.get('format') not in optional or optional[r['format']] in wanted)]
    for row in rows:
        if row.get('format') in ('google-news', 'google-trends'):
            row['language'] = language.split('-')[0]
        if row.get('format') == 'hn-api':
            row['topic'] = value['topic']
        if row.get('format') == 'google-news':
            topic = 'AI automation' if value['topic'] == 'AI 자동화' and value['region'] != 'KR' else value['topic']
            row['url'] = 'https://news.google.com/rss/search?' + urlencode({'q': topic + ' when:7d', 'hl': language, 'gl': value['region'], 'ceid': ceid})
        elif row.get('format') == 'google-trends':
            row.update(url='https://trends.google.com/trending/rss?' + urlencode({'geo': value['region']}), topic=value['topic'])
    for channel in value['youtube_channels']:
        registered = next((r for r in load_sources() if r.get('channel_id') == channel), None)
        rows.append(dict(registered) if registered else {'id': 'youtube-' + channel, 'name': 'YouTube ' + channel,
                    'url': 'https://www.youtube.com/feeds/videos.xml?' + urlencode({'channel_id': channel}),
                    'format': 'youtube', 'segment': 'ai', 'topics': ['AI', '자동화'], 'language': 'en'})
    return rows


def queue(store):
    value = config(store)
    prefix = f'discover:{digest(value)}:{int(time.time())//900}'
    with store.connection() as db:
        finished = db.execute("SELECT COUNT(*) FROM tasks WHERE kind='discover' AND dedup_key LIKE ? AND state NOT IN ('queued','running')", (prefix + '%',)).fetchone()[0]
    # Public metadata is safe to request again after cancellation; model/cost retries stay untouched.
    return store.enqueue('discover', {'config_hash': digest(value)}, key=f'{prefix}:{finished}')


def restore_cached(store, value):
    with store.connection(transaction=True) as db:
        current = db.execute("SELECT value FROM settings WHERE key='discovery_config'").fetchone()
        if digest(json.loads(current[0]) if current else DEFAULT) != digest(value):
            raise WorkflowError('조사 조건이 바뀌었습니다. 현재 설정으로 다시 요청하세요')
        row = db.execute('SELECT value FROM settings WHERE key=?', ('discovery_report:' + digest(value),)).fetchone()
        snapshot = json.loads(row[0]) if row else None
        if snapshot and snapshot.get('checked_at') and snapshot.get('feed_report'):
            age = (datetime.now(timezone.utc) - datetime.fromisoformat(snapshot['checked_at'])).total_seconds()
            if 0 <= age < 900:
                db.execute('INSERT OR REPLACE INTO settings VALUES(?,?)', ('feed_report', canonical(snapshot['feed_report'])))
                return snapshot
    return None


def save(store, value, expected_hash):
    value = validate(value)
    with store.connection(transaction=True) as db:
        row = db.execute("SELECT value FROM settings WHERE key='discovery_config'").fetchone()
        previous = json.loads(row[0]) if row else DEFAULT
        if digest(previous) != expected_hash:
            raise WorkflowError('다른 화면에서 조사 조건이 바뀌었습니다. 입력을 보존하고 현재 설정을 다시 읽으세요')
        db.execute('INSERT OR REPLACE INTO settings VALUES(?,?)', ('discovery_config', canonical(value)))
        store._event(db, 'discovery_config_saved', {'config_hash': digest(value), 'platforms': value['platforms'], 'paid_call_made': False})
    restore_cached(store, value)
    return queue(store)


def record(store, value, articles, report):
    recommendations = {}
    for platform in value['platforms']:
        kinds = ROUTES[platform]
        candidates = [r for r in articles if r.get('segment') in ('ai', 'exam') and relevant(r['title'] + ' ' + r.get('summary', ''), value['topic'])]
        def weight(row):
            kind = row.get('source_kind', 'official')
            metric = {'youtube': 'youtube_views', 'community': 'hn_points'}.get(kind)
            measured = row.get('signals', {}).get(metric) if metric else None
            # Different units are compared only after source-kind priority, never summed together.
            popularity = measured if type(measured) is int and measured >= 0 else -1
            return (len(kinds) - kinds.index(kind) if kind in kinds else 0, popularity, row.get('score', 0))
        candidates.sort(key=weight, reverse=True)
        recommendations[platform] = [{'id': r['id'], 'title': r['title'], 'url': r['url'], 'feed_name': r.get('feed_name'),
                                      'kind': r.get('source_kind', 'official'), 'signals': r.get('signals', {}),
                                      'published_at': r.get('published_at'), 'observed_at': r.get('retrieved_at'),
                                      'date_note': r.get('date_note'), 'signal_note': r.get('signal_note'),
                                      'reason': f"{PLATFORMS[platform]} 출처 우선순위 → 같은 출처 종류의 누적 반응 → 날짜·편집 점수. 사실 확인이나 흥행 보장은 별도입니다"}
                                     for r in candidates[:6]]
    snapshot = {'config_hash': digest(value), 'config': value, 'checked_at': report['checked_at'],
                'sources': report['feeds'], 'feed_report': report, 'recommendations': recommendations, 'paid_calls': 0,
                'method': '주제 일치 후보에서 출처 우선순위·동일 종류의 누적 반응·날짜를 비교한 규칙 추천. AI 예측·증가율·플랫폼 전체 순위가 아님'}
    store.set_setting('discovery_report', snapshot)
    store.set_setting('discovery_report:' + digest(value), snapshot)
    return snapshot


def status(store):
    value = config(store)
    snapshot = store.setting('discovery_report:' + digest(value)) or store.setting('discovery_report')
    if snapshot:
        snapshot = {k: v for k, v in snapshot.items() if k != 'feed_report'}
    with store.connection() as db:
        row = db.execute("SELECT state,updated_at,result FROM tasks WHERE kind='discover' AND json_extract(payload,'$.config_hash')=? ORDER BY created_at DESC LIMIT 1", (digest(value),)).fetchone()
    activity = {'state': row[0], 'updated_at': row[1], 'error': (json.loads(row[2]) if row[2] else {}).get('error')} if row else None
    return {'config': value, 'config_hash': digest(value), 'platforms': PLATFORMS,
            'activity': activity,
            'plan': {p: ROUTES[p] for p in value['platforms']}, 'snapshot': snapshot,
            'stale': bool(snapshot and snapshot.get('config_hash') != digest(value)),
            'window_open': can_collect(store),
            'unconnected': ['ViewStats·vling: 공식 자동 연동 미구현', '블랙키위·NAVER API HUB: 자동 연동 미구현',
                            'Instagram·Threads·X·LinkedIn: 각 서비스 내부 인기 순위·계정 성과 API 미연동',
                            'Google Trends: 공개 급상승 RSS 사용, 알파 시계열 API 미연동']}


def run(store, expected_hash=None):
    if not can_collect(store):
        raise WorkflowError('운영자가 확인한 작업 시간 안에서만 새 조사를 실행합니다')
    value = config(store)
    if expected_hash and digest(value) != expected_hash:
        raise WorkflowError('조사 조건이 바뀌어 이전 대기 작업을 실행하지 않았습니다')
    previous = restore_cached(store, value)
    if previous:
        return {'cached': True, 'checked_at': previous['checked_at'], 'paid_calls': 0}
    from .bootstrap import refresh
    result = refresh(store, metadata_only=True)
    return {'checked_at': result['checked_at'], 'sources': len(result['feeds']), 'articles': result['eligible_items'], 'paid_calls': 0}
