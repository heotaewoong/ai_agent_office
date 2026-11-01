"""Source-approved, nonpublic drafts. Never creates release approvals or public posts."""
import hashlib
import json
import re
from pathlib import Path
from urllib.parse import urlparse

from .channels import channel
from .runtime import window_open
from .store import WorkflowError, canonical, digest, identifier, now

SETTING = 'owner_draft_deliveries'
TARGETS = ('youtube_main_ko', 'youtube_english', 'instagram_main', 'instagram_english',
           'threads_main', 'linkedin_personal', 'tistory_main', 'naver_blog_main')
TEXT_FILES = {'tistory_main': 'blog.md', 'naver_blog_main': 'naver.txt',
              'threads_main': 'threads-main.txt', 'linkedin_personal': 'linkedin-personal.txt',
              'instagram_main': 'instagram-main-caption.txt', 'instagram_english': 'instagram-english-caption.txt'}


def snapshot(store, key):
    row = channel(store, key)
    return {k: row.get(k) for k in ('key', 'platform', 'locale', 'public_url', 'external_account_id', 'publication_enabled')}


def policy(store, job, targets, actor):
    if not isinstance(targets, list) or len(targets) > len(TARGETS) or any(not isinstance(k,str) for k in targets) or len(set(targets)) != len(targets):
        raise WorkflowError('초안 채널 선택이 올바르지 않습니다')
    rows = []
    language = ((job.get('source_packet') or {}).get('audience') or {}).get('language')
    for key in targets:
        if key not in TARGETS:
            raise WorkflowError('비공개·임시저장 대상이 아닌 채널입니다')
        row = snapshot(store, key)
        if row['locale'] != language or not row['publication_enabled'] or not row['public_url']:
            raise WorkflowError('초안 채널의 언어·전송 허용·주소를 확인하세요')
        if row['platform'] == 'youtube' and not row['external_account_id']:
            raise WorkflowError('대상 YouTube 채널 ID를 먼저 확인하세요')
        outputs = job.get('selections') or {}
        if row['platform'] == 'youtube' and not outputs.get('video'):
            raise WorkflowError('YouTube 비공개 초안에는 영상 제작을 선택하세요')
        if row['platform'] != 'youtube' and not outputs.get('blog'):
            raise WorkflowError('웹 초안에는 블로그·소셜 원고 제작을 선택하세요')
        if row['platform'] == 'instagram' and not (outputs.get('video') or outputs.get('cards')):
            raise WorkflowError('Instagram에는 카드 또는 영상 제작도 선택하세요')
        rows.append(row)
    return {'source_hash': job['source_hash'], 'channels': rows, 'actor': actor,
            'created_at': now(), 'visibility': 'private_or_draft', 'public_publish': False}


def _approved(store, jid):
    job = store.require_source_approval(jid)
    selected = job.get('owner_draft_policy') or {}
    if selected.get('source_hash') != job['source_hash'] or selected.get('public_publish') is not False:
        raise WorkflowError('현재 원고의 비공개 초안 선택이 필요합니다')
    for row in selected.get('channels', []):
        if row != snapshot(store, row['key']):
            raise WorkflowError('초안 대상 채널이 변경됐습니다. 원고 승인에서 다시 선택하세요')
    return job, selected


def _file(store, record):
    root = store.artifacts.resolve()
    path = (root / record['path']).resolve()
    if not path.is_relative_to(root) or not path.is_file() or path.stat().st_size > 100_000_000:
        raise WorkflowError('초안 파일 경로·크기를 확인하세요')
    if hashlib.sha256(path.read_bytes()).hexdigest() != record.get('sha256'):
        raise WorkflowError('초안 파일이 변경됐습니다')
    return path


def _ledger(db):
    row = db.execute('SELECT value FROM settings WHERE key=?', (SETTING,)).fetchone()
    return json.loads(row[0]) if row else {}


def _save(db, rows):
    db.execute('INSERT OR REPLACE INTO settings VALUES(?,?)', (SETTING, canonical(rows)))


def prepare(store, jid):
    if not (store.job(jid).get('owner_draft_policy') or {}).get('channels'):
        return []
    job, selected = _approved(store, jid)
    manifest = job.get('manifest') or {}
    if manifest.get('source_hash') != job['source_hash']:
        raise WorkflowError('현재 원고로 제작한 파일이 필요합니다')
    records = {r['name']: r for r in manifest.get('files', [])}
    result = []
    for target in selected['channels']:
        key = target['key']
        video = target['platform'] == 'youtube'
        needed = ['short.mp4', 'description.txt'] if video else [TEXT_FILES[key]]
        # Instagram drafts must include the selected media, never just an uploaded caption.
        if target['platform'] == 'instagram':
            needed += ['short.mp4'] if job['selections'].get('video') else sorted(n for n in records if re.fullmatch(r'scene-\d+\.png', n))
            if len(needed) < 2:
                needed.append('출력 카드 또는 영상')
        missing = [name for name in needed if name not in records]
        files = [records[name] for name in needed if name in records]
        for record in files:
            _file(store, record)
        text_name = 'description.txt' if video else TEXT_FILES[key]
        text_file = records.get(text_name)
        text = ''
        if text_file:
            path = _file(store, text_file)
            if path.stat().st_size > 150_000:
                raise WorkflowError('초안 본문이 허용 크기를 넘었습니다')
            text = path.read_text(encoding='utf-8')
        packet = job.get('source_packet') or {}
        title = (packet.get('video') or {}).get('title', job['title']) if video else job['title']
        if video and (len(title) > 100 or len(text) > 5000):
            missing.append('YouTube 제목·설명 길이 확인')
        account = target['external_account_id'] or urlparse(target['public_url']).path.strip('/')
        content = {'channel_key': key, 'account_id': account, 'title': title, 'text': text,
                   'files': files, 'source_hash': job['source_hash'], 'manifest_hash': manifest['hash'],
                   'target': target, 'visibility': 'private' if video else 'draft'}
        checksum = digest(content)
        result.append({**content, 'id': 'od_' + checksum[:24], 'job_id': jid, 'content_hash': checksum,
                       'state': 'blocked' if missing else 'pending',
                       'reason': '필요한 제작 파일이 없습니다' if missing else None, 'created_at': now()})
    with store.connection(transaction=True) as db:
        current = store._job(db, jid)
        if (current['source_hash'], current.get('manifest'), current.get('owner_draft_policy'), current.get('source_approval')) != (job['source_hash'], manifest, selected, job['source_approval']):
            raise WorkflowError('초안 준비 중 원고·제작물·선택이 변경됐습니다')
        rows = _ledger(db)
        for item in result:
            rows.setdefault(item['id'], item)
        _save(db, rows)
        store._event(db, 'owner_drafts_prepared', {'ids': [r['id'] for r in result], 'public_sent': False}, jid)
        return [rows[r['id']] for r in result]


