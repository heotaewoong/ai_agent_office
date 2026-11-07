"""Competitor metadata stays separate from evidence, approvals and paid work."""
import copy
from concurrent.futures import ThreadPoolExecutor
from datetime import datetime, timedelta, timezone
from threading import Barrier

import pytest
from fastapi.testclient import TestClient

from office import benchmarks, feeds
from office.store import Store, WorkflowError, digest


@pytest.fixture
def store(tmp_path, monkeypatch):
    real_dns = feeds.socket.getaddrinfo
    def public_dns(host, *args, **kwargs):
        if host in ('localhost', '127.0.0.1', '::1'):
            return real_dns(host, *args, **kwargs)
        return [(2, 1, 6, '', ('93.184.216.34', 443))]
    monkeypatch.setattr(feeds.socket, 'getaddrinfo', public_dns)
    return Store(tmp_path)


def database(store):
    with store.connection() as db:
        return list(db.iterdump())


def protected(store):
    with store.connection() as db:
        return {table: [tuple(row) for row in db.execute('SELECT * FROM ' + table)]
                for table in ('jobs', 'approvals', 'costs', 'versions', 'drafts')}


def open_window(store):
    store.set_setting('work_window', {'authorized_end': (datetime.now(timezone.utc) + timedelta(hours=1)).isoformat(), 'user_confirmed': True})


def registry(store):
    return benchmarks.status(store)['registry']


def save(store, sources):
    return benchmarks.save(store, {'sources': sources}, digest(registry(store)))


def rss(title='AI 공부 자료 비교'):
    stamp = datetime.now(timezone.utc).isoformat()
    return f'''<feed xmlns="http://www.w3.org/2005/Atom"><entry><title>{title}</title>
    <link rel="alternate" href="https://www.youtube.com/watch?v=valid"/><published>{stamp}</published></entry>
    <entry><title>Unknown date</title><link href="https://www.youtube.com/watch?v=unknown"/></entry>
    <entry><title>Future</title><link href="https://www.youtube.com/watch?v=future"/>
    <published>2099-01-01T00:00:00Z</published></entry></feed>'''.encode()


def test_get_defaults_is_pure_and_never_fetches_or_resolves(store, monkeypatch):
    before = database(store)
    monkeypatch.setattr(feeds, 'fetch_public', lambda *a, **k: pytest.fail('GET fetched'))
    monkeypatch.setattr(feeds.socket, 'getaddrinfo', lambda *a, **k: pytest.fail('GET resolved DNS'))
    result = benchmarks.status(store)
    assert database(store) == before and result['registry_hash'] == digest(result['registry'])
    sources = result['registry']['sources']
    assert any(s['url'] == 'https://www.instagram.com/every._ai/' for s in sources)
    assert any(s.get('channel_id') == 'UC-SyuGFlZXpGdR7WszgYBhw' for s in sources)
    assert {s['state'] for s in result['sources_status']} == {'ready', 'manual'}
    assert result['items'] == result['ideas'] == [] and not result['window_open']


def test_registry_save_has_optimistic_lock_and_does_not_queue_or_collect(store, monkeypatch):
    value = registry(store)
    before = protected(store)
    monkeypatch.setattr(feeds, 'fetch_public', lambda *a, **k: pytest.fail('save fetched'))
    changed = copy.deepcopy(value)
    changed['sources'][0]['fields'] = ['공부법', '콘텐츠 제작']
    result = benchmarks.save(store, changed, digest(value))
    assert result['registry'] == changed and store.tasks() == [] and protected(store) == before
    saved = database(store)
    with pytest.raises(WorkflowError, match='바뀌'):
        benchmarks.save(store, value, digest(value))
    assert database(store) == saved


@pytest.mark.parametrize('patch', [
    {'url': 'https://127.0.0.1/private'}, {'url': 'https://instagram.com.evil.example/every._ai/'},
    {'url': 'http://www.instagram.com/every._ai/'}, {'url': 'https://user:password@www.instagram.com/every._ai/'},
    {'id': '../private'}, {'name': 'name\nInjected'}, {'fields': ['x'] * 7}, {'platform': 'unknown'},
])
def test_invalid_registry_does_not_change_state(store, patch):
    value = registry(store)
    value['sources'][0].update(patch)
    before = database(store)
    with pytest.raises(WorkflowError):
        benchmarks.save(store, value, digest(registry(store)))
    assert database(store) == before


def test_private_dns_and_duplicate_ids_are_rejected(store, monkeypatch):
    value = registry(store)
    monkeypatch.setattr(feeds.socket, 'getaddrinfo', lambda *a, **k: [(2, 1, 6, '', ('10.0.0.1', 443))])
    before = database(store)
    with pytest.raises(WorkflowError):
        benchmarks.save(store, value, digest(value))
    assert database(store) == before
    value['sources'].append(copy.deepcopy(value['sources'][0]))
    with pytest.raises(WorkflowError):
        benchmarks.save(store, value, digest(registry(store)))


