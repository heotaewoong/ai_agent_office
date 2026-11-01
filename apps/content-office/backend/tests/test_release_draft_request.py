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
