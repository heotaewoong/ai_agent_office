import hashlib
from datetime import datetime, timedelta, timezone

import pytest

from office import owner_drafts
from office.store import WorkflowError
from test_youtube_delivery import enabled_fixture


def ready(tmp_path):
    store, jid = enabled_fixture(tmp_path, approve_release=False)
    from office.channels import update_channel
    update_channel(store, 'youtube_main_ko', {'external_account_id':'UCh9Oa74qc9mOvgmgMTXBFVw'}, actor='fixture')
    store.set_setting('work_window', {'status': 'open', 'authorized_end': (datetime.now(timezone.utc) + timedelta(minutes=10)).isoformat()})
    job = store.job(jid)
    policy = owner_drafts.policy(store, job, ['youtube_main_ko'], 'fixture')
    store.update_job(jid, owner_draft_policy=policy)
    return store, jid


def test_draft_requires_explicit_current_source_approval_but_never_creates_release(tmp_path):
    store, jid = ready(tmp_path)
    rows = owner_drafts.prepare(store, jid)
    assert len(rows) == 1 and rows[0]['state'] == 'pending'
    assert store.job(jid)['release_approval'] is None
    assert owner_drafts.prepare(store, jid) == rows
    store.update_job(jid, source_approval=None)
    with pytest.raises(WorkflowError, match='승인①'):
        owner_drafts.claim(store, rows[0]['id'], 'fixture')


def test_tistory_queue_accepts_real_blog_export_names(tmp_path):
    from office.channels import update_channel
    from office.exports import write_blog_exports
    from office.media import artifact_record
    store, jid = ready(tmp_path)
    update_channel(store, 'tistory_main', {'publication_enabled': True}, actor='fixture')
    job = store.job(jid)
    folder = store.artifacts / jid / 'actual-blog-export'
    folder.mkdir()
    paths = write_blog_exports(job['source_packet'], folder)
    manifest = {**job['manifest'], 'files': [{**artifact_record(store.artifacts, p), 'outputs': ['blog']} for p in paths]}
    store.update_job(jid, manifest=manifest, owner_draft_policy=owner_drafts.policy(store, job, ['tistory_main'], 'fixture'))
    row, = owner_drafts.prepare(store, jid)
    assert row['state'] == 'pending'
    assert row['files'][0]['name'] == 'tistory.md'
    assert row['text'] == (folder / 'tistory.md').read_text(encoding='utf-8')
    assert store.job(jid)['source_approval'] == job['source_approval']
    assert store.job(jid)['release_approval'] is None


def test_claim_is_single_and_public_receipt_is_rejected(tmp_path):
    store, jid = ready(tmp_path)
    row, = owner_drafts.prepare(store, jid)
    claimed = owner_drafts.claim(store, row['id'], 'fixture')
    with pytest.raises(WorkflowError):
        owner_drafts.claim(store, row['id'], 'second')
    with pytest.raises(WorkflowError):
        owner_drafts.receipt(store, row['id'], {'state': 'published', 'claim_id': claimed['claim_id']})
    assert owner_drafts.view(store, jid)['items'][0]['state'] == 'claimed'


def test_changed_account_or_file_blocks_before_claim(tmp_path):
    store, jid = ready(tmp_path)
    row, = owner_drafts.prepare(store, jid)
    job = store.job(jid)
    file = next(r for r in job['manifest']['files'] if r['name'] == 'short.mp4')
    (store.artifacts / file['path']).write_bytes(b'changed')
    with pytest.raises(WorkflowError, match='파일'):
        owner_drafts.claim(store, row['id'], 'fixture')


def test_no_policy_no_queue_and_wrong_language_or_notification_target_rejected(tmp_path):
    store, jid = enabled_fixture(tmp_path, approve_release=False)
    assert owner_drafts.prepare(store, jid) == []
    for target in ('youtube_english', 'slack_internal', 'store'):
        with pytest.raises(WorkflowError):
            owner_drafts.policy(store, store.job(jid), [target], 'fixture')


