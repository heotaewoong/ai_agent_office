import hashlib,json
import pytest
from fastapi.testclient import TestClient
from office.store import Store,WorkflowError
from office.video_platforms import selected_platforms,set_platforms
from office.api import create_app


def fixture(tmp_path):
 s=Store(tmp_path/'state');j=s.create_job({'id':'video-platforms','title':'합성 검토'})
 j=s.save_source(j['id'],{'title':'합성 검토','body':'그대로 유지할 원문','quality':{'status':'passed','critical':False},'audience':{'language':'ko'},'video':{'title':'영상 제목','description':'기존 설명','scenes':[]}})
 return s,j


def test_legacy_defaults_to_youtube():
 assert selected_platforms({})==['youtube_shorts']


@pytest.mark.parametrize('value',[[],['tiktok'],['youtube_shorts','youtube_shorts'],True,'instagram_reels',[True],None])
def test_invalid_destinations_rejected(value):
 with pytest.raises(WorkflowError):selected_platforms({'video_platforms':value})


def test_destination_changes_preserve_source_approval_and_files(tmp_path):
 from office.video_platforms import effective_packet
 s,j=fixture(tmp_path);j=s.review_source(j['id'],j['source_hash'],'approved','test')
 j=s.save_manifest_if_current(j['id'],j['source_hash'],j['selections'],{'hash':'a'*64,'source_hash':j['source_hash'],'files':[],'completed_outputs':[]})
 s.update_job(j['id'],release_approval={'decision':'approved','version':j['manifest']['hash']})
 budget=s.budget();updated=set_platforms(s,j['id'],j['source_hash'],['instagram_reels'])
 assert updated['source_hash']==j['source_hash']
 assert updated['source_packet']==j['source_packet']
 assert updated['source_approval']==j['source_approval']
 assert updated['release_approval'] is None and updated['manifest']['files']==j['manifest']['files']
 assert updated['manifest']['hash']!=j['manifest']['hash']
 assert effective_packet(updated)['video_platforms']==['instagram_reels']
 assert updated['video_delivery']['channel_registry'] and s.budget()==budget
 with pytest.raises(WorkflowError):set_platforms(s,j['id'],j['source_hash'],['youtube_shorts'],expected_delivery_hash='stale')
 regenerated=s.save_source(j['id'],{**j['source_packet'],'title':'새 제목'},expected_hash=updated['source_hash'])
 assert regenerated['video_delivery']==updated['video_delivery']


def test_stale_selection_and_pending_task_preserve_job(tmp_path):
 s,j=fixture(tmp_path)
 with pytest.raises(WorkflowError):set_platforms(s,j['id'],'0'*64,['instagram_reels'])
 s.enqueue('cards',{'job_id':j['id'],'source_hash':j['source_hash']},key='pending-card')
 with pytest.raises(WorkflowError):set_platforms(s,j['id'],j['source_hash'],['instagram_reels'])
 assert s.job(j['id'])['source_hash']==j['source_hash']


def test_video_exports_reuse_master_but_split_caption(tmp_path):
 from office.exports import write_video_exports
 s,j=fixture(tmp_path);packet={**j['source_packet'],'video_platforms':['youtube_shorts','instagram_reels'],'channel_posts':{'instagram_main':'인스타그램용 캡션'}}
 folder=tmp_path/'export';folder.mkdir()
 files=write_video_exports(packet,folder)
 assert 'instagram-reels-caption.txt' in [p.name for p in files]
 assert (folder/'instagram-reels-caption.txt').read_text()=='인스타그램용 캡션\n'
 assert not (folder/'video-platforms.json').exists()  # No stale destination list in production files.


def test_instagram_only_cannot_use_youtube_release_gate(tmp_path):
 from office.youtube_delivery import _released_video
 s,j=fixture(tmp_path);j=set_platforms(s,j['id'],j['source_hash'],['instagram_reels'])
 with pytest.raises(WorkflowError,match='영상 목적지'):_released_video(s,j['id'])


def test_api_requires_csrf_and_valid_platforms(tmp_path):
 s,j=fixture(tmp_path);c=TestClient(create_app(s),base_url='http://localhost:8510');url=f'/api/jobs/{j["id"]}/video-platforms';body={'version':j['source_hash'],'platforms':['instagram_reels'],'delivery_hash':''}
 assert c.put(url,json=body).status_code==403
 csrf=c.get('/api/session').json()['csrf'];headers={'X-Office-CSRF':csrf,'Origin':'http://localhost:8510'}
 assert c.put(url,json={**body,'platforms':['unknown']},headers=headers).status_code==422
 response=c.put(url,json=body,headers=headers);assert response.status_code==200
 assert response.json()['video_delivery']['platforms']==['instagram_reels']


def test_video_only_reels_staging_keeps_channel_snapshot_and_no_external_draft(tmp_path):
 from office.channels import registry,update_channel
 from office.staging import staging_view
 s,j=fixture(tmp_path);j=set_platforms(s,j['id'],j['source_hash'],['instagram_reels']);selections={'video':True,'blog':False,'cards':False,'pdf':False}
 s.review_source(j['id'],j['source_hash'],'approved','test',selections)
 folder=s.artifacts/j['id']/j['source_hash'];folder.mkdir(parents=True)
 files=[]
 for name,data in [('short.mp4',b'synthetic-video'),('instagram-reels-caption.txt','검토 캡션'.encode()),('description.txt','영상 설명'.encode())]:
  p=folder/name;p.write_bytes(data);files.append({'name':name,'path':p.relative_to(s.artifacts).as_posix(),'sha256':hashlib.sha256(data).hexdigest(),'bytes':len(data),'outputs':['video']})
 m={'hash':'m'*64,'source_hash':j['source_hash'],'files':files,'completed_outputs':['video'],'output_status':{'video':{'state':'completed'}},'thumbnail_candidates':[{'id':'thumb-1','name':'thumb-1.png'}]}
 s.save_manifest_if_current(j['id'],j['source_hash'],selections,m);j=s.select_thumbnail(j['id'],'thumb-1',m['hash'],'test');s.review_release(j['id'],j['manifest']['hash'],'approved','test',True,['video'])
 rows={x['channel_key']:x for x in staging_view(s,j['id'])['channels']}
 assert rows['instagram_main']['local_ready'] is True
 assert rows['instagram_main']['external_draft_created'] is False
 assert rows['instagram_main']['video_destination']=='instagram_reels'
 assert rows['youtube_main_ko']['local_ready'] is False
 update_channel(s,'instagram_main',{'public_url':'https://www.instagram.com/changed'},actor='test')
 rows={x['channel_key']:x for x in staging_view(s,j['id'])['channels']}
 assert rows['instagram_main']['local_ready'] is False
 assert any('채널 설정' in x for x in rows['instagram_main']['blockers'])
