"""Pexels free stock footage: query building, file choice, receipts, limits. No network here."""
import json

import pytest

from office.store import Store, WorkflowError


MP4 = b"\x00\x00\x00\x18ftypmp42" + b"\x00" * 2048


def scenes():
    return [
        {'narration': '노트북으로 문서를 정리해요.', 'caption': '문서 정리', 'visual': '노트북 앞에서 서류를 정리하는 손', 'footage': 'hands typing laptop'},
        {'narration': '회의에서 결정을 내려요.', 'caption': '결정 회의', 'visual': '회의실에서 메모하는 장면'},
        {'narration': '그다음 확인해요.', 'caption': 'Review', 'visual': '흐름: 확인 → 정리'},
    ]


def approved_fixture(tmp_path, *, video=True, approve=True, scene_list=None):
    store = Store(tmp_path / 'state')
    job = store.create_job({'id': 'stock-footage', 'title': '실사 영상 시험'})
    packet = {'title': '합성 자료', 'body': '실사 영상 프로필 시험입니다.', 'quality': {'status': 'passed', 'critical': []},
              'video': {'title': '실사 영상', 'scenes': scene_list or scenes()}}
    job = store.save_source(job['id'], packet)
    if approve:
        store.review_source(job['id'], job['source_hash'], 'approved', 'op', {'video': video, 'cards': not video})
    return store, job['id']


def video(video_id, files, name='Kim Photographer'):
    return {'id': video_id, 'url': f'https://www.pexels.com/video/sample-{video_id}/', 'width': 1080, 'height': 1920, 'duration': 12,
            'user': {'id': 7, 'name': name, 'url': 'https://www.pexels.com/@kim'}, 'video_files': files}


def vfile(width, height, *, quality='hd', file_type='video/mp4', link=None, file_id=1):
    return {'id': file_id, 'quality': quality, 'file_type': file_type, 'width': width, 'height': height, 'fps': 25,
            'link': link or f'https://videos.pexels.com/video-files/{width}x{height}.mp4'}


class Response:
    def __init__(self, status=200, payload=None, body=b'', headers=None):
        self.status_code, self._payload, self._body, self.headers = status, payload, body, headers or {}

    def json(self):
        if self._payload is None:
            raise ValueError('no json')
        return self._payload

    def iter_content(self, chunk_size=65536):
        for start in range(0, len(self._body), chunk_size):
            yield self._body[start:start + chunk_size]

    def close(self):
        pass


class Session:
    def __init__(self, search=None, body=MP4, fail=None, download_headers=None):
        self.calls = []
        self.search = search if search is not None else {'videos': [video(11, [vfile(720, 1280, file_id=1), vfile(1080, 1920, file_id=2), vfile(1920, 1080, file_id=3)]),
                                                                    video(12, [vfile(1080, 1920, file_id=4)], name='Lee Filmmaker')]}
        self.body, self.fail, self.download_headers = body, fail, download_headers or {}

    def get(self, url, params=None, headers=None, timeout=None, stream=False):
        import requests
        self.calls.append({'url': url, 'params': params, 'headers': headers, 'timeout': timeout, 'stream': stream})
        if self.fail == 'network':
            raise requests.ConnectionError('offline')
        if url.startswith('https://api.pexels.com/'):
            if self.fail == 'http':
                return Response(429, {'error': 'rate limited'})
            return Response(200, self.search)
        return Response(200, body=self.body, headers=self.download_headers)


def good_probe(path):
    return {'streams': [{'codec_type': 'video', 'width': 1080, 'height': 1920}], 'format': {'duration': '12.0'}}


def test_footage_query_prefers_english_field_then_korean_map_then_ascii_caption_then_generic():
    from office.stock_video import GENERIC_QUERY, footage_query
    assert footage_query({'footage': 'Hands typing on a laptop!!', 'visual': '회의실'}) == 'hands typing laptop'
    assert footage_query({'caption': '결정 회의', 'visual': '회의실에서 메모하는 장면'}) == 'meeting room notes'
    assert footage_query({'caption': '문서 정리', 'visual': '노트북 앞에서 서류를 정리하는 손'}) == 'laptop documents hands'
    assert footage_query({'caption': 'Weekly review', 'visual': '흐름: 확인 → 정리'}) == 'weekly review'
    assert footage_query({'caption': '알 수 없는 개념', 'visual': '추상적인 무언가'}) == GENERIC_QUERY
    # Korean text and filler words never reach the search query; an over-long field is cut to four words.
    assert footage_query({'footage': '노트북 laptop', 'caption': '조건'}) == 'laptop'
    assert footage_query({'footage': 'one two three four five six'}) == 'one two three four'


