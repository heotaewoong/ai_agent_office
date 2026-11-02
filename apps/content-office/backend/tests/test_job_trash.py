"""Recoverable job removal uses real SQLite and preserves media and approvals."""
import json

import pytest
from fastapi.testclient import TestClient

from office.api import create_app
from office.store import Store, WorkflowError, canonical


@pytest.fixture
def ctx(tmp_path):
    store = Store(tmp_path)
    job = store.create_job({'id': 'trash-one', 'title': '보존할 원고', 'url': 'https://example.com/one'})
    job = store.update_job(job['id'], source_hash='a' * 64,
        source_packet={'title': '보존할 원고', 'body': '내 원문'},
        source_approval={'version': 'a' * 64, 'decision': 'approved'},
        release_approval={'version': 'b' * 64, 'decision': 'approved'})
    media = store.artifacts / 'original.mp4'
    media.write_bytes(b'preserved-media')
    client = TestClient(create_app(store), base_url='http://localhost:8510')
    csrf = client.get('/api/session').json()['csrf']
    return store, job, media, client, {'Origin': 'http://localhost:3110', 'X-Office-CSRF': csrf}


def test_trash_restore_preserves_content_and_never_queues_or_purges(ctx):
    store, job, media, client, headers = ctx
    before = {k: job[k] for k in ('source_packet', 'source_hash', 'source_approval', 'release_approval', 'selections')}
    response = client.post(f"/api/jobs/{job['id']}/trash", json={'expected_updated_at': job['updated_at']}, headers=headers)
    assert response.status_code == 200
    deleted = response.json()
    assert deleted['deleted_at'] and store.jobs() == []
    assert client.get(f"/api/jobs/{job['id']}").status_code == 409
    assert client.get('/api/jobs/summaries').json()['jobs'] == []
    assert client.get('/api/dashboard').json()['jobs'] == []
    rows = client.get('/api/trash/jobs').json()['jobs']
    assert len(rows) == 1 and rows[0]['id'] == job['id']
    assert 'source_packet' not in rows[0] and 'article' not in rows[0]
    restored = client.post(f"/api/jobs/{job['id']}/restore", json={'expected_updated_at': deleted['updated_at']}, headers=headers)
    assert restored.status_code == 200
    assert {k: store.job(job['id'])[k] for k in before} == before
    assert not store.job(job['id']).get('deleted_at')
    assert len(store.jobs()) == 1 and client.get('/api/trash/jobs').json()['jobs'] == []
    assert store.tasks() == [] and media.read_bytes() == b'preserved-media'


@pytest.mark.parametrize('state', ['queued', 'running', 'unknown'])
def test_pending_work_blocks_trash_atomically(ctx, state):
    store, job, _, client, headers = ctx
    task = store.enqueue('evaluate', {'job_id': job['id']}, key='pending')
    with store.connection(transaction=True) as db:
        db.execute('UPDATE tasks SET state=? WHERE id=?', (state, task['id']))
    response = client.post(f"/api/jobs/{job['id']}/trash", json={'expected_updated_at': job['updated_at']}, headers=headers)
    assert response.status_code == 409
    assert not store.job(job['id']).get('deleted_at')
    assert store.task(task['id'])['state'] == state


@pytest.mark.parametrize('key,state', [('owner_draft_deliveries','pending'), ('owner_draft_deliveries','claimed'), ('owner_draft_deliveries','unknown'), ('deliveries','accepted'), ('deliveries','pending_owner')])
def test_inflight_external_delivery_is_not_hidden(ctx, key, state):
    store, job, _, client, headers = ctx
    store.set_setting(key, {'row': {'job_id': job['id'], 'state': state}})
    response = client.post(f"/api/jobs/{job['id']}/trash", json={'expected_updated_at': job['updated_at']}, headers=headers)
    assert response.status_code == 409
    assert store.setting(key)['row']['state'] == state


def test_deleted_job_cannot_be_mutated_requeued_or_recreated(ctx):
    store, job, _, client, headers = ctx
    client.post(f"/api/jobs/{job['id']}/trash", json={'expected_updated_at': job['updated_at']}, headers=headers)
    with pytest.raises(WorkflowError, match='휴지통'):
        store.update_job(job['id'], title='바꾸지 못함')
    with pytest.raises(WorkflowError, match='휴지통'):
        store.enqueue('produce', {'job_id': job['id']}, key='late')
    with pytest.raises(WorkflowError, match='휴지통'):
        store.create_job(job['article'])
    assert store.tasks() == []


