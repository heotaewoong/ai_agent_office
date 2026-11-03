import copy
import hashlib
from concurrent.futures import ThreadPoolExecutor

import pytest

from tests.test_api_assistant_requests import bridge, submit
from tests.test_assistant_collaboration import collaboration
from office.owned_source import create_owned_job

RID = 'b318a3ab-8d96-4a0a-b9c3-99f2820b0b70'
TITLE = '합성 원문 연결 시험'
BODY = '  첫 줄의 공백과 이모지🙂를 보존합니다.\r\n\r\n' + '사용자가 검토할 합성 문장입니다. ' * 8 + '  '
SUMMARY = '검증된 합성 완료 보고입니다.\r\n\r\n# ' + TITLE + '\r\n\r\n' + BODY + '\r\n'


def sha(text):
    return hashlib.sha256(text.encode('utf-8')).hexdigest()


def complete(env, summary=SUMMARY):
    assert submit(env, RID).status_code == 202
    native = env[2]
    nodes = collaboration(request_id=RID, root_id='t_fixture')
    nodes['t_fixture']['task'] = {**native.cards[0], **nodes['t_fixture']['task']}
    nodes['t_final']['runs'][0]['summary'] = summary
    native.details = nodes
    return nodes


def expected(summary=SUMMARY, body=BODY):
    return {'task_id': 't_final', 'run_id': 5, 'event_id': 50,
            'report_sha256': sha(summary), 'body_sha256': sha(body)}


def connect(env, payload=None):
    return env[3].post('/api/assistant/requests/' + RID + '/content-job',
                       json=expected() if payload is None else payload, headers=env[4])


def test_get_exposes_exact_candidate_without_creating_a_job(bridge):
    complete(bridge)
    content = bridge[3].get('/api/assistant/requests/' + RID).json()['content']
    assert content == {'request_id': RID, **expected(), 'title': TITLE, 'body_length': len(BODY), 'job': None}
    assert bridge[0].jobs() == [] and bridge[0].tasks() == []


def test_explicit_import_preserves_unicode_bytes_without_approval_or_work(bridge):
    complete(bridge)
    response = connect(bridge)
    assert response.status_code == 200, response.text
    content = response.json()['content']
    job = bridge[0].job(content['job']['id'])
    assert job['source_packet']['body'] == BODY
    assert job['article']['operator_source_text'] == BODY
    assert job['source_packet']['preserve_original'] is True
    assert job['source_packet']['quality']['status'] == 'unverified'
    assert job['source_approval'] is None and job['release_approval'] is None and job['manifest'] is None
    assert job['state'] == 'research_ready' and bridge[0].tasks() == []
    with bridge[0].connection() as db:
        assert db.execute('SELECT count(*) FROM costs').fetchone()[0] == 0
        assert db.execute('SELECT count(*) FROM versions').fetchone()[0] == 1
    assert list(bridge[0].artifacts.iterdir()) == []
    assert len(bridge[2].posts) == 1  # Only setup's original native request.


@pytest.mark.parametrize('patch', [
    {'task_id': 't_other'}, {'run_id': 6}, {'event_id': 51},
    {'report_sha256': '0' * 64}, {'body_sha256': '0' * 64},
])
def test_stale_or_forged_reference_never_creates_a_job(bridge, patch):
    complete(bridge)
    response = connect(bridge, {**expected(), **patch})
    assert response.status_code == 409
    assert bridge[0].jobs() == []


@pytest.mark.parametrize('patch', [
    {'run_id': True}, {'run_id': '5'}, {'event_id': 0}, {'task_id': '../bad'},
    {'body_sha256': 'A' * 64}, {'report_sha256': 'f' * 63}, {'extra': 'field'},
])
def test_import_rejects_invalid_wire_fields(bridge, patch):
    complete(bridge)
    assert connect(bridge, {**expected(), **patch}).status_code == 422
    assert bridge[0].jobs() == []


