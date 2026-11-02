"""Recoverable visibility; files, approvals, costs and external posts stay intact."""
import json
from .store import WorkflowError, canonical, now


def move(store, job_id, expected_updated_at, *, restore=False):
    with store.connection(transaction=True) as db:
        job = store._job(db, job_id, include_deleted=True)
        if job['updated_at'] != expected_updated_at:
            raise WorkflowError('작업이 변경됐습니다. 최신 내용을 확인한 뒤 다시 요청하세요')
        if bool(job.get('deleted_at')) != restore:
            raise WorkflowError('이미 복원됐거나 휴지통으로 이동한 작업입니다. 목록을 새로 확인하세요')
        if not restore:
            if job['state'] in ('drafting', 'production_queued', 'producing', 'needs_reconciliation') or db.execute(
                "SELECT 1 FROM tasks WHERE json_extract(payload,'$.job_id')=? AND state IN ('queued','running','claimed','unknown') LIMIT 1", (job_id,)
            ).fetchone():
                raise WorkflowError('진행·대기·결과 불명 작업이 있습니다. 운영 기록에서 결과를 확인한 뒤 삭제하세요')
            if db.execute("SELECT 1 FROM costs WHERE json_extract(data,'$.job_id')=? AND state IN ('reserved','unknown') LIMIT 1", (job_id,)).fetchone():
                raise WorkflowError('미정산 비용 예약이 있습니다. 비용 결과를 확인한 뒤 삭제하세요')
            for key in ('owner_draft_deliveries', 'deliveries'):
                row = db.execute('SELECT value FROM settings WHERE key=?', (key,)).fetchone()
                records = json.loads(row[0]) if row else {}
                if any(r.get('job_id') == job_id and r.get('state') in ('pending','pending_owner','office_held','claimed','created','accepted','unknown','needs_review') for r in records.values()):
                    raise WorkflowError('전송 대기 또는 확인 중인 결과가 있습니다. 전달 상태를 확인한 뒤 삭제하세요')
            job.update(deleted_at=now(), deleted_by='local-operator')
        else:
            job.pop('deleted_at', None)
            job.pop('deleted_by', None)
        job['updated_at'] = now()
        db.execute('UPDATE jobs SET data=?,updated_at=? WHERE id=?', (canonical(job),job['updated_at'],job_id))
        store._event(db, 'job_restored' if restore else 'job_trashed', {'actor':'local-operator','source_hash':job.get('source_hash'),'files_preserved':True}, job_id)
        return job
