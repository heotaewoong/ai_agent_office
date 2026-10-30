from fastapi.testclient import TestClient
from office.store import Store
from office.api import create_app

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