@pytest.mark.parametrize('summary', [
    '본문만 있습니다. ' * 20,
    '# 첫 원고\n' + BODY + '\n# 두 번째 원고\n' + BODY,
    '```markdown\n# 코드 속 제목\n' + BODY + '\n```',
    '~~~\n# 코드 속 제목\n' + BODY + '\n~~~',
    '# 짧은 원고\n짧음', '# ' + '가' * 201 + '\n' + BODY,
])
def test_ambiguous_or_fenced_or_invalid_draft_is_hidden_and_not_imported(bridge, summary):
    complete(bridge, summary)
    assert bridge[3].get('/api/assistant/requests/' + RID).json()['content'] is None
    assert connect(bridge).status_code == 409
    assert bridge[0].jobs() == []


def test_fenced_heading_does_not_make_a_real_single_heading_ambiguous(bridge):
    summary = '```md\n# 예제 제목\n```\n\n# ' + TITLE + '\n' + BODY
    complete(bridge, summary)
    result = bridge[3].get('/api/assistant/requests/' + RID).json()['content']
    assert result['title'] == TITLE and result['body_sha256'] == sha(BODY)
    assert connect(bridge, expected(summary)).status_code == 200


def test_done_root_without_collaboration_cannot_be_imported(bridge):
    nodes = complete(bridge)
    nodes['t_fixture']['links']['children'] = []
    nodes['t_fixture']['runs'][0]['summary'] = SUMMARY
    observed = bridge[3].get('/api/assistant/requests/' + RID).json()
    assert observed['status'] == 'blocked' and observed['content'] is None
    assert connect(bridge).status_code == 409 and bridge[0].jobs() == []


def test_duplicate_and_concurrent_imports_share_one_job(bridge):
    complete(bridge)
    with ThreadPoolExecutor(max_workers=4) as pool:
        responses = list(pool.map(lambda _: connect(bridge), range(4)))
    assert [r.status_code for r in responses] == [200] * 4
    ids = {r.json()['content']['job']['id'] for r in responses}
    assert len(ids) == 1 and len(bridge[0].jobs()) == 1
    with bridge[0].connection() as db:
        assert db.execute('SELECT count(*) FROM versions').fetchone()[0] == 1


def test_existing_edited_approved_job_and_original_version_are_preserved(bridge):
    complete(bridge)
    store = bridge[0]
    original = create_owned_job(store, TITLE, BODY)
    original_hash = original['source_hash']
    packet = {**original['source_packet'], 'body': '이미 편집한 별도 판본입니다. ' * 10}
    edited = store.save_source(original['id'], packet, expected_hash=original_hash)
    store.update_job(original['id'], source_approval={'decision': 'approved', 'version': edited['source_hash']},
                     release_approval={'decision': 'approved'}, manifest={'hash': 'a' * 64}, state='released',
                     selections={'blog': False, 'video': False, 'pdf': True, 'cards': False})
    before = copy.deepcopy(store.job(original['id']))
    content = connect(bridge).json()['content']
    assert content['job'] == {'id': original['id'], 'source_hash': original_hash,
                              'current_source_hash': edited['source_hash'], 'state': 'released'}
    assert store.job(original['id']) == before
    assert connect(bridge).json()['content'] == content
    assert bridge[3].get('/api/assistant/requests/' + RID).json()['content'] == content


def test_deleted_existing_job_is_not_recreated(bridge):
    complete(bridge)
    job = create_owned_job(bridge[0], TITLE, BODY)
    bridge[0].update_job(job['id'], deleted_at='2026-01-01T00:00:00Z')
    assert connect(bridge).status_code == 409
    assert bridge[0].jobs() == [] and len(bridge[0].jobs(deleted=True)) == 1


def test_changed_report_cannot_replace_an_existing_binding(bridge):
    nodes = complete(bridge)
    first = connect(bridge)
    assert first.status_code == 200
    changed = SUMMARY + '원문에 새 문장을 덧붙였습니다.'
    nodes['t_final']['runs'][0]['summary'] = changed
    assert connect(bridge, expected(changed, BODY + '\r\n원문에 새 문장을 덧붙였습니다.')).status_code == 409
    assert len(bridge[0].jobs()) == 1


def test_import_requires_normal_operator_csrf(bridge):
    complete(bridge)
    response = bridge[3].post('/api/assistant/requests/' + RID + '/content-job', json=expected())
    assert response.status_code == 403 and bridge[0].jobs() == []


