"""Native research uses fixture receipts only: no model, Slack or live service calls."""
import copy
import hashlib
from datetime import datetime, timedelta, timezone
from uuid import uuid4

import pytest

from office import assistant_requests, benchmark_research, benchmarks
from office.store import Store, WorkflowError, digest


class Native:
    def __init__(self):
        self.cards, self.details, self.posts = [], {}, []
        self.delivery_reads = self.subscriptions = 0
        self.timeout_after_create = False

    def board(self):
        return {'columns': [{'name': 'ready', 'tasks': copy.deepcopy(self.cards)}]}

    def create(self, payload):
        self.posts.append(copy.deepcopy(payload))
        card = {**copy.deepcopy(payload), 'id': 't_root', 'status': 'ready', 'created_at': 1,
                'current_run_id': None}
        self.cards.append(card)
        self.details['t_root'] = {'task': card, 'events': [], 'runs': [], 'links': {'parents': [], 'children': []}}
        if self.timeout_after_create:
            raise TimeoutError('fixture admission response lost')
        return {'task': copy.deepcopy(card)}

    def task(self, ident):
        return copy.deepcopy(self.details[ident])

    def delivery_status(self, task_id, request_id):
        self.delivery_reads += 1
        return {'task_id': task_id, 'request_id': request_id, 'state': 'not_attached'}

    def subscribe(self, task_id, request_id):
        self.subscriptions += 1
        return {'task_id': task_id, 'request_id': request_id, 'state': 'watching'}


def open_window(store):
    store.set_setting('work_window', {'status': 'active', 'user_confirmed': True,
        'authorized_end': (datetime.now(timezone.utc) + timedelta(hours=1)).isoformat()})


@pytest.fixture
def research(tmp_path):
    store = Store(tmp_path)
    native = Native()
    overview = benchmarks.status(store)
    source = next(row for row in overview['registry']['sources'] if row['platform'] == 'instagram')
    stamp = datetime.now(timezone.utc).isoformat()
    item = {'id': 'benchmark-public-observation', 'title': '공개 게시물 관측',
        'url': 'https://www.instagram.com/p/observed123/', 'source_id': source['id'],
        'creator_id': source['creator_id'], 'source_name': source['name'], 'platform': 'instagram',
        'fields': source['fields'], 'summary': '직접 읽은 공개 화면의 독립 요약',
        'published_at': stamp, 'checked_at': stamp, 'verification_state': 'metadata_only',
        'metrics': {'likes': {'value': 29, 'availability': 'observed', 'raw_text': '29', 'precision': 'exact'}},
        'provenance': {'method': 'browser_public_observation', 'source_url': source['url'],
            'observed_at': stamp, 'capture_sha256': 'a' * 64, 'source_hash': digest(source),
            'scope': '공개 DOM 관측만; 동영상 시청·다운로드 없음'}}
    snapshot = {'registry_hash': overview['registry_hash'], 'checked_at': stamp,
                'items': [item], 'sources_status': []}
    store.set_setting('benchmark_snapshot', snapshot)
    open_window(store)
    body = {'request_id': str(uuid4()), 'source_ids': [source['id']], 'fields': [], 'platforms': [],
            'expected_hash': overview['registry_hash'], 'item_ids': [item['id']],
            'snapshot_hash': benchmarks.status(store)['snapshot_hash']}
    return store, native, body, item


def protected(store):
    with store.connection() as db:
        return {table: [tuple(row) for row in db.execute('SELECT * FROM ' + table)]
                for table in ('jobs', 'approvals', 'costs', 'versions', 'drafts')}


def completed(native, worker='mybots-sage', reviewer='ada', summary=None):
    summary = summary or '# 공개 관측을 직접 검증하는 콘텐츠 기획\n\n' + '공개 자료의 주장과 관측 수치를 구분하고 직접 재현할 절차와 반례를 정리합니다. ' * 5
    key = native.cards[0]['idempotency_key']
    actors = [('t_root', '', 'lumi'), ('t_work', ':work', worker),
              ('t_verify', ':verify', reviewer), ('t_final', ':final', 'lumi')]
    for run_id, (ident, suffix, actor) in enumerate(actors, 1):
        task = {**(native.cards[0] if ident == 't_root' else {}), 'id': ident,
                'idempotency_key': key + suffix, 'tenant': 'heobrain-world', 'assignee': actor,
                'status': 'done', 'created_at': 1, 'current_run_id': None}
        native.details[ident] = {'task': task,
            'runs': [{'id': run_id, 'task_id': ident, 'profile': actor, 'status': 'done',
                'outcome': 'completed', 'ended_at': run_id * 10,
                'summary': summary if ident == 't_final' else '역할별 fixture 실행 영수증'}],
            'events': [{'id': run_id * 10, 'task_id': ident, 'run_id': run_id,
                        'kind': 'completed', 'created_at': run_id * 10}],
            'links': {'parents': [], 'children': []}}
    for parent, child in [('t_root', 't_work'), ('t_work', 't_verify'), ('t_work', 't_final'), ('t_verify', 't_final')]:
        native.details[parent]['links']['children'].append(child)
        native.details[child]['links']['parents'].append(parent)


