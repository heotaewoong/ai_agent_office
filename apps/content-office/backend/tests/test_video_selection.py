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
    assert set(PROFILES) == {'none', 'runway-gen4-turbo', 'runway-gen4.5'}
    assert profile_summary(store)['id'] == 'none' and profile_summary(store)['configured'] is False
    assert clip_renderer_for_job(store, job) is None
    before = store.budget()
    summary = select_profile(store, 'runway-gen4-turbo', actor='test-operator')
    assert summary['paid'] is True and summary['job_cap_krw'] == 3000 and summary['model'] == 'gen4_turbo'
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
    assert clip_renderer_for_job(store2, store2.job(plain['id'])) is None
