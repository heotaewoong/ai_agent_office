from __future__ import annotations

import hashlib
import hmac
import json
import math
import mimetypes
import os
import secrets
import time
import tempfile
import zipfile
from pathlib import Path
from typing import Literal

from fastapi import FastAPI, HTTPException, Request
from fastapi.exceptions import RequestValidationError
from fastapi.responses import FileResponse, HTMLResponse, JSONResponse
from pydantic import BaseModel, ConfigDict, Field, field_validator
from starlette.middleware.trustedhost import TrustedHostMiddleware

from .bootstrap import default_store
from .feeds import rank_articles
from .store import Store, WorkflowError, canonical, digest, identifier, now
from .runtime import window_open
from .analytics import baseline, parse_studio_text, propose_lessons
from .brand import load_brand
from .briefs import DEFAULT_PRESET, build_brief, presets_payload
from .gates import run_gates
from .ideas import rank_ideas, score_idea
from .packaging import attach_packaging, require_packaging
from .space import project_space

ALLOWED_ORIGINS = {"http://localhost:3110", "http://127.0.0.1:3110", "http://localhost:8510", "http://127.0.0.1:8510"}


def public_origin():
    """One explicit HTTPS origin served by an authenticating reverse proxy, or None.

    The API itself has no user accounts, so a public origin is only safe behind a proxy that
    authenticates every request (for example nginx basic auth over TLS).
    """
    raw = os.environ.get("OFFICE_PUBLIC_ORIGIN", "").strip()
    if not raw:
        return None
    from urllib.parse import urlsplit
    value = raw[:-1] if raw.endswith("/") else raw
    parts = urlsplit(value)
    if (parts.scheme != "https" or not parts.hostname or parts.username or parts.password or parts.path
            or parts.query or parts.fragment or "*" in value or value != f"https://{parts.netloc}"):
        raise WorkflowError("OFFICE_PUBLIC_ORIGIN은 https://호스트 형식의 단일 주소여야 합니다 (경로·와일드카드·계정 정보 불가)")
    return value
AGENTS = [
    {"id": "director", "name": "총괄", "description": "목표·담당·완료 상태", "mode": "업무 규칙"},
    {"id": "research", "name": "RSS 연구", "description": "공식 피드·날짜·원문 근거", "mode": "수집 + 검토"},
    {"id": "editor", "name": "편집", "description": "독자 맞춤 원고", "mode": "별도 모델 호출"},
    {"id": "critique", "name": "비평", "description": "설명·구조·근거 누락", "mode": "독립 호출"},
    {"id": "eval", "name": "평가", "description": "숫자·주장·중대 오류", "mode": "독립 호출"},
    {"id": "video", "name": "영상·디자인", "description": "음성·장면·자막·썸네일", "mode": "로컬 작업자"},
    {"id": "qa", "name": "QA", "description": "버전·파일·실제 미디어 확인", "mode": "검사 + 사람 검토"},
    {"id": "release", "name": "배포 준비", "description": "출고 승인·수동 전달 패키지", "mode": "외부 게시 대기"},
    {"id": "marketing", "name": "마케팅", "description": "후크·메타데이터·독자 가치", "mode": "편집 계약"},
]


class JobSelection(BaseModel):
    article_ids: list[str] = Field(min_length=1, max_length=3)


class SourceEdit(BaseModel):
    packet: dict
    version: str | None = None


class Review(BaseModel):
    version: str
    decision: Literal["approved", "rejected"]
    selections: dict[str, bool] | None = None
    media_reviewed: bool = False
    outputs: list[Literal['blog', 'video', 'cards', 'pdf']] | None = None


class ProfileChoice(BaseModel):
    kind: Literal["voice", "image", "clip", "text"]
    profile: str


class WindowRequest(BaseModel):
    minutes: int


class ThumbnailChoice(BaseModel):
    artifact_id: str


class EvidenceInput(BaseModel):
    source_text: str = Field(min_length=200, max_length=20000)
    version: str | None = None


