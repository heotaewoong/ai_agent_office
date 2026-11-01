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
