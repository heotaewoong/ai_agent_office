import pytest

from office.store import Store, WorkflowError


def fixture(store):
    job = store.create_job({'id': 'synthetic-profile', 'title': '음성 선택 시험'})
    packet = {'title': '합성 자료', 'body': '프로필 기능 시험입니다.', 'quality': {'status': 'passed', 'critical': []},
              'video': {'scenes': [{'narration': text, 'caption': text} for text in ['근거를 확인합니다.', '원고를 승인합니다.', '선택한 결과를 제작합니다.']]}}
    return store.save_source(job['id'], packet)


def test_local_profile_is_default_and_profile_selection_never_resets_budget(tmp_path):
    from office.voice_selection import select_profile, renderer_for_job, profile_summary
    store = Store(tmp_path)
    job = fixture(store)
    assert renderer_for_job(store, job) is None
    before = store.budget()
    select_profile(store, 'gemini-kore', actor='test-operator')
    assert store.budget() == before
    assert profile_summary(store)['id'] == 'gemini-kore'
    assert profile_summary(store)['automatic_fallback'] is False


def test_gemini_factory_requires_source_approval_and_binds_its_full_profile(tmp_path):
    from office.voice_selection import select_profile, renderer_for_job
    from office.media import production_contract
    store = Store(tmp_path)
    job = fixture(store)
    select_profile(store, 'gemini-kore', actor='test-operator')
    renderer = renderer_for_job(store, job)
    with pytest.raises(WorkflowError, match='승인'):
        renderer(job['source_packet']['video']['scenes'][0]['narration'], store.root / 'must-not-exist.wav')
    assert not (store.root / 'must-not-exist.wav').exists()
    store.review_source(job['id'], job['source_hash'], 'approved', 'fixture-operator', {'video': True})
    job = store.job(job['id'])
    renderer = renderer_for_job(store, job)
    assert renderer.speech_provider.config['mode'] == 'approved_production'
    assert renderer.speech_provider.config['request_limits']['tts'] == 3
    assert production_contract(renderer, job['selections'])['hash'] != production_contract(None, job['selections'])['hash']
    assert store.budget()['spent_krw'] == store.budget()['reserved_krw'] == 0


def test_unknown_profile_is_rejected_and_blog_only_never_constructs_paid_voice(tmp_path):
    from office.voice_selection import select_profile, renderer_for_job
    store = Store(tmp_path)
    job = fixture(store)
    with pytest.raises(WorkflowError, match='프로필'):
        select_profile(store, 'unregistered-provider', actor='test-operator')
    select_profile(store, 'gemini-kore', actor='test-operator')
    store.review_source(job['id'], job['source_hash'], 'approved', 'fixture-operator', {'blog': True, 'video': False})
    assert renderer_for_job(store, store.job(job['id'])) is None



def test_voice_availability_follows_platform_and_keys(monkeypatch):
    from office import voice_selection
    monkeypatch.delenv('GEMINI_API_KEY', raising=False)
    monkeypatch.setenv('OPENAI_API_KEY', 'k')
    monkeypatch.setattr(voice_selection.os, 'name', 'posix')
    result = voice_selection.availability()
    assert result['windows-heami']['available'] is False and 'Windows' in result['windows-heami']['reason']
    assert result['gemini-kore']['available'] is False and result['openai-tts'] == {'available': True, 'reason': ''}
