from pathlib import Path
import pytest
from office.store import WorkflowError
from office.worker import process_task
from test_thumbnail_studio import fixture, make


def test_thumbnail_queue_uses_current_selected_reference_and_original_state(fixture, monkeypatch):
    from office.thumbnail_studio import choose, snapshot
    store, job = fixture
    state = make(fixture)
    state = choose(store, job['id'], state['candidates'][0]['id'], state['revision'])
    calls=[]
    def generate(*args, **kwargs):
        calls.append(kwargs)
        return {'revision':'synthetic'}
    monkeypatch.setattr('office.thumbnail_studio.generate',generate)
    payload={'job_id':job['id'],'source_hash':job['source_hash'],'revision':state['revision'],
             'edit_id':state['selected_id'],'instruction':'빛만 수정','paid_confirmed':True}
    result=process_task(store,{'kind':'thumbnail_artwork','payload':payload})
    assert result['thumbnail_revision']=='synthetic'
    assert calls[0]['edit_id']==state['selected_id']
    assert store.job(job['id'])['manifest'] is None
    assert store.job(job['id'])['source_approval'] is None
    changed=choose(store,job['id'],state['candidates'][1]['id'],state['revision'])
    with pytest.raises(WorkflowError):
        process_task(store,{'kind':'thumbnail_artwork','payload':payload})
    assert len(calls)==1


def test_thumbnail_queue_cannot_use_stale_source_or_missing_cost_confirmation(fixture,monkeypatch):
    store,job=fixture
    monkeypatch.setattr('office.thumbnail_studio.generate',lambda *a,**k:pytest.fail('must not call'))
    with pytest.raises(WorkflowError,match='원고'):
        process_task(store,{'kind':'thumbnail_artwork','payload':{'job_id':job['id'],'source_hash':'old','paid_confirmed':True}})
    with pytest.raises(WorkflowError,match='비용'):
        process_task(store,{'kind':'thumbnail_artwork','payload':{'job_id':job['id'],'source_hash':job['source_hash'],'paid_confirmed':False}})