def idea_input(run, item):
    return {'item_id': item['id'], 'title': '내 자료로 공개 주장을 확인하기',
            'angle': '공개 관측을 출발점으로 직접 재현하고 반례를 함께 보여준다',
            'target_platforms': ['youtube'], 'receipt': run['analysis_receipt']}


@pytest.mark.parametrize('reference', [
    'https://www.youtube.com/watch?v=--Quy-4QTMs',
    'http://example.com/public-source',
    'HTTPS://www.instagram.com/p/De6OvlsFfaA/',
])
def test_completed_research_accepts_public_source_urls(research, reference):
    store, native, body, _ = research
    benchmark_research.submit_run(store, native, body)
    summary = '# 공개 관측 조사 보고\n\n' + ('공개 관측과 추론을 구분하고 독립 검토한 결과를 정리합니다. ' * 8) + reference
    completed(native, summary=summary)
    before = protected(store)
    result = benchmark_research.read_run(store, native, body['request_id'])
    assert result['execution']['status'] == 'completed'
    assert result['execution']['report']['summary'] == summary
    assert result['analysis_receipt']['report_sha256'] == hashlib.sha256(summary.encode()).hexdigest()
    assert protected(store) == before
    assert len(native.posts) == 1 and native.subscriptions == native.delivery_reads == 0


@pytest.mark.parametrize('private_text', [
    r'C:\Users\owner\private.txt', 'D:/private/report.md',
    r'prefixC:\Users\owner\private.txt', r'httpS:\Users\owner\private.txt',
    'P:/private/report.md', 'S://private/report.md', 'file:///C:/private/report.md',
    '/home/owner/private.txt', '%2fhome%2fowner', '../private.txt', r'..\private.txt',
    'https://example.com/home/owner/private.txt',
    'Bearer private-value', 'token=private-value', 'api_key: private-value',
    'xoxb-123456789012-secret', '\u202ereversed', '\x01control',
])
def test_completed_research_still_blocks_private_paths_and_secrets(research, private_text):
    store, native, body, _ = research
    benchmark_research.submit_run(store, native, body)
    completed(native, summary=('공개 원문을 검토한 결과입니다. ' * 8) + '\nhttps://example.com/public\n' + private_text)
    before = protected(store)
    result = benchmark_research.read_run(store, native, body['request_id'])
    assert result['execution']['status'] == 'blocked'
    assert result['execution']['error']['code'] == 'report_redaction_required'
    assert result['execution']['report'] is None and result['analysis_receipt'] is None
    assert protected(store) == before
    assert len(native.posts) == 1 and native.subscriptions == native.delivery_reads == 0


def test_closed_window_and_exhausted_budget_do_not_admit_or_reserve(research):
    store, native, body, _ = research
    store.set_setting('work_window', {'status': 'closed'})
    before = protected(store)
    with pytest.raises(WorkflowError):
        benchmark_research.submit_run(store, native, body)
    assert store.setting('benchmark_research_run:' + body['request_id']) is None
    open_window(store)
    store.set_setting('budget_cap', 0)
    with pytest.raises(WorkflowError):
        benchmark_research.submit_run(store, native, body)
    assert native.posts == [] and protected(store) == before


def test_research_freezes_public_observation_and_same_uuid_posts_once_without_delivery(research):
    store, native, body, item = research
    before = protected(store)
    first = benchmark_research.submit_run(store, native, body)
    snapshot = store.setting('benchmark_snapshot')
    snapshot['items'][0]['metrics']['likes']['value'] = 999
    store.set_setting('benchmark_snapshot', snapshot)
    second = benchmark_research.submit_run(store, native, body)
    assert first['request_id'] == second['request_id'] == body['request_id']
    assert second['observations'][0]['metrics']['likes']['value'] == 29
    assert len(native.posts) == 1 and native.subscriptions == native.delivery_reads == 0
    assert native.posts[0]['max_runtime_seconds'] == 300 and native.posts[0]['goal_mode'] is False
    assert native.posts[0]['skills'] == ['heobrain-office-coordinator']
    assert 'mybots-sage' in native.posts[0]['body'] and item['url'] in native.posts[0]['body']
    assert first['budget_evidence']['native_monetary_guard'] is False
    assert first['budget_evidence']['billing_mode'] == 'not_exposed_by_native_bridge'
    assert first['budget_evidence']['native_usage_verified'] is False
    assert protected(store) == before


