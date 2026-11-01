"""Verified, redacted report references in the existing Store settings ledger.

Not an executor or API. The trusted caller must independently verify receipt ID
and SHA256 against actual execution evidence, and supply only redacted summaries.
No canonical chat, source files, model calls or approval writes belong here.
"""
import json
import re
import unicodedata

from .store import WorkflowError, canonical, digest, now


def _identifier(value):
    if type(value) is not str or not re.fullmatch(r'[A-Za-z0-9][A-Za-z0-9_-]{0,95}', value):
        raise WorkflowError('invalid identifier')
    return value


def _validate(payload):
    required = {'work_id', 'request_id', 'facts', 'limitations', 'evidence'}
    display_fields = {'title', 'collaboration_kind', 'participants'}
    if type(payload) is not dict or not required <= payload.keys() or payload.keys() - required - {'job_id', 'source_hash'} - display_fields:
        raise WorkflowError('invalid report fields')
    for name in ('work_id', 'request_id'):
        _identifier(payload[name])
    if ('job_id' in payload) != ('source_hash' in payload):
        raise WorkflowError('job reference requires source snapshot')
    if 'job_id' in payload:
        _identifier(payload['job_id'])
        if payload['source_hash'] is not None and (type(payload['source_hash']) is not str or not re.fullmatch('[0-9a-f]{64}', payload['source_hash'])):
            raise WorkflowError('invalid source hash')
    summaries = {name: payload[name] for name in ('facts', 'limitations')}
    if display_fields & payload.keys():
        if not display_fields <= payload.keys():
            raise WorkflowError('incomplete collaboration metadata')
        if type(payload['title']) is not str or not 1 <= len(payload['title']) <= 160:
            raise WorkflowError('invalid report title')
        if type(payload['collaboration_kind']) is not str or payload['collaboration_kind'] not in ('dm_review', 'group_review'):
            raise WorkflowError('invalid collaboration kind')
        people = payload['participants']
        if (type(people) is not list or not 1 <= len(people) <= 6
                or any(type(person) is not str or not re.fullmatch(r'[a-z0-9][a-z0-9_-]{0,63}', person) for person in people)
                or len(set(people)) != len(people)):
            raise WorkflowError('invalid collaboration participants')
        summaries['title'] = [payload['title']]
    for values in summaries.values():
        if type(values) is not list or not 1 <= len(values) <= 20:
            raise WorkflowError('bounded summary list required')
        for text in values:
            if (type(text) is not str or not 1 <= len(text) <= 300 or not text.strip()
                    or any(unicodedata.category(c).startswith('C') for c in text)
                    or any(c in text for c in '/\\%~')
                    or re.search(r'private|canonical|transcript|강의|개인대화', text, re.I)):
                raise WorkflowError('private or invalid summary')
    evidence = payload['evidence']
    if type(evidence) is not list or not 1 <= len(evidence) <= 20:
        raise WorkflowError('bounded evidence required')
    ids = set()
    for item in evidence:
        if type(item) is not dict or set(item) != {'id', 'sha256'}:
            raise WorkflowError('invalid evidence fields')
        eid = _identifier(item['id'])
        if eid in ids or type(item['sha256']) is not str or not re.fullmatch('[0-9a-f]{64}', item['sha256']):
            raise WorkflowError('invalid evidence hash or duplicate ID')
        ids.add(eid)
    # Own the validated JSON so a caller cannot mutate it during verification.
    return json.loads(canonical(payload))


def import_report(store, payload, *, verify_evidence):
    """Import a verified summary; verify_evidence(id, sha256) must return True."""
    payload = _validate(payload)
    with store.connection(transaction=True) as db:
        if 'job_id' in payload:
            current = store._job(db, payload['job_id'])
            if current.get('source_hash') != payload['source_hash']:
                raise WorkflowError('stale job source snapshot')
        key = 'assistant_report:request:' + payload['request_id']
        old = db.execute('SELECT value FROM settings WHERE key=?', (key,)).fetchone()
        if old:
            previous = json.loads(old[0])
            if previous['sha256'] != digest(payload):
                raise WorkflowError('request conflict')
            return previous
        for evidence in payload['evidence']:
            try:
                verified = verify_evidence(evidence['id'], evidence['sha256'])
            except Exception:
                raise WorkflowError('evidence verification unavailable') from None
            if verified is not True:
                raise WorkflowError('evidence not verified')
        record = {**payload, 'sha256': digest(payload),
                  'scope': 'verified_reference_not_approval', 'created_at': now()}
        db.execute('INSERT INTO settings VALUES(?,?)',
                   (key, canonical(record)))
    return record


def get_report(store, request_id):
    """Return a historical reference, not proof that its job is still current."""
    _identifier(request_id)
    return store.setting('assistant_report:request:' + request_id)
