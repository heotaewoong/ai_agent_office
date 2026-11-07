"""One explicit native research request, frozen public evidence and verified candidate links."""
import hashlib
import json
from uuid import UUID

from . import assistant_content_jobs, assistant_requests as bridge, benchmarks
from .assistant_request_protocol import task_payload
from .discovery import can_collect
from .store import WorkflowError, canonical, digest, now


RECEIPT_FIELDS = ('task_id', 'run_id', 'event_id', 'report_sha256', 'body_sha256')


def _request_id(value):
    try:
        result = str(UUID(value))
        if result != value:
            raise ValueError()
        return result
    except (ValueError, TypeError, AttributeError):
        raise WorkflowError('조사 요청 UUID를 확인하세요') from None


def _key(request_id):
    return 'benchmark_research_run:' + request_id


def _record(store, request_id):
    record = store.setting(_key(request_id))
    if not isinstance(record, dict):
        raise bridge.BridgeError('benchmark_research_not_found', '저장한 조사 요청을 찾을 수 없습니다', 404)
    return record


def _can_start(store):
    if not can_collect(store):
        raise WorkflowError('운영자가 확인한 작업 시간 안에서만 새 세이지 조사를 접수할 수 있습니다')
    budget = store.budget()
    if budget['remaining_krw'] <= 0:
        raise WorkflowError('기존 예산 잔액이 없어 조사를 접수하지 않았습니다')
    return {**budget, 'recorded_at': now(), 'native_monetary_guard': False,
            'billing_mode': 'not_exposed_by_native_bridge', 'billing_basis': 'native_provider_not_in_bridge_receipt',
            'native_usage_verified': False}


def _text(packet):
    text = ('[배정 요청: 세이지 (mybots-sage)]\n'
        '사용자가 아래 공개 관측의 실제 조사를 승인했습니다. 루미는 기존 mybots-sage 작업자 1명에게 '
        '분석을 맡기고, 다른 실제 역할의 독립 검토 후 루미가 최종 보고하세요. '
        '기존 coordinator의 정확한 단계 키·부모 관계를 사용하고 최대 역할4·깊이3·카드5를 지키세요. '
        '각 실행300초·goal_mode=false를 유지하고 새 daemon·예약·서비스·모델/provider override를 만들지 마세요. '
        '기존 openai-codex 구독 경로만 사용하며 별도 유료 API·MCP·생성 도구·결제·게시·메시지 발송은 금지합니다. '
        '구독 사용량을 비용0으로 단정하지 말고 기존 예산·승인⓪①②③과 다른 업무를 보존하세요. '
        '관측값은 누적 수치이며 미표시는 null입니다. 주장·관측·추론·직접 검증의 한계를 구분하세요. '
        '최종 루미 보고는 H1 제목 한 개와 본문100~5000자로 작성하고 내부 경로·인증값·첨부를 넣지 마세요. '
        '최종 보고의 단일 완료 표시로 세이지 실행이나 독립 검토를 대신하지 마세요.\n\n' + packet['text'])
    body = task_payload('00000000-0000-4000-8000-000000000000', text)['body']
    if len(body) > 8000 or len(body.encode('utf-8')) > 24000:
        raise WorkflowError('조사 입력이 깁니다. 실제 관측 근거를 줄여 다시 준비하세요')
    return text


def _prepare(store, body):
    required = {'request_id', 'source_ids', 'fields', 'platforms', 'expected_hash', 'item_ids', 'snapshot_hash'}
    if not isinstance(body, dict) or set(body) != required:
        raise WorkflowError('조사 접수 항목을 확인하세요')
    request_id = _request_id(body['request_id'])
    selection = {key: value for key, value in body.items() if key != 'request_id'}
    items = selection['item_ids']
    if not isinstance(items, list) or not 1 <= len(items) <= 6:
        raise WorkflowError('서버에 보관된 실제 관측 근거를 1~6개 선택하세요')
    input_hash = digest(selection)
    budget = _can_start(store)
    existing = store.setting(_key(request_id))
    if existing:
        if existing['input_hash'] != input_hash:
            raise WorkflowError('같은 조사 요청 UUID의 선택 근거가 바뀌었습니다. 기존 요청을 보존했습니다')
        return existing
    packet = benchmarks.research_packet(store, selection)
    text = _text(packet)
    body_hash = hashlib.sha256(task_payload(request_id, text)['body'].encode('utf-8')).hexdigest()
    assistant_record = bridge._record(store, request_id)
    if assistant_record and assistant_record['payload_hash'] != digest({'text': text, 'assignee': 'lumi'}):
        raise WorkflowError('다른 비서 요청에서 사용한 UUID입니다. 기존 요청은 보존했습니다')
    record = {'request_id': request_id, 'input_hash': input_hash, 'packet': packet,
              'text': text, 'native_body_hash': body_hash, 'budget_evidence': budget, 'created_at': now()}
    with store.connection(transaction=True) as db:
        saved = db.execute('SELECT value FROM settings WHERE key=?', (_key(request_id),)).fetchone()
        if saved:
            saved = json.loads(saved[0])
            if saved['input_hash'] != input_hash:
                raise WorkflowError('같은 조사 UUID에 다른 선택 근거가 있습니다')
            return saved
        benchmarks._expect(benchmarks._read_registry(db), selection['expected_hash'])
        benchmarks._expect_snapshot(benchmarks._read_snapshot(db), selection['snapshot_hash'], store=store, db=db)
        db.execute('INSERT INTO settings VALUES(?,?)', (_key(request_id), canonical(record)))
        store._event(db, 'benchmark_research_prepared', {'request_id': request_id,
            'packet_hash': packet['packet_hash'], 'item_ids': packet['item_ids'],
            'native_monetary_guard': False, 'delivery_attached': False})
    return record


