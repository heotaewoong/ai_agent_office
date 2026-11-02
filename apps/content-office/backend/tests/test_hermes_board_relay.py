import copy
import importlib.util
import io
import json
import os
import sys
import types
from pathlib import Path
import uuid

import pytest

SCRIPT = Path(__file__).parents[2] / 'scripts' / 'hermes-board-relay.py'
spec = importlib.util.spec_from_file_location('hermes_board_relay', SCRIPT) if SCRIPT.exists() else None
relay = importlib.util.module_from_spec(spec) if spec else None
if spec:
    spec.loader.exec_module(relay)

RID = 'aa3a151d-72e8-4abf-b09d-10d416279c41'
ROOT = 't_root123'


def detail(task_id=ROOT, assignee='lumi', event_id=12):
    return {'task': {'id': task_id, 'tenant': 'heobrain-world', 'assignee': assignee,
                     'idempotency_key': 'office-world:' + RID, 'status': 'done',
                     'body': 'Never forward this private body', 'claim_lock': 'native-owner-lock',
                     'title': '3D 비서 요청 · ' + RID[:8]},
            'events': [{'id': event_id, 'task_id': task_id, 'run_id': event_id, 'kind': 'completed', 'created_at': 1793624400, 'payload': {'summary': 'PRIVATE SUMMARY', 'artifacts': ['/home/private/file']}}],
            'runs': [{'id': event_id, 'task_id': task_id, 'profile': assignee, 'status': 'done', 'outcome': 'completed', 'ended_at': 1793624400, 'summary': 'PRIVATE SUMMARY', 'claim_lock': 'native-owner-lock'}],
            'links': {'parents': [], 'children': []}, 'attachments': [{'stored_path': '/home/private/file'}]}


def collaboration(native, rid=RID, root=ROOT, parallel=False, event_start=12):
    prefix = 'office-world:' + rid
    work_ids = [root + '_work_a', root + '_work_b'] if parallel else [root + '_work']
    verify, final = root + '_verify', root + '_final'
    roles = [(root, 'lumi', prefix, []),
             *[(ident, ['ethan', 'sam'][i], prefix + (':work-' + 'ab'[i] if parallel else ':work'), [root]) for i, ident in enumerate(work_ids)],
             (verify, 'ada', prefix + ':verify', work_ids),
             (final, 'lumi', prefix + ':final', [verify, *work_ids])]
    for index, (ident, actor, key, parents) in enumerate(roles):
        item = detail(ident, actor, event_start + index)
        item['task']['idempotency_key'] = key
        item['links']['parents'] = list(parents)
        native.details[ident] = item
    for ident, _, _, parents in roles:
        for parent in parents:
            native.details[parent]['links']['children'].append(ident)
    return {'root': root, 'works': work_ids, 'verify': verify, 'final': final}


def blocked_work(native, roles):
    work = native.details[roles['works'][0]]
    work['task']['status'] = 'blocked'
    work['runs'].append({'id': 40, 'task_id': work['task']['id'], 'profile': work['task']['assignee'], 'status': 'blocked', 'outcome': 'blocked', 'ended_at': 1793624500})
    work['events'].append({'id': 40, 'task_id': work['task']['id'], 'run_id': 40, 'kind': 'blocked', 'created_at': 1793624500})
    native.details[roles['verify']]['task']['status'] = 'todo'
    native.details[roles['final']]['task']['status'] = 'todo'


def finish_work(native, roles, event_start=50):
    for i, ident in enumerate([*roles['works'], roles['verify'], roles['final']]):
        node = native.details[ident]; node['task']['status'] = 'done'
        run_id = event_start + i
        node['runs'].append({'id': run_id, 'task_id': ident, 'profile': node['task']['assignee'], 'status': 'done', 'outcome': 'completed', 'ended_at': 1793624600})
        node['events'].append({'id': run_id, 'task_id': ident, 'run_id': run_id, 'kind': 'completed', 'created_at': 1793624600})


class Native:
    def __init__(self):
        self.details = {ROOT: detail()}
        self.created = []

    def board(self):
        return {'columns': [{'name': 'done', 'tasks': [copy.deepcopy(x['task']) for x in self.details.values()]}], 'tenants': ['foreign-secret-tenant']}

    def task(self, task_id):
        return copy.deepcopy(self.details[task_id])

    def create(self, payload):
        self.created.append(copy.deepcopy(payload))
        item = detail('t_new123'); item['task'].update(payload)
        self.details['t_new123'] = item
        return {'task': copy.deepcopy(item['task'])}


class Sender:
    def __init__(self):
        self.sent = []
        self.fail = False
        self.confirm = False

    def send(self, target, metadata):
        self.sent.append((target, copy.deepcopy(metadata)))
        if self.fail:
            raise TimeoutError('must not expose native credentials')
        return {'message_id': '1793624400.000001'}

    def readback(self, target, metadata):
        return self.confirm


def fixture(tmp_path):
    assert relay is not None, 'native-owned relay script must exist'
    state = tmp_path / 'watch.json'
    native, sender = Native(), Sender()
    app = relay.Relay(native, state, source=lambda: {'chat_id': 'G1234567890'}, sender=sender, notify_enabled=True)
    return app, native, sender, state


