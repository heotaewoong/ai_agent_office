"""Attach review media to an editorial draft without replacing approved production."""
import hashlib
import re
from pathlib import Path
from .store import WorkflowError,digest

KINDS={'.png':'image/png','.jpg':'image/jpeg','.mp4':'video/mp4','.md':'text/plain','.txt':'text/plain','.srt':'text/plain'}

def register_assets(store,job_id,source_hash,title,body,files):
    if not re.fullmatch(r'job_[a-zA-Z0-9_-]+',job_id) or not re.fullmatch(r'[0-9a-f]{64}',source_hash or ''):
        raise WorkflowError('연결할 작업과 원고 판본을 확인해 주세요')
    if not title.strip() or len(title)>200 or not body.strip() or len(body)>50000 or len(files)>32:
        raise WorkflowError('편집 결과의 제목·본문·파일 수를 확인해 주세요')
    if not files:raise WorkflowError('연결할 검토 파일이 없습니다')
    if store.job(job_id).get('source_hash')!=source_hash:raise WorkflowError('연결 대상 원고가 변경되었습니다')
    records=[];total=0;seen=set()
    for name,path in files:
        path=Path(path)
        if name in seen or not name or Path(name).name!=name or any(c in name for c in '/\\:') or Path(name).suffix.lower() not in KINDS:
            raise WorkflowError('검토 파일 이름 또는 형식을 확인해 주세요')
        seen.add(name);total+=path.stat().st_size
        if total>64*1024*1024 or path.stat().st_size>32*1024*1024:raise WorkflowError('검토 파일 용량 한도를 넘었습니다')
        with path.open('rb') as f:data=f.read(32*1024*1024+1)
        if len(data)>32*1024*1024:raise WorkflowError('검토 파일 용량이 변경되었습니다')
        checksum=hashlib.sha256(data).hexdigest()
        relative=Path(job_id)/source_hash/'editorial'/checksum/name
        destination=store.artifacts/relative
        if not destination.resolve().is_relative_to(store.artifacts.resolve()):raise WorkflowError('검토 파일 경로가 저장 영역 밖입니다')
        destination.parent.mkdir(parents=True,exist_ok=True)
        if destination.exists() and destination.read_bytes()!=data:raise WorkflowError('같은 검토 파일의 내용이 달라졌습니다')
        destination.write_bytes(data)
        records.append({'name':name,'path':relative.as_posix(),'sha256':checksum,'size':len(data),'media_type':KINDS[Path(name).suffix.lower()]})
    return store.add_draft(job_id,{'title':title,'body':body,'assets':records,'source_hash_snapshot':source_hash,'note':'미승인 편집 검토본입니다. 원고·제작물·출고 승인을 대체하지 않습니다.'},expected_source_hash=source_hash)