def _execution(store, native, record):
    execution = bridge.read_request(store, native, record['request_id'], attach_delivery=False)
    root_id = execution.get('native_task_id')
    if root_id:
        root = native.task(root_id)
        task = root.get('task', {})
        body_hash = hashlib.sha256(str(task.get('body') or '').encode('utf-8')).hexdigest()
        if (task.get('idempotency_key') != 'office-world:' + record['request_id'] or
                body_hash != record['native_body_hash']):
            raise bridge.BridgeError('benchmark_research_conflict', '조사 원문과 실제 접수 카드가 다릅니다', 409)
        if execution.get('status') == 'completed':
            sage_executed = False
            for ident in root.get('links', {}).get('children', []):
                work = native.task(ident)
                work_task = work.get('task', {})
                key = work_task.get('idempotency_key')
                if (key not in {'office-world:' + record['request_id'] + suffix for suffix in (':work', ':work-a', ':work-b')}
                        or work_task.get('assignee') != 'mybots-sage'):
                    continue
                proof = bridge._completed_evidence(work_task, work.get('events', []), work.get('runs', []))
                if proof and any(event['task_id'] == ident and event['run_id'] == proof[0]['id']
                        and event['id'] == proof[1]['id'] and event['kind'] == 'completed'
                        and event['assignee'] == 'mybots-sage' for event in execution['events']):
                    sage_executed = True
            if not sage_executed:
                execution = {**execution, 'status': 'blocked', 'report': None,
                    'error': {'code': 'sage_execution_unverified',
                              'message': '세이지 작업자의 실제 실행·완료 영수증을 확인해야 합니다'}}
    return execution


def _result(record, execution):
    content = assistant_content_jobs.candidate(execution)
    receipt = {key: content[key] for key in RECEIPT_FIELDS} if content else None
    packet = record['packet']
    return {'request_id': record['request_id'], 'packet_hash': packet['packet_hash'],
            'registry_hash': packet['registry_hash'], 'snapshot_hash': packet['snapshot_hash'],
            'item_ids': packet['item_ids'], 'observations': packet['observations'],
            'created_at': record['created_at'], 'budget_evidence': record['budget_evidence'],
            'execution': execution, 'analysis_receipt': receipt}


def submit_run(store, native, body):
    record = _prepare(store, body)
    _can_start(store)
    bridge.submit(store, native, record['request_id'], record['text'], attach_delivery=False,
                  before_create=lambda: _can_start(store))
    return _result(record, _execution(store, native, record))


def read_run(store, native, request_id):
    record = _record(store, _request_id(request_id))
    return _result(record, _execution(store, native, record))


def save_run_idea(store, native, request_id, body):
    record = _record(store, _request_id(request_id))
    if (not isinstance(body, dict) or set(body) != {'item_id', 'title', 'angle', 'target_platforms', 'receipt'}
            or not isinstance(body['receipt'], dict) or set(body['receipt']) != set(RECEIPT_FIELDS)):
        raise WorkflowError('완료 분석의 정확한 영수증과 후보 입력을 확인하세요')
    result = _result(record, _execution(store, native, record))
    receipt = result['analysis_receipt']
    if receipt is None or receipt != body['receipt']:
        raise WorkflowError('실제 세이지 분석·독립 검토·루미 최종 보고가 완료된 현재 영수증이 필요합니다')
    item = next((row for row in record['packet']['observations'] if row['id'] == body['item_id']), None)
    if item is None:
        raise WorkflowError('이 조사에 동결된 실제 관측 근거를 선택하세요')
    provenance = {**receipt, 'request_id': request_id, 'packet_hash': result['packet_hash'],
                  'registry_hash': result['registry_hash'], 'snapshot_hash': result['snapshot_hash']}
    return benchmarks.save_research_idea(store, item,
        {key: body[key] for key in ('title', 'angle', 'target_platforms')}, provenance)