def request(op, **kwargs):
    return {'op': op, **kwargs}


def test_relay_rejects_wrong_uid_unknown_ops_and_override_fields_before_native_io(tmp_path):
    app, native, _, _ = fixture(tmp_path)
    for value in [request('config'), request('board', url='https://evil.example'), request('task', task_id='../secret')]:
        assert app.handle(value, 1000)['ok'] is False
    assert app.handle(request('board'), 1002)['error']['code'] == 'forbidden'
    assert app.handle(request('create', request_id=RID, payload={}), 1001)['error']['code'] == 'forbidden'
    assert native.created == []


def test_board_and_task_never_expose_foreign_tenants_claim_tokens_or_attachments(tmp_path):
    app, native, _, _ = fixture(tmp_path)
    native.details['t_foreign'] = detail('t_foreign'); native.details['t_foreign']['task']['tenant'] = 'other'
    data = app.handle(request('board'), 1000)['result']
    assert [x['id'] for c in data['columns'] for x in c['tasks']] == [ROOT]
    assert 'foreign-secret-tenant' not in json.dumps(data)
    assert not app.handle(request('task', task_id='t_foreign'), 1000)['ok']
    data = app.handle(request('task', task_id=ROOT), 1000)['result']
    assert 'native-owner-lock' not in json.dumps(data)
    assert 'artifacts' not in json.dumps(data)
    assert 'attachments' not in data


def test_create_is_fixed_scope_idempotent_and_rejects_credentials_and_model_overrides(tmp_path):
    app, native, _, _ = fixture(tmp_path)
    native.details.clear()
    payload = {'title': '3D 비서 요청 · ' + RID[:8], 'body': '근거를 정리해 주세요.', 'assignee': 'lumi', 'tenant': 'heobrain-world', 'idempotency_key': 'office-world:' + RID, 'max_runtime_seconds': 300, 'goal_mode': False}
    first = app.handle(request('create', request_id=RID, payload=payload), 1000)
    assert first['ok']
    assert app.handle(request('create', request_id=RID, payload=payload), 1000) == first
    assert len(native.created) == 1
    assert native.created[0]['skills'] == ['heobrain-office-coordinator']
    for patch in [{'model_override': 'anything'}, {'skills': ['foreign-skill']}, {'assignee': 'ada'}, {'body': 'token=secret'}, {'body': 'Bearer secret-value'}, {'body': 'xoxb-1234567890-abcde'}, {'body': 'https://user:password@example.com'}, {'max_runtime_seconds': 301}]:
        assert not app.handle(request('create', request_id=RID, payload={**payload, **patch}), 1000)['ok']


def test_authenticated_private_request_body_accepts_sources_and_ec2_paths_without_public_title_leak(tmp_path):
    app, native, _, path = fixture(tmp_path)
    native.details.clear()
    payload = {'title': '3D 비서 요청 · ' + RID[:8], 'body': '공식 https://example.com/docs 읽고 /home/user/project 확인', 'assignee': 'lumi', 'tenant': 'heobrain-world', 'idempotency_key': 'office-world:' + RID, 'max_runtime_seconds': 300, 'goal_mode': False}
    reply = app.handle(request('create', request_id=RID, payload=payload), 1000)
    assert reply['ok']
    assert native.created[0]['body'] == payload['body']
    assert '/home/' not in reply['result']['task']['title']
    assert not path.exists(), 'the private body never belongs in notification state'


def test_watch_registration_is_idempotent_and_state_contains_only_metadata(tmp_path):
    app, _, _, path = fixture(tmp_path)
    value = request('subscribe', request_id=RID, task_id=ROOT)
    first = app.handle(value, 1000)
    assert first['ok'] and first['result']['state'] == 'watching'
    assert app.handle(value, 1000) == first
    text = path.read_text()
    for forbidden in ['private body', 'SUMMARY', 'G1234567890', 'native-owner-lock', 'token']:
        assert forbidden not in text
    assert app.handle(request('subscribe', request_id=str(uuid.uuid4()), task_id=ROOT), 1000)['ok'] is False


def test_status_sender_gets_only_fixed_metadata_and_confirmed_requires_readback(tmp_path):
    app, native, sender, _ = fixture(tmp_path)
    roles = collaboration(native)
    app.handle(request('subscribe', request_id=RID, task_id=ROOT), 1000)
    app.tick()
    assert len(sender.sent) == 1
    metadata = sender.sent[0][1]
    assert metadata['task_id'] == roles['final'] and metadata['event_id'] == 15
    assert metadata['participants'] == ['ada', 'ethan', 'lumi']
    for name in ['body', 'summary', 'files', 'attachments', 'token']:
        assert name not in metadata
    result = app.handle(request('delivery_status', request_id=RID, task_id=ROOT), 1000)['result']
    assert result['state'] == 'sent_unverified' and not result['external_delivery_verified']
    app.tick(); assert len(sender.sent) == 1
    sender.confirm = True; app.tick()
    result = app.handle(request('delivery_status', request_id=RID, task_id=ROOT), 1000)['result']
    assert result['state'] == 'confirmed' and result['external_delivery_verified']


