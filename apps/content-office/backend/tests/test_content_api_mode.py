import copy
import pytest
from fastapi.testclient import TestClient
from office.store import Store, WorkflowError
from office.api import create_app
from office.content_api_mode import activate
from office.providers import Provider


def protected_rows(store):
    with store.connection() as db:
        return {table:[tuple(r) for r in db.execute(f'SELECT * FROM {table}')] for table in ['jobs','versions','approvals','costs','drafts']}


def test_activation_is_atomic_idempotent_and_preserves_content_approvals_unknown_and_caps(tmp_path,monkeypatch):
    monkeypatch.setenv('OPENAI_API_KEY','synthetic-test-placeholder')
    store=Store(tmp_path)
    job=store.create_job({'id':'fixture','title':'합성 전환 검사'})
    job=store.save_source(job['id'],{'title':'합성 원고','body':'보존할 본문','quality':{'status':'passed','critical':False}})
    store.review_source(job['id'],job['source_hash'],'approved','human',{'blog':True})
    store.update_job(job['id'],manifest={'hash':'a'*64,'source_hash':job['source_hash'],'files':[]})
    store.add_draft(job['id'],{'title':'이전 검토본','body':'기존 결과 유지'})
    limit=store.get_job_budget(job['id'])
    store.set_job_budget(job['id'],1000,'human',expected_hash=limit['hash'])
    cost=store.reserve_cost('model',10,{'job_id':job['id'],'cache_key':'old-subscription'})
    store.unknown_cost(cost['id'],'synthetic_result_unknown')
    store.set_setting('model','codex-subscription-text')
    store.set_setting('image_profile',{'id':'codex-subscription'})
    voice={'id':'openai-tts','selected_by':'human','selected_at':'old'}
    store.set_setting('voice_profile',voice)
    before=protected_rows(store);budget=copy.deepcopy(store.budget());job_budget=store.get_job_budget(job['id'])
    assert activate(store,text_model='gpt-5.4-mini',actor='human-approved-migration')['changed']
    assert protected_rows(store)==before and store.budget()==budget and store.get_job_budget(job['id'])==job_budget
    assert store.setting('voice_profile')==voice
    assert store.setting('model')=='gpt-5.4-mini' and store.setting('image_profile')['id']=='openai-gpt-image'
    assert activate(store,text_model='gpt-5.4-mini',actor='same')['changed'] is False


def test_running_or_queued_work_blocks_switch_and_missing_key_does_not_partially_change_settings(tmp_path,monkeypatch):
    store=Store(tmp_path)
    monkeypatch.delenv('OPENAI_API_KEY',raising=False)
    with pytest.raises(WorkflowError,match='OPENAI_API_KEY'):activate(store,text_model='gpt-5.4-mini',actor='human')
    assert store.setting('content_api_only') is None
    monkeypatch.setenv('OPENAI_API_KEY','synthetic')
    store.enqueue('draft',{'job_id':'fixture'},'fixture')
    with pytest.raises(WorkflowError,match='진행 중'):activate(store,text_model='gpt-5.4-mini',actor='human')
    assert store.setting('content_api_only') is None


def test_explicit_dormant_reservations_and_queued_refresh_are_preserved(tmp_path,monkeypatch):
    monkeypatch.setenv('OPENAI_API_KEY','synthetic')
    store=Store(tmp_path)
    cost=store.reserve_cost('model',7,{'model':'gemini-3.5-flash-lite'})
    with store.connection(transaction=True) as db:
        db.execute("UPDATE costs SET updated_at='2026-10-28T00:00:00+00:00' WHERE id=?",(cost['id'],))
    store.set_setting('work_window',{'authorized_start':'2026-10-29T00:00:00+00:00','authorized_end':'2026-10-29T01:00:00+00:00'})
    store.enqueue('refresh',{},'refresh')
    before=protected_rows(store);budget=store.budget()
    with pytest.raises(WorkflowError,match='응답'):activate(store,text_model='gpt-5.4-mini',actor='human')
    activate(store,text_model='gpt-5.4-mini',actor='human',preserve_dormant_cost_ids=[cost['id']])
    assert protected_rows(store)==before and store.budget()==budget


def test_retired_choices_are_hidden_by_availability_and_rejected_by_api(tmp_path,monkeypatch):
    monkeypatch.setenv('OPENAI_API_KEY','synthetic')
    store=Store(tmp_path);activate(store,text_model='gpt-5.4-mini',actor='human')
    client=TestClient(create_app(store),base_url='http://localhost:8510')
    headers={'Origin':'http://localhost:3110','X-Office-CSRF':client.get('/api/session').json()['csrf']}
    settings=client.get('/api/settings/profiles').json()
    assert settings['content_api_only'] is True
    for kind,profile in [('text','codex-subscription-text'),('image','codex-subscription'),('voice','windows-heami')]:
        assert settings['availability'][kind][profile]['available'] is False
        assert client.post('/api/settings/profiles',json={'kind':kind,'profile':profile},headers=headers).status_code==409


def test_stale_direct_subscription_paths_cannot_run_or_reuse_cache_after_switch(tmp_path,monkeypatch):
    monkeypatch.setenv('OPENAI_API_KEY','synthetic')
    store=Store(tmp_path);activate(store,text_model='gpt-5.4-mini',actor='human')
    before=protected_rows(store)
    with pytest.raises(WorkflowError,match='API 전용'):
        Provider(store,model='codex-subscription-text',transport=lambda *a,**kw:pytest.fail('No request permitted')).generate('test',[],{})
    from office.codex_image_provider import CodexImageProvider
    with pytest.raises(WorkflowError,match='API 전용'):CodexImageProvider(store,job_id='unused')
    assert protected_rows(store)==before


def test_inflight_http_call_blocks_migration_even_without_worker_task(tmp_path,monkeypatch):
    monkeypatch.setenv('OPENAI_API_KEY','synthetic')
    store=Store(tmp_path)
    store.reserve_cost('model',10,{'cache_key':'inflight'})
    with pytest.raises(WorkflowError,match='응답을 기다리는'):activate(store,text_model='gpt-5.4-mini',actor='human')
    assert store.setting('content_api_only') is None
