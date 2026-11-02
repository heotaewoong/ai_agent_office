import pytest
from office import owner_drafts
from office.store import WorkflowError
from office.channels import update_channel
from test_youtube_delivery import enabled_fixture


def context(tmp_path, released=True, language="ko"):
    s, jid = enabled_fixture(tmp_path, approve_release=released, outputs=('blog','video'),language=language)
    update_channel(s, 'linkedin_personal', {'publication_enabled': True}, actor='fixture')
    from office.media import artifact_record
    job=s.job(jid)
    path=s.artifacts / jid / 'linkedin-personal.txt'
    path.write_text('Approved draft text',encoding='utf8')
    manifest={**job['manifest'],'files':[*job['manifest']['files'],{**artifact_record(s.artifacts,path),'outputs':['blog']}]}
    s.update_job(jid,manifest=manifest)
    return s,jid


def test_request_after_release_preserves_approvals_and_is_idempotent(tmp_path):
    s,jid=context(tmp_path)
    before=s.job(jid)
    first=owner_drafts.request_after_release(s,jid,before['manifest']['hash'],'linkedin_personal',owner_drafts.snapshot(s,'linkedin_personal'))
    again=owner_drafts.request_after_release(s,jid,before['manifest']['hash'],'linkedin_personal',owner_drafts.snapshot(s,'linkedin_personal'))
    assert first == again
    after=s.job(jid)
    assert after['source_approval']==before['source_approval']
    assert after['release_approval']==before['release_approval']
    assert after['manifest']==before['manifest']
    assert len(first['items'])==1
    assert first['items'][0]['state']=='pending'
    assert first['items'][0]['visibility']=='draft'


@pytest.mark.parametrize('failure',['unreleased','stale','instagram','youtube','unknown','language','file'])
def test_request_blocks_unsafe_targets_without_mutation(tmp_path,failure):
    s,jid=context(tmp_path,released=failure!='unreleased',language='en' if failure=='language' else 'ko')
    before=s.job(jid);version=before['manifest']['hash'];key='linkedin_personal'
    if failure=='stale':version='0'*64
    if failure in ['instagram','youtube','unknown']:key={'instagram':'instagram_main','youtube':'youtube_main_ko','unknown':'tiktok_main'}[failure]
    if failure=='file':
        record=before['manifest']['files'][0]
        (s.artifacts/record['path']).write_bytes(b'changed')
    with pytest.raises(WorkflowError):owner_drafts.request_after_release(s,jid,version,key,owner_drafts.snapshot(s,'linkedin_personal'))
    assert s.job(jid)==before
    assert s.setting(owner_drafts.SETTING,{})=={}


def test_changed_account_after_preview_cannot_queue(tmp_path):
    s,jid=context(tmp_path)
    before=s.job(jid);target=owner_drafts.snapshot(s,'linkedin_personal')
    update_channel(s,'linkedin_personal',{'public_url':'https://www.linkedin.com/in/changed-account'},actor='fixture')
    with pytest.raises(WorkflowError):owner_drafts.request_after_release(s,jid,before['manifest']['hash'],'linkedin_personal',target)
    assert s.job(jid)==before
    assert s.setting(owner_drafts.SETTING,{})=={}


def test_endpoint_rejects_public_and_unknown_fields(tmp_path):
    from fastapi.testclient import TestClient
    from office.api import create_app
    s,jid=context(tmp_path)
    c=TestClient(create_app(s),base_url='http://localhost:8510')
    csrf=c.get('/api/session').json()['csrf']
    response=c.post(f'/api/jobs/{jid}/owner-drafts/request',headers={'X-Office-CSRF':csrf,'Origin':'http://localhost:8510'},json={'version':s.job(jid)['manifest']['hash'],'channel_key':'linkedin_personal','target':owner_drafts.snapshot(s,'linkedin_personal'),'public':True})
    assert response.status_code==422
    assert s.setting(owner_drafts.SETTING,{})=={}


