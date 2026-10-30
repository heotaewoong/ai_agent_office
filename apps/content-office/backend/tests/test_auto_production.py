import pytest
from office.store import Store,WorkflowError

def ready(store):
    job=store.create_job({'id':'own','title':'내 원고','url':''})
    return store.save_source(job['id'],{'title':'내 글','body':'원고','quality':{'status':'passed','critical':False},'evidence':[]})

def test_approval_and_production_are_saved_in_one_transaction(tmp_path):
    store=Store(tmp_path);job=ready(store)
    result=store.review_source(job['id'],job['source_hash'],'approved','owner',{'blog':True,'video':True,'cards':True},production_contract='a'*64)
    assert result['state']=='production_queued' and result['source_approval']['decision']=='approved'
    task=store.tasks()[0]
    assert task['payload']['source_hash']==result['source_hash'] and task['payload']['production_contract']=='a'*64
    assert task['kind']=='produce' and task['state']=='queued'
    with pytest.raises(WorkflowError,match='이미'):store.review_source(job['id'],job['source_hash'],'approved','owner',production_contract='a'*64)
    assert len(store.tasks())==1

@pytest.mark.parametrize('case',['stale','critical','invalid_contract','rejected'])
def test_failed_approval_never_leaves_a_queue_or_approval(tmp_path,case):
    store=Store(tmp_path);job=ready(store)
    if case=='critical':
        job=store.save_source(job['id'],{'title':'글','body':'글','quality':{'status':'blocked','critical':True}})
    version='old' if case=='stale' else job['source_hash']
    with pytest.raises(WorkflowError):store.review_source(job['id'],version,'rejected' if case=='rejected' else 'approved','owner',production_contract='bad' if case=='invalid_contract' else 'a'*64)
    assert store.tasks()==[] and store.job(job['id'])['source_approval'] is None

def test_unknown_production_blocks_a_different_profile_retry(tmp_path):
    store=Store(tmp_path);job=ready(store)
    task=store.enqueue('produce',{'job_id':job['id'],'source_hash':job['source_hash']},key='unknown')
    store.claim('worker');store.finish_task(task['id'],'worker',{'error':'unknown'},state='unknown')
    with pytest.raises(WorkflowError,match='결과 불명'):store.review_source(job['id'],job['source_hash'],'approved','owner',production_contract='b'*64)
    assert len(store.tasks())==1 and store.job(job['id'])['source_approval'] is None
