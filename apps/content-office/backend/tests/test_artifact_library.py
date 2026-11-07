import hashlib
import json
import os

import pytest
from fastapi.testclient import TestClient
from office.api import create_app
from office.store import Store


@pytest.fixture
def ctx(tmp_path):
    store = Store(tmp_path)
    job = store.create_job({'id': 'library-news', 'title': '보존할 원고', 'url': 'https://example.com/news'})
    folder = store.artifacts / job['id'] / 'old'
    folder.mkdir(parents=True)
    video = folder / 'short.mp4'
    video.write_bytes(b'old generated video')
    for n in (1, 2):
        (folder / f'card-{n:02}.png').write_bytes(f'card {n}'.encode())
    (folder / 'thumbnail-01.png').write_bytes(b'thumbnail')
    original = store.artifacts / 'originals' / 'original.mp4'
    original.parent.mkdir()
    original.write_bytes(b'user original')
    client = TestClient(create_app(store), base_url='http://localhost:8510')
    headers = {'Origin': 'http://localhost:3110', 'X-Office-CSRF': client.get('/api/session').json()['csrf']}
    return store, job, video, original, client, headers


def listing(ctx):
    response = ctx[4].get('/api/library')
    assert response.status_code == 200
    return response.json()['items']


def item(ctx, kind):
    return next(x for x in listing(ctx) if x['kind'] == kind)


def quote(ctx, ids, action):
    response = ctx[4].post('/api/library/quote', json={'ids': ids, 'action': action}, headers=ctx[5])
    assert response.status_code == 200, response.text
    return response.json()


def mutate(ctx, ids, action, request_id):
    q = quote(ctx, ids, action)
    return ctx[4].post('/api/library/change', json={'ids': ids, 'action': action, 'quote': q['token'], 'request_id': request_id}, headers=ctx[5])


def test_real_file_groups_exclude_originals_and_get_is_readonly(ctx):
    before = ctx[0].job(ctx[1]['id'])
    rows = listing(ctx)
    assert sorted(x['kind'] for x in rows) == ['cards', 'thumbnail', 'video']
    assert item(ctx, 'cards')['file_count'] == 2
    assert ctx[0].job(ctx[1]['id']) == before
    assert ctx[0].setting('artifact_library', None) is None
    assert ctx[3].read_bytes() == b'user original'


def test_trash_restore_then_purge_preserves_source_approvals_and_request_receipt(ctx):
    store, job, video, original, client, headers = ctx
    before = store.job(job['id'])
    ids = [item(ctx, 'video')['id'], item(ctx, 'cards')['id']]
    assert mutate(ctx, ids, 'trash', 'trash-one').status_code == 200
    assert video.exists() and original.exists()
    assert all(x['state'] == 'trash' for x in listing(ctx) if x['id'] in ids)
    assert mutate(ctx, ids, 'restore', 'restore-one').status_code == 200
    assert all(x['state'] == 'available' for x in listing(ctx) if x['id'] in ids)
    assert mutate(ctx, ids, 'trash', 'trash-two').status_code == 200
    q = quote(ctx, ids, 'purge')
    body = {'ids': ids, 'action': 'purge', 'quote': q['token'], 'request_id': 'purge-one'}
    result = client.post('/api/library/change', json=body, headers=headers)
    assert result.status_code == 200 and result.json()['state'] == 'completed'
    assert not video.exists() and original.exists()
    assert store.job(job['id']) == before and store.tasks() == []
    assert client.post('/api/library/change', json=body, headers=headers).json() == result.json()
    assert not any(x['id'] in ids for x in listing(ctx))