def test_owned_source_creation_rolls_back_if_registration_fails(bridge, monkeypatch):
    from office.store import Store
    original = Store._event
    def fail_source_event(db, kind, data, job_id=None):
        if kind == 'source_input_saved':
            raise OSError('synthetic local storage failure')
        return original(db, kind, data, job_id)
    monkeypatch.setattr(Store, '_event', staticmethod(fail_source_event))
    with pytest.raises(OSError):
        create_owned_job(bridge[0], TITLE, BODY)
    assert bridge[0].jobs() == []


def test_import_failure_rolls_back_and_retry_creates_one_complete_binding(bridge, monkeypatch):
    from office.store import Store
    complete(bridge)
    original = Store._event
    def fail_source_event(db, kind, data, job_id=None):
        if kind == 'source_input_saved':
            raise OSError('synthetic local storage failure')
        return original(db, kind, data, job_id)
    monkeypatch.setattr(Store, '_event', staticmethod(fail_source_event))
    assert connect(bridge).status_code == 502
    assert bridge[0].jobs() == []
    monkeypatch.setattr(Store, '_event', staticmethod(original))
    response = connect(bridge)
    assert response.status_code == 200
    assert len(bridge[0].jobs()) == 1
    assert bridge[3].get('/api/assistant/requests/' + RID).json()['content'] == response.json()['content']



def test_database_failure_is_safe_and_retryable_without_partial_job(bridge, monkeypatch):
    import sqlite3
    from office.store import Store
    complete(bridge)
    original = Store._event
    def fail_link_event(db, kind, data, job_id=None):
        if kind == 'assistant_content_linked':
            raise sqlite3.OperationalError('synthetic private database diagnostic')
        return original(db, kind, data, job_id)
    monkeypatch.setattr(Store, '_event', staticmethod(fail_link_event))
    response = connect(bridge)
    assert response.status_code == 502
    assert 'synthetic private' not in response.text
    assert bridge[0].jobs() == []
    monkeypatch.setattr(Store, '_event', staticmethod(original))
    assert connect(bridge).status_code == 200
    assert len(bridge[0].jobs()) == 1


def test_display_truncated_native_report_is_not_an_original_source_candidate(bridge):
    summary = '# ' + TITLE + '\n' + '긴 합성 원문🙂입니다. ' * 700
    assert len(summary) > 7000
    complete(bridge, summary)
    observed = bridge[3].get('/api/assistant/requests/' + RID).json()
    assert observed['status'] == 'completed' and observed['report']['verified'] is True
    assert len(observed['report']['summary']) < 6000
    assert observed['content'] is None
    assert bridge[0].jobs() == []


def test_client_hashes_of_a_truncated_display_cannot_self_authorize_import(bridge):
    summary = '# ' + TITLE + '\n' + '긴 합성 원문🙂입니다. ' * 700
    complete(bridge, summary)
    displayed = bridge[3].get('/api/assistant/requests/' + RID).json()['report']['summary']
    displayed_body = displayed.split('\n', 1)[1].strip('\r\n')
    response = connect(bridge, expected(displayed, displayed_body))
    assert response.status_code == 409
    assert bridge[0].jobs() == [] and bridge[0].tasks() == []


@pytest.mark.parametrize('kind', ['invalid_json', 'array', 'boolean', 'missing', 'missing_job', 'missing_hash', 'bad_job', 'bad_hash', 'bad_identity'])
def test_corrupt_optional_binding_cannot_hide_report_or_create_a_replacement(bridge, kind):
    import json
    complete(bridge)
    content = bridge[3].get('/api/assistant/requests/' + RID).json()['content']
    identity = {key: value for key, value in content.items() if key != 'job'}
    valid = {'identity': identity, 'job_id': 'job_unavailable', 'source_hash': 'a' * 64, 'created_at': '2026-01-01T00:00:00Z'}
    values = {'array': [], 'boolean': False, 'missing': {},
              'missing_job': {k: v for k, v in valid.items() if k != 'job_id'},
              'missing_hash': {k: v for k, v in valid.items() if k != 'source_hash'},
              'bad_job': {**valid, 'job_id': ['invalid']},
              'bad_hash': {**valid, 'source_hash': None},
              'bad_identity': {**valid, 'identity': []}}
    raw = '{broken' if kind == 'invalid_json' else json.dumps(values[kind])
    key = 'assistant_content_job:' + RID
    with bridge[0].connection() as db:
        db.execute('INSERT INTO settings VALUES(?,?)', (key, raw))
    observed = bridge[3].get('/api/assistant/requests/' + RID)
    assert observed.status_code == 200
    assert observed.json()['status'] == 'completed' and observed.json()['report']['verified'] is True
    assert observed.json()['content']['job'] is None
    assert connect(bridge).status_code == 409 and bridge[0].jobs() == []
    with bridge[0].connection() as db:
        assert db.execute('SELECT value FROM settings WHERE key=?', (key,)).fetchone()[0] == raw


