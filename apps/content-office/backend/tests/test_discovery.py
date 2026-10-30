import copy
import json
from datetime import datetime, timedelta, timezone
import pytest
from fastapi.testclient import TestClient
from office.store import Store, WorkflowError, digest
from office import discovery, bootstrap
from office.api import create_app
from office.feeds import parse_feed, rank_articles
from office.public_sources import hn_articles, annotate_feed


def active(store):
    store.set_setting('work_window', {'status': 'active', 'user_confirmed': True, 'authorized_end': (datetime.now(timezone.utc)+timedelta(minutes=5)).isoformat()})


def protected(store):
    with store.connection() as db:
        return {t:[tuple(r) for r in db.execute('SELECT * FROM '+t+' ORDER BY 1')] for t in ('jobs','versions','approvals','costs','drafts')}


def test_platform_routes_choose_different_external_sources_without_new_provider_credentials():
    linkedin = discovery.feeds_for({**discovery.DEFAULT, 'platforms': ['linkedin']})
    instagram = discovery.feeds_for({**discovery.DEFAULT, 'platforms': ['instagram'], 'region': 'JP'})
    assert any(r['format']=='google-news' for r in linkedin if 'format' in r)
    assert not any(r.get('format')=='google-trends' for r in linkedin)
    assert not any(r.get('format')=='google-news' for r in instagram)
    assert next(r for r in instagram if r.get('format')=='google-trends')['url'].endswith('geo=JP')
    assert {'hacker-news','youtube-openai','youtube-google','moe-exam'} <= {r['id'] for r in linkedin}


@pytest.mark.parametrize('change', [{'platforms':['unknown']},{'topic':'\n'},{'youtube_channels':['https://127.0.0.1']},{'region':'XX'},{'platforms':[]}])
def test_untrusted_research_settings_do_not_save_or_queue(tmp_path,change):
    s=Store(tmp_path)
    with pytest.raises(WorkflowError):discovery.save(s,{**discovery.DEFAULT,**change},digest(discovery.DEFAULT))
    assert s.setting('discovery_config') is None and s.tasks()==[]


def test_save_automatically_queues_but_does_not_open_window_call_models_or_touch_protected_records(tmp_path,monkeypatch):
    s=Store(tmp_path);s.set_setting('work_window',{'status':'closed','user_confirmed':True,'authorized_end':'2026-01-01T00:00:00+00:00'})
    j=s.create_job({'id':'synthetic','title':'기존 원고'})
    j=s.save_source(j['id'],{'title':'기존','body':'보존','quality':{'status':'passed','critical':False}})
    s.review_source(j['id'],j['source_hash'],'approved','synthetic-human',{'blog':True})
    c=s.reserve_cost('model',10,{'job_id':j['id']});s.unknown_cost(c['id'],'synthetic')
    s.add_draft(j['id'],{'title':'검토본','body':'보존'})
    before=protected(s);budget=copy.deepcopy(s.budget());window=s.setting('work_window')
    task=discovery.save(s,{**discovery.DEFAULT,'platforms':['youtube']},digest(discovery.DEFAULT))
    assert task['kind']=='discover' and task['state']=='queued'
    assert protected(s)==before and s.budget()==budget and s.setting('work_window')==window
    with pytest.raises(WorkflowError,match='작업 시간'):discovery.run(s,task['payload']['config_hash'])
    with pytest.raises(WorkflowError,match='다른 화면'):discovery.save(s,discovery.DEFAULT,digest(discovery.DEFAULT))


def test_metadata_run_adds_news_and_platform_results_and_uses_cache_without_model_calls(tmp_path,monkeypatch):
    s=Store(tmp_path);active(s)
    stamp=datetime.now(timezone.utc).isoformat()
    rows=[{'id':kind,'title':'New AI agent tool '+kind,'url':'https://example.com/'+kind,'feed_id':kind,'feed_name':kind,'segment':'ai','source_kind':kind,'published_at':stamp,'retrieved_at':stamp,'score':80,'signals':{'youtube_views':42} if kind=='youtube' else {'hn_points':9}} for kind in ('youtube','community')]
    calls=[]
    def collect(root,feeds=None):
        calls.append(feeds)
        return {'checked_at':stamp,'feeds':[{'id':r['id'],'name':r['name'],'state':'ok','count':1} for r in feeds], 'articles':copy.deepcopy(rows),'total_items':2,'eligible_items':2,'days':7,'partial_failure':False}
    monkeypatch.setattr(bootstrap,'collect_feeds',collect)
    monkeypatch.setattr(bootstrap,'korean_cards',lambda *a,**k:pytest.fail('Metadata research must not call models'))
    s.set_setting('discovery_config',{**discovery.DEFAULT,'platforms':['youtube','linkedin']})
    before=protected(s);budget=s.budget()
    discovery.run(s,digest(discovery.config(s)))
    report=discovery.status(s)['snapshot']
    assert report['recommendations']['youtube'][0]['kind']=='youtube'
    assert report['recommendations']['linkedin'][0]['kind']=='community'
    assert len(s.articles_list())==2 and protected(s)==before and s.budget()==budget
    assert discovery.run(s)['cached'] and len(calls)==1
    s.set_setting('discovery_config',{**discovery.DEFAULT,'platforms':['x']})
    assert discovery.status(s)['stale']
    with pytest.raises(WorkflowError,match='조사 조건'):discovery.run(s,digest(discovery.DEFAULT))
    s.set_setting('feed_report',{'active_article_ids':[]})
    discovery.save(s,{**discovery.DEFAULT,'platforms':['youtube','linkedin']},digest(discovery.config(s)))
    assert set(s.setting('feed_report')['active_article_ids'])=={'youtube','community'}
    assert discovery.run(s)['cached'] and len(calls)==1
    assert not discovery.status(s)['stale']


