"""Explicit, verified report-to-original-source links. Never approves or executes."""
import hashlib
import json
import re
import sqlite3

from . import owned_source
from .assistant_requests import BridgeError
from .store import WorkflowError, canonical, now


def _conflict():
    return BridgeError('assistant_content_conflict', '완료 보고와 연결된 원고를 다시 확인해 주세요. 기존 원고와 승인은 보존했습니다', 409)


def candidate(request):
    report = request.get('report')
    if (request.get('status') != 'completed' or request.get('native_status') != 'done'
            or not isinstance(report, dict) or report.get('verified') is not True
            or report.get('summary_truncated', False) is not False):
        return None
    summary = report.get('summary')
    if not isinstance(summary, str):
        return None
    headings, fence = [], None
    for line in re.finditer(r'[^\r\n]*(?:\r\n|\r|\n|$)', summary):
        value = line.group().rstrip('\r\n')
        marker = re.fullmatch(r' {0,3}(`{3,}|~{3,})(.*)', value)
        if fence:
            if marker and marker[1][0] == fence[0] and len(marker[1]) >= len(fence) and not marker[2].strip():
                fence = None
            continue
        if marker:
            fence = marker[1]
            continue
        heading = re.fullmatch(r' {0,3}#[ \t]+(.+)', value)
        if heading:
            title = re.sub(r'[ \t]+#+[ \t]*$', '', heading[1]).strip(' \t')
            headings.append((title, line.end()))
    if len(headings) != 1:
        return None
    title, offset = headings[0]
    body = summary[offset:].strip('\r\n')
    if not 1 <= len(title) <= 200 or not 100 <= len(body) <= 50000 or not body.strip():
        return None
    return {'request_id': request['request_id'], 'task_id': report['task_id'],
            'run_id': report['run_id'], 'event_id': report['event_id'], 'title': title,
            'body_length': len(body), 'report_sha256': hashlib.sha256(summary.encode('utf-8')).hexdigest(),
            'body_sha256': hashlib.sha256(body.encode('utf-8')).hexdigest(), '_body': body}


def _identity(content):
    return {key: value for key, value in content.items() if key != '_body'}


def _key(content):
    return 'assistant_content_job:' + content['request_id']


def _binding(db, content):
    row = db.execute('SELECT value FROM settings WHERE key=?', (_key(content),)).fetchone()
    if row is None:
        return None
    try:
        binding = json.loads(row[0])
    except (TypeError, ValueError):
        raise _conflict() from None
    if (type(binding) is not dict or set(binding) != {'identity', 'job_id', 'source_hash', 'created_at'}
            or type(binding['identity']) is not dict or set(binding['identity']) != set(_identity(content))
            or type(binding['job_id']) is not str or not re.fullmatch(r'[A-Za-z0-9][A-Za-z0-9_-]{0,95}', binding['job_id'])
            or type(binding['source_hash']) is not str or not re.fullmatch(r'[0-9a-f]{64}', binding['source_hash'])
            or type(binding['created_at']) is not str or not binding['created_at']):
        raise _conflict()
    return binding


def _job_reference(store, db, binding, *, allow_deleted=False):
    job = store._job(db, binding['job_id'], include_deleted=allow_deleted)
    return {'id': job['id'], 'source_hash': binding['source_hash'],
            'current_source_hash': job['source_hash'], 'state': 'deleted' if job.get('deleted_at') else job['state']}


def content_for_request(store, request):
    content = candidate(request)
    if content is None:
        return None
    result = {**_identity(content), 'job': None}
    with store.connection() as db:
        try:
            binding = _binding(db, content)
        except BridgeError:
            return result  # Optional link corruption must not hide the verified native report.
        if binding and binding.get('identity') == _identity(content):
            try:
                result['job'] = _job_reference(store, db, binding, allow_deleted=True)
            except WorkflowError:
                pass  # A historical report remains readable when its job is unavailable.
    return result


def connect_content_job(store, request, expected):
    content = candidate(request)
    if content is None or any(content[key] != value for key, value in expected.items()):
        raise _conflict()
    identity = _identity(content)
    try:
        # One writer transaction covers deduplication, original version and its immutable link.
        with store.connection(transaction=True) as db:
            binding = _binding(db, content)
            if binding:
                if binding.get('identity') != identity:
                    raise _conflict()
                return {**identity, 'job': _job_reference(store, db, binding)}
            article_id = owned_source.owned_article_id(content['title'], content['_body'])
            existing = db.execute("SELECT id FROM jobs WHERE json_extract(data,'$.article.id')=?", (article_id,)).fetchall()
            if len(existing) > 1:
                raise _conflict()
            job = (store._job(db, existing[0]['id']) if existing else
                   owned_source._create_owned_job(store, db, content['title'], content['_body']))
            # Reuse an edited/approved original job without resetting it; bind its original version.
            snapshots = db.execute('SELECT hash,packet FROM versions WHERE job_id=? ORDER BY created_at,hash', (job['id'],))
            source_hash = next((row['hash'] for row in snapshots
                                if (packet := json.loads(row['packet'])).get('title') == content['title']
                                and packet.get('body') == content['_body']), None)
            if source_hash is None:
                raise _conflict()
            binding = {'identity': identity, 'job_id': job['id'], 'source_hash': source_hash, 'created_at': now()}
            db.execute('INSERT INTO settings VALUES(?,?)', (_key(content), canonical(binding)))
            store._event(db, 'assistant_content_linked', {**identity, 'job_id': job['id'], 'source_hash': source_hash}, job['id'])
            return {**identity, 'job': _job_reference(store, db, binding)}
    except WorkflowError:
        raise _conflict() from None
    except sqlite3.Error:
        raise BridgeError('assistant_content_unavailable', '원고 연결을 확인할 수 없습니다. 기존 원고는 보존했습니다') from None