def test_confirmed_blocked_receipt_cannot_confirm_a_later_completed_notice(tmp_path):
    app, native, sender, path = fixture(tmp_path)
    roles = collaboration(native); blocked_work(native, roles)
    app.handle(request('subscribe', request_id=RID, task_id=ROOT), 1000)
    app.tick(); sender.confirm = True; app.tick()
    blocked = app.handle(request('delivery_status', request_id=RID, task_id=ROOT), 1000)['result']
    assert blocked['external_delivery_verified']
    assert blocked['notice_ref'] == {'request_id': RID, 'task_id': roles['works'][0], 'run_id': 40, 'event_id': 40, 'terminal_state': 'blocked'}
    work = native.details[roles['works'][0]]; work['task']['status'] = 'running'
    work['runs'].append({'id': 45, 'task_id': work['task']['id'], 'profile': 'ethan', 'status': 'running', 'outcome': None, 'ended_at': None})
    resumed = app.handle(request('delivery_status', request_id=RID, task_id=ROOT), 1000)['result']
    assert resumed['state'] == 'watching' and resumed['external_delivery_verified'] is False
    finish_work(native, roles)
    stale = app.handle(request('delivery_status', request_id=RID, task_id=ROOT), 1000)['result']
    assert stale['state'] == 'watching' and not stale['external_delivery_verified']
    assert stale['notice_ref'] == blocked['notice_ref']
    sender.confirm = False; app.tick()
    assert len(sender.sent) == 2 and sender.sent[-1][1]['terminal_state'] == 'completed'
    pending = app.handle(request('delivery_status', request_id=RID, task_id=ROOT), 1000)['result']
    assert pending['notice_ref']['task_id'] == roles['final'] and not pending['external_delivery_verified']
    sender.confirm = True; app.tick()
    completed = app.handle(request('delivery_status', request_id=RID, task_id=ROOT), 1000)['result']
    assert completed['notice_ref']['event_id'] == 52 and completed['external_delivery_verified']
    saved = json.loads(path.read_text())[RID]
    assert [(entry['notice']['terminal_state'], entry['state']) for entry in saved['receipts']] == [('blocked', 'confirmed'), ('completed', 'confirmed')]
    restored = relay.Relay(native, path, source=lambda: {'chat_id': 'G1234567890'}, sender=sender, notify_enabled=True)
    restored.tick(); assert len(sender.sent) == 2


def test_unknown_blocked_send_is_not_reposted_and_new_completion_waits_for_reconciliation(tmp_path):
    app, native, sender, _ = fixture(tmp_path)
    roles = collaboration(native); blocked_work(native, roles)
    app.handle(request('subscribe', request_id=RID, task_id=ROOT), 1000)
    sender.fail = True; app.tick()
    finish_work(native, roles)
    sender.fail = False; app.tick(); app.tick()
    assert len(sender.sent) == 1
    unknown = app.handle(request('delivery_status', request_id=RID, task_id=ROOT), 1000)['result']
    assert unknown['state'] == 'unknown' and not unknown['external_delivery_verified']
    sender.confirm = True; app.tick()
    assert len(sender.sent) == 2 and sender.sent[-1][1]['terminal_state'] == 'completed'
    assert app.handle(request('delivery_status', request_id=RID, task_id=ROOT), 1000)['result']['external_delivery_verified'] is False


def test_bounded_receipt_history_keeps_an_event_fence_after_old_receipts_are_pruned(tmp_path):
    app, native, sender, path = fixture(tmp_path)
    roles = collaboration(native); sender.confirm = True
    app.handle(request('subscribe', request_id=RID, task_id=ROOT), 1000)
    first_snapshot = None
    for index in range(18):
        finish_work(native, roles, event_start=50 + index * 10)
        if first_snapshot is None:
            first_snapshot = copy.deepcopy(native.details)
        app.tick(); app.tick()
    assert len(sender.sent) == 18
    saved = json.loads(path.read_text())[RID]
    assert len(saved['receipts']) <= 16
    assert saved['notice_cursor'] == 222
    assert all(entry['notice']['event_id'] != 52 for entry in saved['receipts'])
    native.details = first_snapshot
    restored = relay.Relay(native, path, source=lambda: {'chat_id': 'G1234567890'}, sender=sender, notify_enabled=True)
    restored.tick()
    assert len(sender.sent) == 18, 'an old view must not replay a pruned receipt after restart'
    status = restored.handle(request('delivery_status', request_id=RID, task_id=ROOT), 1000)['result']
    assert status['external_delivery_verified'] is False


def test_unknown_ack_and_restarted_pending_watch_never_blindly_resend(tmp_path):
    app, native, sender, path = fixture(tmp_path)
    collaboration(native)
    sender.fail = True
    app.handle(request('subscribe', request_id=RID, task_id=ROOT), 1000)
    app.tick(); app.tick()
    assert len(sender.sent) == 1
    restarted = relay.Relay(native, path, source=lambda: {'chat_id': 'G1234567890'}, sender=sender, notify_enabled=True)
    restarted.tick()
    assert len(sender.sent) == 1
    assert restarted.handle(request('delivery_status', request_id=RID, task_id=ROOT), 1000)['result']['state'] == 'unknown'