def test_refresh_is_deduplicated_and_worker_checks_window_and_registry(store, monkeypatch):
    value_hash = digest(registry(store))
    monkeypatch.setattr(benchmarks, 'collect_feeds', lambda *a, **k: pytest.fail('closed window collected'))
    with pytest.raises(WorkflowError, match='작업 시간'):
        benchmarks.queue(store, value_hash)
    assert store.tasks() == []
    open_window(store)
    first = benchmarks.queue(store, value_hash)
    assert first == benchmarks.queue(store, value_hash) and len(store.tasks()) == 1
    assert first['task']['kind'] == 'benchmark_refresh'
    assert first['task']['payload'] == {'registry_hash': value_hash}
    store.set_setting('work_window', {'status': 'closed'})
    with pytest.raises(WorkflowError, match='작업 시간'):
        benchmarks.run(store, value_hash)
    open_window(store)
    with pytest.raises(WorkflowError, match='바뀌'):
        benchmarks.run(store, '0' * 64)


def test_real_feed_parser_collects_only_known_youtube_and_distinguishes_failure_and_zero(store, monkeypatch):
    sources = registry(store)['sources']
    youtube = next(s for s in sources if s['platform'] == 'youtube')
    sources += [{**youtube, 'id': 'yt-failed', 'creator_id': 'failed', 'channel_id': 'UC' + 'x' * 22, 'url': 'https://www.youtube.com/@failed'},
                {**youtube, 'id': 'yt-empty', 'creator_id': 'empty', 'channel_id': 'UC' + 'z' * 22, 'url': 'https://www.youtube.com/@empty'},
                {**youtube, 'id': 'yt-unready', 'creator_id': 'unready', 'channel_id': '', 'url': 'https://www.youtube.com/@unready'}]
    save(store, sources)
    open_window(store)
    calls = []
    def fetch(url, **kwargs):
        calls.append(url)
        if 'UC' + 'x' * 22 in url:
            raise ValueError('unavailable')
        return (b'<feed/>' if 'UC' + 'z' * 22 in url else rss()), url, 'application/atom+xml'
    monkeypatch.setattr(feeds, 'fetch_public', fetch)
    before = protected(store)
    result = benchmarks.run(store, digest(registry(store)))
    status = benchmarks.status(store)
    assert len(calls) == 3 and all(url.startswith('https://www.youtube.com/feeds/videos.xml?channel_id=UC') for url in calls)
    assert len(status['items']) == 1 and status['items'][0]['source_id'] == youtube['id']
    item = status['items'][0]
    assert item['fields'] == youtube['fields'] and item['verification_state'] == 'metadata_only'
    assert item['published_at'] != '2099-01-01T00:00:00Z' and item['checked_at']
    states = {row['source_id']: row for row in status['sources_status']}
    assert states['yt-failed']['state'] == 'failed' and states['yt-failed']['count'] is None
    assert states['yt-empty']['state'] == 'ok' and states['yt-empty']['count'] == 0
    assert states['yt-unready']['state'] == 'channel_id_required'
    assert result['paid_calls'] == 0 and result['partial_failure'] and protected(store) == before


def test_failure_preserves_old_items_with_their_original_observation_time(store, monkeypatch):
    open_window(store)
    monkeypatch.setattr(feeds, 'fetch_public', lambda url, **kw: (rss(), url, 'application/atom+xml'))
    benchmarks.run(store, digest(registry(store)))
    original = benchmarks.status(store)['items'][0]
    monkeypatch.setattr(feeds, 'fetch_public', lambda *a, **k: (_ for _ in ()).throw(ValueError('failed')))
    benchmarks.run(store, digest(registry(store)))
    result = benchmarks.status(store)
    assert result['items'][0]['checked_at'] == original['checked_at']
    assert result['items'][0]['verification_state'] == 'stale_metadata'
    assert any(s['state'] == 'failed' for s in result['sources_status'])


def test_manual_only_registry_never_falls_back_to_default_feeds(store, monkeypatch):
    save(store, [s for s in registry(store)['sources'] if s['platform'] == 'instagram'])
    open_window(store)
    monkeypatch.setattr(benchmarks, 'collect_feeds', lambda *a, **k: pytest.fail('empty feeds fell back'))
    result = benchmarks.run(store, digest(registry(store)))
    assert result['paid_calls'] == 0 and benchmarks.status(store)['items'] == []


def test_registry_change_during_collection_cannot_publish_a_mismatched_snapshot(store, monkeypatch):
    open_window(store)
    expected = digest(registry(store))
    def collect(root, feeds):
        changed = registry(store)
        changed['sources'][0]['name'] = 'Changed while collecting'
        benchmarks.save(store, changed, expected)
        return {'checked_at': datetime.now(timezone.utc).isoformat(), 'feeds': [], 'articles': [], 'partial_failure': False}
    monkeypatch.setattr(benchmarks, 'collect_feeds', collect)
    with pytest.raises(WorkflowError, match='바뀌'):
        benchmarks.run(store, expected)
    assert store.setting('benchmark_snapshot') is None