def test_same_uuid_changed_selection_is_rejected_without_second_admission(research):
    store, native, body, _ = research
    benchmark_research.submit_run(store, native, body)
    with pytest.raises(WorkflowError):
        benchmark_research.submit_run(store, native, {**body, 'item_ids': ['different']})
    assert len(native.posts) == 1 and native.subscriptions == 0


def test_uncertain_admission_reconciles_same_uuid_without_reposting(research):
    store, native, body, _ = research
    native.timeout_after_create = True
    with pytest.raises(assistant_requests.BridgeError) as error:
        benchmark_research.submit_run(store, native, body)
    assert error.value.code == 'native_admission_unknown'
    native.timeout_after_create = False
    result = benchmark_research.submit_run(store, native, body)
    assert result['execution']['native_task_id'] == 't_root'
    assert len(native.posts) == 1 and native.subscriptions == native.delivery_reads == 0


@pytest.mark.parametrize('worker,reviewer', [('ethan', 'ada'), ('ethan', 'mybots-sage')])
def test_lumi_summary_or_sage_reviewer_never_claims_sage_worker_execution(research, worker, reviewer):
    store, native, body, item = research
    benchmark_research.submit_run(store, native, body)
    completed(native, worker, reviewer)
    result = benchmark_research.read_run(store, native, body['request_id'])
    assert result['execution']['status'] == 'blocked' and result['analysis_receipt'] is None
    with pytest.raises(WorkflowError):
        benchmark_research.save_run_idea(store, native, body['request_id'], idea_input(result, item))
    assert store.ideas() == []


def test_verified_sage_graph_saves_unverified_idea_with_server_receipt_and_observation(research):
    store, native, body, item = research
    benchmark_research.submit_run(store, native, body)
    completed(native)
    run = benchmark_research.read_run(store, native, body['request_id'])
    assert run['execution']['status'] == 'completed'
    assert run['analysis_receipt']['task_id'] == 't_final' and run['analysis_receipt']['event_id'] == 40
    before = protected(store)
    payload = idea_input(run, item)
    first = benchmark_research.save_run_idea(store, native, body['request_id'], payload)
    second = benchmark_research.save_run_idea(store, native, body['request_id'], payload)
    assert first['id'] == second['id'] and first['state'] == 'candidate'
    assert first['primary_sources'] == 0 and first['verification_state'] == 'unverified'
    assert first['observed_metrics'] == item['metrics']
    assert first['analysis_receipt']['request_id'] == body['request_id']
    assert first['analysis_receipt']['report_sha256'] == run['analysis_receipt']['report_sha256']
    assert protected(store) == before and native.subscriptions == native.delivery_reads == 0


@pytest.mark.parametrize('field,value', [('task_id', 't_other'), ('run_id', 99), ('event_id', 99),
    ('report_sha256', 'b' * 64), ('body_sha256', 'c' * 64)])
def test_mismatched_final_receipt_cannot_save_a_candidate(research, field, value):
    store, native, body, item = research
    benchmark_research.submit_run(store, native, body)
    completed(native)
    run = benchmark_research.read_run(store, native, body['request_id'])
    payload = idea_input(run, item)
    payload['receipt'] = {**payload['receipt'], field: value}
    with pytest.raises(WorkflowError):
        benchmark_research.save_run_idea(store, native, body['request_id'], payload)
    assert store.ideas() == []


def test_changed_final_report_or_unselected_observation_is_rejected(research):
    store, native, body, item = research
    benchmark_research.submit_run(store, native, body)
    completed(native)
    run = benchmark_research.read_run(store, native, body['request_id'])
    payload = idea_input(run, item)
    native.details['t_final']['runs'][0]['summary'] += '\n검토 후 달라진 최종 내용'
    with pytest.raises(WorkflowError):
        benchmark_research.save_run_idea(store, native, body['request_id'], payload)
    current = benchmark_research.read_run(store, native, body['request_id'])
    with pytest.raises(WorkflowError):
        benchmark_research.save_run_idea(store, native, body['request_id'], {**idea_input(current, item), 'item_id': 'unselected'})
    assert store.ideas() == []


def test_existing_assistant_delivery_default_is_preserved_and_explicit_false_is_quiet(research):
    store, native, _, _ = research
    rid = str(uuid4())
    assistant_requests.submit(store, native, rid, '기존 비서 경로')
    assert native.delivery_reads == native.subscriptions == 1
    counts = native.delivery_reads, native.subscriptions
    assistant_requests.submit(store, native, rid, '기존 비서 경로', attach_delivery=False)
    assistant_requests.read_request(store, native, rid, attach_delivery=False)
    assert (native.delivery_reads, native.subscriptions) == counts