def test_receipt_is_bound_to_claim_content_and_nonpublic_platform_state(tmp_path):
    store, jid = ready(tmp_path)
    row, = owner_drafts.prepare(store, jid)
    claimed = owner_drafts.claim(store, row['id'], 'fixture')
    proof = {'state': 'platform_private', 'claim_id': claimed['claim_id'], 'content_hash': row['content_hash'], 'account_id': row['account_id'], 'external_id': 'youtube_fixture'}
    with pytest.raises(WorkflowError):
        owner_drafts.receipt(store, row['id'], {**proof, 'content_hash': '0' * 64})
    saved = owner_drafts.receipt(store, row['id'], proof)
    assert saved['state'] == 'platform_private'
    assert not store.job(jid).get('release_approval')


def test_expired_window_and_stale_policy_do_not_dispatch(tmp_path):
    store, jid = ready(tmp_path)
    row, = owner_drafts.prepare(store, jid)
    store.set_setting('work_window', {'status': 'closed'})
    assert owner_drafts.pending(store) == []
    with pytest.raises(WorkflowError):
        owner_drafts.claim(store, row['id'], 'fixture')


def test_human_approval_records_policy_and_explicit_empty_selection_clears_it(tmp_path):
    store, jid = ready(tmp_path)
    job = store.job(jid)
    approved = store.review_source(jid, job['source_hash'], 'approved', 'fixture-human', production_contract='c'*64, draft_targets=['youtube_main_ko'])
    assert approved['owner_draft_policy']['channels'][0]['key'] == 'youtube_main_ko'
    assert approved['owner_draft_policy']['public_publish'] is False
    assert not approved['release_approval']
    cleared = store.review_source(jid, job['source_hash'], 'approved', 'fixture-human', draft_targets=[])
    assert cleared['owner_draft_policy']['channels'] == []


def test_account_change_and_unknown_result_are_never_silently_retried(tmp_path):
    store, jid = ready(tmp_path)
    row, = owner_drafts.prepare(store, jid)
    claimed = owner_drafts.claim(store, row['id'], 'fixture')
    proof = {k:claimed[k] for k in ('claim_id','account_id','content_hash')}
    owner_drafts.receipt(store, row['id'], {**proof,'state':'unknown','reason':'connection ended'})
    assert owner_drafts.pending(store) == []
    assert owner_drafts.prepare(store, jid)[0]['state'] == 'unknown'
    from office.channels import update_channel
    update_channel(store, 'youtube_main_ko', {'publication_enabled':False}, actor='fixture')
    with pytest.raises(WorkflowError, match='채널'):
        owner_drafts.prepare(store, jid)


def test_old_platform_result_is_preserved_but_not_shown_as_current_version(tmp_path):
    store, jid = ready(tmp_path)
    row, = owner_drafts.prepare(store, jid)
    store.update_job(jid, manifest=None)
    assert owner_drafts.view(store, jid)['items'] == []
    assert row['id'] in store.setting(owner_drafts.SETTING)


def instagram_ready(tmp_path):
    from office.channels import update_channel
    from office.media import artifact_record
    store, jid = ready(tmp_path)
    update_channel(store, 'instagram_main', {'publication_enabled': True}, actor='fixture')
    job = store.job(jid)
    folder = store.artifacts / jid
    path = folder / 'instagram-main-caption.txt'
    path.write_text('검토한 Instagram 문구', encoding='utf-8')
    manifest = {**job['manifest'], 'files': [*job['manifest']['files'],
                {**artifact_record(store.artifacts, path), 'outputs': ['blog']}]}
    store.update_job(jid, manifest=manifest, owner_draft_policy=owner_drafts.policy(
        store, job, ['youtube_main_ko', 'instagram_main'], 'fixture'))
    return store, jid


def test_instagram_is_held_in_office_until_current_release_approval(tmp_path):
    store, jid = instagram_ready(tmp_path)
    rows = owner_drafts.prepare(store, jid)
    ig = next(r for r in rows if r['channel_key'] == 'instagram_main')
    assert ig['state'] == 'office_held'
    assert [r['channel_key'] for r in owner_drafts.pending(store)] == ['youtube_main_ko']
    with pytest.raises(WorkflowError, match='승인②'):
        owner_drafts.claim(store, ig['id'], 'fixture')
    assert store.job(jid)['release_approval'] is None


