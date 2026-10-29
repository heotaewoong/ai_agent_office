import pytest

from office.store import Store, WorkflowError


def fixture(store):
    job = store.create_job({'id': 'image-profile', 'title': '배경 이미지 선택 시험'})
    packet = {'title': '합성 자료', 'body': '프로필 기능 시험입니다.', 'quality': {'status': 'passed', 'critical': []},
              'video': {'scenes': [{'narration': text, 'caption': text} for text in ['근거를 확인합니다.', '원고를 승인합니다.', '선택한 결과를 제작합니다.']]}}
    return store.save_source(job['id'], packet)


def test_none_profile_is_default_and_selection_never_touches_budget_or_assets(tmp_path):
    from office.image_selection import select_profile, background_renderer_for_job, profile_summary
    store = Store(tmp_path)
    job = fixture(store)
    summary = profile_summary(store)
    assert summary['id'] == 'none' and summary['paid'] is False and summary['automatic_fallback'] is False
    assert background_renderer_for_job(store, job) is None
    before = store.budget()
    select_profile(store, 'openai-gpt-image', actor='test-operator')
    assert store.budget() == before
    assert profile_summary(store)['id'] == 'openai-gpt-image'
    assert profile_summary(store)['paid'] is True and profile_summary(store)['job_cap_krw'] == 2000
    assert not (store.root / 'image-assets').exists()


def test_unknown_profile_and_blank_actor_are_rejected(tmp_path):
    from office.image_selection import select_profile
    store = Store(tmp_path)
    with pytest.raises(WorkflowError, match='프로필'):
        select_profile(store, 'midjourney', actor='test-operator')
    with pytest.raises(WorkflowError, match='프로필|운영자'):
        select_profile(store, 'openai-gpt-image', actor='  ')


def test_openai_factory_requires_approval_and_visual_selection(tmp_path, monkeypatch):
    from office.image_selection import select_profile, background_renderer_for_job
    monkeypatch.setenv('OPENAI_API_KEY', 'test-placeholder')
    store = Store(tmp_path)
    job = fixture(store)
    select_profile(store, 'openai-gpt-image', actor='test-operator')
    with pytest.raises(WorkflowError, match='승인'):
        background_renderer_for_job(store, job)
    store.review_source(job['id'], job['source_hash'], 'approved', 'fixture-operator', {'blog': True})
    assert background_renderer_for_job(store, store.job(job['id'])) is None
    store.review_source(job['id'], job['source_hash'], 'approved', 'fixture-operator', {'cards': True})
    renderer = background_renderer_for_job(store, store.job(job['id']))
    assert renderer.image_provider.config['model'].startswith('gpt-image-2.5')
    assert store.budget()['spent_krw'] == store.budget()['reserved_krw'] == 0


def test_codex_profile_is_free_capped_and_reports_login_not_api_key(tmp_path, monkeypatch):
    from office.codex_image_provider import CodexImageProvider, DAILY_CAP
    from office.image_selection import select_profile, background_renderer_for_job, profile_summary
    monkeypatch.setenv('OPENAI_API_KEY', 'test-placeholder')
    monkeypatch.setenv('CODEX_HOME', str(tmp_path / 'no-codex-login'))
    store = Store(tmp_path)
    job = fixture(store)
    summary = select_profile(store, 'codex-subscription', actor='test-operator')
    assert summary['paid'] is False and summary['job_cap_krw'] == 0 and summary['automatic_fallback'] is False
    assert summary['configured'] is False and summary['openai_configured'] is True
    assert summary['daily_cap_images'] == DAILY_CAP and summary['used_today'] == 0 and 'API 키 사용 안 함' in summary['key_source']
    store.review_source(job['id'], job['source_hash'], 'approved', 'fixture-operator', {'video': True})
    renderer = background_renderer_for_job(store, store.job(job['id']))
    assert isinstance(renderer.image_provider, CodexImageProvider) and renderer.image_provider.config['reservation_krw'] == 0
    assert store.budget()['spent_krw'] == store.budget()['reserved_krw'] == 0
    assert profile_summary(store)['id'] == 'codex-subscription'


def test_summary_reports_key_presence_without_exposing_it(tmp_path, monkeypatch):
    from office.image_selection import profile_summary
    store = Store(tmp_path)
    monkeypatch.delenv('OPENAI_API_KEY', raising=False)
    assert profile_summary(store)['configured'] is False
    monkeypatch.setenv('OPENAI_API_KEY', 'sk-secret-value')
    summary = profile_summary(store)
    assert summary['configured'] is True
    assert 'sk-secret-value' not in repr(summary)