def test_official_news_is_website_source_and_never_a_destination_platform_claim(store):
    stamp = datetime.now(timezone.utc).isoformat()
    store.save_articles([{'id': 'official', 'title': 'AI release', 'url': 'https://openai.com/news/example', 'feed_id': 'openai',
                          'feed_name': 'OpenAI', 'segment': 'ai', 'published_at': stamp, 'retrieved_at': stamp}])
    before = database(store)
    item = benchmarks.status(store)['items'][0]
    assert item['platform'] == 'website' and item['source_id'] == ''
    assert '분류' in item['classification_note'] and database(store) == before


def test_latest_items_compare_real_times_across_timezone_offsets(store):
    current = datetime.now(timezone.utc)
    newer = (current - timedelta(hours=1)).astimezone(timezone(-timedelta(hours=10))).isoformat()
    older = (current - timedelta(hours=2)).astimezone(timezone(timedelta(hours=10))).isoformat()
    store.save_articles([{'id': key, 'title': key, 'url': 'https://example.com/' + key, 'published_at': stamp}
                         for key, stamp in [('newer', newer), ('older', older)]])
    assert [item['title'] for item in benchmarks.status(store)['items']] == ['newer', 'older']


@pytest.mark.parametrize('registered_count', [0, 210])
def test_status_bounds_large_board_without_changing_sources_news_or_snapshots(store, registered_count):
    current = datetime.now(timezone.utc)
    sources = registry(store)['sources']
    youtube = next(source for source in sources if source['platform'] == 'youtube')
    articles = []
    for i in range(2500):
        published = (current - timedelta(seconds=10 * i)).astimezone(timezone(timedelta(hours=9 if i % 2 else -8)))
        articles.append({'id': str(i), 'title': f'공식 뉴스 {i}', 'url': f'https://example.com/news/{i}',
                         'feed_id': 'official-feed', 'feed_name': '공식 출처', 'segment': 'ai',
                         'published_at': published.isoformat(), 'retrieved_at': current.isoformat(), 'summary': '가' * 700})
    store.save_articles(list(reversed(articles)))
    registered = [{'id': f'rss-{i}', 'title': f'등록 RSS {i}', 'url': f'https://www.youtube.com/watch?v=item{i}',
                   'source_id': youtube['id'], 'creator_id': youtube['creator_id'], 'source_name': youtube['name'],
                   'platform': 'youtube', 'fields': youtube['fields'], 'summary': '등록 채널 원문 요약',
                   'published_at': (current - timedelta(seconds=10 * i + 5)).isoformat(),
                   'checked_at': current.isoformat(), 'verification_state': 'metadata_only', 'idea_angle': '기획 제안'}
                  for i in range(registered_count)]
    snapshot = {'registry_hash': digest({'sources': sources}), 'checked_at': current.isoformat(),
                'items': list(reversed(registered)), 'sources_status': [
                    {'source_id': youtube['id'], 'state': 'ok', 'method': 'youtube_rss',
                     'checked_at': current.isoformat(), 'count': registered_count, 'error': None, 'note': '메타데이터'}]}
    store.set_setting('benchmark_snapshot', snapshot)
    before = database(store)
    result = benchmarks.status(store)
    expected_registered = min(registered_count, 192)
    assert result['coverage'] == {'available_items': 2500 + registered_count, 'returned_items': 48 + expected_registered,
                                  'limit': 240, 'official_limit': 48}
    assert len(result['items']) == 48 + expected_registered
    official = [item for item in result['items'] if item['platform'] == 'website']
    rss_items = [item for item in result['items'] if item['source_id'] == youtube['id']]
    assert [item['id'] for item in official] == [f'official-{i}' for i in range(48)]
    assert [item['id'] for item in rss_items] == [f'rss-{i}' for i in range(expected_registered)]
    assert all(item['source_id'] == '' and len(item['summary']) == 700 for item in official)
    published = [feeds.parse_date(item['published_at']) for item in result['items']]
    assert published == sorted(published, reverse=True)
    assert next(row for row in result['sources_status'] if row['source_id'] == youtube['id']) == snapshot['sources_status'][0]
    assert registry(store)['sources'] == sources and store.setting('benchmark_snapshot') == snapshot
    assert database(store) == before and len(store.articles_list()) == 2500
    # A display cap must not narrow original-source validation for an existing manual proposal.
    outside = articles[2000]
    idea = benchmarks.save_idea(store, {'title': '표시 범위 밖 원문도 검토', 'source_url': outside['url'], 'source_id': '',
                                        'fields': ['AI·기술'], 'target_platforms': ['youtube'], 'angle': '공식 원문 직접 확인',
                                        'expected_hash': digest({'sources': sources})})
    assert idea['state'] == 'candidate' and idea['primary_sources'] == 0 and idea['blocked']
    assert store.setting('benchmark_snapshot') == snapshot and len(store.articles_list()) == 2500


