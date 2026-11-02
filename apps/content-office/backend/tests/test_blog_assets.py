import hashlib,json
from PIL import Image
import pytest
from office.store import Store,WorkflowError
from office.media import artifact_record


def fixture(tmp_path):
    store=Store(tmp_path/'state');job=store.create_job({'id':'one','title':'전파망원경','url':'https://example.org/research'})
    p={'title':'전파망원경에 AI를 붙인 이유','body':'## 관측과 분석\n\n전파망원경 관측을 연결합니다.','quality':{'status':'passed','critical':False}}
    job=store.save_source(job['id'],p);store.review_source(job['id'],job['source_hash'],'approved','synthetic',{'blog':True})
    input_folder=store.artifacts/job['id']/job['source_hash']/'cards';input_folder.mkdir(parents=True)
    slides=[]
    for i in range(6):
        path=input_folder/f'card-{i}.png';Image.new('RGB',(100,100),(i*30,40,50)).save(path)
        slides.append({'index':i+1,'title':'관측을 연결','artifact':artifact_record(store.artifacts,path)})
    cards={'source_hash':job['source_hash'],'checks':{'passed':True},'slides':slides}
    store.update_job(job['id'],cards=cards)
    folder=store.artifacts/job['id']/job['source_hash']/'production-test';folder.mkdir(parents=True)
    return store,store.job(job['id']),folder


def test_blog_reuses_verified_current_cards_and_packages_same_bytes(tmp_path):
    from office.blog_assets import collect_assets,compose_body
    from office.exports import write_blog_exports
    store,job,folder=fixture(tmp_path)
    images,paths,meta=collect_assets(store,job,folder)
    assert len(images)==6 and images[0]['kind']=='card'
    assert paths[0].read_bytes()==(store.artifacts/job['cards']['slides'][0]['artifact']['path']).read_bytes()
    files=write_blog_exports(job['source_packet'],folder,images=images)
    html=(folder/'tistory.html').read_text(encoding='utf-8')
    assert '<img src="blog-image-01.png"' in html
    assert '관측을 연결' in html and '카드로 다시 보는 핵심 내용' in html
    assert job['source_packet']['body']=='## 관측과 분석\n\n전파망원경 관측을 연결합니다.'
    assert meta['source_hash']==job['source_hash']


def test_blog_ignores_previous_source_and_blocks_tampered_current_card(tmp_path):
    from office.blog_assets import collect_assets
    store,job,folder=fixture(tmp_path)
    job['cards']['source_hash']='old'
    assert collect_assets(store,job,folder)[0]==[]
    job['cards']['source_hash']=job['source_hash'];(store.artifacts/job['cards']['slides'][0]['artifact']['path']).write_bytes(b'changed')
    with pytest.raises(WorkflowError):collect_assets(store,job,folder)


def test_selected_but_not_finalized_thumbnail_is_not_auto_picked(tmp_path):
    from office.blog_assets import collect_assets
    store,job,folder=fixture(tmp_path)
    job['cards']={};job['thumbnail_studio']={'source_hash':job['source_hash'],'selected_id':'candidate','candidates':[]}
    assert collect_assets(store,job,folder)[0]==[]


def test_finalized_same_source_thumbnail_reuses_exact_bytes(tmp_path):
    from office.blog_assets import collect_assets
    store,job,folder=fixture(tmp_path)
    photo=folder/'final-cover.png';Image.new('RGB',(1280,720),'#234567').save(photo)
    record=artifact_record(store.artifacts,photo)
    job['thumbnail_studio']={'source_hash':job['source_hash'],'selected_id':'final','finalized_id':'final','finalized_format':'landscape','candidates':[{'id':'final','image':record}]}
    images,_,_=collect_assets(store,job,folder)
    assert images[0]['kind']=='thumbnail' and (folder/'blog-image-00.png').read_bytes()==photo.read_bytes()


def test_current_blog_asset_dependency_change_invalidates_release_bundle(tmp_path):
    from office.blog_assets import collect_assets,verify_manifest
    store,job,folder=fixture(tmp_path)
    images,paths,meta=collect_assets(store,job,folder)
    record={**artifact_record(store.artifacts,folder/'blog-assets.json'),'outputs':['blog']}
    manifest={'source_hash':job['source_hash'],'files':[record,*[{**artifact_record(store.artifacts,p),'outputs':['blog']} for p in paths if p.name!='blog-assets.json']]}
    verify_manifest(store,job,manifest)
    job['cards']['slides'][0]['title']='변경한 카드'
    with pytest.raises(WorkflowError,match='이미지'):verify_manifest(store,job,manifest)


def test_blog_release_preview_and_staging_include_verified_image_bundle(tmp_path):
    from office.blog_assets import collect_assets
    from office.exports import write_blog_exports
    from office.api import _local_photo_preview
    from office.store import digest
    from office.staging import staging_view
    store,job,folder=fixture(tmp_path)
    packet={**job['source_packet'],'audience':{'language':'ko'}}
    # The approval is synthetic fixture data; no operating job is touched.
    images,paths,_=collect_assets(store,job,folder)
    paths+=write_blog_exports(packet,folder,images=images)
    manifest={'source_hash':job['source_hash'],'completed_outputs':['blog'],'files':[{**artifact_record(store.artifacts,p),'outputs':['blog']} for p in paths]}
    manifest['hash']=digest(manifest)
    store.save_manifest_if_current(job['id'],job['source_hash'],job['selections'],manifest)
    store.review_release(job['id'],manifest['hash'],'approved','synthetic',outputs=['blog'])
    latest=store.job(job['id']);html=(folder/'tistory.html').read_text(encoding='utf-8')
    localized=_local_photo_preview(store,latest,folder/'tistory.html',html)
    assert 'src="blog-image-' not in localized and '/api/artifacts/' in localized
    view=staging_view(store,job['id']);tistory=next(r for r in view['channels'] if r['channel_key']=='tistory_main')
    assert 'blog-image-01.png' in tistory['required_files'] and 'blog-assets.json' in tistory['required_files']
    (folder/'blog-image-01.png').write_bytes(b'changed')
    with pytest.raises(WorkflowError,match='이미지'):store.review_release(job['id'],manifest['hash'],'approved','synthetic',outputs=['blog'])
