from fastapi.testclient import TestClient
from office.store import Store
from office.api import create_app
import pytest

def test_explicit_approval_queue_requires_window_and_has_no_partial_approval(tmp_path,monkeypatch):
    store=Store(tmp_path)
    job=store.create_job({'id':'one','title':'글','url':''})
    job=store.save_source(job['id'],{'title':'글','body':'내용','quality':{'status':'passed','critical':False}})
    client=TestClient(create_app(store),base_url='http://localhost:8510')
    csrf=client.get('/api/session').json()['csrf'];headers={'Origin':'http://localhost:3110','X-Office-CSRF':csrf}
    data={'version':job['source_hash'],'decision':'approved','selections':{'blog':True},'auto_produce':True}
    monkeypatch.setattr('office.api.window_open',lambda _:False)
    assert client.post(f'/api/jobs/{job["id"]}/reviews/source',json=data,headers=headers).status_code==409
    assert store.job(job['id'])['source_approval'] is None and store.tasks()==[]
    monkeypatch.setattr('office.api.window_open',lambda _:True)
    r=client.post(f'/api/jobs/{job["id"]}/reviews/source',json=data,headers=headers)
    assert r.status_code==200 and r.json()['state']=='production_queued'
    assert len(store.tasks())==1


@pytest.mark.parametrize('profile',['codex-subscription','openai-gpt-image'])
def test_image_profile_can_build_contract_before_atomic_approval_but_cannot_generate(tmp_path,monkeypatch,profile):
    from office.image_selection import background_renderer_for_job
    from office.store import WorkflowError
    store=Store(tmp_path)
    store.set_setting('image_profile',{'id':profile})
    job=store.create_job({'id':'image-approval','title':'그림 설정'})
    job=store.save_source(job['id'],{'title':'그림 설정','body':'합성 자료',
        'quality':{'status':'passed','critical':False},'video':{'scenes':[{'caption':'확인','narration':'확인해요.'}]}})
    renderer=background_renderer_for_job(store,job)
    assert renderer.cache_key and store.job(job['id'])['source_approval'] is None
    with pytest.raises(WorkflowError,match='승인'):renderer(0,store.root/'must-not-exist.png')
    assert not (store.root/'must-not-exist.png').exists()
    assert store.budget()['reserved_krw']==store.budget()['spent_krw']==0
    client=TestClient(create_app(store),base_url='http://localhost:8510')
    csrf=client.get('/api/session').json()['csrf'];headers={'Origin':'http://localhost:3110','X-Office-CSRF':csrf}
    monkeypatch.setattr('office.api.window_open',lambda _:True)
    data={'version':job['source_hash'],'decision':'approved','selections':{'blog':True,'video':True},'auto_produce':True}
    r=client.post(f'/api/jobs/{job["id"]}/reviews/source',json=data,headers=headers)
    assert r.status_code==200,r.text
    assert r.json()['state']=='production_queued'
    assert store.job(job['id'])['source_approval']['version']==job['source_hash']
    assert len(store.tasks())==1
    assert client.post(f'/api/jobs/{job["id"]}/reviews/source',json=data,headers=headers).status_code==409
    with store.connection() as db:assert db.execute('SELECT COUNT(*) FROM approvals').fetchone()[0]==1