def test_idea_candidate_keeps_unverified_evidence_and_never_selects_or_creates_job(store, monkeypatch):
    source = next(s for s in registry(store)['sources'] if s['platform'] == 'instagram')
    body = {'title': '직접 재현해 볼 공부 워크플로', 'source_url': source['url'], 'source_id': source['id'],
            'fields': ['공부법'], 'target_platforms': ['instagram', 'youtube'], 'angle': '실제 자료로 성공·실패를 비교',
            'expected_hash': digest(registry(store))}
    before = protected(store)
    monkeypatch.setattr(feeds, 'fetch_public', lambda *a, **k: pytest.fail('idea fetched'))
    first = benchmarks.save_idea(store, body)
    assert first['state'] == 'candidate' and first['primary_sources'] == 0 and first['blocked']
    assert first['fields'] == ['공부법'] and first['target_platforms'] == ['instagram', 'youtube']
    assert benchmarks.save_idea(store, body)['id'] == first['id'] and len(store.ideas()) == 1
    assert protected(store) == before and store.tasks() == []


def test_idea_registry_race_is_rechecked_before_insert(store, monkeypatch):
    source = registry(store)['sources'][0]
    body = {'title': '경합 검증', 'source_url': source['url'], 'source_id': source['id'], 'fields': ['공부법'],
            'target_platforms': ['youtube'], 'angle': '원출처 확인', 'expected_hash': digest(registry(store))}
    score = benchmarks.score_idea
    def changed_while_preparing(card):
        scored = score(card)
        changed = registry(store)
        changed['sources'][0]['name'] = '새 이름'
        store.set_setting('benchmark_registry', changed)
        return scored
    monkeypatch.setattr(benchmarks, 'score_idea', changed_while_preparing)
    before = protected(store)
    with pytest.raises(WorkflowError, match='바뀌'):
        benchmarks.save_idea(store, body)
    assert store.ideas() == [] and protected(store) == before


def test_duplicate_save_cannot_rewrite_an_existing_human_selection(store):
    source = registry(store)['sources'][0]
    original = store.save_idea(benchmarks.score_idea({'title': '기존 인간 선택', 'source_url': source['url'],
                                                    'primary_sources': 2, 'angle': '사람이 편집한 관점'}))
    selected = store.select_idea(original['id'], actor='human-reviewer')
    before = database(store)
    result = benchmarks.save_idea(store, {'title': selected['title'], 'source_url': source['url'], 'source_id': source['id'],
                                         'fields': ['공부법'], 'target_platforms': ['youtube'], 'angle': '새 관점',
                                         'expected_hash': digest(registry(store))})
    assert result == selected and result['primary_sources'] == 2 and database(store) == before


def test_concurrent_idea_saves_return_the_same_original_card(store, monkeypatch):
    source = registry(store)['sources'][0]
    body = {'title': '동시 저장', 'source_url': source['url'], 'source_id': source['id'], 'fields': ['공부법'],
            'target_platforms': ['youtube'], 'angle': '첫 관점', 'expected_hash': digest(registry(store))}
    score, ideas = benchmarks.score_idea, store.ideas
    preparing, old_precheck = Barrier(2), Barrier(2)
    def prepared(card):
        scored = score(card)
        preparing.wait(timeout=10)
        return scored
    def racing_precheck():
        rows = ideas()
        old_precheck.wait(timeout=10)
        return rows
    monkeypatch.setattr(benchmarks, 'score_idea', prepared)
    monkeypatch.setattr(store, 'ideas', racing_precheck)
    before = protected(store)
    with ThreadPoolExecutor(max_workers=2) as pool:
        a = pool.submit(benchmarks.save_idea, store, body)
        b = pool.submit(benchmarks.save_idea, store, {**body, 'angle': '두 번째 관점'})
        first, second = a.result(timeout=15), b.result(timeout=15)
    assert first == second and len(ideas()) == 1 and protected(store) == before


def test_research_packet_is_read_only_bounded_and_does_not_claim_sage_execution(store, monkeypatch):
    source_ids = [s['id'] for s in registry(store)['sources']]
    body = {'source_ids': source_ids, 'fields': ['AI 활용'], 'platforms': ['youtube', 'instagram'], 'expected_hash': digest(registry(store))}
    before = database(store)
    monkeypatch.setattr(feeds, 'fetch_public', lambda *a, **k: pytest.fail('packet fetched'))
    result = benchmarks.research_packet(store, body)
    assert 'mybots-sage' in result['text'] and '루미' in result['text'] and '유료' in result['text']
    assert '외부 게시' in result['text'] and '⓪' in result['text'] and len(result['text']) <= 3600
    assert result['registry_hash'] == body['expected_hash'] and database(store) == before
    with pytest.raises(WorkflowError):
        benchmarks.research_packet(store, {**body, 'source_ids': ['missing']})


def test_research_empty_filters_mean_all_without_mutating_registry(store):
    body = {'source_ids': [s['id'] for s in registry(store)['sources']], 'fields': [], 'platforms': [],
            'expected_hash': digest(registry(store))}
    before = database(store)
    packet = benchmarks.research_packet(store, body)
    assert '분야: 전체' in packet['text'] and '플랫폼: 전체' in packet['text']
    assert database(store) == before


