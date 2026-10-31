import hashlib
from pathlib import Path

import pytest
from PIL import Image

from office.store import Store, WorkflowError, digest
from office.thumbnail_studio import add_candidate, candidate_path, choose, context, generate, snapshot, production_candidates


@pytest.fixture
def fixture(tmp_path):
    store = Store(tmp_path / 'state')
    job = store.create_job({'id': 'thumbnail-test', 'title': '합성 시험'})
    packet = {'title': '합성 시험', 'body': '편입 시험 한 달 전 성적을 돌아봤습니다. 매일 아침 러닝과 복습을 했습니다.',
              'quality': {'status': 'passed', 'critical': []}, 'synthetic_fixture': True,
              'video': {'scenes': [{'narration': '합성 시험', 'caption': '합성 시험'}]}}
    job = store.save_source(job['id'], packet)
    return store, job


class FakeProvider:
    calls = []

    def __init__(self, store, *, job_id, edit_reference=None):
        self.reference = edit_reference

    def render(self, prompt, output):
        self.calls.append({'reference': self.reference, 'prompt': prompt})
        Image.new('RGB', (1536, 1024), ('#506040' if self.reference else ['#395166', '#683b39', '#2d5c3d'][len(self.calls) % 3])).save(output)
        return {'provider': 'synthetic-test', 'model': 'not-an-api'}


def make(fixture):
    store, job = fixture
    FakeProvider.calls = []
    return generate(store, job['id'], job['source_hash'], provider_factory=FakeProvider)


def test_three_unique_images_and_no_duplicate_call(fixture):
    store, job = fixture
    state = make(fixture)
    assert len(state['candidates']) == 3
    assert len({c['image']['sha256'] for c in state['candidates']}) == 3
    assert len({c['image']['name'] for c in state['candidates']}) == 3
    generate(store, job['id'], job['source_hash'], provider_factory=FakeProvider)
    assert len(FakeProvider.calls) == 3
    assert store.job(job['id'])['source_approval'] is None
    assert store.job(job['id'])['release_approval'] is None
    for c in state['candidates']:
        with Image.open(candidate_path(store, state, c)) as image:
            assert image.size == (1280, 720)


def test_select_reference_edit_keep_original_and_manual_final(fixture):
    store, job = fixture
    state = make(fixture)
    original = state['candidates'][0]
    state = choose(store, job['id'], original['id'], state['revision'])
    state = generate(store, job['id'], job['source_hash'], edit_id=original['id'], instruction='배경 빛만 밝게', provider_factory=FakeProvider)
    assert len(state['candidates']) == 4
    assert FakeProvider.calls[-1]['reference'] == candidate_path(store, state, original, 'artwork')
    assert state.get('finalized_id') is None
    revised = state['candidates'][-1]
    assert revised['parent_id'] == original['id']
    assert hashlib.sha256(candidate_path(store, state, original).read_bytes()).hexdigest() == original['image']['sha256']
    with pytest.raises(WorkflowError, match='먼저'):
        choose(store, job['id'], revised['id'], state['revision'], finalize=True)
    state = choose(store, job['id'], revised['id'], state['revision'])
    state = choose(store, job['id'], revised['id'], state['revision'], finalize=True)
    assert state['finalized_id'] == revised['id']
    assert store.job(job['id'])['source_approval'] is None


def test_stale_revision_source_and_tamper_rejected(fixture):
    store, job = fixture
    state = make(fixture)
    c = state['candidates'][0]
    state2 = choose(store, job['id'], c['id'], state['revision'])
    with pytest.raises(WorkflowError, match='판본'):
        choose(store, job['id'], c['id'], state['revision'])
    candidate_path(store, state2, c, 'artwork').write_bytes(b'changed')
    calls = len(FakeProvider.calls)
    with pytest.raises(WorkflowError):
        generate(store, job['id'], job['source_hash'], edit_id=c['id'], instruction='밝게', provider_factory=FakeProvider)
    assert len(FakeProvider.calls) == calls
    store.save_source(job['id'], {**job['source_packet'], 'body': '바뀐 원고'})
    assert snapshot(store, job['id'])['stale'] is True
    with pytest.raises(WorkflowError):
        choose(store, job['id'], c['id'], state2['revision'])


def test_finalize_updates_only_manifest_after_operator_choice(fixture):
    store, job = fixture
    state = make(fixture)
    c = state['candidates'][0]
    manifest = {'source_hash': job['source_hash'], 'hash': 'old', 'files': [], 'completed_outputs': ['video']}
    store.update_job(job['id'], manifest=manifest, release_approval={'decision': 'approved'})
    state = choose(store, job['id'], c['id'], state['revision'])
    choose(store, job['id'], c['id'], state['revision'], finalize=True)
    updated = store.job(job['id'])
    assert updated['release_approval'] is None
    assert updated['manifest']['selected_thumbnail_id'] == c['image']['id']
    assert len(updated['manifest']['thumbnail_candidates']) == 3
    assert updated['manifest']['hash'] != 'old'


def test_production_requires_approval_and_reuses_three(fixture, tmp_path):
    store, job = fixture
    make(fixture)
    with pytest.raises(WorkflowError):
        production_candidates(store, job['id'], tmp_path, provider_factory=FakeProvider)
    store.review_source(job['id'], job['source_hash'], 'approved', 'synthetic-test', {'video': True})
    paths = production_candidates(store, job['id'], tmp_path, provider_factory=FakeProvider)
    assert len(paths) == 3 and len(FakeProvider.calls) == 3
    assert all(p.exists() for p in paths)


