from datetime import date, datetime
from zoneinfo import ZoneInfo
import re
from typing import Literal
from urllib.parse import urlsplit, parse_qsl
from fastapi import FastAPI
from fastapi.responses import JSONResponse, Response
from pydantic import BaseModel, ConfigDict, Field, StrictInt
from .store import WorkflowError, digest
from .improvements import workspace, save_review, save_record, learning_contract


class Input(BaseModel):
    model_config = ConfigDict(extra='forbid')


class Versioned(Input):
    source_hash: str = Field(pattern=r'^[0-9a-f]{64}$')


class Revision(Input):
    expected_hash: str = Field(pattern=r'^[0-9a-f]{64}$')


class JobClip(Versioned):
    profile: Literal['none', 'global']
    override_hash: str = Field(pattern=r'^[0-9a-f]{64}$')


class Review(Versioned):
    case_id: str = Field(default='', pattern=r'^(?:[AB](?:0[1-9]|10))?$')
    target_id: str = Field(min_length=1, max_length=100)
    target_hash: str = Field(pattern=r'^[0-9a-f]{64}$')
    scores: dict[str, StrictInt]
    critical: bool = Field(strict=True)
    reasons: list[str] = Field(max_length=6)
    note: str = Field(min_length=1, max_length=1500)


class Experience(Input):
    title: str = Field(min_length=1, max_length=150)
    axis: Literal['A', 'B', 'both']
    facts: str = Field(min_length=10, max_length=2500)
    evidence_note: str = Field(min_length=1, max_length=1000)
    checked_on: date
    tags: list[str] = Field(min_length=1, max_length=8)
    confirmed: bool = Field(strict=True)
    use_in_content: bool = Field(strict=True)


class Learning(Versioned):
    quiz_hash: str = Field(pattern=r'^[0-9a-f]{64}$')
    question_id: str = Field(min_length=1, max_length=100)
    observation_key: str = Field(pattern=r'^[a-zA-Z0-9_-]{1,80}$')
    attempts: StrictInt = Field(ge=1, le=1000000)
    correct: StrictInt = Field(ge=0, le=1000000)


class Outcome(Versioned):
    channel_id: str = Field(pattern=r'^[a-zA-Z0-9_-]{1,80}$')
    campaign_id: str = Field(default='', max_length=80, pattern=r'^[a-zA-Z0-9_-]*$')
    variant_id: str = Field(default='', max_length=80, pattern=r'^[a-zA-Z0-9_-]*$')
    observed_on: date
    period: Literal['24h', '7d', '28d']
    external_url: str = Field(min_length=1, max_length=1500)
    views: StrictInt = Field(ge=0, le=1000000000)
    saves: StrictInt = Field(ge=0, le=1000000000)
    quiz_completed: StrictInt = Field(ge=0, le=1000000000)
    downloads: StrictInt = Field(ge=0, le=1000000000)
    free_orders: StrictInt = Field(ge=0, le=1000000000)
    paid_orders: StrictInt = Field(ge=0, le=1000000000)
    paid_revenue_krw: StrictInt = Field(ge=0, le=1000000000)