def test_final_release_unlocks_only_instagram_and_never_requeues_saved_channel(tmp_path):
    store, jid = instagram_ready(tmp_path)
    rows = owner_drafts.prepare(store, jid)
    yt = next(r for r in rows if r['channel_key'] == 'youtube_main_ko')
    ig = next(r for r in rows if r['channel_key'] == 'instagram_main')
    held = owner_drafts.claim(store, yt['id'], 'fixture')
    saved = owner_drafts.receipt(store, yt['id'], {
        **{k: held[k] for k in ('claim_id', 'content_hash', 'account_id')},
        'state': 'platform_private', 'external_id': 'existing_video'})
    original = store.job(jid)
    store.review_release(jid, original['manifest']['hash'], 'approved', 'fixture-human',
                         media_reviewed=True, outputs=['blog', 'video'])
    assert [r['id'] for r in owner_drafts.pending(store)] == [ig['id']]
    claimed = owner_drafts.claim(store, ig['id'], 'fixture')
    assert owner_drafts.claimed(store, ig['id'], claimed['claim_id'])['id'] == ig['id']
    owner_drafts.prepare(store, jid)
    assert store.setting(owner_drafts.SETTING)[yt['id']] == saved
    assert store.job(jid)['source_approval'] == original['source_approval']
    with pytest.raises(WorkflowError):
        owner_drafts.claim(store, ig['id'], 'second')
    store.update_job(jid, release_approval=None)
    with pytest.raises(WorkflowError, match='승인②'):
        owner_drafts.claimed(store, ig['id'], claimed['claim_id'])
    with pytest.raises(WorkflowError, match='승인②'):
        owner_drafts.receipt(store, ig['id'], {
            **{k: claimed[k] for k in ('claim_id', 'content_hash', 'account_id')},
            'state': 'platform_draft', 'external_id': 'https://instagram.com/'})


@pytest.mark.parametrize('outputs', [['video'], ['blog']])
def test_instagram_requires_both_caption_and_selected_media_in_release(tmp_path, outputs):
    store, jid = instagram_ready(tmp_path)
    ig = next(r for r in owner_drafts.prepare(store, jid) if r['channel_key'] == 'instagram_main')
    job = store.job(jid)
    store.review_release(jid, job['manifest']['hash'], 'approved', 'fixture-human',
                         media_reviewed=True, outputs=outputs)
    assert not any(r['id'] == ig['id'] for r in owner_drafts.pending(store))
    with pytest.raises(WorkflowError, match='승인②'):
        owner_drafts.claim(store, ig['id'], 'fixture')


def test_prepare_holds_legacy_instagram_but_preserves_previous_failure_and_other_rows(tmp_path):
    store, jid = instagram_ready(tmp_path)
    rows = owner_drafts.prepare(store, jid)
    ledger = store.setting(owner_drafts.SETTING)
    ig = next(r for r in rows if r['channel_key'] == 'instagram_main')
    ledger[ig['id']].update(state='blocked', reason='Facebook reel only', claim_id='old-claim')
    ledger[ig['id']].pop('office_hold_policy', None)
    other = {k: v for k, v in ledger.items() if k != ig['id']}
    store.set_setting(owner_drafts.SETTING, ledger)
    owner_drafts.prepare(store, jid)
    current = store.setting(owner_drafts.SETTING)
    assert current[ig['id']]['state'] == 'office_held'
    assert current[ig['id']]['previous_attempt']['reason'] == 'Facebook reel only'
    assert 'claim_id' not in current[ig['id']]
    assert {k: v for k, v in current.items() if k != ig['id']} == other
    assert next(r for r in owner_drafts.view(store, jid)['items'] if r['id'] == ig['id'])['state'] == 'office_held'


def test_instagram_failed_after_final_approval_is_not_automatically_retried(tmp_path):
    store, jid = instagram_ready(tmp_path)
    ig = next(r for r in owner_drafts.prepare(store, jid) if r['channel_key'] == 'instagram_main')
    job = store.job(jid)
    store.review_release(jid, job['manifest']['hash'], 'approved', 'fixture-human',
                         media_reviewed=True, outputs=['blog', 'video'])
    claimed = owner_drafts.claim(store, ig['id'], 'fixture')
    failed = owner_drafts.receipt(store, ig['id'], {
        **{k: claimed[k] for k in ('claim_id', 'content_hash', 'account_id')},
        'state': 'blocked', 'reason': 'Facebook reel only'})
    owner_drafts.prepare(store, jid)
    assert store.setting(owner_drafts.SETTING)[ig['id']] == failed
    assert not any(r['id'] == ig['id'] for r in owner_drafts.pending(store))


