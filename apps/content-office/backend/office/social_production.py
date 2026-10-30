"""Reuse verified current social cards or create them once for production."""
import hashlib
from pathlib import Path
from .store import WorkflowError,canonical,digest

def card_paths(store,job_id,source_hash,folder):
    from .cards import plan_cards
    job=store.require_source_approval(job_id)
    if job['source_hash']!=source_hash:raise WorkflowError('카드 제작 원고가 변경되었습니다')
    cards=job.get('cards') or {}
    if cards.get('source_hash')!=source_hash or (cards.get('checks') or {}).get('passed') is not True:
        with store.connection() as db:
            pending=db.execute("SELECT 1 FROM tasks WHERE kind='cards' AND state IN ('queued','running','unknown') AND json_extract(payload,'$.job_id')=? AND json_extract(payload,'$.source_hash')=?",(job_id,source_hash)).fetchone()
        if pending:raise WorkflowError('별도 카드 작업이 대기·진행·결과 불명입니다. 결과를 확인한 뒤 카드 제작을 다시 요청하세요')
        cards=plan_cards(store,job_id,require_passed=True)
    if cards.get('source_hash')!=source_hash or (cards.get('checks') or {}).get('passed') is not True or not 6<=len(cards.get('slides',[]))<=8:
        raise WorkflowError('카드뉴스 검사 이슈가 남아 출고 제작물에 넣지 않았습니다. 카드뉴스 영역을 확인하세요')
    root=store.artifacts.resolve();paths=[];seen=set()
    for slide in cards['slides']:
        record=slide.get('artifact') or {}
        path=(root/record.get('path','')).resolve()
        if not path.is_relative_to(root) or not path.is_file() or hashlib.sha256(path.read_bytes()).hexdigest()!=record.get('sha256'):
            raise WorkflowError('카드뉴스 파일 검증에 실패했습니다. 새로 검수해 주세요')
        if record['sha256'] in seen:raise WorkflowError('같은 카드 이미지가 중복되어 있습니다. 카드 순서를 다시 검수해 주세요')
        seen.add(record['sha256'])
        paths.append(path)
    metadata=Path(folder)/f'card-news-{digest(cards)[:16]}.json'
    payload=canonical(cards)
    if metadata.exists() and metadata.read_text(encoding='utf-8')!=payload:raise WorkflowError('기존 카드 검토 기록이 변경되었습니다')
    if not metadata.exists():metadata.write_text(payload,encoding='utf-8')
    latest=store.require_source_approval(job_id)
    if latest['source_hash']!=source_hash:raise WorkflowError('카드 연결 중 원고가 변경되었습니다')
    return [metadata,*paths]
