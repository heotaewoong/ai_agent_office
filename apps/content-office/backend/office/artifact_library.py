"""Owner-selected generated media lifecycle. Never edits sources, approvals or inputs."""
from __future__ import annotations

from collections import defaultdict
from datetime import datetime, timezone
import hashlib
import hmac
import json
import mimetypes
import os
from pathlib import Path
import re
import shutil
import stat
import time

from .runtime import ProcessLock, AlreadyRunning
from .store import WorkflowError, canonical, digest, now

KEY = 'artifact_library'
BUSY = {'queued', 'running', 'claimed', 'unknown', 'needs_reconciliation'}
SKIP = {'original', 'originals', 'input', 'inputs', 'source', 'sources', 'imports', 'editorial', 'reference', 'references', 'node_modules', '.git'}


def _path(store, relative):
    relative = Path(relative)
    root = store.artifacts
    if root.is_symlink() or relative.is_absolute() or not relative.parts or any(p in {'..', '.'} for p in relative.parts):
        raise WorkflowError('저장 영역 밖의 파일은 정리할 수 없습니다')
    current = root
    for part in relative.parts:
        current /= part
        if current.is_symlink():
            raise WorkflowError('연결 파일은 원본을 확인한 뒤 정리하세요')
    if not current.resolve().is_relative_to(root.resolve()):
        raise WorkflowError('파일 경로가 변경되었습니다')
    return current


def _kind(name):
    name = name.lower()
    if any(word in name for word in ('original', 'source-', 'source_', 'input-')):
        return None
    if name.endswith('.mp4'):
        return 'video'
    if re.fullmatch(r'(?:card|slide)[-_]?\d+\.(?:png|jpg|jpeg)', name):
        return 'cards'
    if name.endswith(('.png', '.jpg', '.jpeg', '.webp')) and re.search(r'thumb|cover', name):
        return 'thumbnail'
    if re.fullmatch(r'(?:summary|checklist|quiz|export|result)(?:[-_].*)?\.pdf', name) or re.fullmatch(r'(?:tistory|naver|blog)(?:[-_].*)?\.(?:html|md|txt)', name):
        return 'document'
    return None