def test_legacy_pending_instagram_cannot_bypass_release_gate(tmp_path):
    store, jid = instagram_ready(tmp_path)
    ig = next(r for r in owner_drafts.prepare(store, jid) if r['channel_key'] == 'instagram_main')
    ledger = store.setting(owner_drafts.SETTING)
    ledger[ig['id']]['state'] = 'pending'
    store.set_setting(owner_drafts.SETTING, ledger)
    assert not any(r['id'] == ig['id'] for r in owner_drafts.pending(store))
    with pytest.raises(WorkflowError, match='승인②'):
        owner_drafts.claim(store, ig['id'], 'fixture')


def test_instagram_status_api_does_not_approve_or_dispatch(tmp_path):
    from fastapi.testclient import TestClient
    from office.api import create_app
    store, jid = instagram_ready(tmp_path)
    owner_drafts.prepare(store, jid)
    with TestClient(create_app(store), base_url='http://localhost:8510') as client:
        client.get('/api/session')
        result = client.get(f'/api/jobs/{jid}/owner-drafts')
        assert result.status_code == 200
        row = next(r for r in result.json()['items'] if r['channel_key'] == 'instagram_main')
        assert row['state'] == 'office_held'
        assert '승인②' in row['reason']
        assert store.job(jid)['release_approval'] is None


@pytest.mark.parametrize('change', ['old_release', 'account', 'file'])
def test_instagram_final_approval_cannot_be_reused_for_changed_inputs(tmp_path, change):
    from office.channels import update_channel
    store, jid = instagram_ready(tmp_path)
    ig = next(r for r in owner_drafts.prepare(store, jid) if r['channel_key'] == 'instagram_main')
    job = store.job(jid)
    approved = store.review_release(jid, job['manifest']['hash'], 'approved', 'fixture-human',
                                    media_reviewed=True, outputs=['blog', 'video'])
    if change == 'old_release':
        store.update_job(jid, release_approval={**approved['release_approval'], 'version': 'old'})
    elif change == 'account':
        update_channel(store, 'instagram_main', {'public_url': 'https://instagram.com/another/'}, actor='fixture')
    else:
        (store.artifacts / ig['files'][0]['path']).write_text('수정된 문구', encoding='utf-8')
    assert not any(r['id'] == ig['id'] for r in owner_drafts.pending(store))
    with pytest.raises(WorkflowError):
        owner_drafts.claim(store, ig['id'], 'fixture')


def test_manifest_only_change_does_not_resend_identical_saved_channel(tmp_path):
    store, jid = instagram_ready(tmp_path)
    yt = next(r for r in owner_drafts.prepare(store, jid) if r['channel_key'] == 'youtube_main_ko')
    claimed = owner_drafts.claim(store, yt['id'], 'fixture')
    saved = owner_drafts.receipt(store, yt['id'], {
        **{k: claimed[k] for k in ('claim_id', 'content_hash', 'account_id')},
        'state': 'platform_private', 'external_id': 'existing_video'})
    job = store.job(jid)
    store.update_job(jid, manifest={**job['manifest'], 'hash': 'n' * 64})
    reused = next(r for r in owner_drafts.prepare(store, jid) if r['channel_key'] == 'youtube_main_ko')
    assert reused['state'] == 'platform_private'
    assert reused['external_id'] == 'existing_video'
    assert reused['reused_from'] == saved['id']
    assert store.setting(owner_drafts.SETTING)[saved['id']] == saved
    assert owner_drafts.pending(store) == []
    # A changed caption is a new delivery, even when the job and channel are the same.
    record = next(r for r in store.job(jid)['manifest']['files'] if r['name'] == 'description.txt')
    path = store.artifacts / record['path']
    path.write_text('변경한 설명', encoding='utf-8')
    from office.media import artifact_record
    files = [artifact_record(store.artifacts, path) if r['name'] == 'description.txt' else r for r in job['manifest']['files']]
    store.update_job(jid, manifest={**job['manifest'], 'files': files, 'hash': 'o' * 64})
    changed = next(r for r in owner_drafts.prepare(store, jid) if r['channel_key'] == 'youtube_main_ko')
    assert changed['state'] == 'pending'


