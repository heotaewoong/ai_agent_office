"""Read-only history and immutable production references; never adopts or approves."""
import json
from .store import canonical, now


def archive_production(db, job):
    manifest = job.get('manifest')
    if not manifest or not manifest.get('hash'):
        return
    record = {'manifest': manifest, 'created_at': job.get('updated_at') or now()}
    db.execute('INSERT OR IGNORE INTO settings VALUES(?,?)',
               (f"history:{job['id']}:{manifest['hash']}", canonical(record)))


def history(store, job_id):
    with store.connection() as db:
        job = store._job(db, job_id)
        sources = [{'id': r[0], 'packet': json.loads(r[1]), 'created_at': r[2]}
                   for r in db.execute('SELECT hash,packet,created_at FROM versions WHERE job_id=? ORDER BY created_at,hash', (job_id,))]
        prefix = f'history:{job_id}:'
        productions = [json.loads(r[0]) for r in db.execute('SELECT value FROM settings WHERE substr(key,1,?)=?', (len(prefix), prefix))]
        approvals = [json.loads(r[0]) for r in db.execute('SELECT data FROM approvals WHERE job_id=? ORDER BY created_at', (job_id,))]
    current = job.get('manifest')
    if current:
        productions = [p for p in productions if p['manifest']['hash'] != current['hash']]
        productions.append({'manifest': current, 'created_at': job['updated_at']})
    productions.sort(key=lambda p: (p['created_at'], p['manifest']['hash']))
    for p in productions:
        m = p['manifest']
        p['current'] = bool(current and current['hash'] == m['hash'])
        p['approved_before'] = any(a.get('version') == m['hash'] and a.get('decision') == 'approved' for a in approvals)
        m['files'] = [{**f, 'url': f"/api/jobs/{job_id}/history/{m['hash']}/files/{f['id']}"} for f in m.get('files', [])]
    for s in sources:
        s['current'] = s['id'] == job.get('source_hash')
        s['approved_before'] = any(a.get('version') == s['id'] and a.get('decision') == 'approved' for a in approvals)
    return {'job_id': job_id, 'current_source_hash': job.get('source_hash'), 'current_manifest_hash': (current or {}).get('hash'), 'sources': sources,
            'productions': productions, 'drafts': store.drafts(job_id)}


def register(app, store):
    from fastapi import HTTPException
    from fastapi.responses import FileResponse
    from .api_quiz_cards import _verified_path
    import mimetypes

    @app.get('/api/jobs/{job_id}/history')
    def read_history(job_id: str):
        return history(store, job_id)

    @app.get('/api/jobs/{job_id}/history/{manifest_hash}/files/{artifact_id}')
    def history_file(job_id: str, manifest_hash: str, artifact_id: str):
        for p in history(store, job_id)['productions']:
            if p['manifest']['hash'] == manifest_hash:
                for f in p['manifest'].get('files', []):
                    if f.get('id') == artifact_id:
                        path = _verified_path(store, f)
                        return FileResponse(path, media_type=mimetypes.guess_type(path.name)[0] or 'application/octet-stream', filename=path.name)
        raise HTTPException(404, '이 버전의 파일을 찾을 수 없습니다')