def test_deleted_job_cannot_reserve_a_late_paid_call(ctx):
    store, job, _, client, headers = ctx
    client.post(f"/api/jobs/{job['id']}/trash", json={'expected_updated_at': job['updated_at']}, headers=headers)
    with pytest.raises(WorkflowError, match='휴지통'):
        store.reserve_cost('late-image',200,{'job_id':job['id']})
    assert store.budget()['reserved_krw']==0


def test_stale_confirmation_and_missing_csrf_do_not_delete(ctx):
    store, job, _, client, headers = ctx
    url = f"/api/jobs/{job['id']}/trash"
    assert client.post(url, json={'expected_updated_at': job['updated_at']}).status_code == 403
    store.update_job(job['id'], title='다른 탭의 변경')
    assert client.post(url, json={'expected_updated_at': job['updated_at']}, headers=headers).status_code == 409
    assert store.job(job['id'])['title'] == '다른 탭의 변경'


def test_unknown_cost_blocks_trash_without_releasing_reservation(ctx):
    store, job, _, client, headers = ctx
    with store.connection(transaction=True) as db:
        db.execute("INSERT INTO costs VALUES('unknown-cost','text','unknown',53,NULL,?,?,?)", (canonical({'job_id':job['id']}), job['updated_at'],job['updated_at']))
    assert client.post(f"/api/jobs/{job['id']}/trash", json={'expected_updated_at':job['updated_at']}, headers=headers).status_code == 409
    assert store.budget()['reserved_krw'] == 53


def test_restore_preserves_ledger_rows_and_hidden_job_cannot_overwrite_a_newer_delete(ctx):
    store, job, _, client, headers = ctx
    with store.connection(transaction=True) as db:
        db.execute("INSERT INTO approvals VALUES('approval-original',?,'source',?,'approved','test-operator','{}',?)", (job['id'],job['source_hash'],job['updated_at']))
        db.execute('INSERT INTO versions VALUES(?,?,?,?)', (job['id'],job['source_hash'],canonical(job['source_packet']),job['updated_at']))
        db.execute("INSERT INTO drafts VALUES('draft-original',?,'{}',?)", (job['id'],job['updated_at']))
        before={table:[tuple(r) for r in db.execute('SELECT * FROM '+table)] for table in ('approvals','versions','drafts','costs')}
    deleted=client.post(f"/api/jobs/{job['id']}/trash",json={'expected_updated_at':job['updated_at']},headers=headers).json()
    with pytest.raises(WorkflowError,match='휴지통'):
        with store.connection(transaction=True) as db:store._write_job(db,job)
    with store.connection() as db:
        assert {table:[tuple(r) for r in db.execute('SELECT * FROM '+table)] for table in before}==before
    restored=client.post(f"/api/jobs/{job['id']}/restore",json={'expected_updated_at':deleted['updated_at']},headers=headers)
    assert restored.status_code==200
    with store.connection() as db:
        assert {table:[tuple(r) for r in db.execute('SELECT * FROM '+table)] for table in before}==before
    assert store.tasks()==[]


def test_pc_delivery_checked_before_delete_cannot_be_queued_after_delete(tmp_path,monkeypatch):
    from datetime import datetime,timedelta,timezone
    from test_owner_auth import ready
    from office import owner_auth,youtube_delivery
    from office.job_trash import move
    store,jid=ready(tmp_path,monkeypatch)
    store.set_setting('work_window',{'status':'active','authorized_end':(datetime.now(timezone.utc)+timedelta(minutes=10)).isoformat()})
    original=youtube_delivery._save
    def delete_before_save(store,record,**kwargs):
        move(store,jid,store.job(jid)['updated_at'])
        return original(store,record,**kwargs)
    monkeypatch.setattr(youtube_delivery,'_save',delete_before_save)
    with pytest.raises(WorkflowError,match='휴지통'):
        owner_auth.stage_delivery(store,jid,'youtube_main_ko','test-operator')
    assert store.jobs(deleted=True)[0]['id']==jid
    assert store.setting('deliveries',{})=={}


def test_terminal_receipt_is_preserved_even_if_the_job_was_removed(ctx):
    from office.youtube_delivery import _save
    from office.job_trash import move
    store,job,_,_,_=ctx
    move(store,job['id'],job['updated_at'])
    record={'key':'confirmed-receipt','job_id':job['id'],'state':'private','external_id':'synthetic-existing-video'}
    assert _save(store,record)==record
    assert store.setting('deliveries')['confirmed-receipt']==record
    assert store.jobs()==[] and store.tasks()==[]