class IdeaInput(BaseModel):
    title: str = Field(min_length=1, max_length=200)
    source_url: str = Field(default="", max_length=2000)
    views: int | None = Field(default=None, le=10**12)
    channel_avg_views: int | None = Field(default=None, le=10**12)
    demand: float = Field(default=0, ge=0, le=100)
    primary_sources: int = Field(default=0, ge=0)
    fit: float = Field(default=0, ge=0, le=1)
    covered_before: bool = False
    policy_flags: list[str] = []
    # 독자 브리프: 프리셋 ID(없으면 기본 ai-agent)와 필드별 덮어쓰기(topic·reader·prior_knowledge·problem·outcome·tone·language·cta)
    brief_preset: str | None = Field(default=None, max_length=100)
    brief: dict | None = None


class BriefInput(BaseModel):
    preset: str = Field(min_length=1, max_length=100)
    overrides: dict | None = None


class ThumbnailInput(BaseModel):
    text: str
    visual: str


class PackagingInput(BaseModel):
    titles: list[str]
    thumbnails: list[ThumbnailInput]
    hook: str
    logline: str
    reasons: list[str]
    chosen_title: str | None = None


class SnapshotInput(BaseModel):
    channel: Literal["youtube_long", "shorts", "blog_tistory", "blog_naver", "newsletter"]
    external_id: str = Field(min_length=1, max_length=200)
    period: Literal["24h", "7d", "28d"]
    metrics: dict[str, float | int | None]
    job_id: str | None = None

    @field_validator("metrics")
    @classmethod
    def finite_metrics(cls, value):
        if any(isinstance(v, float) and not math.isfinite(v) for v in value.values()):
            raise ValueError("지표 값은 유한한 숫자여야 합니다")
        return value


class StudioCsvInput(BaseModel):
    channel: Literal["youtube_long", "shorts", "blog_tistory", "blog_naver", "newsletter"]
    period: Literal["24h", "7d", "28d"]
    csv: str = Field(min_length=1, max_length=2_000_000)
    job_id: str | None = None


class LessonReview(BaseModel):
    decision: Literal["approved", "rejected"]


class ChannelPatch(BaseModel):
    # 운영자가 바꿀 수 있는 채널 설정만 받는다. refresh token 같은 비밀값은 환경변수로만 전달한다.
    # 모르는 필드는 버리지 않고 channels.update_channel이 '필드' 오류(409)로 돌려보낸다.
    model_config = ConfigDict(extra="allow")
    external_account_id: str | None = Field(default=None, max_length=200)
    publication_enabled: bool | None = None
    public_url: str | None = Field(default=None, max_length=500)


class YoutubeDeliveryRequest(BaseModel):
    channel_key: str = Field(default="youtube_main_ko", max_length=64)


