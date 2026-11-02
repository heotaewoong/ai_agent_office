import copy
from fastapi.testclient import TestClient
from office.api import create_app
from office.store import Store


def test_diagnostics_do_not_call_short_intro_an_answer_or_accept_unknown_citations():
    from office.content_diagnostics import analyse_packet
    packet={'title':'전파망원경에 AI 에이전트를 붙인 이유','body':'무관한 도입이에요. [E999]','evidence':[{'id':'E1','url':'https://example.org'}]}
    before=copy.deepcopy(packet);result=analyse_packet(packet)
    by_id={c['id']:c for c in result['blog']}
    assert by_id['intro_length']['passed']
    assert '답' not in by_id['intro_length']['label']
    assert not by_id['citations']['passed'] and 'E999' in by_id['citations']['detail']
    assert packet==before and '성과' in result['note']


def test_empty_and_fenced_markdown_are_not_positive_content_signals():
    from office.content_diagnostics import analyse_packet
    assert not any(c['passed'] for c in analyse_packet({})['blog'])
    assert not any(c['passed'] for c in analyse_packet({'channel_posts':{'threads_main':''}})['social']['threads_main'])
    result=analyse_packet({'body':'```md\n## 소제목 하나\n## 둘\n## 셋\n- 목록\n```'})
    by_id={c['id']:c for c in result['blog']}
    assert not by_id['headings']['passed'] and not by_id['structured']['passed']
    assert not analyse_packet({'body':'본문 [E1]','evidence':None})['blog'][-1]['passed']


def test_current_readonly_diagnostics_do_not_mutate_source_approvals_or_costs(tmp_path):
    store=Store(tmp_path);job=store.create_job({'id':'diagnostics-fixture','title':'합성 검수'})
    job=store.save_source(job['id'],{'title':'검토할 합성 원고','body':'첫 문단이에요. [E1]','evidence':[{'id':'E1','url':'https://example.org'}]})
    before=store.job(job['id'])
    with store.connection() as db:costs_before=list(db.execute('select * from costs'))
    response=TestClient(create_app(store)).get(f"/api/jobs/{job['id']}/content-diagnostics")
    assert response.status_code==200
    assert response.json()['source_hash']==job['source_hash']
    assert store.job(job['id'])==before
    with store.connection() as db:assert list(db.execute('select * from costs'))==costs_before