def test_choose_file_takes_portrait_mp4_at_least_720_wide_preferring_1080x1920():
    from office.stock_video import choose_file
    files = [vfile(1920, 1080, file_id=1), vfile(540, 960, quality='sd', file_id=2), vfile(2160, 3840, quality='uhd', file_id=3),
             vfile(720, 1280, file_id=4), vfile(1080, 1920, file_id=5), vfile(1080, 1920, file_type='video/quicktime', file_id=6)]
    assert choose_file({'video_files': files})['id'] == 5
    assert choose_file({'video_files': [vfile(720, 1280, file_id=4), vfile(2160, 3840, file_id=3)]})['id'] == 4
    assert choose_file({'video_files': [vfile(1920, 1080), vfile(540, 960)]}) is None
    assert choose_file({'video_files': [vfile(1080, 1920, link='http://videos.pexels.com/a.mp4')]}) is None
    assert choose_file({'video_files': [vfile(1080, 1920, link='https://evil.example.com/a.mp4')]}) is None
    assert choose_file({'video_files': 'broken'}) is None


def test_clip_searches_with_raw_key_downloads_and_writes_receipt_with_attribution(tmp_path, monkeypatch):
    from office.stock_video import LICENSE_URL, make_pexels_clip_renderer
    monkeypatch.setenv('PEXELS_API_KEY', 'test-pexels-key')
    store, job_id = approved_fixture(tmp_path)
    session = Session()
    render = make_pexels_clip_renderer(store, job_id=job_id, session=session, probe=good_probe)
    assert render.needs_background is False and render.fallback_to_still is True
    assert render.generated_scenes == [0, 1, 2]
    out = store.root / 'job' / 'generated-01.mp4'
    meta = render(0, None, out)
    search = session.calls[0]
    assert search['url'] == 'https://api.pexels.com/videos/search'
    assert search['headers'] == {'Authorization': 'test-pexels-key'}
    assert search['params']['query'] == 'hands typing laptop'
    assert search['params']['orientation'] == 'portrait' and search['params']['size'] == 'medium'
    assert search['timeout'] and session.calls[1]['url'] == 'https://videos.pexels.com/video-files/1080x1920.mp4'
    assert session.calls[1]['stream'] is True
    assert out.read_bytes() == MP4
    assert meta['provider'] == 'pexels' and meta['attribution']['name'] == 'Kim Photographer'
    assert meta['attribution']['pexels_video_id'] == 11 and meta['attribution']['license_url'] == LICENSE_URL
    assert meta['attribution']['page_url'] == 'https://www.pexels.com/video/sample-11/'
    receipts = list((store.root / 'stock-assets').glob('*.json'))
    assert len(receipts) == 1
    receipt = json.loads(receipts[0].read_text(encoding='utf-8'))
    assert receipt['query'] == 'hands typing laptop' and receipt['pexels_video_id'] == 11
    assert receipt['user_name'] == 'Kim Photographer' and len(receipt['sha256']) == 64
    assert 'test-pexels-key' not in receipts[0].read_text(encoding='utf-8')
    assert any(e['kind'] == 'stock_footage_downloaded' for e in store.events(job_id))
    assert store.budget() == Store(tmp_path / 'state').budget()


def test_cached_query_is_reused_without_network_and_repeated_queries_get_different_videos(tmp_path, monkeypatch):
    from office.stock_video import make_pexels_clip_renderer
    monkeypatch.setenv('PEXELS_API_KEY', 'test-pexels-key')
    same = [{'narration': '하나', 'caption': '하나', 'visual': '추상'}, {'narration': '둘', 'caption': '둘', 'visual': '추상'}]
    store, job_id = approved_fixture(tmp_path, scene_list=same)
    session = Session()
    render = make_pexels_clip_renderer(store, job_id=job_id, session=session, probe=good_probe)
    first = render(0, None, store.root / 'a' / 'generated-01.mp4')
    second = render(1, None, store.root / 'a' / 'generated-02.mp4')
    assert first['attribution']['pexels_video_id'] == 11 and second['attribution']['pexels_video_id'] == 12
    calls = len(session.calls)
    again = make_pexels_clip_renderer(store, job_id=job_id, session=session, probe=good_probe)
    assert again(0, None, store.root / 'b' / 'generated-01.mp4')['attribution']['pexels_video_id'] == 11
    assert len(session.calls) == calls