def register(app: FastAPI, store):
    @app.get('/api/jobs/{job_id}/clip-profile')
    def clip_profile(job_id: str):
        from .video_selection import profile_for_job
        job = store.job(job_id)
        return {'source_hash':job.get('source_hash'),'override_hash':digest(job.get('clip_profile_override')),'effective':profile_for_job(store,job),'global_profile_id':(store.setting('clip_profile') or {}).get('id','none')}

    @app.put('/api/jobs/{job_id}/clip-profile')
    def choose_clip_profile(job_id: str, request: JobClip):
        from .video_selection import set_job_clip_profile
        return set_job_clip_profile(store,job_id,request.profile,request.source_hash,request.override_hash,'local-operator')

    @app.get('/api/jobs/{job_id}/improvements')
    def get_workspace(job_id: str):
        return workspace(store, job_id)

    @app.post('/api/jobs/{job_id}/quality-reviews')
    def review(job_id: str, request: Review):
        if not request.note.strip():
            raise WorkflowError('직접 확인한 평가 사유를 적어 주세요')
        return save_review(store, job_id, request.model_dump())

    @app.get('/api/jobs/{job_id}/quality-reviews.csv')
    def reviews_csv(job_id: str):
        import csv
        import io
        from .improvements import records, RUBRIC
        store.job(job_id)
        columns = ['id','job_id','source_hash','case_id','dataset_split','target_id','target_hash','critical','quality_passed',*RUBRIC]
        output = io.StringIO()
        writer = csv.DictWriter(output, fieldnames=columns, extrasaction='ignore')
        writer.writeheader()
        for r in records(store, 'review', job_id):
            writer.writerow({**r, **r['scores']})
        return Response('\ufeff' + output.getvalue(), media_type='text/csv', headers={'Cache-Control':'no-store','Content-Disposition':'attachment; filename="quality-reviews.csv"','X-Content-Type-Options':'nosniff'})

    @app.post('/api/experiences')
    def experience(request: Experience):
        if request.checked_on > datetime.now(ZoneInfo('Asia/Seoul')).date() or not request.title.strip() or len(request.facts.strip()) < 10 or not request.evidence_note.strip() or any(not t.strip() or len(t) > 60 for t in request.tags):
            raise WorkflowError('확인일·근거·주제 태그를 확인하세요')
        if request.use_in_content and not request.confirmed:
            raise WorkflowError('본인이 확인한 사실만 원고 생성에 사용하세요')
        return save_record(store, 'experience', request.model_dump(mode='json'))

    @app.post('/api/experiences/{experience_id}/withdraw-use')
    def withdraw_experience(experience_id: str, request: Revision):
        import json
        from .store import canonical, now
        if not re.fullmatch(r'improve_[a-f0-9]{24}', experience_id):
            raise WorkflowError('경험 자료 ID를 확인하세요')
        key = 'improvement:experience:' + experience_id
        with store.connection(transaction=True) as db:
            row = db.execute('SELECT value FROM settings WHERE key=?', (key,)).fetchone()
            if not row or digest(json.loads(row[0])) != request.expected_hash:
                raise WorkflowError('경험 자료 판본이 바뀌었습니다. 다시 확인하세요')
            record = {**json.loads(row[0]), 'use_in_content': False, 'withdrawn_at': now()}
            db.execute('UPDATE settings SET value=? WHERE key=?', (canonical(record), key))
            store._event(db, 'experience_use_withdrawn', {'experience_id': experience_id})
        return {'status': 'future_generation_use_withdrawn', 'id': experience_id, 'note': '기존 원고·게시물은 지우지 않습니다. 필요한 정정은 별도 검토하세요.'}

    @app.get('/api/jobs/{job_id}/learning-contract')
    def contract(job_id: str):
        return JSONResponse(learning_contract(store.job(job_id)), headers={'Cache-Control': 'no-store', 'Content-Disposition': 'attachment; filename="learning-contract.json"'})

    @app.post('/api/jobs/{job_id}/learning-observations')
    def learning(job_id: str, request: Learning):
        job = store.job(job_id)
        contract = learning_contract(job)
        item = next((q for q in contract['items'] if q['id'] == request.question_id), None)
        if job.get('source_hash') != request.source_hash or contract.get('quiz_hash') != request.quiz_hash or not item or request.correct > request.attempts:
            raise WorkflowError('현재 검사 통과 문항과 응답 집계를 확인하세요')
        payload = {**request.model_dump(), 'concept_id': item['concept_id'], 'incorrect': request.attempts-request.correct, 'status': 'manual_aggregate_not_store_sync'}
        return save_record(store, 'learning', payload, job_id=job_id, source_hash=request.source_hash)

    @app.post('/api/jobs/{job_id}/channel-outcomes')
    def outcome(job_id: str, request: Outcome):
        from .channels import registry
        if request.channel_id not in {r['key'] for r in registry(store)}:
            raise WorkflowError('등록된 채널을 선택하세요')
        try:
            from .evidence import reference_url
            reference_url(request.external_url)
            url = urlsplit(request.external_url)
        except ValueError:
            raise WorkflowError('올바른 공개 HTTPS 결과 주소를 입력하세요') from None
        if any(c.isspace() for c in request.external_url) or any(re.search(r'(?i)token|secret|password|email|api.?key', k) or '@' in v for k, v in parse_qsl(url.query)):
            raise WorkflowError('개인정보·인증값이 없는 공개 HTTPS 결과 주소를 입력하세요')
        if request.observed_on > datetime.now(ZoneInfo('Asia/Seoul')).date() or (request.paid_orders == 0 and request.paid_revenue_krw != 0):
            raise WorkflowError('관측일 또는 유료 주문/매출을 확인하세요. 무료 주문은 매출이 아닙니다')
        return save_record(store, 'outcome', {**request.model_dump(mode='json'), 'verification': 'operator_reported_not_platform_receipt'}, job_id=job_id, source_hash=request.source_hash)

    @app.get('/api/jobs/{job_id}/channel-outcomes.csv')
    def outcome_csv(job_id: str):
        import csv
        import io
        from .improvements import records
        store.job(job_id)
        columns = ['id','job_id','source_hash','channel_id','campaign_id','variant_id','observed_on','period','external_url','views','saves','quiz_completed','downloads','free_orders','paid_orders','paid_revenue_krw','verification']
        output = io.StringIO()
        writer = csv.DictWriter(output, fieldnames=columns, extrasaction='ignore')
        writer.writeheader()
        writer.writerows(records(store, 'outcome', job_id))
        return Response('\ufeff' + output.getvalue(), media_type='text/csv', headers={'Cache-Control':'no-store','Content-Disposition':'attachment; filename="channel-outcomes.csv"','X-Content-Type-Options':'nosniff'})

    @app.post('/api/jobs/{job_id}/learning-observations/{observation_id}/idea')
    def learning_idea(job_id: str, observation_id: str, request: Versioned):
        from .improvements import records
        from .ideas import score_idea
        from .briefs import brief_for_job
        job = store.job(job_id)
        contract = learning_contract(job)
        observation = next((r for r in records(store, 'learning', job_id) if r['id'] == observation_id), None)
        if not observation or observation.get('source_hash') != request.source_hash or observation.get('quiz_hash') != contract.get('quiz_hash') or observation.get('incorrect', 0) <= 0:
            raise WorkflowError('현재 문항의 오답 관측을 확인하세요')
        item = next((q for q in contract['items'] if q['id'] == observation['question_id']), None)
        if not item:
            raise WorkflowError('기획에 연결할 현재 문항이 없습니다')
        card = score_idea({'title': ('다시 설명하기: ' + item['question'])[:200], 'origin': 'learning_feedback', 'source_url': job.get('article', {}).get('url') or None, 'primary_sources': 0, 'demand': 0, 'fit': 0.7, 'policy_flags': [], 'brief': brief_for_job(job), 'parent_job_id': job_id, 'parent_source_hash': request.source_hash, 'concept_id': item['concept_id'], 'observation_id': observation_id, 'note': '익명 오답 관측에서 만든 검토 후보입니다. 자료 근거를 확인/보완한 뒤 사람이 기획⓪을 선택합니다. 오답 수를 검색 수요로 환산하지 않습니다.'})
        idea = store.save_idea(card, parent_job_id=job_id, parent_source_hash=request.source_hash, parent_quiz_hash=contract['quiz_hash'])
        return {'idea': idea, 'status': 'candidate_not_selected' if idea.get('state') == 'candidate' else 'existing_idea_preserved'}