def test_selected_reference_request_uses_official_edit_endpoint(fixture, monkeypatch):
    from office.thumbnail_studio import ThumbnailProvider
    store, job = fixture
    state = make(fixture)
    ref = candidate_path(store, state, state['candidates'][0], 'artwork')
    calls = []
    def transport(url, **kwargs):
        calls.append((url, kwargs['files']['image'][1].read(), kwargs.get('json')))
        return 'synthetic'
    monkeypatch.setenv('OPENAI_API_KEY', 'synthetic-key')
    provider = ThumbnailProvider(store, job_id=job['id'], edit_reference=ref, transport=transport)
    assert provider._request({'model': 'synthetic', 'prompt': '빛만 수정'}) == 'synthetic'
    assert calls == [('https://api.openai.com/v1/images/edits', ref.read_bytes(), None)]


def test_api_window_csrf_version_and_manual_choice(fixture):
    from fastapi.testclient import TestClient
    from office.api import create_app
    store, job = fixture
    state = make(fixture)
    client = TestClient(create_app(store), base_url='http://localhost:8510')
    token = client.get('/api/session').json()['csrf']
    headers = {'Origin': 'http://localhost:3110', 'X-Office-CSRF': token}
    url = f"/api/jobs/{job['id']}/thumbnail-studio"
    state = client.get(url).json()
    payload = {'source_hash': job['source_hash'], 'revision': state['revision'], 'confirm_paid': True}
    store.set_setting('work_window', {'status': 'closed'})
    assert client.post(url+'/generate', headers=headers, json=payload).status_code == 409
    assert store.tasks(job['id']) == []
    choice = {'candidate_id': state['candidates'][0]['id'], 'revision': state['revision'], 'finalize': False}
    assert client.post(url+'/choose', json=choice).status_code == 403
    response = client.post(url+'/choose', headers=headers, json=choice)
    assert response.status_code == 200
    assert client.get(state['candidates'][0]['url']).status_code == 200
    store.set_setting('work_window', {'status': 'open'})
    payload['revision'] = response.json()['revision']
    payload['confirm_paid'] = False
    assert client.post(url+'/generate', headers=headers, json=payload).status_code == 409
    assert store.tasks(job['id']) == []
    payload['confirm_paid'] = True
    first = client.post(url+'/generate', headers=headers, json=payload)
    second = client.post(url+'/generate', headers=headers, json=payload)
    assert first.status_code == 202 and second.json()['id'] == first.json()['id']
    assert store.job(job['id'])['source_approval'] is None


def test_no_paid_generation_after_window_closed(fixture):
    from office.thumbnail_studio import ThumbnailProvider
    store, job = fixture
    store.set_setting('work_window', {'status': 'closed'})
    provider = ThumbnailProvider(store, job_id=job['id'], transport=lambda *a, **k: pytest.fail('must not call'))
    with pytest.raises(WorkflowError, match='작업 시간'):
        provider.authorize()


def test_studio_candidates_attach_without_fabricating_final_selection(fixture):
    from office.thumbnail_studio import attach_to_manifest
    store, job = fixture
    state = make(fixture)
    manifest = {'source_hash':job['source_hash'], 'files':[], 'completed_outputs':['video']}
    result = attach_to_manifest(store, job['id'], manifest)
    assert len(result['thumbnail_candidates']) == 3
    assert result['selected_thumbnail_id'] is None
    assert len({r['name'] for r in result['files']}) == 3


def test_portrait_format_is_bound_to_final_choice(fixture):
    from office.thumbnail_studio import attach_to_manifest
    store, job = fixture
    state = make(fixture)
    c = state['candidates'][0]
    with Image.open(candidate_path(store, state, c, 'portrait')) as image:
        assert image.size == (1080, 1920)
    state = choose(store, job['id'], c['id'], state['revision'])
    with pytest.raises(WorkflowError, match='먼저'):
        choose(store, job['id'], c['id'], state['revision'], finalize=True, format='shorts')
    state = choose(store, job['id'], c['id'], state['revision'], format='shorts')
    state = choose(store, job['id'], c['id'], state['revision'], finalize=True, format='shorts')
    manifest = attach_to_manifest(store, job['id'], {'source_hash':job['source_hash'], 'files':[], 'completed_outputs':['video']})
    assert state['finalized_format'] == 'shorts'
    assert manifest['selected_thumbnail_id'] == c['portrait']['id']
    assert all('-shorts.png' in r['name'] for r in manifest['thumbnail_candidates'])
    assert store.job(job['id'])['source_approval'] is None


def test_both_sizes_served_and_invalid_format_rejected(fixture):
    import io
    from fastapi.testclient import TestClient
    from office.api import create_app
    store, job = fixture
    state = make(fixture)
    c = state['candidates'][0]
    client = TestClient(create_app(store), base_url='http://localhost:8510')
    for url, size in [(c['url'], (1280,720)),(c['portrait_url'], (1080,1920))]:
        response=client.get(url)
        assert response.status_code == 200
        with Image.open(io.BytesIO(response.content)) as image:
            assert image.size == size
    assert client.get(c['url']+'?format=invalid').status_code == 422