def test_account_change_during_file_checks_is_rejected(tmp_path,monkeypatch):
    from office import staging
    s,jid=context(tmp_path);before=s.job(jid);target=owner_drafts.snapshot(s,'linkedin_personal')
    original=staging._verified_records
    def race(store,job):
        result=original(store,job)
        update_channel(store,'linkedin_personal',{'public_url':'https://www.linkedin.com/in/raced-account'},actor='fixture')
        return result
    monkeypatch.setattr(staging,'_verified_records',race)
    with pytest.raises(WorkflowError):owner_drafts.request_after_release(s,jid,before['manifest']['hash'],'linkedin_personal',target)
    assert s.job(jid)==before
    assert s.setting(owner_drafts.SETTING,{})=={}


def test_request_one_target_does_not_requeue_other_policy_targets(tmp_path):
    s,jid=context(tmp_path)
    update_channel(s,'tistory_main',{'publication_enabled':True},actor='fixture')
    job=s.job(jid)
    s.update_job(jid,owner_draft_policy=owner_drafts.policy(s,job,['tistory_main'],'fixture'))
    result=owner_drafts.request_after_release(s,jid,job['manifest']['hash'],'linkedin_personal',owner_drafts.snapshot(s,'linkedin_personal'))
    assert [r['channel_key'] for r in result['items']]==['linkedin_personal']


@pytest.mark.parametrize('old_state',['pending','unknown','claimed','platform_draft'])
def test_explicit_current_release_request_replaces_only_stale_policy(tmp_path,old_state):
    from copy import deepcopy
    s,jid=context(tmp_path)
    update_channel(s,'tistory_main',{'publication_enabled':True},actor='fixture')
    job=s.job(jid)
    old_policy=owner_drafts.policy(s,job,['tistory_main','linkedin_personal'],'fixture')
    old_policy['source_hash']='0'*64
    old_rows={'old-request':{'id':'old-request','job_id':jid,'source_hash':'0'*64,
                           'manifest_hash':'old-manifest','state':old_state,'channel_key':'tistory_main'}}
    s.set_setting(owner_drafts.SETTING,deepcopy(old_rows))
    s.update_job(jid,owner_draft_policy=old_policy)
    before=s.job(jid)
    first=owner_drafts.request_after_release(s,jid,job['manifest']['hash'],
                                           'linkedin_personal',owner_drafts.snapshot(s,'linkedin_personal'))
    after=s.job(jid)
    assert after['owner_draft_policy']['source_hash']==job['source_hash']
    assert [r['key'] for r in after['owner_draft_policy']['channels']]==['linkedin_personal']
    assert [r['channel_key'] for r in first['items']]==['linkedin_personal']
    assert s.setting(owner_drafts.SETTING)['old-request']==old_rows['old-request']
    for field in ['source_packet','source_approval','release_approval','manifest','selections']:
        assert after[field]==before[field]
    again=owner_drafts.request_after_release(s,jid,job['manifest']['hash'],
                                           'linkedin_personal',owner_drafts.snapshot(s,'linkedin_personal'))
    assert again==first
    from datetime import datetime,timedelta,timezone
    s.set_setting('work_window',{'status':'active','user_confirmed':True,
                  'authorized_start':(datetime.now(timezone.utc)-timedelta(minutes=1)).isoformat(),
                  'authorized_end':(datetime.now(timezone.utc)+timedelta(minutes=5)).isoformat()})
    assert [r['channel_key'] for r in owner_drafts.pending(s)]==['linkedin_personal']
    with s.connection() as db:
        saved=db.execute("SELECT data FROM events WHERE job_id=? AND kind='owner_draft_policy_replaced'",(jid,)).fetchall()
    import json
    assert len(saved)==1 and json.loads(saved[0][0])['previous_policy']==old_policy