def test_current_manifest_file_and_busy_job_are_protected(ctx):
    store, job, video, _, client, headers = ctx
    record = {'id': 'asset_current', 'path': video.relative_to(store.artifacts).as_posix(), 'sha256': hashlib.sha256(video.read_bytes()).hexdigest(), 'name': video.name}
    store.update_job(job['id'], manifest={'hash': 'approved', 'files': [record]}, release_approval={'decision': 'approved', 'version': 'approved'})
    row = item(ctx, 'video')
    assert row['protected_reason']
    assert client.post('/api/library/quote', json={'ids': [row['id']], 'action': 'trash'}, headers=headers).status_code == 409
    store.enqueue('produce', {'job_id': job['id']}, key='busy-library')
    row = item(ctx, 'cards')
    assert row['protected_reason'] and video.exists()


def test_shared_inode_counts_reclaimable_bytes_once(ctx):
    store, _, video, _, client, headers = ctx
    second = store.artifacts / 'another'
    second.mkdir()
    try:
        os.link(video, second / 'short.mp4')
    except OSError:
        pytest.skip('filesystem has no hard links')
    ids = [x['id'] for x in listing(ctx) if x['kind'] == 'video']
    assert mutate(ctx, ids, 'trash', 'shared-trash').status_code == 200
    assert quote(ctx, ids[:1], 'purge')['reclaimable_bytes'] == 0
    assert quote(ctx, ids, 'purge')['reclaimable_bytes'] > 0
    assert mutate(ctx, ids[:1], 'purge', 'shared-purge-one').status_code == 200
    assert len([x for x in listing(ctx) if x['kind'] == 'video']) == 1


def test_stale_quote_csrf_and_direct_purge_are_rejected(ctx):
    row = item(ctx, 'video'); ids = [row['id']]
    client = ctx[4]
    assert client.post('/api/library/quote', json={'ids': ids, 'action': 'trash'}).status_code == 403
    assert client.post('/api/library/quote', json={'ids': ids, 'action': 'purge'}, headers=ctx[5]).status_code == 409
    q = quote(ctx, ids, 'trash')
    ctx[2].write_bytes(b'other operator changed file')
    response = client.post('/api/library/change', json={'ids': ids, 'action': 'trash', 'quote': q['token'], 'request_id': 'stale'}, headers=ctx[5])
    assert response.status_code == 409 and ctx[2].exists()


def test_symlink_not_listed_or_deleted(ctx):
    link = ctx[0].artifacts / 'unsafe'
    try:
        link.symlink_to(ctx[3].parent, target_is_directory=True)
    except OSError:
        pytest.skip('symlink requires privilege')
    assert len(listing(ctx)) == 3
    assert ctx[3].exists()


def test_changed_card_membership_after_trash_blocks_purge(ctx):
    ids = [item(ctx, 'cards')['id']]
    assert mutate(ctx, ids, 'trash', 'cards-trash').status_code == 200
    (ctx[2].parent / 'card-03.png').write_bytes(b'new file')
    response = ctx[4].post('/api/library/quote', json={'ids': ids, 'action': 'purge'}, headers=ctx[5])
    assert response.status_code == 409
    assert (ctx[2].parent / 'card-03.png').exists()


def test_non_job_task_does_not_lock_unrelated_artifacts(ctx):
    folder = ctx[0].artifacts / 'standalone'
    folder.mkdir()
    (folder / 'short.mp4').write_bytes(b'standalone')
    ctx[0].enqueue('refresh', {}, key='non-job')
    rows = [x for x in listing(ctx) if x['job_id'] is None]
    assert rows and not rows[0]['protected_reason']


def test_new_generated_file_at_purged_path_is_visible_and_available(ctx):
    ids = [item(ctx, 'video')['id']]
    assert mutate(ctx, ids, 'trash', 'old-trash').status_code == 200
    assert mutate(ctx, ids, 'purge', 'old-purge').status_code == 200
    ctx[2].write_bytes(b'fresh generated video, new generation')
    assert item(ctx, 'video')['state'] == 'available'
    from office.artifact_library import require_available
    require_available(ctx[0], ctx[2].relative_to(ctx[0].artifacts).as_posix())