def test_unknown_create_ack_cannot_post_again_when_board_has_not_reconciled(tmp_path):
    app, native, _, _ = fixture(tmp_path)
    native.details.clear()
    payload = {'title': '3D 비서 요청 · ' + RID[:8], 'body': '근거 확인', 'assignee': 'lumi', 'tenant': 'heobrain-world', 'idempotency_key': 'office-world:' + RID, 'max_runtime_seconds': 300, 'goal_mode': False}
    count = []
    def fail(value):
        count.append(value)
        raise TimeoutError('unconfirmed admission')
    native.create = fail
    assert not app.handle(request('create', request_id=RID, payload=payload), 1000)['ok']
    assert not app.handle(request('create', request_id=RID, payload=payload), 1000)['ok']
    assert len(count) == 1


def test_lost_native_admission_ack_is_durable_across_new_relay_instances(tmp_path):
    app, native, sender, path = fixture(tmp_path)
    native.details.clear()
    payload = {'title': '3D 비서 요청 · ' + RID[:8], 'body': '재시작 전 접수한 비공개 업무', 'assignee': 'lumi', 'tenant': 'heobrain-world', 'idempotency_key': 'office-world:' + RID, 'max_runtime_seconds': 300, 'goal_mode': False}
    attempts = []
    def lost_ack(value):
        attempts.append(value)
        raise TimeoutError('native response lost')
    native.create = lost_ack
    assert not app.handle(request('create', request_id=RID, payload=payload), 1000)['ok']
    restored = relay.Relay(native, path, source=lambda: {'chat_id': 'G1234567890'}, sender=sender)
    reply = restored.handle(request('create', request_id=RID, payload=payload), 1000)
    assert reply['error']['code'] == 'native_admission_unknown'
    assert len(attempts) == 1
    changed = restored.handle(request('create', request_id=RID, payload={**payload, 'body': '다른 내용'}), 1000)
    assert changed['error']['code'] == 'request_conflict'


def test_admission_metadata_is_saved_before_native_post_and_never_contains_body(tmp_path):
    app, native, _, path = fixture(tmp_path)
    native.details.clear()
    admission_path = path.with_name(path.name + '.admissions.json')
    payload = {'title': '3D 비서 요청 · ' + RID[:8], 'body': 'PRIVATE BODY MUST NOT PERSIST', 'assignee': 'lumi', 'tenant': 'heobrain-world', 'idempotency_key': 'office-world:' + RID, 'max_runtime_seconds': 300, 'goal_mode': False}
    original = native.create
    def inspect_before_post(value):
        row = json.loads(admission_path.read_text())[RID]
        assert row['request_id'] == RID and row['phase'] == 'posting'
        assert row['native_task_id'] is None and len(row['payload_hash']) == 64
        assert set(row) == {'request_id', 'payload_hash', 'phase', 'native_task_id'}
        assert payload['body'] not in admission_path.read_text()
        return original(value)
    native.create = inspect_before_post
    assert app.handle(request('create', request_id=RID, payload=payload), 1000)['ok']
    assert json.loads(admission_path.read_text())[RID]['native_task_id'] == 't_new123'


def test_definite_board_preflight_failure_does_not_reserve_a_post_attempt(tmp_path):
    app, native, _, path = fixture(tmp_path)
    native.details.clear()
    original = native.board
    def fail():
        raise OSError('read failed before post')
    native.board = fail
    payload = {'title': '3D 비서 요청 · ' + RID[:8], 'body': '명시적 재확인', 'assignee': 'lumi', 'tenant': 'heobrain-world', 'idempotency_key': 'office-world:' + RID, 'max_runtime_seconds': 300, 'goal_mode': False}
    assert not app.handle(request('create', request_id=RID, payload=payload), 1000)['ok']
    assert not path.with_name(path.name + '.admissions.json').exists()
    native.board = original
    assert app.handle(request('create', request_id=RID, payload=payload), 1000)['ok']
    assert len(native.created) == 1


def test_full_admission_metadata_rejects_new_posts_without_forgetting_unknowns(tmp_path):
    app, native, _, path = fixture(tmp_path)
    native.details.clear()
    metadata = {str(uuid.UUID(int=i)): {'request_id': str(uuid.UUID(int=i)), 'payload_hash': '0' * 64, 'phase': 'unknown', 'native_task_id': None} for i in range(4096)}
    admission_path = path.with_name(path.name + '.admissions.json')
    relay.save_private_json(admission_path, metadata)
    payload = {'title': '3D 비서 요청 · ' + RID[:8], 'body': '새 업무', 'assignee': 'lumi', 'tenant': 'heobrain-world', 'idempotency_key': 'office-world:' + RID, 'max_runtime_seconds': 300, 'goal_mode': False}
    reply = app.handle(request('create', request_id=RID, payload=payload), 1000)
    assert reply['error']['code'] == 'admission_limit'
    assert native.created == [] and json.loads(admission_path.read_text()) == metadata