def test_existing_original_job_with_changed_brief_is_reused_without_mutation(bridge):
    from office.briefs import build_brief
    complete(bridge)
    store = bridge[0]
    original = create_owned_job(store, TITLE, BODY)
    original_hash = original['source_hash']
    store.set_brief(original['id'], build_brief('transfer-admission'), 'synthetic-operator')
    edited = store.save_source(original['id'], {**original['source_packet'], 'body': '다르게 편집한 합성 원고입니다. ' * 8}, expected_hash=original_hash)
    store.update_job(original['id'], source_approval={'decision': 'approved'}, release_approval={'decision': 'approved'},
                     manifest={'hash': 'b' * 64}, selections={'blog': False, 'video': False, 'pdf': True, 'cards': False}, state='released')
    before = copy.deepcopy(store.job(original['id']))
    result = connect(bridge)
    assert result.status_code == 200, result.text
    assert result.json()['content']['job']['id'] == original['id']
    assert result.json()['content']['job']['source_hash'] == original_hash
    assert result.json()['content']['job']['current_source_hash'] == edited['source_hash']
    assert store.job(original['id']) == before and len(store.jobs()) == 1


@pytest.mark.parametrize('transport', ['scoped_fixture', 'http_fallback'])
@pytest.mark.parametrize('changed', ['root_tenant', 'missing_root_tenant', 'worker_tenant',
                                     'reviewer_tenant', 'final_tenant', 'missing_final_tenant', 'root_body'])
def test_stored_receipt_rechecks_current_graph_scope_before_read_or_import(bridge, monkeypatch, tmp_path, transport, changed):
    import io
    import json
    from urllib.parse import urlsplit
    from office import assistant_requests

    nodes = complete(bridge)
    if changed == 'root_body':
        nodes['t_fixture']['task']['body'] += '\nchanged after admission'
    else:
        ident = {'root': 't_fixture', 'worker': 't_work', 'reviewer': 't_verify', 'final': 't_final'}[
            changed.removeprefix('missing_').split('_', 1)[0]]
        if changed.startswith('missing_'):
            nodes[ident]['task'].pop('tenant', None)
        else:
            nodes[ident]['task']['tenant'] = 'different-tenant'
    if transport == 'http_fallback':
        # Exercise the supported HTTP adapter, which does not have the Unix relay's scope filter.
        token = tmp_path / 'synthetic-native-token'
        token.write_text('A' * 40, encoding='utf-8')
        token.chmod(0o600)
        class Opener:
            def open(self, request, timeout):
                ident = urlsplit(request.full_url).path.rsplit('/', 1)[-1]
                return io.BytesIO(json.dumps(bridge[2].task(ident)).encode())
        monkeypatch.setattr(assistant_requests, 'build_opener', lambda *_: Opener())
        monkeypatch.setenv('OFFICE_HERMES_BASE_URL', 'http://127.0.0.1:9119')
        monkeypatch.setenv('OFFICE_HERMES_TOKEN_FILE', str(token))
        bridge[1].state.assistant_native = None
    before_posts = len(bridge[2].posts)
    observed = bridge[3].get('/api/assistant/requests/' + RID)
    assert observed.status_code == 409
    assert connect(bridge).status_code == 409
    assert bridge[0].jobs() == [] and bridge[0].tasks() == []
    assert len(bridge[2].posts) == before_posts