def test_api_preserves_session_csrf_hash_and_exact_dto(store, monkeypatch):
    monkeypatch.setenv('OFFICE_STATE_DIR', str(store.root / 'import-state'))
    from office.api import create_app
    client = TestClient(create_app(store), base_url='http://localhost:8510')
    before = database(store)
    read = client.get('/api/benchmarks')
    assert read.status_code == 200 and database(store) == before
    value = read.json()
    body = {**value['registry'], 'expected_hash': value['registry_hash']}
    assert client.put('/api/benchmarks', json=body).status_code == 403
    headers = {'Origin': 'http://localhost:3110', 'X-Office-CSRF': client.get('/api/session').json()['csrf']}
    assert client.put('/api/benchmarks', json=body, headers=headers).status_code == 200
    assert client.post('/api/benchmarks/refresh', json={'expected_hash': '0' * 64}, headers=headers).status_code == 409
    unchanged = database(store)
    packet = client.post('/api/benchmarks/research-packet', json={'source_ids': [s['id'] for s in value['registry']['sources']],
                          'fields': [], 'platforms': [], 'expected_hash': value['registry_hash']}, headers=headers)
    assert packet.status_code == 200 and '플랫폼: 전체' in packet.json()['text'] and database(store) == unchanged
    bad = {**body, 'unapproved': True}
    assert client.put('/api/benchmarks', json=bad, headers=headers).status_code == 422


def observation_body(store, **item_changes):
    current = datetime.now(timezone.utc)
    item = {'url': 'https://www.instagram.com/every._ai/p/De6OvlsFfaA/', 'author_username': 'every._ai',
            'title': '실제 공개 게시물 관측', 'summary': '게시자의 도구 소개이며 성능 주장은 미검증입니다.',
            'published_at': (current - timedelta(days=14)).isoformat(), 'observed_at': current.isoformat(),
            'metrics': {'likes': {'value': 761, 'availability': 'observed', 'raw_text': '761', 'precision': 'exact'},
                        'comments': {'value': 5800, 'availability': 'observed', 'raw_text': '5.8천', 'precision': 'approximate'},
                        'views': {'value': None, 'availability': 'not_visible', 'raw_text': '', 'precision': 'unknown'}}}
    item.update(item_changes)
    board = benchmarks.status(store)
    return {'source_id': 'every-ai-instagram', 'expected_hash': board['registry_hash'],
            'snapshot_hash': board['snapshot_hash'], 'capture_sha256': 'a' * 64,
            'collection_scope': '프로필에 표시된 게시물 1건의 공개 DOM만 관측. 전체 최신순·인기순위 미확인.', 'items': [item]}


def test_observed_youtube_metrics_keep_original_feed_hash_without_model_or_other_state(store, monkeypatch):
    open_window(store)
    raw = rss().replace(b'<entry>', b'<entry xmlns:media="http://search.yahoo.com/mrss/">', 1).replace(
        b'</published>', b'</published><media:group><media:community><media:statistics views="1234"/></media:community></media:group>', 1)
    monkeypatch.setattr(feeds, 'fetch_public', lambda url, **kw: (raw, url, 'application/atom+xml'))
    before = protected(store)
    benchmarks.run(store, digest(registry(store)))
    board = benchmarks.status(store)
    item = board['items'][0]
    assert item['metrics']['views'] == {'value': 1234, 'availability': 'observed', 'raw_text': '1234', 'precision': 'exact'}
    assert item['provenance']['method'] == 'youtube_rss'
    import hashlib
    assert item['provenance']['capture_sha256'] == hashlib.sha256(raw).hexdigest()
    assert board['snapshot_hash'] == benchmarks._snapshot_hash(store.setting('benchmark_snapshot'), store=store)
    assert protected(store) == before


def test_browser_import_preserves_historical_dates_missing_metrics_and_immutable_receipt(store, monkeypatch):
    body = observation_body(store)
    before = protected(store)
    monkeypatch.setattr(feeds, 'fetch_public', lambda *a, **kw: pytest.fail('import must not fetch'))
    first = benchmarks.import_observations(store, body)
    item = first['items'][0]
    assert item['freshness'] == 'historical' and item['published_at'] == body['items'][0]['published_at']
    assert item['metrics']['views']['value'] is None and item['metrics']['comments']['precision'] == 'approximate'
    assert item['provenance']['method'] == 'browser_public_observation'
    assert item['provenance']['source_hash'] == digest(registry(store)['sources'][0])
    assert item['provenance']['capture_sha256'] == body['capture_sha256']
    assert first['sources_status'][0]['state'] == 'observed'
    before_replay = database(store)
    replay = benchmarks.import_observations(store, body)
    assert replay['import_receipt']['replayed'] and replay['items'] == first['items']
    assert database(store) == before_replay and protected(store) == before and store.tasks() == []
    assert not feeds.rank_articles([{'url': item['url'], 'published_at': item['published_at'], 'title': item['title']}])


def test_undated_browser_observation_keeps_null_and_get_is_pure(store, monkeypatch):
    benchmarks.import_observations(store, observation_body(store, published_at=None))
    before = database(store)
    monkeypatch.setattr(feeds, 'fetch_public', lambda *a, **kw: pytest.fail('GET fetched'))
    board = benchmarks.status(store)
    assert board['items'][0]['published_at'] is None and board['items'][0]['freshness'] == 'unknown'
    assert database(store) == before


