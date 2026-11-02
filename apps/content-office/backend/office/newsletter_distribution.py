"""뉴스레터 전달 준비만 담당한다. 네트워크 전송·자동 승인·자격 저장은 하지 않는다."""
from __future__ import annotations

import json
import os
import re
from urllib.parse import urlsplit

from .store import WorkflowError, canonical, digest, identifier, now

DESTINATIONS = {'email': '구독자 이메일', 'slack': 'Slack', 'website': 'heobrain.kr'}


def _public_https(value, *, website=False):
    try:
        url = urlsplit(value)
        host = (url.hostname or '').lower()
        valid = url.scheme == 'https' and bool(host) and not url.username and not url.password
        valid = valid and not url.fragment and not re.search(r'[\r\n]', value)
        valid = valid and not any(key in url.query.lower() for key in ('token=', 'secret=', 'key='))
        return valid and (host in ('heobrain.kr', 'www.heobrain.kr') and url.path not in ('', '/') if website else '.' in host and host not in ('127.0.0.1', 'localhost'))
    except ValueError:
        return False


def connection_status():
    """존재/형식만 검사한다. configured는 실제 계정·수신 확인을 뜻하지 않는다."""
    values = {
        'email': [os.environ.get('NEWSLETTER_FROM', ''), os.environ.get('NEWSLETTER_UNSUBSCRIBE_URL', '')],
        'slack': [os.environ.get('NEWSLETTER_SLACK_CHANNEL', '')],
        'website': [os.environ.get('HEOBRAIN_NEWSLETTER_DRAFT_URL', '')],
    }
    checks = {
        'email': [('발송 공급자 인증', bool(os.environ.get('RESEND_API_KEY'))),
                  ('발신 주소', bool(re.fullmatch(r'[^\s<>@]+@[^\s<>@]+\.[^\s<>@]+', values['email'][0]))),
                  ('수신거부 연결', _public_https(values['email'][1]))],
        'slack': [('Slack 인증', bool(os.environ.get('SLACK_BOT_TOKEN'))),
                  ('게시 채널 ID', bool(re.fullmatch(r'[CG][A-Z0-9]{8,}', values['slack'][0])))],
        'website': [('웹사이트 인증', bool(os.environ.get('HEOBRAIN_NEWSLETTER_TOKEN'))),
                    ('확인할 초안 수신 API', _public_https(values['website'][0], website=True))],
    }
    return {'mode': 'prepare-only', 'destinations': [
        {'key': key, 'label': label, 'configured': all(ok for _, ok in checks[key]), 'verified': False,
         'missing': [name for name, ok in checks[key] if not ok], 'target_hash': digest(values[key]),
         'note': '설정값 확인만 수행하며 실제 수신·게시 연결은 아직 검증하지 않았습니다.'}
        for key, label in DESTINATIONS.items()
    ]}


def connection_contract(destinations):
    return {row['key']: row['target_hash'] for row in connection_status()['destinations'] if row['key'] in destinations}


def prepare_delivery(store, issue_id, *, expected_hash, actor):
    from . import newsletter
    if not str(actor or '').strip():
        raise WorkflowError('전달 준비 담당자가 필요합니다')
    with store.connection(transaction=True) as db:
        current = newsletter._load(db, issue_id)
        if expected_hash != current['review_hash']:
            raise WorkflowError('회차 또는 수신자 판본이 달라졌습니다. 다시 확인하세요')
        newsletter._require_issue_approval(current)
        newsletter._require_current_issue(db, store, current)
        if not current.get('package'):
            raise WorkflowError('이전 회차에는 전달 목적지가 없습니다. 새 회차에서 목적지를 검토하세요')
        key = 'newsletter_prepared:' + issue_id + ':' + expected_hash
        row = db.execute('SELECT value FROM settings WHERE key=?', (key,)).fetchone()
        destinations = [row for row in connection_status()['destinations'] if row['key'] in current['editorial']['destinations']]
        destination_status = [{**row, 'external_sent': False} for row in destinations]
        state = 'prepared' if all(row['configured'] for row in destinations) else 'connection_required'
        if row:
            existing = json.loads(row[0])
            if existing['destinations'] != destination_status:
                existing.update(destinations=destination_status, state=state, checked_at=now())
                db.execute('UPDATE settings SET value=? WHERE key=?', (canonical(existing), key))
                store._event(db, 'newsletter_delivery_preparation_refreshed', {'issue_id': issue_id,
                             'review_hash': expected_hash, 'external_requests': 0}, current['job_id'])
            return existing
        record = {'id': identifier('newsletter_prepared'), 'issue_id': issue_id, 'review_hash': expected_hash,
                  'content_hash': current['hash'], 'prepared_at': now(), 'external_requests': 0,
                  'state': state, 'destinations': destination_status,
                  'note': '전달 준비 기록입니다. 이메일 발송·Slack 게시·웹사이트 게시는 하지 않았습니다.'}
        db.execute('INSERT INTO settings VALUES(?,?)', (key, canonical(record)))
        store._event(db, 'newsletter_delivery_prepared', {'issue_id': issue_id, 'review_hash': expected_hash,
                     'destinations': current['editorial']['destinations'], 'external_requests': 0}, current['job_id'])
        return record


def prepared_delivery(store, issue_id):
    from . import newsletter
    with store.connection() as db:
        current = newsletter._load(db, issue_id)
        newsletter._require_current_issue(db, store, current)
        key = 'newsletter_prepared:' + issue_id + ':' + current['review_hash']
        row = db.execute('SELECT value FROM settings WHERE key=?', (key,)).fetchone()
        if not row:
            return None
        record = json.loads(row[0])
        destinations = [{**item, 'external_sent': False} for item in connection_status()['destinations']
                        if item['key'] in current['editorial']['destinations']]
        return {**record, 'destinations': destinations, 'checked_at': now(),
                'state': 'prepared' if all(item['configured'] for item in destinations) else 'connection_required'}