def _current(store, row):
    job, selected = _approved(store, row['job_id'])
    if job['source_hash'] != row['source_hash'] or (job.get('manifest') or {}).get('hash') != row['manifest_hash'] or row['target'] not in selected['channels']:
        raise WorkflowError('현재 원고·파일·초안 대상 판본과 다릅니다')
    for record in row['files']:
        _file(store, record)
    return job


def view(store, jid):
    rows = store.setting(SETTING, {})
    job = store.job(jid)
    return {'policy': job.get('owner_draft_policy'), 'items': [r for r in rows.values() if r['job_id'] == jid and r.get('source_hash') == job.get('source_hash') and r.get('manifest_hash') == (job.get('manifest') or {}).get('hash')],
            'note': '플랫폼 비공개·임시저장만 허용합니다. 공개·예약 발행과 출고 승인②를 실행하지 않습니다'}


def pending(store):
    window = store.setting('work_window', {})
    if not window.get('authorized_end') or not window_open(store):
        return []
    result = []
    for row in store.setting(SETTING, {}).values():
        if row['state'] != 'pending':
            continue
        try:
            _current(store, row)
            result.append({**row, 'authorized_end': window['authorized_end']})
        except WorkflowError:
            continue
    return result


def claim(store, rid, actor):
    if not actor or not store.setting('work_window', {}).get('authorized_end') or not window_open(store):
        raise WorkflowError('승인한 작업 시간이 필요합니다')
    row = store.setting(SETTING, {}).get(rid)
    if not row:
        raise WorkflowError('초안 전달을 찾을 수 없습니다')
    checked_job = _current(store, row)
    with store.connection(transaction=True) as db:
        rows = _ledger(db)
        current = rows.get(rid)
        job = store._job(db, row['job_id'])
        if current != row or current['state'] != 'pending' or any(job.get(k) != checked_job.get(k) for k in ('source_hash', 'manifest', 'source_approval', 'owner_draft_policy')):
            raise WorkflowError('이미 처리 중이거나 초안 판본이 변경됐습니다')
        current.update(state='claimed', claim_id=identifier('claim'), claimed_at=now(), claimed_by=actor)
        _save(db, rows)
        return {**current, 'authorized_end': store.setting('work_window', {})['authorized_end']}


def receipt(store, rid, proof):
    allowed = {'state', 'claim_id', 'content_hash', 'account_id', 'external_id', 'reason'}
    if not isinstance(proof, dict) or set(proof) - allowed or proof.get('state') not in ('platform_private', 'platform_draft', 'blocked', 'unknown'):
        raise WorkflowError('공개 결과 또는 잘못된 초안 결과입니다')
    row = store.setting(SETTING, {}).get(rid)
    if not row:
        raise WorkflowError('초안 전달을 찾을 수 없습니다')
    _current(store, row)
    if any(proof.get(k) != row.get(k) for k in ('claim_id', 'content_hash', 'account_id')):
        raise WorkflowError('초안 결과의 본문·계정·처리 키가 다릅니다')
    expected = 'platform_private' if row['visibility'] == 'private' else 'platform_draft'
    if proof['state'] not in (expected, 'blocked', 'unknown') or (proof['state'] == expected and not re.fullmatch(r'[A-Za-z0-9_:/?.=&@%#\-]{1,500}', proof.get('external_id', ''))):
        raise WorkflowError('플랫폼의 비공개·임시저장 확인이 필요합니다')
    with store.connection(transaction=True) as db:
        rows = _ledger(db)
        if rows.get(rid) != row or row['state'] != 'claimed':
            raise WorkflowError('현재 처리 중인 초안 결과가 아닙니다')
        row.update(state=proof['state'], external_id=proof.get('external_id'), reason=str(proof.get('reason', ''))[:200], verified_at=now())
        rows[rid] = row
        _save(db, rows)
        store._event(db, 'owner_draft_result', {'id': rid, 'state': row['state'], 'public_sent': False}, row['job_id'])
    return row


def claimed(store, rid, claim_id):
    if not store.setting('work_window', {}).get('authorized_end') or not window_open(store):
        raise WorkflowError('초안 작업 시간이 종료됐습니다')
    row = store.setting(SETTING, {}).get(rid)
    if not row or row['state'] != 'claimed' or row.get('claim_id') != claim_id:
        raise WorkflowError('현재 PC가 처리 중인 초안이 아닙니다')
    _current(store, row)
    return {**row, 'authorized_end': store.setting('work_window', {})['authorized_end']}