@pytest.mark.parametrize('change', [
    {'url': 'https://www.instagram.com/accounts/login/'},
    {'url': 'https://www.instagram.com/someone_else/p/De6OvlsFfaA/'},
    {'url': 'https://www.instagram.com.evil.example/p/De6OvlsFfaA/'},
    {'url': 'https://user:secret@www.instagram.com/p/De6OvlsFfaA/'},
    {'author_username': 'someone_else'}, {'observed_at': '2020-01-01T00:00:00Z'},
    {'published_at': '2099-01-01T00:00:00Z'},
    {'metrics': {'likes': {'value': True, 'availability': 'observed', 'raw_text': '1', 'precision': 'exact'}}},
    {'metrics': {'likes': {'value': 0, 'availability': 'not_visible', 'raw_text': '', 'precision': 'unknown'}}},
    {'metrics': {'likes': {'value': 5800, 'availability': 'observed', 'raw_text': '5.8천', 'precision': 'exact'}}},
    {'metrics': {'likes': {'value': 700, 'availability': 'observed', 'raw_text': '761', 'precision': 'exact'}}},
])
def test_invalid_browser_observations_never_write_or_fetch(store, change, monkeypatch):
    body = observation_body(store, **change)
    before = database(store)
    monkeypatch.setattr(feeds, 'fetch_public', lambda *a, **kw: pytest.fail('invalid import fetched'))
    with pytest.raises(WorkflowError):
        benchmarks.import_observations(store, body)
    assert database(store) == before


def test_import_rejects_stale_snapshot_conflicting_capture_and_older_observation(store):
    body = observation_body(store)
    first = benchmarks.import_observations(store, body)
    changed = copy.deepcopy(body)
    changed['items'][0]['metrics']['likes']['value'] += 1
    before = database(store)
    with pytest.raises(WorkflowError):
        benchmarks.import_observations(store, changed)
    stale = {**body, 'capture_sha256': 'b' * 64}
    with pytest.raises(WorkflowError):
        benchmarks.import_observations(store, stale)
    older = {**stale, 'snapshot_hash': first['snapshot_hash'], 'items': [{**body['items'][0],
             'observed_at': (datetime.now(timezone.utc) - timedelta(hours=1)).isoformat()}]}
    with pytest.raises(WorkflowError):
        benchmarks.import_observations(store, older)
    assert database(store) == before


def test_rss_collection_merges_an_import_that_arrives_while_fetching(store, monkeypatch):
    open_window(store)
    body = observation_body(store)
    def collect(root, feeds):
        benchmarks.import_observations(store, body)
        return {'checked_at': datetime.now(timezone.utc).isoformat(), 'feeds': [], 'articles': [], 'partial_failure': False}
    monkeypatch.setattr(benchmarks, 'collect_feeds', collect)
    benchmarks.run(store, digest(registry(store)))
    board = benchmarks.status(store)
    assert len(board['items']) == 1 and board['items'][0]['platform'] == 'instagram'
    assert board['sources_status'][0]['method'] == 'browser_public_observation'


def test_snapshot_bound_idea_copies_server_observation_and_preserves_existing_selection(store):
    board = benchmarks.import_observations(store, observation_body(store))
    item = board['items'][0]
    body = {'title': '관측 근거가 붙은 후보', 'source_url': item['url'], 'source_id': item['source_id'],
            'fields': ['공부법'], 'target_platforms': ['youtube'], 'angle': '직접 비교 실험',
            'expected_hash': board['registry_hash'], 'snapshot_hash': board['snapshot_hash'], 'item_id': item['id']}
    card = benchmarks.save_idea(store, body)
    assert card['observed_metrics'] == item['metrics'] and card['provenance'] == item['provenance']
    assert card['primary_sources'] == 0 and card['blocked'] and card['verification_state'] == 'unverified'
    before = database(store)
    assert benchmarks.save_idea(store, body) == card and database(store) == before
    with pytest.raises(WorkflowError):
        benchmarks.save_idea(store, {**body, 'source_url': 'https://www.instagram.com/p/anotherPost/'})
    with pytest.raises(WorkflowError):
        benchmarks.save_idea(store, {**body, 'snapshot_hash': '0' * 64})


def test_research_packet_carries_bounded_actual_observations_and_separate_public_trends(store):
    board = benchmarks.import_observations(store, observation_body(store))
    stamp = datetime.now(timezone.utc).isoformat()
    store.set_setting('discovery_report', {'checked_at': stamp, 'recommendations': {'youtube': [
        {'id': 'trend', 'title': 'AI 공개 반응 참고', 'url': 'https://news.ycombinator.com/item?id=1', 'kind': 'community',
         'published_at': stamp, 'observed_at': stamp, 'signals': {'hn_points': 123}, 'feed_name': 'HN'},
        {'id': 'fake', 'title': '미지원 성과', 'url': 'https://example.com/fake', 'kind': 'instagram', 'observed_at': stamp}]}})
    before = database(store)
    overview = benchmarks.status(store)
    assert len(overview['trend_refs']) == 1 and overview['trend_refs'][0]['source_id'] == ''
    packet = benchmarks.research_packet(store, {'source_ids': ['every-ai-instagram'], 'fields': [], 'platforms': [],
        'expected_hash': board['registry_hash'], 'snapshot_hash': overview['snapshot_hash'],
        'item_ids': [board['items'][0]['id'], overview['trend_refs'][0]['id']]})
    assert '5.8천' in packet['text'] and 'historical' in packet['text'] and '누적' in packet['text']
    assert 'https://news.ycombinator.com/item?id=1' in packet['text'] and len(packet['text']) <= 3600
    assert packet['coverage']['included_items'] == 1 and packet['coverage']['available_items'] == 1
    assert packet['coverage']['included_trend_refs'] == 1
    assert database(store) == before