def test_two_live_relay_instances_share_the_durable_admission_lock(tmp_path):
    import threading
    app, native, sender, path = fixture(tmp_path)
    native.details.clear()
    other = relay.Relay(native, path, source=lambda: {'chat_id': 'G1234567890'}, sender=sender)
    entered, release = threading.Event(), threading.Event()
    original = native.create
    def delayed(value):
        entered.set()
        assert release.wait(3)
        return original(value)
    native.create = delayed
    payload = {'title': '3D 비서 요청 · ' + RID[:8], 'body': '동시 접수', 'assignee': 'lumi', 'tenant': 'heobrain-world', 'idempotency_key': 'office-world:' + RID, 'max_runtime_seconds': 300, 'goal_mode': False}
    replies = []
    thread = threading.Thread(target=lambda: replies.append(app.handle(request('create', request_id=RID, payload=payload), 1000)))
    thread.start()
    try:
        assert entered.wait(2)
        assert other.handle(request('create', request_id=RID, payload=payload), 1000)['error']['code'] == 'native_admission_unknown'
    finally:
        release.set(); thread.join(3)
    assert replies[0]['ok']
    assert other.handle(request('create', request_id=RID, payload=payload), 1000)['ok']
    assert len(native.created) == 1


@pytest.mark.skipif(os.name != 'posix', reason='directory fsync is verified on the Linux deployment host')
def test_admission_directory_is_fsynced_before_any_native_post(tmp_path, monkeypatch):
    import stat
    app, native, _, _ = fixture(tmp_path)
    native.details.clear()
    kinds = []
    fsync = relay.os.fsync
    def actual_fsync(fd):
        kinds.append('directory' if stat.S_ISDIR(os.fstat(fd).st_mode) else 'file')
        return fsync(fd)
    monkeypatch.setattr(relay.os, 'fsync', actual_fsync)
    original = native.create
    def post(value):
        assert kinds[-2:] == ['file', 'directory']
        return original(value)
    native.create = post
    payload = {'title': '3D 비서 요청 · ' + RID[:8], 'body': '영속 저장 확인', 'assignee': 'lumi', 'tenant': 'heobrain-world', 'idempotency_key': 'office-world:' + RID, 'max_runtime_seconds': 300, 'goal_mode': False}
    assert app.handle(request('create', request_id=RID, payload=payload), 1000)['ok']


@pytest.mark.parametrize('author,bot,expected', [('ULUMI123456', 'BLUMI123456', True), ('UOTHER12345', 'BLUMI123456', False), ('ULUMI123456', 'BOTHER12345', False), ('UOTHER12345', 'BOTHER12345', False), ('ULUMI123456', None, False)])
@pytest.mark.parametrize('text_form,text_allowed', [('raw', True), ('angle', True), ('label', False), ('other_host', False), ('other_path', False), ('other_event', False), ('extra_text', False)])
def test_actual_slack_readback_checks_the_authenticated_lumi_author(monkeypatch, tmp_path, capsys, author, bot, expected, text_form, text_allowed):
    notice = {'request_id': RID, 'task_id': ROOT, 'run_id': 12, 'event_id': 12, 'participants': ['lumi', 'ada', 'ethan'], 'terminal_state': 'completed'}
    client_id = str(uuid.uuid5(uuid.UUID(RID), '12:completed'))
    origin = 'https://office.example.test'
    url = origin + '/office3d'
    text = relay.status_message(notice, origin)
    if text_form == 'angle':
        text = text.replace(url, '<' + url + '>')
    elif text_form == 'label':
        text = text.replace(url, '<' + url + '|사무실>')
    elif text_form == 'other_host':
        text = text.replace(url, '<https://other.example.test/office3d>')
    elif text_form == 'other_path':
        text = text.replace(url, '<' + url + '/other>')
    elif text_form == 'other_event':
        text = text.replace('기록 12', '기록 13')
    elif text_form == 'extra_text':
        text += '\n다른 본문'
    message = {'text': text, 'ts': '1793624400.000001', 'client_msg_id': client_id, 'user': author, 'bot_id': bot}
    calls = []
    class FakeClient:
        def __init__(self, **kwargs):
            assert kwargs['token'] == 'fixture-lumi-token'
        async def auth_test(self):
            calls.append('identity')
            return {'ok': True, 'user_id': 'ULUMI123456', 'bot_id': 'BLUMI123456'}
        async def conversations_history(self, **kwargs):
            calls.append('history')
            assert kwargs['channel'] == 'G1234567890'
            return {'messages': [message]}
    modules = {}
    for name in ['dotenv', 'gateway', 'gateway.config', 'plugins', 'plugins.platforms', 'plugins.platforms.slack', 'plugins.platforms.slack.adapter', 'slack_sdk', 'slack_sdk.web', 'slack_sdk.web.async_client']:
        modules[name] = types.ModuleType(name)
        monkeypatch.setitem(sys.modules, name, modules[name])
    modules['dotenv'].load_dotenv = lambda *args, **kwargs: None
    modules['gateway.config'].Platform = types.SimpleNamespace(SLACK='slack')
    modules['gateway.config'].load_gateway_config = lambda: types.SimpleNamespace(platforms={'slack': types.SimpleNamespace(token='fixture-lumi-token')})
    async def never_post(*args, **kwargs):
        raise AssertionError('readback must never send a message')
    modules['plugins.platforms.slack.adapter']._standalone_post_text = never_post
    modules['slack_sdk.web.async_client'].AsyncWebClient = FakeClient
    monkeypatch.setattr(sys, 'path', list(sys.path))
    monkeypatch.setattr(sys, 'stdin', types.SimpleNamespace(buffer=io.BytesIO(json.dumps({'target': 'G1234567890', 'notice': notice, 'message_id': message['ts'], 'office_origin': origin}).encode())))
    monkeypatch.setattr(relay.logging, 'disable', lambda _: None)
    relay.slack_child('readback', {'native_python': sys.executable, 'native_repo': str(tmp_path), 'pythonpath': [str(tmp_path)]})
    assert json.loads(capsys.readouterr().out)['confirmed'] is (expected and text_allowed)
    assert calls == ['identity', 'history']