def test_purge_failure_records_partial_without_claiming_restore(ctx, monkeypatch):
    from office import artifact_library as library
    ids = [item(ctx, 'cards')['id']]
    assert mutate(ctx, ids, 'trash', 'partial-trash').status_code == 200
    real = library._unlink
    def fail_second(store, file):
        if file['path'].endswith('02.png'):
            raise OSError('synthetic disk failure')
        return real(store, file)
    monkeypatch.setattr(library, '_unlink', fail_second)
    result = mutate(ctx, ids, 'purge', 'partial-purge')
    assert result.status_code == 200 and result.json()['state'] == 'partial'
    assert item(ctx, 'cards')['state'] == 'attention'
    assert ctx[3].exists()


def test_quote_expires_without_modifying_files(ctx, monkeypatch):
    from office import artifact_library as library
    import time
    ids = [item(ctx, 'video')['id']]
    q = quote(ctx, ids, 'trash')
    later = time.time() + 400
    monkeypatch.setattr(library.time, 'time', lambda: later)
    response = ctx[4].post('/api/library/change', json={'ids': ids, 'action': 'trash', 'quote': q['token'], 'request_id': 'expired'}, headers=ctx[5])
    assert response.status_code == 409
    assert ctx[2].exists()


def test_reference_pdf_is_never_offered_for_deletion(ctx):
    (ctx[2].parent / 'reference.pdf').write_bytes(b'user supplied source')
    assert not any(x['name'] == 'reference.pdf' for x in listing(ctx))


def test_editorial_source_media_is_never_offered_for_deletion(ctx):
    folder = ctx[2].parent / 'editorial' / 'source-hash'
    folder.mkdir(parents=True)
    (folder / 'short.mp4').write_bytes(b'owner supplied input')
    assert len([x for x in listing(ctx) if x['kind'] == 'video']) == 1


def test_replaced_trash_file_requires_attention_not_a_new_purge_quote(ctx):
    ids = [item(ctx, 'video')['id']]
    assert mutate(ctx, ids, 'trash', 'replace-trash').status_code == 200
    ctx[2].write_bytes(b'replaced original at same filename')
    assert item(ctx, 'video')['state'] == 'attention'
    assert ctx[4].post('/api/library/quote', json={'ids': ids, 'action': 'purge'}, headers=ctx[5]).status_code == 409


def test_batch_validation_and_current_reference_race_are_atomic(ctx):
    ids = [item(ctx, 'video')['id'], 'not-an-asset']
    assert ctx[4].post('/api/library/quote', json={'ids': ids, 'action': 'trash'}, headers=ctx[5]).status_code == 409
    ids = [item(ctx, 'video')['id']]
    q = quote(ctx, ids, 'trash')
    ctx[0].update_job(ctx[1]['id'], manifest={'files': [{'path': ctx[2].relative_to(ctx[0].artifacts).as_posix()}]})
    response = ctx[4].post('/api/library/change', json={'ids': ids, 'action': 'trash', 'quote': q['token'], 'request_id': 'race'}, headers=ctx[5])
    assert response.status_code == 409
    assert ctx[0].setting('artifact_library', None) is None
    assert ctx[2].exists()


def test_missing_trash_file_cannot_restore_and_tampered_quote_cannot_write(ctx):
    ids = [item(ctx, 'video')['id']]
    q = quote(ctx, ids, 'trash')
    response = ctx[4].post('/api/library/change', json={'ids': ids, 'action': 'trash', 'quote': q['token'][:-1] + ('a' if q['token'][-1] != 'a' else 'b'), 'request_id': 'tamper'}, headers=ctx[5])
    assert response.status_code == 409
    assert mutate(ctx, ids, 'trash', 'missing-trash').status_code == 200
    ctx[2].unlink()
    assert item(ctx, 'video')['state'] == 'attention'
    assert ctx[4].post('/api/library/quote', json={'ids': ids, 'action': 'restore'}, headers=ctx[5]).status_code == 409
