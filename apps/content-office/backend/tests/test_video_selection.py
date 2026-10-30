import pytest

from office.store import Store, WorkflowError


def fixture(store, generated=True):
    job = store.create_job({'id': 'clip-profile', 'title': '생성 영상 선택 시험'})
    scene = {'narration': '원고를 승인합니다.', 'caption': '원고 승인①'}
    packet = {'title': '합성 자료', 'body': '프로필 기능 시험입니다.', 'quality': {'status': 'passed', 'critical': []},
              'video': {'scenes': [{'narration': '근거를 확인합니다.', 'caption': '근거'}, {**scene, 'clip': 'generated'} if generated else scene]}}
    return store.save_source(job['id'], packet)


def test_none_is_default_and_selection_is_free(tmp_path, monkeypatch):
    from office.video_selection import select_profile, clip_renderer_for_job, profile_summary, PROFILES
    monkeypatch.delenv('RUNWAYML_API_SECRET', raising=False)
    store = Store(tmp_path)
    job = fixture(store)
    assert set(PROFILES) == {'none', 'pexels-stock', 'runway-grok-lite', 'runway-gen4-turbo', 'runway-gen4.5'}
    assert profile_summary(store)['id'] == 'none' and profile_summary(store)['configured'] is False
    assert clip_renderer_for_job(store, job) is None
    before = store.budget()
    summary = select_profile(store, 'runway-gen4-turbo', actor='test-operator')
    assert summary['paid'] is True and summary['job_cap_krw'] == 5000 and summary['model'] == 'gen4_turbo'
    assert store.budget() == before
    with pytest.raises(WorkflowError, match='프로필'):
        select_profile(store, 'sora', actor='test-operator')


def test_factory_requires_approval_video_selection_and_opted_scene(tmp_path, monkeypatch):
    from office.video_selection import select_profile, clip_renderer_for_job
    monkeypatch.setenv('RUNWAYML_API_SECRET', 'test-secret')
    store = Store(tmp_path)
    select_profile(store, 'runway-gen4.5', actor='test-operator')
    job = fixture(store)
    with pytest.raises(WorkflowError, match='승인'):
        clip_renderer_for_job(store, job)
    store.review_source(job['id'], job['source_hash'], 'approved', 'op', {'cards': True})
    assert clip_renderer_for_job(store, store.job(job['id'])) is None
    store.review_source(job['id'], job['source_hash'], 'approved', 'op', {'video': True})
    renderer = clip_renderer_for_job(store, store.job(job['id']))
    assert renderer.clip_provider.config['model'] == 'gen4.5'
    plain = fixture(Store(tmp_path / 'plain'), generated=False)
    store2 = Store(tmp_path / 'plain')
    select_profile(store2, 'runway-gen4.5', actor='test-operator')
    store2.review_source(plain['id'], plain['source_hash'], 'approved', 'op', {'video': True})
    # Default: every scene gets a clip, marked or not.
    assert clip_renderer_for_job(store2, store2.job(plain['id'])).generated_scenes == [0, 1]


def test_pexels_stock_profile_is_free_needs_only_its_key_and_covers_every_scene(tmp_path, monkeypatch):
    from office.video_selection import select_profile, clip_renderer_for_job, profile_summary
    monkeypatch.delenv('PEXELS_API_KEY', raising=False)
    monkeypatch.setenv('RUNWAYML_API_SECRET', 'runway-secret')
    store = Store(tmp_path)
    before = store.budget()
    summary = select_profile(store, 'pexels-stock', actor='test-operator')
    assert summary['paid'] is False and summary['job_cap_krw'] == 0 and summary['configured'] is False
    assert summary['pexels_configured'] is False and summary['runway_configured'] is True
    assert 'PEXELS_API_KEY' in summary['key_source'] and summary['license_url'] == 'https://www.pexels.com/license/'
    assert store.budget() == before
    monkeypatch.setenv('PEXELS_API_KEY', 'pexels-key')
    assert profile_summary(store)['configured'] is True
    job = fixture(store, generated=False)
    store.review_source(job['id'], job['source_hash'], 'approved', 'op', {'cards': True})
    assert clip_renderer_for_job(store, store.job(job['id'])) is None
    store.review_source(job['id'], job['source_hash'], 'approved', 'op', {'video': True})
    renderer = clip_renderer_for_job(store, store.job(job['id']))
    # Unlike Runway, stock footage needs neither a clip: generated marker nor a generated background.
    assert renderer.needs_background is False and renderer.generated_scenes == [0, 1]
    assert renderer.cache_key.startswith('pexels-stock:') and 'pexels-key' not in renderer.cache_key


