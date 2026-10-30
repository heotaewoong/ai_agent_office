import pytest
from fastapi.testclient import TestClient
from office.store import Store,WorkflowError
from office.editorial_assets import register_assets
from office.api import create_app

def context(tmp_path):
    store=Store(tmp_path/'state')
    job=store.create_job({'id':'one','title':'원고','url':''})
    job=store.save_source(job['id'],{'title':'제목','body':'내용','quality':{'status':'passed','critical':False}})
    asset=tmp_path/'note.md';asset.write_text('검토 문서',encoding='utf8')
    return store,job,asset

def test_registered_review_assets_are_readable_inside_office_without_changing_source(tmp_path):
    store,job,asset=context(tmp_path)
    before=store.job(job['id'])
    d=register_assets(store,job['id'],job['source_hash'],'새 편집본','미승인 본문',[('note.md',asset)])
    assert store.job(job['id'])==before
    client=TestClient(create_app(store),base_url='http://localhost:8510')
    r=client.get(f'/api/jobs/{job["id"]}/drafts/{d["id"]}/files/note.md')
    assert r.status_code==200 and r.text=='검토 문서'
    assert r.headers['content-disposition']=='attachment'
    assert client.get(f'/api/jobs/{job["id"]}/drafts/{d["id"]}/files/absent.md').status_code==404
    path=store.artifacts/d['assets'][0]['path'];path.write_text('변조',encoding='utf8')
    assert client.get(f'/api/jobs/{job["id"]}/drafts/{d["id"]}/files/note.md').status_code==409

@pytest.mark.parametrize('name',['../escape.md','evil.html','evil.js','x:y.md'])
def test_unsafe_editorial_assets_are_rejected(tmp_path,name):
    store,job,asset=context(tmp_path)
    with pytest.raises(WorkflowError):register_assets(store,job['id'],job['source_hash'],'제목','본문',[(name,asset)])
    assert store.drafts(job['id'])==[]

def test_stale_source_import_is_rejected(tmp_path):
    store,job,asset=context(tmp_path)
    with pytest.raises(WorkflowError):register_assets(store,job['id'],'a'*64,'제목','본문',[('note.md',asset)])
    assert store.drafts(job['id'])==[]
