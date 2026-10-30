import hashlib
import pytest
from office.store import Store,WorkflowError
from office.social_production import card_paths

def context(tmp_path):
    store=Store(tmp_path/'state');j=store.create_job({'id':'one','title':'글','url':''})
    j=store.save_source(j['id'],{'title':'글','body':'내용','quality':{'status':'passed','critical':False}})
    store.review_source(j['id'],j['source_hash'],'approved','owner',{'cards':True})
    folder=store.artifacts/'out';folder.mkdir()
    slides=[]
    for i in range(7):
        path=store.artifacts/f'card-{i}.png';data=f'card{i}'.encode();path.write_bytes(data)
        slides.append({'artifact':{'path':path.name,'sha256':hashlib.sha256(data).hexdigest()}})
    cards={'source_hash':j['source_hash'],'slides':slides,'checks':{'passed':True,'issues':[]}}
    return store,j,folder,cards

def test_current_cards_are_reused_without_provider_cost(tmp_path,monkeypatch):
    store,j,folder,cards=context(tmp_path);store.update_job(j['id'],cards=cards)
    monkeypatch.setattr('office.cards.plan_cards',lambda *a,**k:pytest.fail('do not regenerate'))
    paths=card_paths(store,j['id'],j['source_hash'],folder)
    assert len(paths)==8 and paths[0].name.startswith('card-news-')

def test_missing_cards_plan_once_with_strict_checks(tmp_path,monkeypatch):
    store,j,folder,cards=context(tmp_path);called=[]
    monkeypatch.setattr('office.cards.plan_cards',lambda *a,**k:called.append(k) or cards)
    assert len(card_paths(store,j['id'],j['source_hash'],folder))==8
    assert called==[{'require_passed':True}]

def test_card_failures_and_duplicate_images_cannot_enter_release_manifest(tmp_path,monkeypatch):
    store,j,folder,cards=context(tmp_path)
    bad={**cards,'checks':{'passed':False,'issues':['65자']}}
    monkeypatch.setattr('office.cards.plan_cards',lambda *a,**k:bad)
    with pytest.raises(WorkflowError,match='검사 이슈'):card_paths(store,j['id'],j['source_hash'],folder)
    cards['slides'][5]=cards['slides'][4];store.update_job(j['id'],cards=cards)
    with pytest.raises(WorkflowError,match='중복'):card_paths(store,j['id'],j['source_hash'],folder)

def test_existing_unknown_card_task_prevents_paid_replanning(tmp_path,monkeypatch):
    store,j,folder,cards=context(tmp_path)
    t=store.enqueue('cards',{'job_id':j['id'],'source_hash':j['source_hash']},key='old')
    store.claim('w');store.finish_task(t['id'],'w',{},state='unknown')
    monkeypatch.setattr('office.cards.plan_cards',lambda *a,**k:pytest.fail('must not spend'))
    with pytest.raises(WorkflowError,match='결과 불명'):card_paths(store,j['id'],j['source_hash'],folder)