@pytest.mark.parametrize('fail', ['network', 'http'])
def test_search_failure_is_a_fallback_signal_with_an_event_not_a_paid_retry(tmp_path, monkeypatch, fail):
    from office.stock_video import StockFootageUnavailable, make_pexels_clip_renderer
    monkeypatch.setenv('PEXELS_API_KEY', 'test-pexels-key')
    store, job_id = approved_fixture(tmp_path)
    session = Session(fail=fail)
    render = make_pexels_clip_renderer(store, job_id=job_id, session=session, probe=good_probe)
    with pytest.raises(StockFootageUnavailable):
        render(0, None, store.root / 'job' / 'generated-01.mp4')
    assert len(session.calls) == 1
    assert issubclass(StockFootageUnavailable, WorkflowError)
    assert any(e['kind'] == 'stock_footage_unavailable' for e in store.events(job_id))


def test_oversized_or_non_video_download_is_rejected_and_not_cached(tmp_path, monkeypatch):
    from office import stock_video
    monkeypatch.setenv('PEXELS_API_KEY', 'test-pexels-key')
    monkeypatch.setattr(stock_video, 'MAX_VIDEO_BYTES', 1000)
    store, job_id = approved_fixture(tmp_path)
    render = stock_video.make_pexels_clip_renderer(store, job_id=job_id, session=Session(), probe=good_probe)
    with pytest.raises(stock_video.StockFootageUnavailable, match='크기'):
        render(0, None, store.root / 'job' / 'generated-01.mp4')
    assert not list((store.root / 'stock-assets').glob('*.mp4')) and not list((store.root / 'stock-assets').glob('*.partial*'))
    monkeypatch.setattr(stock_video, 'MAX_VIDEO_BYTES', 60_000_000)
    no_video = stock_video.make_pexels_clip_renderer(store, job_id=job_id, session=Session(), probe=lambda path: {'streams': [{'codec_type': 'audio'}]})
    with pytest.raises(stock_video.StockFootageUnavailable, match='영상'):
        no_video(0, None, store.root / 'job' / 'generated-01.mp4')
    assert not list((store.root / 'stock-assets').glob('*.mp4'))


def test_missing_key_unapproved_source_or_cards_only_never_touch_the_network(tmp_path, monkeypatch):
    from office.stock_video import StockFootageUnavailable, make_pexels_clip_renderer
    monkeypatch.delenv('PEXELS_API_KEY', raising=False)
    store, job_id = approved_fixture(tmp_path)
    session = Session()
    render = make_pexels_clip_renderer(store, job_id=job_id, session=session, probe=good_probe)
    with pytest.raises(StockFootageUnavailable, match='PEXELS_API_KEY'):
        render(0, None, store.root / 'job' / 'generated-01.mp4')
    monkeypatch.setenv('PEXELS_API_KEY', 'test-pexels-key')
    cards_store, cards_job = approved_fixture(tmp_path / 'cards', video=False)
    cards = make_pexels_clip_renderer(cards_store, job_id=cards_job, session=session, probe=good_probe)
    with pytest.raises(WorkflowError, match='영상 제작'):
        cards(0, None, cards_store.root / 'job' / 'generated-01.mp4')
    with pytest.raises(WorkflowError, match='승인'):
        unapproved_store, unapproved_job = approved_fixture(tmp_path / 'draft', approve=False)
        make_pexels_clip_renderer(unapproved_store, job_id=unapproved_job, session=session, probe=good_probe)
    assert session.calls == []


def test_download_cap_per_job_is_enforced_from_recorded_events(tmp_path, monkeypatch):
    from office import stock_video
    monkeypatch.setenv('PEXELS_API_KEY', 'test-pexels-key')
    monkeypatch.setattr(stock_video, 'MAX_DOWNLOADS_PER_JOB', 1)
    store, job_id = approved_fixture(tmp_path)
    session = Session()
    render = stock_video.make_pexels_clip_renderer(store, job_id=job_id, session=session, probe=good_probe)
    render(0, None, store.root / 'job' / 'generated-01.mp4')
    calls = len(session.calls)
    with pytest.raises(stock_video.StockFootageUnavailable, match='1개'):
        render(1, None, store.root / 'job' / 'generated-02.mp4')
    assert len(session.calls) == calls


def test_renderer_identity_is_deterministic_and_carries_no_key(tmp_path, monkeypatch):
    from office.stock_video import make_pexels_clip_renderer
    monkeypatch.setenv('PEXELS_API_KEY', 'test-pexels-key')
    store, job_id = approved_fixture(tmp_path)
    one = make_pexels_clip_renderer(store, job_id=job_id, session=Session(), probe=good_probe)
    two = make_pexels_clip_renderer(store, job_id=job_id, session=Session(), probe=good_probe)
    assert one.cache_key == two.cache_key and one.cache_key.startswith('pexels-stock:')
    assert one.asset_cache_key.startswith('pexels-stock-asset:')
    assert 'test-pexels-key' not in one.cache_key + one.asset_cache_key
