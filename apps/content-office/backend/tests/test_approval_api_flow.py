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
@pytest.mark.parametrize('voice',['windows-heami','openai-tts','gemini-kore'])
def test_image_profile_can_build_contract_before_atomic_approval_but_cannot_generate(tmp_path,monkeypatch,profile,voice):
    from office.image_selection import background_renderer_for_job
    from office.voice_selection import renderer_for_job
    from office.store import WorkflowError
    monkeypatch.setattr('requests.post',lambda *a,**k:pytest.fail('No synthesis or API requests before approval'))
    store=Store(tmp_path)
    store.set_setting('image_profile',{'id':profile})
    store.set_setting('voice_profile',{'id':voice})
    job=store.create_job({'id':'image-approval','title':'그림 설정'})
    job=store.save_source(job['id'],{'title':'그림 설정','body':'합성 자료',
        'quality':{'status':'passed','critical':False},'video':{'scenes':[{'caption':'확인','narration':text} for text in ['확인해요.','비교해요.','보존해요.']]}})
    renderer=background_renderer_for_job(store,job)
    assert renderer.cache_key and store.job(job['id'])['source_approval'] is None
    with pytest.raises(WorkflowError,match='승인'):renderer(0,store.root/'must-not-exist.png')
    assert not (store.root/'must-not-exist.png').exists()
    assert store.budget()['reserved_krw']==store.budget()['spent_krw']==0
    speech=renderer_for_job(store,job)
    if speech is not None:
        assert speech.cache_key
        with pytest.raises(WorkflowError,match='승인'):speech('확인해요.',store.root/'must-not-exist.wav')
        assert not (store.root/'must-not-exist.wav').exists()
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


@pytest.mark.parametrize('thumbnails,clips',[(True,False),(False,True),(True,True)])
def test_paid_approval_requires_confirmation_then_saves_one_atomic_production(tmp_path, monkeypatch, thumbnails, clips):
    store=Store(tmp_path)
    store.set_setting('thumbnail_studio_default',thumbnails)
    job=store.create_job({'id':'paid-approval','title':'비용 확인 원고'})
    job=store.save_source(job['id'],{'title':'비용 확인','body':'검토 원고','quality':{'status':'passed','critical':False},'video':{'scenes':[]}})
    monkeypatch.setattr('office.api.window_open',lambda _:True)
    monkeypatch.setattr('requests.post',lambda *a,**k:pytest.fail('Approval must not call a provider'))
    monkeypatch.setattr('office.video_selection.paid_clip_estimate',lambda _,j:{'paid':clips and j['selections']['video'],'label':'유료 클립','clips':2,'credits':20,'reservation_krw':400,'model':'synthetic'})
    client=TestClient(create_app(store),base_url='http://localhost:8510')
    headers={'Origin':'http://localhost:3110','X-Office-CSRF':client.get('/api/session').json()['csrf']}
    data={'version':job['source_hash'],'decision':'approved','selections':{'video':True},'auto_produce':True}
    url=f"/api/jobs/{job['id']}/reviews/source"
    assert client.post(url,json=data,headers=headers).status_code==409
    assert store.job(job['id'])['source_approval'] is None and store.tasks()==[]
    assert client.get(f"/api/jobs/{job['id']}/production-estimate?video=true").json()['thumbnail_artwork']==thumbnails
    confirmed=client.post(url,json={**data,'confirm_paid_clips':True,'confirm_paid_thumbnails':True},headers=headers)
    assert confirmed.status_code==200,confirmed.text
    assert confirmed.json()['state']=='production_queued'
    task=store.tasks(job['id'])[0]
    assert task['payload'].get('thumbnail_artwork_confirmed',False)==thumbnails
    assert task['payload'].get('paid_clips_confirmed',False)==clips
    if clips:assert task['payload']['paid_clip_estimate']['reservation_krw']==400
    assert client.post(url,json={**data,'confirm_paid_clips':True,'confirm_paid_thumbnails':True},headers=headers).status_code==409
    assert len(store.tasks(job['id']))==1 and store.budget()['spent_krw']==0