def test_watch_polling_rotates_bounded_batches_instead_of_starving_later_requests(tmp_path):
    app, native, sender, _ = fixture(tmp_path)
    native.details.clear()
    for i in range(10):
        rid = str(uuid.UUID(int=i + 100)); ident = 't_task' + str(i)
        collaboration(native, rid, ident, event_start=i * 10 + 20)
        assert app.handle(request('subscribe', request_id=rid, task_id=ident), 1000)['ok']
    app.tick(); assert len(sender.sent) == 8
    app.tick(); assert len(sender.sent) == 10


@pytest.mark.parametrize('parallel', [False, True])
def test_notification_requires_real_four_or_five_card_roles_and_all_completion_proofs(tmp_path, parallel):
    app, native, sender, _ = fixture(tmp_path)
    roles = collaboration(native, parallel=parallel)
    final = native.details[roles['final']]
    final['task']['status'] = 'running'
    app.handle(request('subscribe', request_id=RID, task_id=ROOT), 1000)
    app.tick(); assert sender.sent == []
    final['task']['status'] = 'done'
    app.tick(); assert len(sender.sent) == 1
    assert sender.sent[0][1]['task_id'] == roles['final']


def test_done_intake_without_work_review_final_is_not_a_completed_collaboration(tmp_path):
    app, _, sender, _ = fixture(tmp_path)
    app.handle(request('subscribe', request_id=RID, task_id=ROOT), 1000)
    assert app.terminal({'request_id': RID, 'task_id': ROOT}) is None
    app.tick(); assert sender.sent == []


@pytest.mark.parametrize('bad', ['same_verifier', 'lumi_worker', 'wrong_key', 'missing_final', 'missing_work_parent', 'missing_final_parent', 'non_lumi_final', 'extra_role', 'bad_run'])
def test_role_identity_keys_dependencies_and_receipts_cannot_be_faked(tmp_path, bad):
    app, native, sender, _ = fixture(tmp_path)
    roles = collaboration(native, parallel=True)
    if bad == 'same_verifier':
        node = native.details[roles['verify']]; node['task']['assignee'] = node['runs'][0]['profile'] = 'ethan'
    elif bad == 'lumi_worker':
        node = native.details[roles['works'][0]]; node['task']['assignee'] = node['runs'][0]['profile'] = 'lumi'
    elif bad == 'wrong_key':
        native.details[roles['verify']]['task']['idempotency_key'] = 'office-world:' + str(uuid.uuid4()) + ':verify'
    elif bad == 'missing_final':
        for node in native.details.values():
            node['links']['children'] = [ident for ident in node['links']['children'] if ident != roles['final']]
        del native.details[roles['final']]
    elif bad == 'missing_work_parent':
        native.details[roles['verify']]['links']['parents'].remove(roles['works'][1])
        native.details[roles['works'][1]]['links']['children'].remove(roles['verify'])
    elif bad == 'missing_final_parent':
        native.details[roles['final']]['links']['parents'].remove(roles['works'][1])
        native.details[roles['works'][1]]['links']['children'].remove(roles['final'])
    elif bad == 'non_lumi_final':
        node = native.details[roles['final']]; node['task']['assignee'] = node['runs'][0]['profile'] = 'sam'
    elif bad == 'extra_role':
        extra = detail('t_extra123', 'oliver', 30); extra['task']['idempotency_key'] += ':extra'; extra['links']['parents'] = [ROOT]
        native.details[ROOT]['links']['children'].append('t_extra123'); native.details['t_extra123'] = extra
    else:
        native.details[roles['verify']]['runs'][0]['profile'] = 'lumi'
    app.handle(request('subscribe', request_id=RID, task_id=ROOT), 1000)
    app.tick(); assert sender.sent == []


def test_shared_multi_parent_cycle_is_detected_after_full_collection(tmp_path):
    app, native, _, _ = fixture(tmp_path)
    roles = collaboration(native)
    b, c, d = roles['works'][0], roles['verify'], roles['final']
    edges = {ROOT: [b, c], b: [d], c: [d], d: [c]}
    for ident, node in native.details.items():
        node['links'] = {'children': edges[ident], 'parents': [parent for parent, children in edges.items() if ident in children]}
    with pytest.raises(ValueError) as raised:
        app.terminal({'request_id': RID, 'task_id': ROOT})
    assert raised.value.code == 'native_graph_invalid'


