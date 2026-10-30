import pytest
from office.store import Store,WorkflowError,digest
from office.delivery_queue import process,target

def ready(tmp_path):
    store=Store(tmp_path)
    j=store.create_job({'id':'one','title':'글','url':''})
    j=store.save_source(j['id'],{'title':'글','body':'본문','audience':{'language':'ko'},'quality':{'status':'passed','critical':False}})
    store.review_source(j['id'],j['source_hash'],'approved','owner',{'video':True})
    store.update_job(j['id'],manifest={'hash':'manifest','source_hash':j['source_hash'],'files':[],'completed_outputs':['video'],'thumbnail_candidates':[{'id':'thumb'}],'selected_thumbnail_id':'thumb'})
    row={'key':'youtube_main_ko','platform':'youtube','locale':'ko','publication_enabled':True,'credentials_configured':True,'external_account_id':'UC_test'}
    return store,j,row

def test_release_and_private_request_are_atomic_and_version_bound(tmp_path,monkeypatch):
    store,j,row=ready(tmp_path)
    approved=store.review_release(j['id'],'manifest','approved','owner',True,['video'],private_channel=row)
    task=store.tasks()[0]
    assert task['kind']=='private_delivery' and task['payload']['release_hash']==digest(approved['release_approval'])
    called=[]
    monkeypatch.setattr('office.delivery_queue.channel',lambda *a:row)
    monkeypatch.setattr('office.youtube_delivery.deliver_youtube',lambda *a,**k:called.append(k) or {'state':'private','external_id':'proof'})
    assert process(store,task['payload'])['external_id']=='proof'
    assert called[0]['channel_key']=='youtube_main_ko'
    with pytest.raises(WorkflowError,match='이미'):store.review_release(j['id'],'manifest','approved','owner',True,['video'],private_channel=row)
    store.update_job(j['id'],release_approval=None)
    with pytest.raises(WorkflowError,match='변경'):process(store,task['payload'])
    assert len(called)==1

@pytest.mark.parametrize('field,value',[('credentials_configured',False),('publication_enabled',False),('external_account_id',None),('locale','en')])
def test_unready_channels_never_upload(tmp_path,monkeypatch,field,value):
    store,j,row=ready(tmp_path);row[field]=value
    monkeypatch.setattr('office.delivery_queue.channel',lambda *a:row)
    with pytest.raises(WorkflowError):target(store,row['key'],store.job(j['id']))

def test_unreviewed_video_never_creates_private_task(tmp_path):
    store,j,row=ready(tmp_path)
    with pytest.raises(WorkflowError):store.review_release(j['id'],'manifest','approved','owner',False,['video'],private_channel=row)
    assert store.tasks()==[] and store.job(j['id'])['release_approval'] is None
