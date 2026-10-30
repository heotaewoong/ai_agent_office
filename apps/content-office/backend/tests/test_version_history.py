import copy
from fastapi.testclient import TestClient
from office.api import create_app
from office.store import Store
from office.version_history import history
from office.media import produce


def setup(tmp_path):
    store=Store(tmp_path/'state')
    job=store.create_job({'id':'fixture','title':'합성 버전 검사','url':'https://example.com'})
    job=store.save_source(job['id'],{'title':'처음 원고','body':'원본 내용\n둘째 줄','quality':{'status':'passed','critical':False}})
    store.review_source(job['id'],job['source_hash'],'approved','test',{'blog':True})
    return store,job['id']


def test_history_preserves_production_after_source_edit_and_never_restores_approval(tmp_path):
    store,jid=setup(tmp_path)
    first=produce(store,jid)
    old=copy.deepcopy(store.job(jid))
    store.save_source(jid,{'title':'개선 원고','body':'개선 내용','quality':{'status':'unverified'}})
    before=store.job(jid)
    with store.connection() as db:settings=list(db.execute('SELECT * FROM settings'))
    result=history(store,jid)
    assert len(result['sources'])==2 and len(result['productions'])==1
    assert result['productions'][0]['manifest']['hash']==first['hash']
    assert not result['productions'][0]['current']
    assert result['sources'][0]['approved_before'] is True
    assert store.job(jid)==before and before['source_approval'] is None
    with store.connection() as db:assert list(db.execute('SELECT * FROM settings'))==settings
    client=TestClient(create_app(store))
    file=result['productions'][0]['manifest']['files'][0]
    assert client.get(file['url']).status_code==200
    assert client.get(file['url'].replace(jid,'job_missing')).status_code==409
    assert client.get(file['url'].replace(first['hash'],'0'*64)).status_code==404
    (store.artifacts/file['path']).write_bytes(b'tampered')
    assert client.get(file['url']).status_code==409
    assert old['source_hash']!=before['source_hash']


def test_reproduction_uses_new_directory_and_keeps_previous_bytes(tmp_path):
    store,jid=setup(tmp_path)
    first=produce(store,jid)
    original={f['path']:(store.artifacts/f['path']).read_bytes() for f in first['files']}
    # Force fresh rendering of the same source/contract instead of the completed-output cache.
    store.update_job(jid,manifest=None)
    second=produce(store,jid)
    assert set(original).isdisjoint(f['path'] for f in second['files'])
    assert all((store.artifacts/p).read_bytes()==data for p,data in original.items())
    result=history(store,jid)
    assert len(result['productions'])==2 and sum(p['current'] for p in result['productions'])==1


def test_initial_read_includes_existing_production_and_drafts_without_writing(tmp_path):
    store,jid=setup(tmp_path)
    manifest=produce(store,jid)
    store.add_draft(jid,{'title':'개선안','body':'아직 채택하지 않은 초안'})
    with store.connection() as db:db.execute('DELETE FROM settings WHERE key LIKE ?',('history:%',))
    before=store.job(jid)
    result=history(store,jid)
    assert result['productions'][0]['current']
    assert result['productions'][0]['manifest']['hash']==manifest['hash']
    assert len(result['drafts'])==1 and store.job(jid)==before
    with store.connection() as db:assert not db.execute("SELECT 1 FROM settings WHERE key LIKE 'history:%'").fetchone()
