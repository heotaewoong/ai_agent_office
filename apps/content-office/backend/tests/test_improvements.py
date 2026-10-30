import copy
import json
import pytest
from fastapi.testclient import TestClient
from office.api import create_app
from office.store import Store, digest
from office.improvements import experience_context
from office.editorial_assets import register_assets


@pytest.fixture
def context(tmp_path):
    store = Store(tmp_path/'state')
    job = store.create_job({'id':'one','title':'옵시디언 동기화','url':'https://example.com/source'})
    job = store.save_source(job['id'], {'title':'동기화 상태 구별','body':'기기와 폴더 상태를 구별해요.', 'evidence':[{'id':'E1','claim':'합성 기능 검증용 근거'}], 'quality':{'status':'passed','critical':False}, 'audience':{'axis':'B','outcome':'상태 구별'}, 'video':{'scenes':[{'caption':'표시와 연결 구별','narration':'두 상태를 구별해요. [E1]','visual':'비교: 최신 표시 / 실제 기기 연결'}]}})
    client = TestClient(create_app(store),base_url='http://localhost:8510')
    csrf = client.get('/api/session').json()['csrf']
    return store,job,client,{'Origin':'http://localhost:3110','X-Office-CSRF':csrf}


def test_workspace_read_is_side_effect_free_and_separates_templates_from_evaluation(context):
    store,job,client,_ = context
    before = store.job(job['id'])
    r = client.get(f'/api/jobs/{job["id"]}/improvements')
    assert r.status_code == 200
    data = r.json()
    assert len(data['casebook']) == 20 and sum(c['split']=='holdout' for c in data['casebook']) == 6
    assert all(c['status']=='scenario_template_not_evaluated' for c in data['casebook'])
    assert data['reviews'] == [] and data['learning']['status']=='quiz_pending'
    scene = data['storyboard']['scenes'][0]
    assert scene['kind']=='comparison' and scene['comparison']==['최신 표시','실제 기기 연결'] and scene['evidence_ids']==['E1']
    assert store.job(job['id']) == before


def review_payload(job):
    return {'source_hash':job['source_hash'],'target_id':'source','target_hash':job['source_hash'],'scores':dict(accuracy=5,clarity=5,actionability=5,voice=5,visual=5),'critical':True,'reasons':['fact'],'note':'합성 테스트: 사실 오류는 높은 점수로 상쇄하지 않음'}


def test_review_is_version_bound_idempotent_and_never_approves(context):
    store,job,client,headers = context
    before=copy.deepcopy(store.job(job['id']))
    body=review_payload(job)
    path=f'/api/jobs/{job["id"]}/quality-reviews'
    r=client.post(path,json=body,headers=headers)
    assert r.status_code==200 and r.json()['quality_passed'] is False
    assert r.json()['scope']=='human_observation_not_approval'
    assert client.post(path,json=body,headers=headers).json()['id']==r.json()['id']
    assert store.job(job['id'])==before and len(client.get(f'/api/jobs/{job["id"]}/improvements').json()['reviews'])==1
    store.save_source(job['id'],{**job['source_packet'],'body':'다음 판본'})
    assert client.post(path,json=body,headers=headers).status_code==409


def test_quality_write_requires_csrf_and_rejects_wrong_target(context):
    _,job,client,headers=context
    path=f'/api/jobs/{job["id"]}/quality-reviews'
    body=review_payload(job)
    assert client.post(path,json=body).status_code==403
    body['target_hash']='a'*64
    assert client.post(path,json=body,headers=headers).status_code==409
    body=review_payload(job);body['scores']['accuracy']=True
    assert client.post(path,json=body,headers=headers).status_code==422


def test_only_confirmed_opted_in_relevant_experiences_are_selected(context):
    store,job,client,headers=context
    base={'title':'옵시디언 실제 관측','axis':'B','facts':'합성 테스트용 경험 데이터이며 실제 경험 주장이 아닙니다.','evidence_note':'기능 테스트','checked_on':'2026-01-01','tags':['옵시디언'],'confirmed':True,'use_in_content':False}
    assert client.post('/api/experiences',json=base,headers=headers).status_code==200
    assert experience_context(store,job)==[]
    assert client.post('/api/experiences',json={**base,'confirmed':False,'use_in_content':True},headers=headers).status_code==409
    r=client.post('/api/experiences',json={**base,'use_in_content':True},headers=headers)
    assert r.status_code==200 and len(experience_context(store,job))==1
    assert store.job(job['id'])==job


def quiz_job(store,job):
    return store.update_job(job['id'],quiz={'source_hash':job['source_hash'],'checks':{'passed':True},'questions':[{'id':'Q1','question':'합성 문항','choices':['a','b','c','d'],'answer':1,'explanation':'b가 정답인 합성 테스트','evidence':['E1']}]})