def create_app(store: Store | None = None):
    store = store or default_store()
    app = FastAPI(title="HeoBrain 콘텐츠 오피스", version="0.1.0")
    app.state.store = store
    secret_path = store.root / ".session-secret"
    if not secret_path.is_file():
        secret_path.write_bytes(secrets.token_bytes(32))
        secret_path.chmod(0o600)
    secret = secret_path.read_bytes()
    public = public_origin()
    allowed_origins = ALLOWED_ORIGINS | ({public} if public else set())
    app.add_middleware(TrustedHostMiddleware, allowed_hosts=["localhost", "127.0.0.1", "testserver"])

    def sign(value):
        return hmac.new(secret, value.encode(), hashlib.sha256).hexdigest()

    def require_open_window():
        if not window_open(store):
            raise WorkflowError("허용된 작업 시간이 종료됐습니다. 새 작업 세션을 시작한 뒤 요청하세요")

    def session(request):
        token = request.cookies.get("hb_office_session", "")
        try:
            nonce, stamp, signature = token.split(".")
            if not hmac.compare_digest(sign(nonce + "." + stamp), signature) or not 0 <= time.time() - int(stamp) <= 86400:
                return None
            return nonce + "." + stamp
        except (ValueError, TypeError):
            return None

    @app.middleware("http")
    async def local_session_guard(request: Request, call_next):
        origin = request.headers.get("Origin")
        if origin and origin not in allowed_origins:
            return JSONResponse({"detail": "허용되지 않은 화면의 요청입니다"}, status_code=403)
        if request.method not in ("GET", "HEAD", "OPTIONS"):
            sid = session(request)
            if origin not in allowed_origins or not sid or not hmac.compare_digest(request.headers.get("X-Office-CSRF", ""), sign("csrf:" + sid)):
                return JSONResponse({"detail": "로컬 운영자 세션과 검토 화면에서 다시 요청하세요"}, status_code=403)
        return await call_next(request)

    @app.exception_handler(WorkflowError)
    async def workflow_error(request, error):
        return JSONResponse({"detail": str(error), "code": "workflow_blocked"}, status_code=409)

    @app.exception_handler(RequestValidationError)
    async def validation_error(request, error):
        # 입력값(NaN 등)을 되돌려 직렬화하다 500이 나지 않도록 위치·메시지만 돌려준다
        detail = [{"loc": list(e.get("loc", ())), "msg": e.get("msg", ""), "type": e.get("type", "")} for e in error.errors()]
        return JSONResponse({"detail": detail}, status_code=422)

    @app.get("/api/health")
    def health():
        return {"status": "ok", "scope": "local-content-office", "at": now()}

    @app.get("/api/session")
    def operator_session(request: Request):
        sid = session(request) or secrets.token_urlsafe(24) + "." + str(int(time.time()))
        response = JSONResponse({"csrf": sign("csrf:" + sid), "actor": "local-operator", "scope": "이 컴퓨터의 로컬 검토 화면"})
        response.set_cookie("hb_office_session", sid + "." + sign(sid), httponly=True, samesite="strict", max_age=86400, secure=bool(public))
        return response

    @app.get("/api/dashboard")
    def dashboard():
        from .voice_selection import profile_summary
        from .image_selection import profile_summary as image_profile_summary
        from .video_selection import profile_summary as clip_profile_summary
        from .text_selection import profile_summary as text_profile_summary
        from .youtube_delivery import configured as youtube_configured
        from .channels import configured_youtube_channels
        from .api_leads_newsletter import dashboard_counts
        feed_report = store.setting("feed_report", {})
        current_ids = {article["id"] for article in rank_articles(store.articles_list())}
        active_ids = set(feed_report.get("active_article_ids", current_ids))
        articles = sorted([article for article in store.articles_list() if article["id"] in current_ids & active_ids], key=lambda a: (a.get("score", 0), a.get("published_at") or ""), reverse=True)
        return {"articles": articles[:80], "jobs": store.jobs(), "feeds": feed_report.get("feeds", []), "feed_report": feed_report, "budget": store.budget(), "agents": AGENTS, "events": store.events(limit=60), "tasks": store.tasks(), "window": store.setting("work_window", {}), "worker": store.setting("worker_status", {}), "watcher": store.setting("watcher_status", {}), "provider": {"model": store.setting("model") or os.environ.get("OFFICE_MODEL", "gemini-3.8-flash"), "configured": bool(os.environ.get("GEMINI_API_KEY")), "paid_fallback": False, 'voice': profile_summary(store), 'image': image_profile_summary(store), 'clip': clip_profile_summary(store), 'text': text_profile_summary(store), 'youtube': {'configured': youtube_configured(), 'channels': configured_youtube_channels(), 'visibility': 'private', 'automatic_retry': False}}, "knowledge": store.setting("knowledge_summary", {}), "external_publication": "manual-handoff", **dashboard_counts(store)}

    @app.get("/api/space")
    def space():
        return JSONResponse(project_space(store, office_url=os.environ.get("OFFICE_URL", "http://localhost:3110"), agents=AGENTS), headers={"Cache-Control": "no-store"})

    @app.post("/api/refresh", status_code=202)
    def refresh_feed():
        require_open_window()
        return store.enqueue("refresh", {}, key=f"refresh:{int(time.time()) // 60}")

    @app.post("/api/jobs")
    def create_jobs(selection: JobSelection):
        articles = [store.article(article_id) for article_id in dict.fromkeys(selection.article_ids)]
        eligible_ids = {article["id"] for article in rank_articles(store.articles_list())}
        active_ids = set(store.setting("feed_report", {}).get("active_article_ids", eligible_ids))
        if any(article["id"] not in eligible_ids & active_ids for article in articles):
            raise WorkflowError("현재 최근 기사 후보가 아닙니다. RSS를 새로 확인하고 선택하세요")
        return {"jobs": [store.create_job(article) for article in articles]}

    @app.get("/api/jobs/{job_id}")
    def get_job(job_id: str):
        return {**store.job(job_id), "events": store.events(job_id), "tasks": store.tasks(job_id), "drafts": store.drafts(job_id)}

    @app.get('/api/jobs/{job_id}/drafts/{draft_id}/preview')
    def draft_preview(job_id: str, draft_id: str):
        from .exports import blog_reader_html, blog_markdown, safe_fragment
        job = store.job(job_id)
        draft = next((d for d in store.drafts(job_id) if d['id'] == draft_id), None)
        if not draft:
            raise HTTPException(404, '초안을 찾을 수 없습니다')
        # Same reader and source list the blog export would produce from this draft.
        packet = {**(job.get('source_packet') or {}), 'title': draft['title'], 'body': draft['body'], 'evidence': job['article'].get('evidence', [])}
        html = blog_reader_html(draft['title'], safe_fragment(blog_markdown(packet)), 'draft')
        return HTMLResponse(html, headers={'Cache-Control': 'no-store',
            'Content-Security-Policy': "default-src 'none'; script-src 'none'; style-src 'unsafe-inline'; base-uri 'none'; form-action 'none'"})

    @app.post("/api/jobs/{job_id}/draft", status_code=202)
    def draft_source(job_id: str):
        require_open_window()
        job = store.job(job_id)
        require_packaging(job)
        return store.enqueue("draft", {"job_id": job_id, "source_hash": job["source_hash"]}, key=f"draft:{job_id}:{job['source_hash'] or 'initial'}")

    @app.post("/api/jobs/{job_id}/evaluate", status_code=202)
    def evaluate_source(job_id: str):
        require_open_window()
        job = store.job(job_id)
        if not job["source_hash"]:
            raise WorkflowError("검수할 원고가 없습니다")
        return store.enqueue("evaluate", {"job_id": job_id, "source_hash": job["source_hash"]}, key=f"evaluate:{job_id}:{job['source_hash']}")

    @app.put("/api/jobs/{job_id}/source")
    def edit_source(job_id: str, edit: SourceEdit):
        require_open_window()
        current = store.job(job_id)
        packet = {**edit.packet, "evidence": current["article"].get("evidence", []), "quality": {"status": "unverified", "critical": False, "reviews": [], "refine_count": 0}, "audience": (current.get("source_packet") or {}).get("audience", {})}
        if len(canonical(packet)) > 100000:
            raise WorkflowError("원고 입력이 너무 큽니다")
        saved = store.save_source(job_id, packet, expected_hash=edit.version)
        store.enqueue("evaluate", {"job_id": job_id, "source_hash": saved["source_hash"]}, key=f"evaluate:{job_id}:{saved['source_hash']}")
        return saved

    @app.post("/api/jobs/{job_id}/evidence")
    def register_source_text(job_id: str, evidence_input: EvidenceInput):
        require_open_window()
        job = store.register_source_input(job_id, evidence_input.source_text, expected_hash=evidence_input.version)
        store.event("operator_source_registered", {"characters": len(evidence_input.source_text), "source_sha256": digest(evidence_input.source_text), "role": "연구", "next_action": "근거 추출·원고 생성·재검수"}, job_id)
        store.enqueue("draft", {"job_id": job_id, "source_hash": job["source_hash"]}, key=f"source-input:{job_id}:{digest(evidence_input.source_text)}:{job['source_hash']}")
        return store.job(job_id)

    @app.post("/api/jobs/{job_id}/reviews/source")
    def review_source(job_id: str, review: Review):
        return store.review_source(job_id, review.version, review.decision, "local-operator", review.selections)

    @app.post("/api/jobs/{job_id}/produce", status_code=202)
    def produce(job_id: str):
        require_open_window()
        job = store.require_source_approval(job_id)
        from .media import production_contract
        from .voice_selection import renderer_for_job
        from .image_selection import background_renderer_for_job
        from .video_selection import clip_renderer_for_job
        contract = production_contract(renderer_for_job(store, job), job['selections'], image_renderer=background_renderer_for_job(store, job), clip_renderer=clip_renderer_for_job(store, job))
        task = store.enqueue("produce", {"job_id": job_id, "source_hash": job["source_hash"], "production_contract": contract['hash']}, key=f"produce:{job_id}:{job['source_hash']}:{contract['hash']}")
        if task["state"] == "queued":
            store.update_job(job_id, state="production_queued")
        return task

    @app.post("/api/tasks/{task_id}/retry", status_code=202)
    def retry_task(task_id: str):
        require_open_window()
        previous = store.task(task_id)
        if previous["state"] not in ("failed", "unknown", "partial") or previous["kind"] not in ("draft", "evaluate", "produce", "refresh"):
            raise WorkflowError("재시도할 수 있는 실패 작업이 아닙니다")
        payload = dict(previous["payload"])
        job_id = payload.get("job_id")
        if job_id:
            current = store.job(job_id)
            expected = payload.get("source_hash", payload.get("_source_hash_at_claim"))
            if current["source_hash"] != expected:
                raise WorkflowError("이전 버전의 작업입니다. 현재 원고의 다음 행동을 선택하세요")
            if previous["kind"] == "produce":
                store.require_source_approval(job_id)
            payload["source_hash"] = current["source_hash"]
        payload.pop("_source_hash_at_claim", None)
        task = store.enqueue(previous["kind"], payload, key=f"operator-retry:{task_id}:{identifier('attempt')}")
        store.event("operator_retry_requested", {"previous_task_id": task_id, "new_task_id": task["id"], "actor": "local-operator", "note": "결과불명 모델 호출은 원가·결과 대사 전 Provider에서 다시 차단합니다"}, job_id)
        return task

    def released_files(job, outputs=None):
        records = (job.get('manifest') or {}).get('files', [])
        if outputs is None:
            return records
        selected = set(outputs)
        return [record for record in records if not record.get('outputs') or selected.intersection(record['outputs']) or 'shared' in record['outputs']]

    def verify_files(job, outputs=None):
        manifest = job.get("manifest") or {}
        if manifest.get("source_hash") != job.get("source_hash"):
            raise WorkflowError("현재 원고와 제작물 버전이 다릅니다")
        for file in released_files(job, outputs):
            path = (store.artifacts / file["path"]).resolve()
            if not path.is_relative_to(store.artifacts.resolve()) or not path.is_file() or hashlib.sha256(path.read_bytes()).hexdigest() != file["sha256"]:
                raise WorkflowError("제작물이 변경되었거나 파일 검증에 실패했습니다")
        return manifest

    @app.post("/api/jobs/{job_id}/reviews/release")
    def review_release(job_id: str, review: Review):
        job = store.require_source_approval(job_id)
        manifest = verify_files(job, review.outputs)
        if not manifest or review.version != manifest.get("hash"):
            raise WorkflowError("출고 대상 버전이 변경되었습니다")
        return store.review_release(job_id, review.version, review.decision, "local-operator", review.media_reviewed, review.outputs)

    @app.post("/api/jobs/{job_id}/thumbnail")
    def choose_thumbnail(job_id: str, choice: ThumbnailChoice):
        job = store.require_source_approval(job_id)
        manifest = verify_files(job, ['video'])
        return store.select_thumbnail(job_id, choice.artifact_id, manifest.get("hash"), "local-operator")

    @app.get("/api/jobs/{job_id}/package")
    def download_package(job_id: str):
        job = store.require_source_approval(job_id)
        approval = job.get("release_approval") or {}
        outputs = set(approval.get('outputs', [kind for kind, enabled in job['selections'].items() if enabled]))
        manifest = verify_files(job, outputs)
        approval = job.get("release_approval") or {}
        if approval.get("decision") != "approved" or approval.get("version") != manifest.get("hash"):
            raise WorkflowError("현재 제작물의 출고 승인②가 필요합니다")
        records = released_files(job, outputs)
        folder = store.root / 'handoffs'
        folder.mkdir(exist_ok=True)
        release_key = digest({'job_id': job_id, 'manifest_hash': manifest['hash'], 'release': approval, 'outputs': sorted(outputs)})
        path = folder / f"{job_id}-{release_key}.zip"
        fd, temporary_name = tempfile.mkstemp(prefix='handoff-', suffix='.partial', dir=folder)
        os.close(fd)
        temporary = Path(temporary_name)
        try:
            with zipfile.ZipFile(temporary, 'w', zipfile.ZIP_DEFLATED) as archive:
                for record in records:
                    data = (store.artifacts / record['path']).read_bytes()
                    if hashlib.sha256(data).hexdigest() != record['sha256']:
                        raise WorkflowError('출고 파일이 변경되어 재검수가 필요합니다')
                    archive.writestr(record['name'], data)
                archive.writestr("handoff.json", canonical({"source_hash": job["source_hash"], "manifest": {**manifest, 'files': records, 'exported_outputs': sorted(outputs), 'thumbnail_candidates': manifest.get('thumbnail_candidates', []) if 'video' in outputs else [], 'media': manifest.get('media', {}) if 'video' in outputs else {}}, "release": approval, "extras": [], "next_action": "계정·일정·대상을 확인하고 각 플랫폼에서 직접 게시", "external_published": False}))
            os.replace(temporary, path)
        finally:
            temporary.unlink(missing_ok=True)
        return FileResponse(path, filename=f"{job_id}-출고패키지.zip")

    @app.get('/api/jobs/{job_id}/blog-preview')
    def blog_preview(job_id: str, format: Literal['html', 'markdown', 'naver'] = 'html'):
        from .exports import blog_reader_html
        job = store.require_source_approval(job_id)
        manifest = job.get('manifest') or {}
        if manifest.get('source_hash') != job['source_hash'] or 'blog' not in manifest.get('completed_outputs', []):
            raise WorkflowError('현재 원고의 완성된 블로그를 찾을 수 없습니다')
        filename = {'html': 'tistory.html', 'markdown': 'tistory.md', 'naver': 'naver.txt'}[format]
        record = next((f for f in manifest.get('files', []) if f['name'] == filename and 'blog' in f.get('outputs', ['blog'])), None)
        if not record:
            raise WorkflowError('요청한 블로그 파일이 아직 없습니다')
        path = (store.artifacts / record['path']).resolve()
        if not path.is_relative_to(store.artifacts.resolve()) or not path.is_file():
            raise WorkflowError('블로그 파일을 찾을 수 없습니다')
        data = path.read_bytes()
        if hashlib.sha256(data).hexdigest() != record['sha256']:
            raise WorkflowError('블로그 파일이 변경되어 재검수가 필요합니다')
        current = store.require_source_approval(job_id)
        if current['source_hash'] != job['source_hash'] or (current.get('manifest') or {}).get('hash') != manifest.get('hash'):
            raise WorkflowError('블로그 버전이 변경되었습니다. 현재 작업을 다시 확인하세요')
        html = blog_reader_html(job['source_packet']['title'], data.decode('utf-8'), format)
        return HTMLResponse(html, headers={'Cache-Control': 'no-store',
            'Content-Security-Policy': "default-src 'none'; script-src 'none'; style-src 'unsafe-inline'; base-uri 'none'; form-action 'none'"})

    from .api_quiz_cards import register as register_quiz_cards; register_quiz_cards(app, store)  # 퀴즈·카드뉴스 라우트와 /api/artifacts/{id}(manifest 파일 + 퀴즈 JSON + 카드 PNG) 서빙

    def profile_summaries():
        from .voice_selection import profile_summary as voice_summary
        from .image_selection import profile_summary as image_summary
        from .video_selection import profile_summary as clip_summary
        from .text_selection import profile_summary as text_summary
        return {"voice": voice_summary(store), "image": image_summary(store), "clip": clip_summary(store), "text": text_summary(store)}

    @app.post("/api/settings/profiles")
    def choose_profile(choice: ProfileChoice):
        # Choosing a profile is free and never calls a provider; costs happen only after approval①.
        from . import image_selection, text_selection, video_selection, voice_selection
        module = {"voice": voice_selection, "image": image_selection, "clip": video_selection, "text": text_selection}[choice.kind]
        module.select_profile(store, choice.profile, actor="local-operator-ui")
        return profile_summaries()

    @app.post("/api/session/window")
    def open_work_window(request: WindowRequest):
        # The operator's own explicit action in the UI; agents never call this.
        from .session import start_session
        from . import services
        window = start_session(store, minutes=request.minutes, source="local_operator_ui", stop_services=services.stop_windowless_services)
        return {"work_window": window, "budget": store.budget(), "services": services.start_window_services(store)}

    @app.get("/api/jobs/{job_id}/deliveries")
    def list_deliveries(job_id: str):
        from .youtube_delivery import configured, deliveries
        return {"deliveries": deliveries(store, job_id), "youtube_configured": configured()}

    @app.post("/api/jobs/{job_id}/deliveries/youtube", status_code=202)
    def deliver_youtube_video(job_id: str, body: YoutubeDeliveryRequest | None = None):
        # Explicit private upload of the release-approved② video; never public, never retried on its own.
        # channel_key picks the owner's YouTube channel (youtube_main_ko by default) and its own refresh token.
        require_open_window()
        from .youtube_delivery import deliver_youtube
        channel_key = body.channel_key if body else "youtube_main_ko"
        return deliver_youtube(store, job_id, actor="local-operator", channel_key=channel_key)

    @app.get("/api/channels")
    def list_channels():
        # Owner-provided public addresses plus per-channel state; secrets never leave the environment.
        from .channels import registry
        return {"channels": registry(store)}

    @app.put("/api/channels/{key}")
    def update_channel_settings(key: str, patch: ChannelPatch):
        # CSRF-protected like every mutation; publication_enabled never replaces release approval②.
        from .channels import update_channel
        return update_channel(store, key, patch.model_dump(exclude_unset=True), actor="local-operator")

    @app.post("/api/jobs/{job_id}/deliveries/{delivery_id}/reconcile")
    def reconcile_delivery(job_id: str, delivery_id: str):
        require_open_window()
        from .youtube_delivery import reconcile_youtube
        return reconcile_youtube(store, job_id, delivery_id)

    @app.get("/api/events")
    def events():
        return {"events": store.events(limit=200), "tasks": store.tasks()}

    @app.get("/api/knowledge")
    def knowledge(query: str = "", limit: int = 10):
        from .knowledge import search_knowledge
        path = store.setting("knowledge_index_path")
        return {"summary": store.setting("knowledge_summary", {}), "results": search_knowledge(path, query, limit=min(max(limit, 1), 20)) if path and query.strip() else []}

    @app.get("/api/ideas")
    def list_ideas():
        return {"ideas": rank_ideas(store.ideas(), lessons=store.lessons("approved"))}

    @app.post("/api/ideas")
    def add_idea(idea: IdeaInput):
        card = idea.model_dump()
        overrides = card.pop("brief", None)
        preset = card.pop("brief_preset", None)
        # 잘못된 프리셋·필드는 WorkflowError → 409. 브리프는 기획 카드에 함께 저장되어 선택⓪ 때 작업으로 넘어간다.
        card["brief"] = build_brief(preset or DEFAULT_PRESET, overrides)
        return store.save_idea(score_idea(card, lessons=store.lessons("approved")))

    @app.get("/api/briefs")
    def list_briefs():
        return presets_payload()

    @app.put("/api/jobs/{job_id}/brief")
    def set_job_brief(job_id: str, body: BriefInput):
        # CSRF 보호는 공통 미들웨어가 한다. 승인①②는 건드리지 않으며 다음 생성·재검수부터 적용된다.
        brief = build_brief(body.preset, body.overrides)
        return store.set_brief(job_id, brief, "local-operator")

    @app.post("/api/ideas/{idea_id}/select")
    def choose_idea(idea_id: str):
        stored = next((i for i in store.ideas() if i["id"] == idea_id), None)
        if not stored:
            raise WorkflowError("기획을 찾을 수 없습니다")
        refreshed = store.save_idea(score_idea(stored, lessons=store.lessons("approved")))
        if refreshed.get("blocked"):
            raise WorkflowError("정책·근거 검사에서 막힌 기획은 선택할 수 없습니다")
        if not str(refreshed.get("source_url", "")).startswith("https://"):
            raise WorkflowError("기획을 선택하려면 https 출처 URL이 필요합니다")
        idea = store.select_idea(idea_id, "local-operator")
        job = store.create_job({"id": idea_id, "title": idea["title"], "url": idea["source_url"], "origin": "idea", "evidence": []}, brief=idea.get("brief"))
        return {"idea": idea, "job": job}

    @app.post("/api/jobs/{job_id}/packaging")
    def set_packaging(job_id: str, brief: PackagingInput):
        return attach_packaging(store, job_id, brief.model_dump(exclude_none=True), "local-operator")

    @app.get("/api/jobs/{job_id}/gates")
    def job_gates(job_id: str):
        packet = store.job(job_id).get("source_packet") or {}
        previous = [j["source_packet"] for j in store.jobs() if j["id"] != job_id and j.get("source_packet")]
        from .api_quiz_cards import with_output_warnings  # 퀴즈·카드 검사 문제점은 출고② 전 비차단 경고로 덧붙인다
        return with_output_warnings(run_gates(packet, previous, packet.get("assets", []), load_brand()), store.job(job_id))

    @app.post("/api/analytics/snapshots")
    def add_snapshot(snapshot: SnapshotInput):
        saved = store.save_snapshot(snapshot.channel, snapshot.external_id, snapshot.period, snapshot.metrics, snapshot.job_id)
        base = baseline([s for s in store.snapshots(snapshot.channel) if s["period"] == snapshot.period and s["id"] != saved["id"]])
        return {"snapshot": saved, "lessons": [store.add_lesson(lesson) for lesson in propose_lessons(saved, base)]}

    @app.post("/api/analytics/studio-csv")
    def upload_studio_csv(body: StudioCsvInput):
        rows = parse_studio_text(body.csv)
        if not rows:
            raise WorkflowError("CSV에서 저장할 행을 찾지 못했습니다. Studio '콘텐츠' 표를 그대로 내보낸 파일인지 확인하세요")
        rows = list({row["external_id"]: row for row in rows}.values())
        saved = [
            store.save_snapshot(body.channel, row["external_id"], body.period, {k: v for k, v in row.items() if k != "external_id"}, body.job_id)
            for row in rows
        ]
        lessons = {}
        for snap in saved:
            base = baseline([s for s in store.snapshots(body.channel) if s["period"] == body.period and s["id"] != snap["id"]])
            for lesson in propose_lessons(snap, base):
                added = store.add_lesson(lesson)
                lessons[added["id"]] = added
        return {"snapshots": saved, "lessons": list(lessons.values())}

    @app.get("/api/lessons")
    def list_lessons():
        return {"lessons": store.lessons()}

    @app.post("/api/lessons/{lesson_id}/review")
    def review_lesson(lesson_id: str, review: LessonReview):
        return store.review_lesson(lesson_id, review.decision, "local-operator")

    from .api_leads_newsletter import register as register_leads_newsletter; register_leads_newsletter(app, store)  # 리드 동의 장부·뉴스레터③·오퍼
    from .api_calendar_questions import register as register_calendar_questions; register_calendar_questions(app, store)  # 시험 일정·시의성, 독자 질문 수집

    @app.get("/api/architecture")
    def architecture_overview():
        # 구조도 화면: 저장소 문서 + 실행 사실(커밋·배포·테스트·키 연결 여부·실측 비용). 읽기 전용.
        from .architecture import overview
        return overview(store)
    return app


app = create_app()
