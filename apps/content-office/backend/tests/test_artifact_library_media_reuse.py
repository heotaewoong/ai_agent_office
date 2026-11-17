import copy

import pytest

from office import media
from office.social_production import card_paths
from office.store import WorkflowError, digest
from test_artifact_library_consumers import put_in_trash
from test_artifact_library_image_consumers import artwork, blog_cards
from test_youtube_delivery import released_fixture


def approval_history(store):
    with store.connection() as db:
        return [dict(row) for row in db.execute('SELECT * FROM approvals ORDER BY id')]


def forbidden_renderer(*args, **kwargs):
    pytest.fail('A trashed cached output must not trigger rendering or a provider')


def cached_contract(monkeypatch, contract):
    monkeypatch.setattr(media, 'production_contract', lambda *args, **kwargs: contract)
    monkeypatch.setattr(media, 'render_short', forbidden_renderer)
    monkeypatch.setattr(media, 'write_video_exports', forbidden_renderer)
    monkeypatch.setattr(media, 'write_blog_exports', forbidden_renderer)
    monkeypatch.setattr('office.cards.plan_cards', forbidden_renderer)


def produce_without_external_components(store, job_id):
    return media.produce(store, job_id, voice_renderer=forbidden_renderer,
                         background_renderer=forbidden_renderer, clip_renderer=forbidden_renderer)


@pytest.mark.parametrize('kind,name', [('video', 'short.mp4'), ('blog', 'blog.md')])
def test_cached_output_excludes_trash_and_records_failure_without_rerender(tmp_path, monkeypatch, kind, name):
    store, job_id = released_fixture(tmp_path)
    manifest = copy.deepcopy(store.job(job_id)['manifest'])
    manifest['thumbnail_candidates'] = []
    contract = {'hash': 'cached-contract', 'font_status': 'ready'}
    manifest['production_contract'] = contract
    store.update_job(job_id, manifest=manifest)
    record = next(record for record in manifest['files'] if record['name'] == name)
    path = store.artifacts / record['path']
    original = path.read_bytes()
    put_in_trash(store, record)
    approvals = approval_history(store)
    cached_contract(monkeypatch, contract)

    result = produce_without_external_components(store, job_id)

    assert result['output_status'][kind]['state'] == 'failed'
    assert '휴지통' in result['output_status'][kind]['error']
    assert kind not in result['completed_outputs']
    assert all(file['path'] != record['path'] for file in result['files'])
    assert not any(event['kind'] == 'output_reused' and event['data']['output'] == kind
                   for event in store.events(job_id))
    assert any(event['kind'] == 'output_failed' and event['data']['output'] == kind
               for event in store.events(job_id))
    assert path.read_bytes() == original
    assert approval_history(store) == approvals


def test_cached_cards_fail_without_reusing_trash_or_replanning(blog_cards, monkeypatch):
    store, job, folder = blog_cards
    store.review_source(job['id'], job['source_hash'], 'approved', 'synthetic', {'cards': True})
    store.update_job(job['id'], thumbnail_studio={})
    paths = card_paths(store, job['id'], job['source_hash'], folder)
    contract = {'hash': 'cached-card-contract', 'font_status': 'ready'}
    manifest = {'source_hash': job['source_hash'], 'production_contract': contract,
                'output_status': {'cards': {'state': 'completed'}}, 'completed_outputs': ['cards'],
                'files': [{**media.artifact_record(store.artifacts, path), 'outputs': ['cards']} for path in paths],
                'thumbnail_candidates': []}
    manifest['hash'] = digest(manifest)
    store.update_job(job['id'], manifest=manifest)
    put_in_trash(store, job['cards']['slides'][0]['artifact'])
    before = store.job(job['id'])
    approvals = approval_history(store)
    cached_contract(monkeypatch, contract)

    with pytest.raises(WorkflowError, match='휴지통'):
        produce_without_external_components(store, job['id'])

    assert store.job(job['id']) == before
    assert approval_history(store) == approvals
    assert not any(event['kind'] == 'output_reused' for event in store.events(job['id']))
    assert any(event['kind'] == 'output_failed' and event['data']['output'] == 'cards'
               for event in store.events(job['id']))


def test_card_paths_refuse_trashed_current_cards_then_reuse_restored_files(blog_cards, monkeypatch):
    store, job, folder = blog_cards
    store.review_source(job['id'], job['source_hash'], 'approved', 'synthetic', {'cards': True})
    record = job['cards']['slides'][0]['artifact']
    original = (store.artifacts / record['path']).read_bytes()
    put_in_trash(store, record)
    before = store.job(job['id'])
    approvals = approval_history(store)
    monkeypatch.setattr('office.cards.plan_cards', forbidden_renderer)

    with pytest.raises(WorkflowError, match='휴지통'):
        card_paths(store, job['id'], job['source_hash'], folder)

    assert list(folder.iterdir()) == []
    assert store.job(job['id']) == before
    assert approval_history(store) == approvals
    assert (store.artifacts / record['path']).read_bytes() == original
    store.set_setting('artifact_library', {'entries': {}, 'receipts': {}})
    restored = card_paths(store, job['id'], job['source_hash'], folder)
    assert len(restored) == 7 and all(path.is_file() for path in restored)
    assert store.job(job['id']) == before