def test_observation_api_keeps_csrf_and_rejects_forged_metrics_or_verification(store, monkeypatch):
    monkeypatch.setenv('OFFICE_STATE_DIR', str(store.root / 'import-state'))
    from office.api import create_app
    client = TestClient(create_app(store), base_url='http://localhost:8510')
    body = observation_body(store)
    assert client.post('/api/benchmarks/observations', json=body).status_code == 403
    headers = {'Origin': 'http://localhost:3110', 'X-Office-CSRF': client.get('/api/session').json()['csrf']}
    forged = copy.deepcopy(body)
    forged['items'][0]['verification_state'] = 'verified'
    assert client.post('/api/benchmarks/observations', json=forged, headers=headers).status_code == 422
    assert client.post('/api/benchmarks/observations', json=body, headers=headers).status_code == 200


def test_large_six_observation_packet_is_rejected_without_truncating_evidence(store):
    body = observation_body(store)
    body['items'] = [{**body['items'][0], 'url': f'https://www.instagram.com/p/ExamplePost{i}/',
                      'title': '관측 제목' * 30, 'summary': '독립 요약 문장 ' * 60} for i in range(8)]
    board = benchmarks.import_observations(store, body)
    selection = {'source_ids': [body['source_id']], 'fields': [], 'platforms': [],
                 'expected_hash': board['registry_hash'], 'snapshot_hash': board['snapshot_hash'],
                 'item_ids': [item['id'] for item in board['items'][:6]]}
    before = database(store)
    with pytest.raises(WorkflowError, match='깁니다'):
        benchmarks.research_packet(store, selection)
    assert database(store) == before
    packet = benchmarks.research_packet(store, {**selection, 'item_ids': selection['item_ids'][:3]})
    assert len(packet['observations']) == 3 and len(packet['text']) <= 3600
    assert packet['coverage']['available_items'] == 8 and packet['coverage']['omitted_items'] == 5
    for item in packet['observations']:
        assert item['url'] in packet['text'] and item['published_at'] in packet['text']
        assert item['provenance']['observed_at'] in packet['text']
    assert '5.8천' in packet['text'] and 'browser_public_observation' in packet['text']


def test_verified_research_candidate_keeps_frozen_observation_when_snapshot_advances(store):
    board = benchmarks.import_observations(store, observation_body(store))
    item = board['items'][0]
    newer = observation_body(store)
    newer['capture_sha256'] = 'b' * 64
    newer['items'][0]['metrics']['likes']['value'] = 900
    newer['items'][0]['metrics']['likes']['raw_text'] = '900'
    benchmarks.import_observations(store, newer)
    receipt = {'request_id': '3a06791a-3635-41ab-9496-a4c5dad230e6', 'task_id': 't_final', 'run_id': 1,
               'event_id': 2, 'report_sha256': 'c' * 64, 'body_sha256': 'd' * 64, 'packet_hash': 'e' * 64,
               'registry_hash': board['registry_hash'], 'snapshot_hash': board['snapshot_hash']}
    before = protected(store)
    body = {'title': '완료 보고를 검토한 후보', 'angle': '실제 비교 실험으로 확인', 'target_platforms': ['youtube']}
    idea = benchmarks.save_research_idea(store, item, body, receipt)
    assert idea['observed_metrics']['likes']['value'] == 761 and idea['analysis_receipt'] == receipt
    assert idea['primary_sources'] == 0 and idea['blocked'] and protected(store) == before
    old = database(store)
    assert benchmarks.save_research_idea(store, item, {**body, 'angle': '덮어쓰기 금지'}, receipt) == idea
    assert database(store) == old
    changed = registry(store)
    changed['sources'][0]['name'] = '등록 변경'
    benchmarks.save(store, changed, board['registry_hash'])
    with pytest.raises(WorkflowError):
        benchmarks.save_research_idea(store, item, body, receipt)


def trend_report(points=123):
    stamp = datetime.now(timezone.utc).isoformat()
    return {'checked_at': stamp, 'recommendations': {'youtube': [
        {'id': 'trend', 'title': 'AI 공개 반응 참고', 'url': 'https://news.ycombinator.com/item?id=1', 'kind': 'community',
         'published_at': stamp, 'observed_at': stamp, 'signals': {'hn_points': points}, 'feed_name': 'HN'}]}}


