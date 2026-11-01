import copy
from datetime import datetime, timezone

import pytest
from fastapi.testclient import TestClient

from office.api import create_app
from office.feeds import parse_date, rank_articles
from office.store import Store


@pytest.mark.parametrize('value', ['2026-11-01T01:02:03+00:00', '2026-11-01T01:02:03Z', '2026-11-01T10:02:03+09:00', 'Sun, 01 Nov 2026 01:02:03 GMT'])
def test_dates_keep_the_same_utc_instant(value):
    assert parse_date(value) == datetime(2026,11,1,1,2,3,tzinfo=timezone.utc)


@pytest.mark.parametrize('value', [None,'','invalid','2026-11-01T01:02:03'])
def test_missing_invalid_or_naive_dates_remain_ineligible(value):
    assert parse_date(value) is None


def test_url_duplicates_merge_public_signals_without_changing_inputs():
    article={'id':'first','title':'AI agent launch','url':'https://example.com/story?utm_source=rss','summary':'open source tool','published_at':'2026-11-01T01:02:03Z','signals':{'views':1}}
    rows=[article,{**article,'id':'second','url':'https://example.com/story/','signals':{'views':2,'comments':4}}, {**article,'id':'third','url':'https://example.com/story?ref=community','signals':{'views':3}}]
    before=copy.deepcopy(rows)
    result=rank_articles(rows,datetime(2026,11,1,2,tzinfo=timezone.utc))
    assert len(result)==1 and result[0]['id']=='first'
    assert result[0]['signals']=={'views':3,'comments':4}
    assert len(result[0]['related_sources'])==2
    assert rows==before


def test_dashboard_reads_articles_once_but_new_requests_see_new_rows(tmp_path,monkeypatch):
    store=Store(tmp_path)
    article={'id':'one','title':'AI agent launch','url':'https://example.com/one','summary':'official API tool','published_at':datetime.now(timezone.utc).isoformat()}
    store.save_articles([article])
    original=store.articles_list
    reads=[]
    def counted():
        reads.append(True)
        return original()
    monkeypatch.setattr(store,'articles_list',counted)
    client=TestClient(create_app(store),base_url='http://localhost:8510')
    first=client.get('/api/dashboard?compact=true')
    assert first.status_code==200
    assert len(reads)==1
    store.save_articles([{**article,'id':'two','url':'https://example.com/two','title':'A separate release'}])
    second=client.get('/api/dashboard?compact=true')
    assert second.status_code==200 and len(reads)==2
    assert {a['id'] for a in second.json()['articles']}=={'one','two'}


@pytest.mark.parametrize("state", ["failed", "unknown", "partial", "running"])
def test_completed_results_can_be_omitted_but_failures_and_detail_remain(tmp_path, state):
    from office.store import canonical
    store=Store(tmp_path)
    job=store.create_job({'id':'source','title':'Synthetic source'})
    done=store.enqueue('draft',{'job_id':job['id'],'source_hash':None},key='done')
    failed=store.enqueue('evaluate',{'job_id':job['id'],'source_hash':None},key='failed')
    done_result={'source_packet':{'body':'synthetic-long-body'*20000},'quality':{'passed':True}}
    failure={'error':'synthetic failure','details':{'recoverable':False}}
    with store.connection(transaction=True) as db:
        db.execute('update tasks set state=?,result=? where id=?',('completed',canonical(done_result),done['id']))
        db.execute('update tasks set state=?,result=? where id=?',(state,canonical(failure),failed['id']))
    before=[store.task(done['id']),store.task(failed['id'])]
    client=TestClient(create_app(store),base_url='http://localhost:8510')
    full=client.get('/api/dashboard?compact=true')
    lean=client.get('/api/dashboard?compact=true&task_results=false')
    records={t['id']:t for t in lean.json()['tasks']}
    assert records[done['id']]['result'] is None and records[done['id']]['result_omitted'] is True
    assert records[failed['id']]['result']==failure
    assert records[done['id']]['payload']==before[0]['payload']
    assert len(lean.content)<len(full.content)/5
    assert next(t for t in full.json()['tasks'] if t['id']==done['id'])['result']==done_result
    detail=client.get('/api/jobs/'+job['id']).json()
    assert next(t for t in detail['tasks'] if t['id']==done['id'])['result']==done_result
    assert [store.task(done['id']),store.task(failed['id'])]==before
    assert client.get('/api/dashboard?task_results=invalid').status_code==422
