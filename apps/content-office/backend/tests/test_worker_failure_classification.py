"""BDD: known pre-model source failures must remain recoverable, not billing-unknown."""
from datetime import datetime, timedelta, timezone

import pytest

from office import worker
from office.store import SourceUnavailable, Store, WorkflowError


@pytest.mark.parametrize('source_unavailable', [True, False])
def test_known_source_failure_can_be_explicitly_retried_but_model_unknown_cannot(tmp_path, monkeypatch, source_unavailable):
    store = Store(tmp_path)
    store.set_setting('work_window', {'status':'open', 'authorized_end':(datetime.now(timezone.utc)+timedelta(minutes=5)).isoformat()})
    job = store.create_job({'id':'failure-fixture','title':'수집 실패 분류 검증'})
    task = store.enqueue('draft', {'job_id':job['id'],'source_hash':None}, 'source-fixture')
    def fail(*args):
        if source_unavailable:
            raise SourceUnavailable('원문을 직접 확인하지 못했습니다. 공개 원문을 보완하세요')
        raise WorkflowError('모델 응답을 확인하지 못했습니다. 비용 예약을 유지하며 자동 재호출하지 않습니다')
    monkeypatch.setattr(worker, 'process_task', fail)
    assert worker.run_once(store, 'fixture-worker')
    assert store.task(task['id'])['state'] == ('failed' if source_unavailable else 'unknown')
    assert store.job(job['id'])['state'] == ('blocked' if source_unavailable else 'needs_reconciliation')
    assert store.job(job['id'])['source_approval'] is None
    assert store.budget()['spent_krw'] == store.budget()['reserved_krw'] == 0
    retried = store.enqueue('draft', {'job_id':job['id'],'source_hash':None}, 'source-fixture')
    assert (retried['id'] != task['id']) is source_unavailable