def test_trend_only_packet_and_idea_bind_composite_snapshot_and_preserve_frozen_evidence(store):
    store.set_setting('discovery_report', trend_report())
    board = benchmarks.status(store)
    trend = board['trend_refs'][0]
    selection = {'source_ids': [], 'fields': [], 'platforms': [], 'expected_hash': board['registry_hash'],
                 'snapshot_hash': board['snapshot_hash'], 'item_ids': [trend['id']]}
    packet = benchmarks.research_packet(store, selection)
    assert packet['observations'] == [trend] and packet['coverage']['included_trend_refs'] == 1
    with pytest.raises(WorkflowError):
        benchmarks.research_packet(store, {**selection, 'item_ids': []})
    idea_body = {'title': 'HN 관측에서 검증할 소재', 'source_url': trend['url'], 'source_id': '', 'fields': ['AI·기술'],
                 'target_platforms': ['youtube'], 'angle': '원문과 반례 확인', 'expected_hash': board['registry_hash'],
                 'snapshot_hash': board['snapshot_hash'], 'item_id': trend['id']}
    idea = benchmarks.save_idea(store, idea_body)
    assert idea['observed_signals'] == {'hn_points': 123} and idea['provenance'] == trend['provenance']
    store.set_setting('discovery_report', trend_report(999))
    after_refresh = database(store)
    with pytest.raises(WorkflowError, match='바뀌'):
        benchmarks.save_idea(store, idea_body)
    with pytest.raises(WorkflowError, match='바뀌'):
        benchmarks.research_packet(store, selection)
    assert database(store) == after_refresh and store.ideas()[0]['observed_signals']['hn_points'] == 123
    receipt = {'request_id': '3a06791a-3635-41ab-9496-a4c5dad230e6', 'task_id': 't_final', 'run_id': 1,
               'event_id': 2, 'report_sha256': 'c' * 64, 'body_sha256': 'd' * 64, 'packet_hash': packet['packet_hash'],
               'registry_hash': board['registry_hash'], 'snapshot_hash': board['snapshot_hash']}
    frozen = benchmarks.save_research_idea(store, packet['observations'][0],
        {'title': '독립 검토 보고를 연결한 기획', 'angle': '동결한 표본으로 비교', 'target_platforms': ['youtube']}, receipt)
    assert frozen['observed_signals']['hn_points'] == 123 and frozen['analysis_receipt'] == receipt
    assert frozen['primary_sources'] == 0 and frozen['blocked']


def test_selected_observation_resolves_its_source_without_a_separate_checkbox(store):
    board = benchmarks.import_observations(store, observation_body(store))
    packet = benchmarks.research_packet(store, {'source_ids': [], 'fields': [], 'platforms': [],
        'expected_hash': board['registry_hash'], 'snapshot_hash': board['snapshot_hash'],
        'item_ids': [board['items'][0]['id']]})
    assert packet['observations'] == board['items']
    assert 'every._ai' in packet['text'] and packet['coverage']['included_items'] == 1


def test_trend_change_during_idea_preparation_is_rechecked_under_writer_lock(store, monkeypatch):
    store.set_setting('discovery_report', trend_report())
    board = benchmarks.status(store)
    trend = board['trend_refs'][0]
    score = benchmarks.score_idea
    def changed_while_scoring(card):
        result = score(card)
        store.set_setting('discovery_report', trend_report(456))
        return result
    monkeypatch.setattr(benchmarks, 'score_idea', changed_while_scoring)
    before = protected(store)
    with pytest.raises(WorkflowError, match='바뀌'):
        benchmarks.save_idea(store, {'title': '경합', 'source_url': trend['url'], 'source_id': '', 'fields': ['AI·기술'],
            'target_platforms': ['youtube'], 'angle': '원문 확인', 'expected_hash': board['registry_hash'],
            'snapshot_hash': board['snapshot_hash'], 'item_id': trend['id']})
    assert store.ideas() == [] and protected(store) == before


@pytest.mark.parametrize('selected', [False, True])
def test_research_cannot_claim_receipt_attachment_to_an_existing_manual_candidate(store, selected):
    board = benchmarks.import_observations(store, observation_body(store))
    item = board['items'][0]
    old = store.save_idea(benchmarks.score_idea({'title': '이미 사람이 저장한 기획', 'source_url': item['url'],
                                               'primary_sources': 2, 'angle': '기존 사람 편집'}))
    if selected:
        old = store.select_idea(old['id'], actor='human')
    receipt = {'request_id': '3a06791a-3635-41ab-9496-a4c5dad230e6', 'task_id': 't_final', 'run_id': 1,
               'event_id': 2, 'report_sha256': 'c' * 64, 'body_sha256': 'd' * 64, 'packet_hash': 'e' * 64,
               'registry_hash': board['registry_hash'], 'snapshot_hash': board['snapshot_hash']}
    before = database(store)
    with pytest.raises(WorkflowError, match='기존 후보를 보존'):
        benchmarks.save_research_idea(store, item,
            {'title': old['title'], 'angle': '덮어쓰지 말아야 할 새 분석', 'target_platforms': ['youtube']}, receipt)
    assert database(store) == before and store.ideas()[0] == old