def test_grok_lite_profile_limits_and_estimate_are_visible_before_any_call(tmp_path, monkeypatch):
    from office.video_selection import PROFILES, clip_renderer_for_job, paid_clip_estimate, profile_summary, select_profile, set_clip_limits
    monkeypatch.setenv('RUNWAYML_API_SECRET', 'secret')
    assert list(PROFILES)[:3] == ['none', 'pexels-stock', 'runway-grok-lite']
    store = Store(tmp_path)
    assert profile_summary(store)['id'] == 'none'
    summary = select_profile(store, 'runway-grok-lite', actor='test-operator')
    assert summary['model'] == 'grok_imagine_1_5_lite' and summary['paid'] is True
    assert summary['clip_limits']['max_clips_per_video'] == 12 and summary['clip_limits']['daily_paid_clips'] == 15
    assert summary['paid_clips_today'] == 0 and summary['credits_per_clip'] == 16 and summary['reservation_krw_per_clip'] == 320
    job = fixture(store)
    store.review_source(job['id'], job['source_hash'], 'approved', 'op', {'video': True})
    current = store.job(job['id'])
    estimate = paid_clip_estimate(store, current)
    # Both scenes get a clip sized to its voice; voice length is unknown before production, so the notice is an upper
    # bound: 2 clips x 15s max x 3 credits + 2 start frames = 92 credits.
    assert estimate == {**estimate, 'paid': True, 'clips': 2, 'credits': 92, 'reservation_krw': 1840}
    assert estimate['label'] == '유료: 영상 클립 2개(장면 길이에 맞춤) · 최대 92크레딧($0.92, 예약 최대 1,840원)'
    assert clip_renderer_for_job(store, current).clip_provider.config['model'] == 'grok_imagine_1_5_lite'
    with pytest.raises(WorkflowError):
        set_clip_limits(store, max_clips_per_video=13, daily_paid_clips=3, actor='op')
    limits = set_clip_limits(store, max_clips_per_video=2, daily_paid_clips=5, actor='op')
    assert limits['max_clips_per_video'] == 2 and limits['daily_paid_clips'] == 5
    select_profile(store, 'none', actor='op')
    assert paid_clip_estimate(store, current)['paid'] is False


class OrgResponse:
    def __init__(self, status, body):
        self.status_code, self._body = status, body

    def json(self):
        return self._body


class OrgSession:
    def __init__(self, responses):
        self.responses, self.calls = list(responses), []

    def get(self, url, **kwargs):
        self.calls.append({'url': url, **kwargs})
        item = self.responses.pop(0)
        if isinstance(item, Exception):
            raise item
        return item


def test_runway_options_need_secret_and_a_positive_balance_cached_for_five_minutes(tmp_path, monkeypatch):
    import requests
    from office import video_provider
    from office.video_selection import availability
    store = Store(tmp_path)
    monkeypatch.delenv('RUNWAYML_API_SECRET', raising=False)
    monkeypatch.delenv('PEXELS_API_KEY', raising=False)
    result = availability(store)
    assert result['none'] == {'available': True, 'reason': ''}
    assert not result['runway-grok-lite']['available'] and 'RUNWAYML_API_SECRET' in result['runway-grok-lite']['reason']
    assert not result['pexels-stock']['available']
    monkeypatch.setenv('RUNWAYML_API_SECRET', 'secret')
    store.set_setting('image_profile', {'id': 'openai-gpt-image'})
    session = OrgSession([OrgResponse(200, {'creditBalance': 0}), OrgResponse(200, {'creditBalance': 40}), requests.ConnectionError('offline')])
    assert video_provider.runway_credit_balance(store, session=session) == 0
    assert video_provider.runway_credit_balance(store, session=session) == 0 and len(session.calls) == 1  # cached
    assert session.calls[0]['url'] == 'https://api.dev.runwayml.com/v1/organization'
    assert session.calls[0]['headers']['Authorization'] == 'Bearer secret'
    assert '잔액이 0' in availability(store)['runway-gen4.5']['reason']
    assert video_provider.runway_credit_balance(store, session=session, force=True) == 40
    assert availability(store)['runway-grok-lite'] == {'available': True, 'reason': ''}
    store.set_setting('image_profile', {'id': 'none'})
    assert '배경 이미지' in availability(store)['runway-grok-lite']['reason']
    store.set_setting('image_profile', {'id': 'openai-gpt-image'})
    assert video_provider.runway_credit_balance(store, session=session, force=True) is None
    assert '확인하지 못했습니다' in availability(store)['runway-grok-lite']['reason']
    # Polling screens must not write business records: the deploy compares them and refuses when they change.
    assert store.setting('runway_credit_cache') is None