def test_shared_shortcut_cannot_hide_a_longer_path_beyond_three_edges(tmp_path):
    app, native, _, _ = fixture(tmp_path)
    roles = collaboration(native, parallel=True)
    b, c, d, e = *roles['works'], roles['final'], roles['verify']
    edges = {ROOT: [b, c], b: [c, d], c: [e], e: [d], d: []}
    for ident, node in native.details.items():
        node['links'] = {'children': edges[ident], 'parents': [parent for parent, children in edges.items() if ident in children]}
    with pytest.raises(ValueError) as raised:
        app.terminal({'request_id': RID, 'task_id': ROOT})
    assert raised.value.code == 'native_graph_limit'


def test_disabled_sender_never_posts_and_reports_the_connection_requirement(tmp_path):
    app, _, sender, _ = fixture(tmp_path)
    app.notify_enabled = False
    app.handle(request('subscribe', request_id=RID, task_id=ROOT), 1000)
    app.tick()
    result = app.handle(request('delivery_status', request_id=RID, task_id=ROOT), 1000)['result']
    assert sender.sent == [] and result['error']['code'] == 'status_sender_disabled'


def test_status_message_cannot_include_untrusted_body_summary_or_attachments():
    assert relay is not None, 'native-owned relay script must exist'
    metadata = {'request_id': RID, 'task_id': ROOT, 'run_id': 12, 'event_id': 12, 'participants': ['lumi', 'ada'], 'terminal_state': 'completed'}
    text = relay.status_message(metadata)
    assert RID[:8] in text and ROOT in text and '완료' in text
    with pytest.raises(ValueError):
        relay.status_message({**metadata, 'summary': 'PRIVATE SUMMARY'})


def test_missing_native_runtime_is_rejected_without_guessing_an_executable():
    with pytest.raises(ValueError, match='비서'):
        relay.trusted_runtime({})


def test_service_start_uses_operator_pinned_target_without_opening_native_sqlite(monkeypatch, tmp_path):
    import stat
    class StartupReached(BaseException):
        pass
    config = {'socket_path': str(tmp_path / 'relay.sock'), 'socket_gid': 1000,
              'state_file': str(tmp_path / 'state.json'), 'source_task_id': 't_approved_source',
              'target_chat_id': 'G1234567890'}
    monkeypatch.setattr(sys, 'argv', ['hermes-board-relay', '--config', str(tmp_path / 'config.json')])
    monkeypatch.setattr(relay.sys, 'platform', 'linux')
    monkeypatch.setattr(relay, 'os', types.SimpleNamespace(geteuid=lambda: 1001))
    monkeypatch.setattr(relay, 'private_json', lambda path: config)
    original_lstat = Path.lstat
    def lstat(path):
        info = original_lstat(path)
        return types.SimpleNamespace(st_uid=1001, st_mode=(stat.S_IFDIR | 0o750) if path.is_dir() else (stat.S_IFREG | 0o600))
    monkeypatch.setattr(Path, 'lstat', lstat)
    def no_native_sqlite(*args, **kwargs):
        raise AssertionError('service must not open the native SQLite file under read-only home')
    monkeypatch.setattr(relay.sqlite3, 'connect', no_native_sqlite)
    monkeypatch.setattr(relay, 'approved_target', no_native_sqlite)
    def start(native, state_file, *, source, **kwargs):
        assert source() == {'chat_id': 'G1234567890'}
        raise StartupReached()
    monkeypatch.setattr(relay, 'Relay', start)
    with pytest.raises(StartupReached):
        relay.main()


@pytest.mark.parametrize('target', [None, '', 'D1234567890', 'G1234567890?token=secret', 'https://example.com', 'G1234567890\n'])
def test_operator_target_pin_rejects_missing_dm_or_malformed_destinations(target):
    with pytest.raises(relay.RelayError):
        relay.pinned_target({'source_task_id': 't_approved_source', 'target_chat_id': target})


def test_changed_operator_pin_cannot_confirm_or_retarget_an_existing_watch(tmp_path):
    app, native, sender, _ = fixture(tmp_path)
    collaboration(native)
    app.subscribe(RID, ROOT); app.tick()
    sender.confirm = True; app.tick()
    assert app.delivery_status(RID, ROOT)['external_delivery_verified'] is True
    app.source = lambda: {'chat_id': 'G0987654321'}
    result = app.delivery_status(RID, ROOT)
    assert result['external_delivery_verified'] is False
    assert result['error']['code'] == 'notification_target_changed'
    with pytest.raises(relay.RelayError):
        app.subscribe(RID, ROOT)
    app.tick()
    assert len(sender.sent) == 1


