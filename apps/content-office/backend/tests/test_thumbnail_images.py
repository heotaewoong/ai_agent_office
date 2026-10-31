import base64,io
import pytest,requests
from PIL import Image
from office.store import Store,WorkflowError
from office.thumbnail_images import generate,enqueue,view
from office.api import create_app
from fastapi.testclient import TestClient


def fixture(tmp_path,monkeypatch):
 monkeypatch.setenv('OPENAI_API_KEY','synthetic-not-a-key')
 s=Store(tmp_path/'state');j=s.create_job({'id':'thumbnail-fixture','title':'확정 제목'})
 j=s.save_source(j['id'],{'title':'확정 제목','body':'원고의 실제 공부 루틴과 책상에 있는 노트 이야기입니다.','synthetic_fixture':True,'quality':{'status':'passed','critical':[]},'video':{'title':'확정 제목','scenes':[{'caption':'노트','narration':'공부 루틴을 설명합니다.'}]}})
 j=s.review_source(j['id'],j['source_hash'],'approved','synthetic',{'video':True})
 j=s.save_manifest_if_current(j['id'],j['source_hash'],j['selections'],{'source_hash':j['source_hash'],'hash':'a'*64,'files':[],'thumbnail_candidates':[],'completed_outputs':['video']})
 return s,j


def transport():
 calls=[]
 def post(url,**kwargs):
  calls.append((url,kwargs['json']))
  stream=io.BytesIO();Image.new('RGB',(320,180),(len(calls)*30,80,110)).save(stream,'PNG')
  class Response:
   status_code=200
   def json(self):return {'data':[{'b64_json':base64.b64encode(stream.getvalue()).decode()}],'usage':{'input_tokens':10,'output_tokens':100,'input_tokens_details':{'text_tokens':10,'image_tokens':0}}}
  return Response()
 return calls,post


def payload(j,**extra):return {'job_id':j['id'],'source_hash':j['source_hash'],'manifest_hash':j['manifest']['hash'],'model':view_model(),'paid_confirmed':True,'parent_id':None,'feedback':'',**extra}
def view_model():
 from office.image_provider import MODEL
 return MODEL


def test_three_real_assets_fixed_title_and_human_final_choice(tmp_path,monkeypatch):
 s,j=fixture(tmp_path,monkeypatch);calls,post=transport();approved=j['source_approval'];old_hash=j['source_hash']
 result=generate(s,payload(j),transport=post);current=s.job(j['id']);manifest=current['manifest']
 assert len(calls)==3 and all('/generations' in url for url,_ in calls)
 assert len(manifest['thumbnail_candidates'])==3
 assert {r['title'] for r in manifest['thumbnail_candidates']}=={'확정 제목'}
 assert all('원고의 실제 공부 루틴' in p['prompt'] for _,p in calls)
 assert current['source_hash']==old_hash and current['source_approval']==approved
 assert current['release_approval'] is None and manifest.get('selected_thumbnail_id') is None
 for c in manifest['thumbnail_candidates']:
  assert Image.open(s.artifacts/c['path']).size==(1280,720)
  assert c['image_provider']=='openai' and c['human_selection']=='pending'
 selected=s.select_thumbnail(j['id'],result['candidate_ids'][1],manifest['hash'],'synthetic-human')
 assert selected['manifest']['selected_thumbnail_id']==result['candidate_ids'][1]


def test_refine_sends_selected_background_to_edits_and_keeps_history(tmp_path,monkeypatch):
 s,j=fixture(tmp_path,monkeypatch);calls,post=transport();generate(s,payload(j),transport=post)
 j=s.job(j['id']);first=j['manifest']['thumbnail_candidates'][0]
 generate(s,payload(j,parent_id=first['id'],feedback='배경만 더 단순하게'),transport=post)
 current=s.job(j['id']);last=current['manifest']['thumbnail_candidates'][-1]
 assert calls[-1][0].endswith('/images/edits')
 assert calls[-1][1]['images'][0]['image_url'].startswith('data:image/png;base64,')
 assert '배경만 더 단순하게' in calls[-1][1]['prompt']
 assert last['parent_id']==first['id'] and len(current['thumbnail_image_history'])==2
 assert (s.artifacts/first['path']).is_file()
 assert current['manifest'].get('selected_thumbnail_id') is None


def test_unconfirmed_stale_and_closed_do_not_call_or_spend(tmp_path,monkeypatch):
 s,j=fixture(tmp_path,monkeypatch);before=s.budget();calls,post=transport()
 with pytest.raises(WorkflowError):enqueue(s,j['id'],j['source_hash'],j['manifest']['hash'],confirmed=False)
 with pytest.raises(WorkflowError):generate(s,payload(j,manifest_hash='b'*64),transport=post)
 s.set_setting('work_window',{'status':'closed'})
 with pytest.raises(WorkflowError):generate(s,payload(j),transport=post)
 assert calls==[] and s.budget()==before


def test_parent_tampering_and_unknown_result_are_never_retried(tmp_path,monkeypatch):
 s,j=fixture(tmp_path,monkeypatch);calls,post=transport();generate(s,payload(j),transport=post)
 j=s.job(j['id']);parent=j['manifest']['thumbnail_candidates'][0];(s.artifacts/parent['background']['path']).write_bytes(b'changed')
 with pytest.raises(WorkflowError):generate(s,payload(j,parent_id=parent['id'],feedback='수정'),transport=post)
 assert len(calls)==3
 def timeout(*a,**k):calls.append('timeout');raise requests.Timeout()
 # New synthetic source is isolated from the modified-parent case.
 s2,j2=fixture(tmp_path/'other',monkeypatch)
 with pytest.raises(WorkflowError):generate(s2,payload(j2),transport=timeout)
 with pytest.raises(WorkflowError):generate(s2,payload(j2),transport=timeout)
 assert calls.count('timeout')==1 and s2.budget()['reserved_krw']>0


def test_pending_image_task_blocks_final_choice_and_release(tmp_path,monkeypatch):
 s,j=fixture(tmp_path,monkeypatch);calls,post=transport();generate(s,payload(j),transport=post);j=s.job(j['id'])
 s.enqueue('thumbnail_images',{'job_id':j['id'],'source_hash':j['source_hash']},key='pending')
 with pytest.raises(WorkflowError,match='썸네일'):s.select_thumbnail(j['id'],j['manifest']['thumbnail_candidates'][0]['id'],j['manifest']['hash'],'synthetic')
 with pytest.raises(WorkflowError,match='썸네일'):s.review_release(j['id'],j['manifest']['hash'],'approved','synthetic',True,['video'])


def test_api_requires_csrf_confirmation_and_current_version(tmp_path,monkeypatch):
 s,j=fixture(tmp_path,monkeypatch);c=TestClient(create_app(s),base_url='http://localhost:8510');url=f'/api/jobs/{j["id"]}/thumbnail-images'
 body={'source_hash':j['source_hash'],'manifest_hash':j['manifest']['hash'],'confirm_paid':True}
 assert c.post(url,json=body).status_code==403
 csrf=c.get('/api/session').json()['csrf'];h={'X-Office-CSRF':csrf,'Origin':'http://localhost:8510'}
 assert c.post(url,json={**body,'confirm_paid':'true'},headers=h).status_code==422
 assert c.post(url,json={**body,'confirm_paid':False},headers=h).status_code==409
 result=c.post(url,json=body,headers=h);assert result.status_code==202
 assert result.json()['kind']=='thumbnail_images'
 assert c.get(url).json()['ready'] is False
