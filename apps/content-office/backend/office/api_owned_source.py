from fastapi import FastAPI,HTTPException
from fastapi.responses import FileResponse
from pydantic import BaseModel,Field,ConfigDict
from .owned_source import preview_tistory,create_owned_job
from .evidence import reference_url
from .store import WorkflowError

class Preview(BaseModel):
    model_config=ConfigDict(extra='forbid')
    url:str=Field(min_length=1,max_length=2000)

class Intake(BaseModel):
    model_config=ConfigDict(extra='forbid')
    title:str=Field(min_length=1,max_length=200)
    body:str=Field(min_length=100,max_length=50000)
    source_url:str=Field(default='',max_length=2000)
    owner_confirmed:bool=Field(strict=True)

def register(app:FastAPI,store):
    @app.get('/api/jobs/{job_id}/drafts/{draft_id}/files/{name}')
    def draft_asset(job_id:str,draft_id:str,name:str):
        from .api_quiz_cards import _verified_path
        from .editorial_assets import KINDS
        from pathlib import Path
        draft=next((d for d in store.drafts(job_id) if d['id']==draft_id),None)
        record=next((f for f in (draft or {}).get('assets',[]) if f.get('name')==name),None)
        if not record or Path(name).suffix.lower() not in KINDS:raise HTTPException(404,'검토 파일을 찾지 못했습니다')
        path=_verified_path(store,record)
        return FileResponse(path,media_type=KINDS[Path(name).suffix.lower()],headers={'Cache-Control':'no-store','X-Content-Type-Options':'nosniff','Content-Disposition':'inline' if record['media_type'].startswith(('image/','video/')) else 'attachment'})

    @app.post('/api/owned-source/preview')
    def preview(request:Preview):return preview_tistory(request.url)

    @app.post('/api/owned-source/jobs')
    def create(request:Intake):
        if not request.owner_confirmed or not request.title.strip() or len(request.body.strip())<100:
            raise WorkflowError('사용 권한과 제목을 확인해 주세요')
        if request.source_url:
            try:
                if any(c.isspace() for c in request.source_url):raise ValueError()
                reference_url(request.source_url)
            except ValueError:raise WorkflowError('올바른 공개 HTTPS 원문 주소를 입력해 주세요') from None
        return create_owned_job(store,request.title.strip(),request.body,request.source_url)