@pytest.mark.parametrize('case,allowed', [
    ('private_primary_group', True), ('other_primary_member', False),
    ('other_supplemental_member', False), ('wrong_group', False),
    ('world_writable', False), ('root_owned_group_write', False),
    ('file_group_write', False), ('access_acl', False), ('default_acl', False),
    ('acl_unreadable', False), ('writable_ancestor', False),
])
def test_native_runtime_allows_only_owner_private_group_directories(monkeypatch, case, allowed):
    """Exercise runtime admission with controlled OS ownership/group/ACL metadata, not service GID."""
    import stat
    from pathlib import PurePosixPath
    owner = types.SimpleNamespace(pw_uid=1001, pw_gid=1001, pw_name='native')
    users = [owner]
    members = ['native']
    if case == 'other_primary_member':
        users.append(types.SimpleNamespace(pw_uid=1000, pw_gid=1001, pw_name='ubuntu'))
    if case == 'other_supplemental_member':
        members.append('ubuntu')
    monkeypatch.setitem(sys.modules, 'pwd', types.SimpleNamespace(getpwuid=lambda uid: owner, getpwall=lambda: users))
    monkeypatch.setitem(sys.modules, 'grp', types.SimpleNamespace(getgrgid=lambda gid: types.SimpleNamespace(gr_gid=1001, gr_mem=members)))
    modes = {'/': (0, 0, 0o755), '/home': (0, 0, 0o755), '/home/native': (1001, 1001, 0o750),
             '/home/native/runtime': (1001, 1001, 0o755),
             '/home/native/runtime/python': (1001, 1001, 0o755),
             '/home/native/repo': (1001, 1001, 0o755),
             '/home/native/site-packages': (1001, 1001, 0o775)}
    if case == 'wrong_group':
        modes['/home/native/site-packages'] = (1001, 1000, 0o775)
    if case == 'world_writable':
        modes['/home/native/site-packages'] = (1001, 1001, 0o777)
    if case == 'root_owned_group_write':
        modes['/home/native/site-packages'] = (0, 1001, 0o775)
    if case == 'file_group_write':
        modes['/home/native/runtime/python'] = (1001, 1001, 0o775)
    if case == 'writable_ancestor':
        modes['/home/native'] = (1001, 1000, 0o770)
    class RuntimePath(PurePosixPath):
        def stat(self):
            uid, gid, mode = modes[str(self)]
            kind = stat.S_IFREG if self.name == 'python' else stat.S_IFDIR
            return types.SimpleNamespace(st_uid=uid, st_gid=gid, st_mode=kind | mode)
        def resolve(self, strict=False):
            return self
    def listxattr(path):
        if str(path) == '/home/native/site-packages':
            if case == 'acl_unreadable':
                raise OSError('ACL metadata unavailable')
            if case in {'access_acl', 'default_acl'}:
                return ['system.posix_acl_' + case.removesuffix('_acl')]
        return []
    monkeypatch.setattr(relay, 'Path', RuntimePath)
    monkeypatch.setattr(relay, 'os', types.SimpleNamespace(name='posix', geteuid=lambda: 1001,
                       getegid=lambda: 1000, access=lambda *args: True, X_OK=os.X_OK, listxattr=listxattr))
    config = {'native_python': '/home/native/runtime/python', 'native_repo': '/home/native/repo',
              'pythonpath': ['/home/native/site-packages']}
    if allowed:
        assert relay.trusted_runtime(config) == config
    else:
        with pytest.raises(relay.RelayError, match='비서'):
            relay.trusted_runtime(config)


def test_loaded_watch_state_cannot_carry_a_private_body_or_foreign_fields(tmp_path):
    app, native, sender, path = fixture(tmp_path)
    app.handle(request('subscribe', request_id=RID, task_id=ROOT), 1000)
    value = json.loads(path.read_text()); value[RID]['body'] = 'PRIVATE'
    path.write_text(json.dumps(value)); path.chmod(0o600)
    with pytest.raises(ValueError):
        relay.Relay(native, path, source=lambda: {'chat_id': 'G1234567890'}, sender=sender)


@pytest.mark.skipif(os.name != 'posix', reason='Linux peer credentials are verified on the deployment host')
def test_real_unix_socket_denies_native_probe_writes_and_rejects_oversized_frames(tmp_path):
    import socket
    import socketserver
    import threading
    if not hasattr(socket, 'SO_PEERCRED') or os.getuid() != 1001:
        pytest.skip('requires the native service UID1001 on Linux')
    app, native, _, _ = fixture(tmp_path)
    app.read_probe_uid = 1001
    server = socketserver.UnixStreamServer(str(tmp_path / 'relay.sock'), relay.Handler)
    server.app = app
    thread = threading.Thread(target=server.serve_forever, daemon=True); thread.start()
    def call(data):
        with socket.socket(socket.AF_UNIX) as client:
            client.settimeout(3); client.connect(str(tmp_path / 'relay.sock')); client.sendall(data)
            return json.loads(client.makefile('rb').readline())
    try:
        assert call(b'{"op":"board"}\n')['ok']
        assert call(json.dumps(request('create', request_id=RID, payload={})).encode() + b'\n')['error']['code'] == 'forbidden'
        assert not call(b'x' * (relay.MAX_INPUT + 1) + b'\n')['ok']
        assert native.created == []
    finally:
        server.shutdown(); server.server_close(); thread.join(3)