def _stat(path):
    s = path.lstat()
    if not stat.S_ISREG(s.st_mode):
        raise WorkflowError('일반 파일만 정리할 수 있습니다')
    return {'device': s.st_dev, 'inode': s.st_ino, 'bytes': s.st_size, 'mtime': s.st_mtime_ns, 'ctime': s.st_ctime_ns,
            'links': s.st_nlink, 'allocated': getattr(s, 'st_blocks', (s.st_size + 511) // 512) * 512}


def _paths(value):
    if isinstance(value, dict):
        for key, child in value.items():
            if key == 'path' and isinstance(child, str):
                yield child
            else:
                yield from _paths(child)
    elif isinstance(value, list):
        for child in value:
            yield from _paths(child)


def _scan(store, db):
    row = db.execute('SELECT value FROM settings WHERE key=?', (KEY,)).fetchone()
    ledger = json.loads(row[0]) if row else {'entries': {}, 'receipts': {}}
    jobs = {j['id']: j for r in db.execute('SELECT data FROM jobs') if (j := json.loads(r[0]))}
    protected, owners, busy = {}, {}, set()
    for job in jobs.values():
        for path in _paths([job.get('manifest'), job.get('cards'), job.get('quiz'), job.get('thumbnail_studio')]):
            protected[path] = '현재 제작·출고에서 사용 중입니다'
        for path in _paths(job.get('source_packet')):
            protected[path] = '원고 입력·참조 원본입니다'
    for r in db.execute("SELECT payload FROM tasks WHERE state IN ('queued','running','claimed','unknown')"):
        busy.add(json.loads(r[0]).get('job_id'))
    for r in db.execute("SELECT data FROM costs WHERE state IN ('reserved','unknown')"):
        busy.add(json.loads(r[0]).get('job_id'))
    for r in db.execute("SELECT value FROM settings WHERE key IN ('deliveries','owner_draft_deliveries')"):
        for record in json.loads(r[0]).values():
            if record.get('state') in BUSY | {'pending', 'pending_owner', 'office_held', 'created', 'accepted', 'needs_review'}:
                busy.add(record.get('job_id'))
    for job in jobs.values():
        if job.get('state') in {'drafting', 'production_queued', 'producing', 'needs_reconciliation'}:
            busy.add(job['id'])
    busy.discard(None)
    for r in db.execute('SELECT data FROM drafts'):
        draft = json.loads(r[0])
        for path in _paths(draft.get('assets', [])):
            owners.setdefault(path, (draft.get('title'), draft.get('job_id')))
            protected[path] = '원고 입력·참조 원본입니다'
    groups = {}
    if store.artifacts.is_symlink():
        raise WorkflowError('산출물 저장 경로를 확인하세요')
    for folder, dirs, names in os.walk(store.artifacts, followlinks=False):
        dirs[:] = [d for d in dirs if d.lower() not in SKIP and not d.startswith('.') and not (Path(folder) / d).is_symlink()]
        for name in names:
            kind = _kind(name)
            if not kind:
                continue
            relative = (Path(folder) / name).relative_to(store.artifacts).as_posix()
            try:
                path = _path(store, relative)
                fs = _stat(path)
            except (OSError, WorkflowError):
                continue
            group = str(Path(relative).parent / '@cards') if kind == 'cards' else relative
            identity = 'lib_' + digest(group)[:24]
            owner = owners.get(relative, (None, None))
            job_id = owner[1] or next((p for p in Path(relative).parts if p in jobs), None)
            job = jobs.get(job_id, {})
            title = owner[0] or job.get('title') or job.get('article', {}).get('title') or Path(relative).parent.name
            item = groups.setdefault(identity, {'id': identity, 'kind': kind, 'title': str(title or name)[:200],
                'name': '카드뉴스' if kind == 'cards' else name, 'job_id': job_id, 'files': [], 'protected_reason': '', 'state': 'available'})
            item['files'].append({'path': relative, **fs})
            if relative in protected:
                item['protected_reason'] = protected[relative]
            if job_id in busy:
                item['protected_reason'] = '진행 중이거나 결과·비용·전송 확인이 필요한 작업입니다'
    # Keep missing trash members visible as attention, never pretend that they can be restored.
    for identity, entry in ledger['entries'].items():
        if entry['state'] == 'purged':
            candidate = groups.get(identity)
            previous = {f['path']: f for f in entry.get('files', [])}
            if not candidate or all(previous.get(f['path']) == f for f in candidate['files']):
                groups.pop(identity, None)
            continue
        item = groups.get(identity)
        if not item:
            item = {**entry['summary'], 'files': [], 'protected_reason': '파일이 없어 상태 확인이 필요합니다'}
            groups[identity] = item
        item['state'] = entry['state']
        previous = {f['path']: f for f in entry.get('files', [])}
        changed = any(any(f.get(key) != previous.get(f['path'], {}).get(key) for key in ('device', 'inode', 'bytes', 'mtime')) for f in item['files'])
        if sorted(f['path'] for f in item['files']) != sorted(entry['paths']) or changed or entry['state'] == 'attention':
            item.update(state='attention', protected_reason='휴지통 파일 구성이 변경되었습니다. 상태를 확인하세요')
    for item in groups.values():
        item['files'].sort(key=lambda f: f['path'])
        item['size_bytes'] = sum(f['bytes'] for f in item['files'])
        item['file_count'] = len(item['files'])
        item['modified_at'] = datetime.fromtimestamp(max((f['mtime'] for f in item['files']), default=0) / 1e9, timezone.utc).isoformat()
        item['shared'] = any(f['links'] > 1 for f in item['files'])
        item['fingerprint'] = digest(item)
    return groups, ledger


def _public(item):
    return {k: v for k, v in item.items() if k not in {'files', 'fingerprint'}} | {
        'preview_url': f"/api/library/items/{item['id']}/files/0" if item['file_count'] else None}


def inventory(store):
    with store.connection() as db:
        groups, _ = _scan(store, db)
    disk = shutil.disk_usage(store.artifacts)
    return {'items': sorted((_public(v) for v in groups.values()), key=lambda x: (x['modified_at'], x['id']), reverse=True),
            'storage': {'total_bytes': disk.total, 'used_bytes': disk.used, 'free_bytes': disk.free}, 'checked_at': now()}


def _selection(groups, ids, action):
    if not ids or len(ids) > 100 or len(set(ids)) != len(ids) or action not in {'trash', 'restore', 'purge'}:
        raise WorkflowError('선택 항목과 요청을 다시 확인하세요')
    try:
        chosen = [groups[i] for i in sorted(ids)]
    except KeyError:
        raise WorkflowError('선택한 파일이 변경되었습니다. 새로 확인하세요') from None
    expected = 'available' if action == 'trash' else 'trash'
    for item in chosen:
        if item['state'] != expected or (action != 'restore' and item['protected_reason']):
            raise WorkflowError(item['protected_reason'] or '현재 상태에서는 이 작업을 할 수 없습니다')
    return chosen


def _quote(store, chosen, action, stamp=None):
    files = {f['path']: f for item in chosen for f in item['files']}
    inodes = defaultdict(list)
    for file in files.values():
        inodes[(file['device'], file['inode'])].append(file)
    reclaim = sum(rows[0]['allocated'] for rows in inodes.values() if len(rows) == rows[0]['links'])
    secret = (store.root / '.session-secret').read_bytes()
    stamp = int(time.time()) if stamp is None else stamp
    signature = hmac.new(secret, canonical({'at': stamp, 'action': action, 'items': [(i['id'], i['fingerprint']) for i in chosen]}).encode(), hashlib.sha256).hexdigest()
    return {'token': f'{stamp}.{signature}', 'count': len(chosen), 'size_bytes': sum(f['bytes'] for f in files.values()),
            'reclaimable_bytes': reclaim if action == 'purge' else 0, 'shared_files': sum(f['links'] > 1 for f in files.values())}


def quote(store, ids, action):
    with store.connection() as db:
        groups, _ = _scan(store, db)
    return _quote(store, _selection(groups, ids, action), action)


def _unlink(store, file):
    relative = file['path']
    path = _path(store, relative)
    actual = _stat(path)
    if any(actual[k] != file[k] for k in ('device', 'inode', 'bytes', 'mtime')):
        raise WorkflowError('삭제 도중 파일이 변경되었습니다')
    if os.name == 'posix':
        flags = os.O_RDONLY | os.O_DIRECTORY | os.O_NOFOLLOW
        fd = os.open(store.artifacts, flags)
        try:
            for part in Path(relative).parts[:-1]:
                child = os.open(part, flags, dir_fd=fd)
                os.close(fd)
                fd = child
            name = Path(relative).name
            current = os.stat(name, dir_fd=fd, follow_symlinks=False)
            if (current.st_dev, current.st_ino, current.st_size, current.st_mtime_ns) != (file['device'], file['inode'], file['bytes'], file['mtime']):
                raise WorkflowError('삭제 도중 파일 경로가 변경되었습니다')
            os.unlink(name, dir_fd=fd)
        finally:
            os.close(fd)
    else:
        path.unlink()


def change(store, ids, action, token, request_id):
    if not re.fullmatch(r'[a-zA-Z0-9_-]{1,80}', request_id):
        raise WorkflowError('요청 식별자가 올바르지 않습니다')
    try:
        with ProcessLock(store.root / 'runtime' / 'artifact-library.lock'):
            with store.connection(transaction=True) as db:
                groups, ledger = _scan(store, db)
                identity = digest({'ids': sorted(ids), 'action': action, 'quote': token})
                previous = ledger['receipts'].get(request_id)
                if previous:
                    if previous['identity'] != identity:
                        raise WorkflowError('같은 요청 식별자의 내용이 다릅니다')
                    return previous['result']
                try:
                    stamp = int(token.split('.', 1)[0])
                except ValueError:
                    raise WorkflowError('확인 정보가 올바르지 않습니다') from None
                if not 0 <= time.time() - stamp <= 300:
                    raise WorkflowError('확인 유효시간이 지났습니다. 새로 확인하세요')
                chosen = _selection(groups, ids, action)
                estimate = _quote(store, chosen, action, stamp)
                if not hmac.compare_digest(token, estimate['token']):
                    raise WorkflowError('파일 또는 사용 상태가 변경되었습니다. 새로 확인하세요')
                deleted, failure = [], False
                for item in chosen:
                    if action == 'restore':
                        ledger['entries'].pop(item['id'], None)
                        continue
                    entry = {'state': 'trash', 'paths': [f['path'] for f in item['files']], 'files': item['files'], 'summary': _public(item), 'updated_at': now()}
                    ledger['entries'][item['id']] = entry
                    if action == 'purge':
                        for file in item['files']:
                            try:
                                _unlink(store, file)
                                deleted.append(file['path'])
                            except (OSError, WorkflowError):
                                failure = True
                                break
                        entry['state'] = 'attention' if failure else 'purged'
                        if failure:
                            break
                result = {'state': 'partial' if failure else 'completed', 'action': action, 'count': len(chosen),
                          'deleted_files': len(deleted), 'reclaimable_bytes': estimate['reclaimable_bytes'] if action == 'purge' and not failure else None,
                          'message': '일부 파일 처리에 실패했습니다. 다시 삭제하지 말고 목록 상태를 확인하세요' if failure else '요청한 산출물 정리를 완료했습니다'}
                ledger['receipts'][request_id] = {'identity': identity, 'result': result}
                ledger['receipts'] = dict(list(ledger['receipts'].items())[-200:])
                db.execute('INSERT OR REPLACE INTO settings VALUES(?,?)', (KEY, canonical(ledger)))
                store._event(db, 'artifact_library_' + action, {'ids': sorted(ids), 'request_id': request_id,
                    'state': result['state'], 'deleted_paths': deleted, 'sources_and_approvals_preserved': True})
                return result
    except AlreadyRunning:
        raise WorkflowError('다른 정리 요청을 처리 중입니다. 목록을 새로 확인하세요') from None


def require_available(store, relative):
    ledger = store.setting(KEY, {'entries': {}})
    for row in ledger['entries'].values():
        if relative not in row['paths']:
            continue
        if row['state'] == 'purged':
            try:
                previous = next(f for f in row.get('files', []) if f['path'] == relative)
                if _stat(_path(store, relative)) != {k: v for k, v in previous.items() if k != 'path'}:
                    continue
            except (OSError, StopIteration):
                pass
        raise WorkflowError('휴지통 또는 삭제된 산출물입니다. 산출물 보관함에서 상태를 확인하세요')


def preview_file(store, identity, index):
    with store.connection() as db:
        groups, _ = _scan(store, db)
    item = groups.get(identity)
    if not item or not 0 <= index < len(item['files']):
        raise WorkflowError('미리볼 파일이 없습니다')
    path = _path(store, item['files'][index]['path'])
    return path, mimetypes.guess_type(path.name)[0] or 'application/octet-stream'