def test_other_assistant_uuid_and_native_only_body_cannot_be_adopted_as_research(research):
    store, native, body, _ = research
    assistant_requests.submit(store, native, body['request_id'], '기존의 다른 비서 요청', attach_delivery=False)
    original = copy.deepcopy(store.setting('assistant_request:' + body['request_id']))
    with pytest.raises(WorkflowError):
        benchmark_research.submit_run(store, native, body)
    assert store.setting('assistant_request:' + body['request_id']) == original
    assert store.setting('benchmark_research_run:' + body['request_id']) is None
    assert len(native.posts) == 1


def test_native_only_uuid_collision_stays_conflict_without_exposing_unrelated_report(research):
    from office.assistant_request_protocol import task_payload
    store, native, body, _ = research
    native.create(task_payload(body['request_id'], '기존 native 전용 요청'))
    with pytest.raises(assistant_requests.BridgeError):
        benchmark_research.submit_run(store, native, body)
    completed(native)
    with pytest.raises(assistant_requests.BridgeError) as error:
        benchmark_research.read_run(store, native, body['request_id'])
    assert error.value.code == 'benchmark_research_conflict'
    assert len(native.posts) == 1 and native.subscriptions == native.delivery_reads == 0


def test_closed_window_allows_reading_existing_result_without_new_admission(research):
    store, native, body, _ = research
    benchmark_research.submit_run(store, native, body)
    store.set_setting('work_window', {'status': 'closed'})
    assert benchmark_research.read_run(store, native, body['request_id'])['execution']['status'] == 'queued'
    with pytest.raises(WorkflowError):
        benchmark_research.submit_run(store, native, body)
    assert len(native.posts) == 1 and native.subscriptions == native.delivery_reads == 0


def test_http_research_routes_keep_server_payload_and_no_delivery_contract(research):
    from fastapi.testclient import TestClient
    from office.api import create_app
    store, native, body, item = research
    app = create_app(store)
    app.state.assistant_native = native
    client = TestClient(app, base_url='http://localhost:8510')
    csrf = client.get('/api/session').json()['csrf']
    headers = {'Origin': 'http://localhost:3110', 'X-Office-CSRF': csrf}
    endpoint = '/api/benchmarks/research-runs'
    store.set_setting('work_window', {'status': 'closed'})
    assert client.post(endpoint, json=body, headers=headers).status_code == 409
    open_window(store)
    assert client.post(endpoint, json={**body, 'text': 'client supplied execution'}, headers=headers).status_code == 422
    response = client.post(endpoint, json=body, headers=headers)
    assert response.status_code == 202 and response.json()['execution']['native_task_id'] == 't_root'
    assert client.get(endpoint + '/' + body['request_id']).status_code == 200
    completed(native)
    run = client.get(endpoint + '/' + body['request_id']).json()
    payload = idea_input(run, item)
    idea_endpoint = endpoint + '/' + body['request_id'] + '/ideas'
    assert client.post(idea_endpoint, json={**payload, 'source_url': 'https://untrusted.example/'}, headers=headers).status_code == 422
    assert client.post(idea_endpoint, json=payload, headers=headers).status_code == 200
    assert len(native.posts) == 1 and native.subscriptions == native.delivery_reads == 0


@pytest.mark.parametrize('gate', ['window', 'budget'])
def test_admission_rechecks_after_native_preflight_without_unknown_or_duplicate(research, monkeypatch, gate):
    store, native, body, _ = research
    original_board = native.board
    original_cap = store.budget()['cap_krw']
    def close_during_preflight():
        if gate == 'window':
            store.set_setting('work_window', {'status': 'closed'})
        else:
            store.set_setting('budget_cap', 0)
        return original_board()
    monkeypatch.setattr(native, 'board', close_during_preflight)
    with pytest.raises(WorkflowError):
        benchmark_research.submit_run(store, native, body)
    result = benchmark_research.read_run(store, native, body['request_id'])
    assert result['execution']['native_status'] == 'not_submitted'
    assert result['execution']['error']['code'] == 'native_admission_blocked'
    assert native.posts == [] and native.subscriptions == native.delivery_reads == 0
    monkeypatch.setattr(native, 'board', original_board)
    open_window(store)
    store.set_setting('budget_cap', original_cap)
    assert benchmark_research.submit_run(store, native, body)['execution']['native_task_id'] == 't_root'
    assert len(native.posts) == 1