def test_stale_policy_recovery_keeps_http_approval_and_account_guards(tmp_path):
    from fastapi.testclient import TestClient
    from office.api import create_app
    s,jid=context(tmp_path)
    job=s.job(jid)
    old=owner_drafts.policy(s,job,['linkedin_personal'],'fixture');old['source_hash']='0'*64
    s.update_job(jid,owner_draft_policy=old)
    before=s.job(jid)
    with TestClient(create_app(s),base_url='http://localhost:8510') as c:
        csrf=c.get('/api/session').json()['csrf']
        headers={'X-Office-CSRF':csrf,'Origin':'http://localhost:8510'}
        body={'version':job['manifest']['hash'],'channel_key':'linkedin_personal',
              'target':owner_drafts.snapshot(s,'linkedin_personal')}
        for invalid in [{**body,'version':'0'*64},
                        {**body,'target':{**body['target'],'public_url':'https://www.linkedin.com/in/other'}}]:
            assert c.post(f'/api/jobs/{jid}/owner-drafts/request',headers=headers,json=invalid).status_code==409
            assert s.job(jid)==before
        response=c.post(f'/api/jobs/{jid}/owner-drafts/request',headers=headers,json=body)
        assert response.status_code==200
        assert [r['channel_key'] for r in response.json()['items']]==['linkedin_personal']
        assert c.post(f'/api/jobs/{jid}/owner-drafts/request',headers=headers,json=body).json()==response.json()
        assert s.job(jid)['release_approval']==before['release_approval']
        assert s.job(jid)['source_approval']==before['source_approval']


@pytest.mark.parametrize('key',['linkedin_personal','threads_main','tistory_main','naver_blog_main'])
def test_stale_policy_recovery_supports_each_web_destination(tmp_path,key):
    from office.media import artifact_record
    s,jid=context(tmp_path)
    update_channel(s,key,{'publication_enabled':True},actor='fixture')
    job=s.job(jid)
    if key!='linkedin_personal':
        path=s.artifacts/jid/owner_drafts.TEXT_FILES[key]
        path.write_text('Synthetic approved channel text',encoding='utf8')
        s.update_job(jid,manifest={**job['manifest'],'files':[*job['manifest']['files'],
                     {**artifact_record(s.artifacts,path),'outputs':['blog']}]})
    old=owner_drafts.policy(s,s.job(jid),['linkedin_personal'],'fixture');old['source_hash']='0'*64
    s.update_job(jid,owner_draft_policy=old)
    result=owner_drafts.request_after_release(s,jid,job['manifest']['hash'],key,owner_drafts.snapshot(s,key))
    row,=result['items']
    assert row['state']=='pending' and row['channel_key']==key
    assert row['visibility']=='draft' and not row.get('external_id')


def test_stale_policy_recovery_race_leaves_no_policy_or_audit_write(tmp_path,monkeypatch):
    from office import staging
    s,jid=context(tmp_path);job=s.job(jid)
    old=owner_drafts.policy(s,job,['linkedin_personal'],'fixture');old['source_hash']='0'*64
    s.update_job(jid,owner_draft_policy=old)
    original=staging._verified_records
    def race(store,job):
        result=original(store,job)
        store.update_job(jid,release_approval=None)
        return result
    monkeypatch.setattr(staging,'_verified_records',race)
    with pytest.raises(WorkflowError,match='요청 중 승인'):
        owner_drafts.request_after_release(s,jid,job['manifest']['hash'],
                                          'linkedin_personal',owner_drafts.snapshot(s,'linkedin_personal'))
    assert s.job(jid)['owner_draft_policy']==old
    assert s.setting(owner_drafts.SETTING,{})=={}
    with s.connection() as db:
        assert db.execute("SELECT count(*) FROM events WHERE kind='owner_draft_policy_replaced'").fetchone()[0]==0


def test_current_source_other_account_changes_still_block_new_target(tmp_path):
    s,jid=context(tmp_path)
    update_channel(s,'tistory_main',{'publication_enabled':True},actor='fixture')
    job=s.job(jid)
    s.update_job(jid,owner_draft_policy=owner_drafts.policy(s,job,['tistory_main'],'fixture'))
    before=s.job(jid)
    update_channel(s,'tistory_main',{'public_url':'https://changed.tistory.com'},actor='fixture')
    with pytest.raises(WorkflowError,match='초안 대상 채널이 변경'):
        owner_drafts.request_after_release(s,jid,job['manifest']['hash'],
                                          'linkedin_personal',owner_drafts.snapshot(s,'linkedin_personal'))
    assert s.job(jid)==before and s.setting(owner_drafts.SETTING,{})=={}