def test_hn_public_api_scan_is_bounded_and_deleted_non_ai_items_are_not_news():
    calls=[]
    def fetch(url,**kwargs):
        identity=int(url.rsplit('/',1)[-1].split('.')[0]);calls.append(identity)
        row={'id':identity,'type':'story','title':'AI agent release' if identity%2 else 'Sports today','time':int(datetime.now(timezone.utc).timestamp()),'url':'https://example.com/'+str(identity),'score':12,'descendants':3}
        if identity==1:row['deleted']=True
        return json.dumps(row).encode(),url,'application/json'
    rows=hn_articles(json.dumps(list(range(1,60))).encode(),{'id':'hacker-news','name':'HN','topics':['AI']},fetch)
    assert len(calls)==24 and 1 not in [int(r['url'].rsplit('/',1)[-1]) for r in rows]
    assert all(r['source_kind']=='community' and r['signals']['hn_points']==12 for r in rows)
    with pytest.raises(ValueError):hn_articles(b'["../../secret"]',{},fetch)


def test_youtube_counters_and_trends_topic_filter_are_not_fabricated():
    stamp=datetime.now(timezone.utc).isoformat()
    feed={'id':'yt','name':'YT','format':'youtube'}
    raw=f'''<feed xmlns="http://www.w3.org/2005/Atom" xmlns:media="http://search.yahoo.com/mrss/"><entry><title>AI agent</title><link rel="alternate" href="https://www.youtube.com/watch?v=test"/><published>{stamp}</published><media:group><media:community><media:statistics views="123"/></media:community></media:group></entry></feed>'''.encode()
    rows=annotate_feed(raw,parse_feed(raw,feed),feed)
    assert rows[0]['signals']=={'youtube_views':123} and '증가율' in rows[0]['signal_note']
    trends=f'''<rss xmlns:ht="https://trends.google.com/trending/rss"><channel><item><title>AI agent</title><link>https://trends.google.com/a</link><pubDate>{stamp}</pubDate><ht:approx_traffic>10K+</ht:approx_traffic></item><item><title>Baseball</title><link>https://trends.google.com/b</link><pubDate>{stamp}</pubDate></item></channel></rss>'''.encode()
    feed={'id':'trends','name':'Trends','format':'google-trends','topic':'AI 자동화'}
    rows=annotate_feed(trends,parse_feed(trends,feed),feed)
    assert len(rows)==1 and rows[0]['signals']['search_volume_label']=='10K+'


def test_api_requires_csrf_rejects_conflicts_and_preserves_read_only_get(tmp_path):
    s=Store(tmp_path);client=TestClient(create_app(s),base_url='http://localhost:8510')
    before=protected(s);value=client.get('/api/discovery').json()
    assert value['snapshot'] is None and protected(s)==before and s.tasks()==[]
    body={**value['config'],'expected_hash':value['config_hash']}
    assert client.put('/api/discovery',json=body).status_code==403
    headers={'Origin':'http://localhost:3110','X-Office-CSRF':client.get('/api/session').json()['csrf']}
    response=client.put('/api/discovery',json=body,headers=headers)
    assert response.status_code==200 and response.json()['task']['state']=='queued'
    assert len(s.tasks())==1 and protected(s)==before
    body['expected_hash']='0'*64
    assert client.put('/api/discovery',json=body,headers=headers).status_code==409


def test_news_first_page_is_diverse_and_duplicate_metrics_survive_without_mutating_inputs():
    from office.source_registry import visible_articles
    rows=[{'id':str(i),'segment':'ai','feed_id':'arxiv'} for i in range(90)]+[{'id':'yt','segment':'ai','feed_id':'youtube'},{'id':'hn','segment':'ai','feed_id':'hn'},{'id':'exam','segment':'exam','feed_id':'moe'}]
    shown=visible_articles(rows)
    assert {'youtube','hn','moe'} <= {r['feed_id'] for r in shown[:6]} and len(shown)==80
    stamp=datetime.now(timezone.utc).isoformat()
    first={'id':'one','title':'An AI agent release','url':'https://example.com/a','published_at':stamp}
    second={**first,'id':'two','source_kind':'community','signals':{'hn_points':25}}
    ranked=rank_articles([first,second])
    assert len(ranked)==1 and ranked[0]['signals']['hn_points']==25 and 'signals' not in first