def test_learning_contract_and_duplicate_observations_cannot_inflate_counts(context):
    store,job,client,headers=context
    job=quiz_job(store,job)
    path=f'/api/jobs/{job["id"]}'
    contract=client.get(path+'/learning-contract').json()
    assert contract['status']=='ready_for_store_review' and contract['items'][0]['concept_id'].startswith('concept_')
    body={'source_hash':job['source_hash'],'quiz_hash':digest(job['quiz']),'question_id':'Q1','observation_key':'batch_1','attempts':10,'correct':4}
    a=client.post(path+'/learning-observations',json=body,headers=headers)
    assert a.status_code==200 and a.json()['incorrect']==6
    assert client.post(path+'/learning-observations',json=body,headers=headers).json()['id']==a.json()['id']
    assert client.post(path+'/learning-observations',json={**body,'correct':5},headers=headers).status_code==409
    assert client.post(path+'/learning-observations',json={**body,'observation_key':'bad','correct':11},headers=headers).status_code==409
    assert len(client.get(path+'/improvements').json()['learning_observations'])==1


def test_stale_quiz_hash_is_rejected_even_if_source_is_same(context):
    store,job,client,headers=context
    job=quiz_job(store,job)
    body={'source_hash':job['source_hash'],'quiz_hash':digest(job['quiz']),'question_id':'Q1','observation_key':'batch','attempts':1,'correct':0}
    store.update_job(job['id'],quiz={**job['quiz'],'version':2})
    assert client.post(f'/api/jobs/{job["id"]}/learning-observations',json=body,headers=headers).status_code==409


def test_free_orders_and_manual_channel_metrics_do_not_claim_paid_revenue(context):
    store,job,client,headers=context
    body={'source_hash':job['source_hash'],'channel_id':'youtube_main_ko','campaign_id':'','variant_id':'','observed_on':'2026-01-01','period':'7d','external_url':'https://www.youtube.com/watch?v=sample','views':10,'saves':0,'quiz_completed':0,'downloads':1,'free_orders':1,'paid_orders':0,'paid_revenue_krw':0}
    path=f'/api/jobs/{job["id"]}/channel-outcomes'
    assert client.post(path,json={**body,'paid_revenue_krw':1000},headers=headers).status_code==409
    assert client.post(path,json={**body,'external_url':'https://x.example/?token=private'},headers=headers).status_code==409
    good=client.post(path,json=body,headers=headers)
    assert good.status_code==200 and good.json()['verification']=='operator_reported_not_platform_receipt'
    assert store.job(job['id'])==job
    exported=client.get(f'/api/jobs/{job["id"]}/channel-outcomes.csv')
    assert exported.status_code==200 and 'paid_revenue_krw' in exported.text and 'operator_reported_not_platform_receipt' in exported.text


def test_experience_use_can_be_withdrawn_without_changing_past_sources(context):
    store,job,client,headers=context
    body={'title':'옵시디언 합성 관측','axis':'B','facts':'합성 기능 검증용이며 실제 경험 주장이 아닙니다.','evidence_note':'테스트','checked_on':'2026-01-01','tags':['옵시디언'],'confirmed':True,'use_in_content':True}
    card=client.post('/api/experiences',json=body,headers=headers).json()
    path=f'/api/experiences/{card["id"]}/withdraw-use'
    assert client.post(path,json={'expected_hash':'a'*64},headers=headers).status_code==409
    assert client.post(path,json={'expected_hash':digest(card)},headers=headers).status_code==200
    assert experience_context(store,job)==[] and store.job(job['id'])==job


def test_learning_feedback_becomes_unselected_idea_and_stale_conversion_is_blocked(context):
    store,job,client,headers=context
    job=quiz_job(store,job)
    root=f'/api/jobs/{job["id"]}'
    body={'source_hash':job['source_hash'],'quiz_hash':digest(job['quiz']),'question_id':'Q1','observation_key':'concept_day1','attempts':5,'correct':1}
    observation=client.post(root+'/learning-observations',json=body,headers=headers).json()
    path=root+'/learning-observations/'+observation['id']+'/idea'
    result=client.post(path,json={'source_hash':job['source_hash']},headers=headers)
    assert result.status_code==200 and result.json()['idea']['state']=='candidate'
    assert result.json()['status']=='candidate_not_selected' and store.job(job['id'])==job
    assert result.json()['idea']['primary_sources']==0 and result.json()['idea']['blocked']
    store.update_job(job['id'],quiz={**job['quiz'],'version':2})
    assert client.post(path,json={'source_hash':job['source_hash']},headers=headers).status_code==409


def test_registered_local_photos_render_in_safe_draft_preview(context,tmp_path):
    store,job,client,_=context
    image=tmp_path/'original.png';image.write_bytes(b'fixture-image')
    draft=register_assets(store,job['id'],job['source_hash'],'전체 글','![원본 사진](original.png)\n\n<script>alert(1)</script>',[('original.png',image)])
    response=client.get(f'/api/jobs/{job["id"]}/drafts/{draft["id"]}/preview')
    assert response.status_code==200 and f'/drafts/{draft["id"]}/files/original.png' in response.text
    assert '<script>alert(1)</script>' not in response.text and "script-src 'none'" in response.headers['content-security-policy']