def test_release_api_prepares_current_instagram_after_thumbnail_change_without_resending_saved_youtube(tmp_path):
    from fastapi.testclient import TestClient
    from office.api import create_app
    from office.store import digest
    store, jid = instagram_ready(tmp_path)
    yt = next(r for r in owner_drafts.prepare(store, jid) if r['channel_key'] == 'youtube_main_ko')
    claimed = owner_drafts.claim(store, yt['id'], 'fixture')
    saved = owner_drafts.receipt(store, yt['id'], {
        **{k: claimed[k] for k in ('claim_id', 'content_hash', 'account_id')},
        'state': 'platform_private', 'external_id': 'already_saved_video'})
    job = store.job(jid)
    manifest = {**job['manifest'], 'thumbnail_candidates': [*job['manifest']['thumbnail_candidates'], {'id':'thumb-2'}]}
    store.update_job(jid, manifest=manifest)
    selected = store.select_thumbnail(jid, 'thumb-2', manifest['hash'], 'fixture-human')
    assert selected['manifest']['hash'] != manifest['hash']
    with TestClient(create_app(store), base_url='http://localhost:8510') as client:
        csrf = client.get('/api/session').json()['csrf']
        response = client.post(f'/api/jobs/{jid}/reviews/release',
            json={'version':selected['manifest']['hash'], 'decision':'approved',
                  'media_reviewed':True, 'outputs':['blog','video']},
            headers={'Origin':'http://localhost:3110','X-Office-CSRF':csrf})
        assert response.status_code == 200, response.text
        current = client.get(f'/api/jobs/{jid}/owner-drafts').json()['items']
    ig = next(r for r in current if r['channel_key'] == 'instagram_main')
    assert ig['manifest_hash'] == selected['manifest']['hash']
    assert ig['state'] == 'pending'
    reused = next(r for r in current if r['channel_key'] == 'youtube_main_ko')
    assert reused['state'] == 'platform_private' and reused['reused_from'] == saved['id']
    assert [r['id'] for r in owner_drafts.pending(store)] == [ig['id']]
    assert digest(store.setting(owner_drafts.SETTING)[saved['id']]) == digest(saved)
    assert store.job(jid)['source_approval'] == job['source_approval']


def test_queue_preparation_failure_does_not_turn_committed_release_into_retry_prompt(tmp_path, monkeypatch):
    from fastapi.testclient import TestClient
    from office.api import create_app
    store, jid = instagram_ready(tmp_path)
    owner_drafts.prepare(store, jid)
    previous = store.setting(owner_drafts.SETTING)
    def fail(*args):
        raise OSError('synthetic queue I/O failure')
    monkeypatch.setattr(owner_drafts, 'prepare', fail)
    with TestClient(create_app(store), base_url='http://localhost:8510') as client:
        csrf = client.get('/api/session').json()['csrf']
        response = client.post(f'/api/jobs/{jid}/reviews/release',
            json={'version':store.job(jid)['manifest']['hash'], 'decision':'approved',
                  'media_reviewed':True, 'outputs':['blog','video']},
            headers={'Origin':'http://localhost:3110','X-Office-CSRF':csrf})
    assert response.status_code == 200
    assert store.job(jid)['release_approval']['decision'] == 'approved'
    assert store.setting(owner_drafts.SETTING) == previous
    with store.connection() as db:
        assert db.execute("SELECT count(*) FROM approvals WHERE job_id=? AND kind='release'", (jid,)).fetchone()[0] == 1


def test_content_only_source_review_preserves_existing_delivery_policy_and_pending_receipt(tmp_path):
    store, jid = ready(tmp_path)
    rows = owner_drafts.prepare(store, jid)
    before = store.job(jid)
    saved = store.review_source(jid, before['source_hash'], 'approved', 'fixture', before['selections'])
    assert saved['owner_draft_policy'] == before['owner_draft_policy']
    assert saved['source_hash'] == before['source_hash']
    assert owner_drafts.prepare(store, jid) == rows
