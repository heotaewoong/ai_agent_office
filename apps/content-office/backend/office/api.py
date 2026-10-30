from __future__ import annotations

import hashlib
import hmac
import json
import math
import mimetypes
import os
import re
import secrets
import time
import tempfile
import zipfile
from pathlib import Path
from typing import Literal

from fastapi import FastAPI, HTTPException, Query, Request
from fastapi.exceptions import RequestValidationError
from fastapi.responses import FileResponse, HTMLResponse, JSONResponse, Response
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
from .ideas import rank_ideas, score_idea, select_reviewed_idea, set_idea_sources, with_edit_hash
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


def _job_summary(job, *, compact=False):
    """목록에는 제한된 메타데이터만 제공한다. 원고·근거·경로는 원본 상세 조회에 남긴다."""
    def text(value, limit):
        return value[:limit] if isinstance(value, str) else ""

    def safe_id(value):
        return value if isinstance(value, str) and re.fullmatch(r"[A-Za-z0-9_-]{1,128}", value) else None

    def content_hash(value):
        return value.lower() if isinstance(value, str) and re.fullmatch(r"[a-fA-F0-9]{64}", value) else None

    def outputs(values):
        result = []
        for value in values if isinstance(values, list) else []:
            if isinstance(value, str):
                result.append(value[:60])
                if len(result) == 20:
                    break
        return result

    def approval(record, release=False):
        if not isinstance(record, dict):
            return None
        result = {"decision": text(record.get("decision"), 40), "version": content_hash(record.get("version")), "created_at": text(record.get("created_at"), 60)}
        if release:
            result["outputs"] = outputs(record.get("outputs"))
        else:
            result["id"] = safe_id(record.get("id"))
        return result

    if not isinstance(job, dict) or not safe_id(job.get("id")):
        if compact:
            raise WorkflowError("작업 ID 형식을 확인할 수 없어 전체 작업 목록을 표시하지 못했습니다")
        return None
    if compact:
        packet = job.get("source_packet") if isinstance(job.get("source_packet"), dict) else {}
        article = job.get("article") if isinstance(job.get("article"), dict) else {}
        return {"id": job["id"], "title": text(job.get("title"), 200) or text(article.get("editorial_title"), 200) or text(article.get("title"), 200) or job["id"], "state": text(job.get("state"), 60) or "unknown",
                "updated_at": text(job.get("updated_at"), 60), "source_hash": content_hash(job.get("source_hash")),
                "has_source": isinstance(packet.get("body"), str) and bool(packet["body"])}
    manifest = job.get("manifest") if isinstance(job.get("manifest"), dict) else {}
    files = manifest.get("files") if isinstance(manifest.get("files"), list) else []
    return {"id": job["id"], "title": text(job.get("title"), 200) or job["id"], "state": text(job.get("state"), 60) or "unknown",
            "source_hash": content_hash(job.get("source_hash")), "source_approval": approval(job.get("source_approval")), "release_approval": approval(job.get("release_approval"), True),
            "manifest": {"hash": content_hash(manifest.get("hash")), "source_hash": content_hash(manifest.get("source_hash")),
                         "files": [{"id": safe_id(file.get("id")), "kind": text(file.get("kind"), 60) or "형식 미제공", "sha256": content_hash(file.get("sha256")), "outputs": outputs(file.get("outputs"))} for file in files[:80] if isinstance(file, dict)]}}


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
    preserve_original: bool = Field(default=False, strict=True)


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
    expected_brief_hash: str = Field(pattern=r"^[0-9a-f]{64}$")


class IdeaSourcesInput(BaseModel):
    source_urls: list[str] = Field(min_length=1, max_length=10)
    operator_verified: bool = Field(strict=True)
    expected_hash: str = Field(pattern=r"^[0-9a-f]{64}$")


class IdeaSelectionInput(BaseModel):
    expected_hash: str = Field(pattern=r"^[0-9a-f]{64}$")


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


class StagingRequest(BaseModel):
    expected_hash: str = Field(pattern=r"^[0-9a-f]{64}$")


class JobBudgetRequest(BaseModel):
    cap_krw: int = Field(strict=True, gt=0)
    expected_hash: str = Field(pattern=r"^[0-9a-f]{64}$")


def _local_photo_preview(store, job, html_path, content):
    from html.parser import HTMLParser
    from urllib.parse import urlsplit
    from .exports import SOURCE_PHOTO_HOSTS, SOURCE_PHOTO_MAX_BYTES, SOURCE_PHOTO_NAME_PATTERN

    records = [file for file in (job.get("manifest") or {}).get("files", [])
               if "blog" in file.get("outputs", []) and SOURCE_PHOTO_NAME_PATTERN.fullmatch(file.get("name", ""))]
    if not records and job["article"].get("preserve_original") is not True:
        return content
    root, urls = store.artifacts.resolve(), {}
    try:
        for record in records:
            name = record["name"]
            path = (root / record["path"]).resolve()
            relative = path.relative_to(root)
            if (relative.parts[:2] != (job["id"], job["source_hash"]) or path.parent != html_path.parent
                    or path.name != name or not path.is_file() or path.stat().st_size > SOURCE_PHOTO_MAX_BYTES or name in urls):
                raise WorkflowError("원문 사진이 현재 작업의 블로그 파일과 일치하지 않습니다")
            checksum = hashlib.sha256(path.read_bytes()).hexdigest()
            asset_id = "asset_" + digest({"path": relative.as_posix(), "sha256": checksum})[:24]
            if checksum != record.get("sha256") or record.get("id") != asset_id:
                raise WorkflowError("원문 사진이 변경되어 미리보기를 중단했습니다. 재제작·검수하세요")
            urls[name] = "/api/artifacts/" + asset_id
    except (OSError, ValueError, KeyError, TypeError):
        raise WorkflowError("원문 사진을 확인하지 못했습니다. 재제작·검수하세요") from None

    def replace(match):
        if match[3] not in urls:
            raise WorkflowError("블로그의 원문 사진이 현재 제작물 목록에 없습니다")
        return match[1] + match[2] + urls[match[3]] + match[2]

    localized = re.sub(rf'''((?i:src|href)\s*=\s*)(["'])({SOURCE_PHOTO_NAME_PATTERN.pattern})\2''', replace, content)

    class PhotoReferences(HTMLParser):
        def handle_starttag(self, tag, attributes):
            values = dict(attributes)
            if tag == "img" and (sum(key == "src" for key, _ in attributes) != 1 or "srcset" in values or values.get("src") not in urls.values()):
                raise WorkflowError("블로그 사진을 현재 작업의 검증된 파일로 연결하지 못했습니다")
            href = values.get("href")
            if tag == "a" and href and href not in urls.values():
                if (sum(key == "href" for key, _ in attributes) != 1 or href.startswith(("source-photo-", "/", ".", "\\"))
                        or re.match(r"(?i)^(?:file:|[a-z]:)", href) or urlsplit(href).hostname in SOURCE_PHOTO_HOSTS):
                    raise WorkflowError("원문 사진의 확대 주소를 현재 작업의 파일로 확인하지 못했습니다")

    try:
        PhotoReferences().feed(localized)
    except ValueError:
        raise WorkflowError("블로그 사진 주소를 안전하게 확인하지 못했습니다. 재제작·검수하세요") from None
    return localized


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
    from .public_leads import PUBLIC_ROUTES, lead_allowed_origins
    lead_origins = allowed_origins | lead_allowed_origins()  # 공개 신청 경로에만 쓰는 출처 목록
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
        if (request.method, request.url.path) in PUBLIC_ROUTES:
            # 운영자 세션 없이 여는 유일한 경로(공개 리드 신청·공개 자료 목록). 쓰기는 허용 출처를 반드시 요구한다.
            if (origin or request.method != "GET") and origin not in lead_origins:
                return JSONResponse({"detail": "허용되지 않은 화면의 요청입니다"}, status_code=403)
            return await call_next(request)
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
    def dashboard(compact: bool = False):
        from .voice_selection import profile_summary
        from .image_selection import profile_summary as image_profile_summary
        from .video_selection import profile_summary as clip_profile_summary
        from .text_selection import profile_summary as text_profile_summary
        from .youtube_delivery import configured as youtube_configured
        from .channels import configured_youtube_channels
        from .api_leads_newsletter import dashboard_counts
        from .source_registry import classify_article, load_sources, visible_articles
        feed_report = store.setting("feed_report", {})
        current_ids = {article["id"] for article in rank_articles(store.articles_list())}
        active_ids = set(feed_report.get("active_article_ids", current_ids))
        articles = sorted([article for article in store.articles_list() if article["id"] in current_ids & active_ids], key=lambda a: (a.get("score", 0), a.get("published_at") or ""), reverse=True)
        jobs = store.jobs()
        if compact:
            jobs = [_job_summary(job, compact=True) for job in jobs]
        return {"articles": visible_articles([classify_article(article) for article in articles]), "source_registry": load_sources(), "jobs": jobs, "feeds": feed_report.get("feeds", []), "feed_report": feed_report, "budget": store.budget(), "agents": AGENTS, "events": store.events(limit=60), "tasks": store.tasks(), "window": store.setting("work_window", {}), "worker": store.setting("worker_status", {}), "watcher": store.setting("watcher_status", {}), "provider": {"model": store.setting("model") or os.environ.get("OFFICE_MODEL", "gemini-3.8-flash"), "configured": bool(os.environ.get("GEMINI_API_KEY")), "paid_fallback": False, 'voice': profile_summary(store), 'image': image_profile_summary(store), 'clip': clip_profile_summary(store), 'text': text_profile_summary(store), 'youtube': {'configured': youtube_configured(), 'channels': configured_youtube_channels(), 'visibility': 'private', 'automatic_retry': False}}, "knowledge": store.setting("knowledge_summary", {}), "external_publication": "manual-handoff", **dashboard_counts(store)}

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

    @app.get("/api/jobs/summaries")
    def job_summaries(limit: int = Query(80, ge=1, le=80)):
        return {"jobs": [summary for job in store.jobs(limit=limit) if (summary := _job_summary(job)) is not None]}

    @app.get("/api/jobs/{job_id}")
    def get_job(job_id: str):
        job = store.job(job_id)
        return {**job, "brief_hash": digest(job.get("brief")), "events": store.events(job_id), "tasks": store.tasks(job_id), "drafts": store.drafts(job_id)}

    @app.get("/api/jobs/{job_id}/budget")
    def get_job_budget(job_id: str):
        return store.get_job_budget(job_id)

    @app.put("/api/jobs/{job_id}/budget")
    def set_job_budget(job_id: str, request: JobBudgetRequest):
        return store.set_job_budget(job_id, request.cap_krw, "local-operator", expected_hash=request.expected_hash)

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
            'Content-Security-Policy': "default-src 'none'; script-src 'none'; style-src 'unsafe-inline'; img-src 'self' https://blog.kakaocdn.net https://t1.daumcdn.net; base-uri 'none'; form-action 'none'"})

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
        if current["article"].get("preserve_original") is True:
            original = current["article"].get("operator_source_text")
            if not isinstance(original, str) or edit.packet.get("body") != original:
                raise WorkflowError("원문 보존 모드의 본문은 원문 입력에서 수정·재등록하세요. 편집 내용은 저장하지 않았습니다")
            packet.update(preserve_original=True, source_input_hash=digest(original),
                          reference_evidence_ids=(current.get("source_packet") or {}).get("reference_evidence_ids", []))
        else:
            for field in ("preserve_original", "source_input_hash", "reference_evidence_ids"):
                packet.pop(field, None)
        if len(canonical(packet)) > 100000:
            raise WorkflowError("원고 입력이 너무 큽니다")
        saved = store.save_source(job_id, packet, expected_hash=edit.version)
        store.enqueue("evaluate", {"job_id": job_id, "source_hash": saved["source_hash"]}, key=f"evaluate:{job_id}:{saved['source_hash']}")
        return saved

    @app.post("/api/jobs/{job_id}/evidence")
    def register_source_text(job_id: str, evidence_input: EvidenceInput):
        require_open_window()
        require_packaging(store.job(job_id))
        job = store.register_source_input(job_id, evidence_input.source_text, expected_hash=evidence_input.version, preserve_original=evidence_input.preserve_original)
        store.event("operator_source_registered", {"characters": len(evidence_input.source_text), "source_sha256": digest(evidence_input.source_text), "preserve_original": evidence_input.preserve_original, "role": "연구", "next_action": "근거 추출·원문 보존·영상 대본·재검수" if evidence_input.preserve_original else "근거 추출·원고 생성·재검수"}, job_id)
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
        from .channels import registry
        contract = production_contract(renderer_for_job(store, job), job['selections'], image_renderer=background_renderer_for_job(store, job), clip_renderer=clip_renderer_for_job(store, job), channel_registry=registry(store) if job['selections'].get('blog') else None)
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
        from .offers import require_offer_ready, require_campaign_packet
        require_offer_ready(job.get("offer"))
        require_campaign_packet(job.get("source_packet"), job.get("offer"))
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
        saved = store.review_release(job_id, review.version, review.decision, "local-operator", review.media_reviewed, review.outputs)
        if review.decision == "approved":
            from .staging import auto_prepare_staging
            auto_prepare_staging(store, job_id, "local-operator")
        return saved

    @app.post("/api/jobs/{job_id}/thumbnail")
    def choose_thumbnail(job_id: str, choice: ThumbnailChoice):
        job = store.require_source_approval(job_id)
        manifest = verify_files(job, ['video'])
        return store.select_thumbnail(job_id, choice.artifact_id, manifest.get("hash"), "local-operator")

    @app.get('/api/jobs/{job_id}/review-package')
    def download_review_package(job_id: str):
        from .review_bundle import build_review_bundle
        job = store.require_source_approval(job_id)
        data = build_review_bundle(job, store.artifacts)
        return Response(data, media_type='application/zip', headers={
            'Content-Disposition': f'attachment; filename="{job["id"]}-review.zip"',
            'Cache-Control': 'no-store',
        })

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
        content = data.decode('utf-8')
        if format == 'html':
            content = _local_photo_preview(store, job, path, content)
        current = store.require_source_approval(job_id)
        if current['source_hash'] != job['source_hash'] or (current.get('manifest') or {}).get('hash') != manifest.get('hash'):
            raise WorkflowError('블로그 버전이 변경되었습니다. 현재 작업을 다시 확인하세요')
        html = blog_reader_html(job['source_packet']['title'], content, format)
        return HTMLResponse(html, headers={'Cache-Control': 'no-store',
            'Content-Security-Policy': "default-src 'none'; script-src 'none'; style-src 'unsafe-inline'; img-src 'self' https://blog.kakaocdn.net https://t1.daumcdn.net; base-uri 'none'; form-action 'none'"})

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

    @app.get("/api/jobs/{job_id}/staging")
    def get_channel_staging(job_id: str):
        from .staging import staging_view
        return staging_view(store, job_id)

    @app.post("/api/jobs/{job_id}/staging")
    def record_channel_staging(job_id: str, request: StagingRequest):
        from .staging import prepare_staging
        return prepare_staging(store, job_id, request.expected_hash, "local-operator")

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
        return {"ideas": rank_ideas([with_edit_hash(card) for card in store.ideas()], lessons=store.lessons("approved"))}

    @app.post("/api/ideas")
    def add_idea(idea: IdeaInput):
        card = idea.model_dump()
        overrides = card.pop("brief", None)
        preset = card.pop("brief_preset", None)
        # 잘못된 프리셋·필드는 WorkflowError → 409. 브리프는 기획 카드에 함께 저장되어 선택⓪ 때 작업으로 넘어간다.
        card["brief"] = build_brief(preset or DEFAULT_PRESET, overrides)
        return store.save_idea(score_idea(card, lessons=store.lessons("approved")))

    @app.put("/api/ideas/{idea_id}/sources")
    def update_idea_sources(idea_id: str, body: IdeaSourcesInput):
        return set_idea_sources(store, idea_id, body.source_urls, expected_hash=body.expected_hash,
                                operator_verified=body.operator_verified, lessons=store.lessons("approved"))

    @app.get("/api/briefs")
    def list_briefs():
        return presets_payload()

    @app.put("/api/jobs/{job_id}/brief")
    def set_job_brief(job_id: str, body: BriefInput):
        # CSRF 보호는 공통 미들웨어가 한다. 승인①②는 건드리지 않으며 다음 생성·재검수부터 적용된다.
        brief = build_brief(body.preset, body.overrides)
        job = store.set_brief(job_id, brief, "local-operator", expected_hash=body.expected_brief_hash)
        return {**job, "brief_hash": digest(job.get("brief"))}

    @app.post("/api/ideas/{idea_id}/select")
    def choose_idea(idea_id: str, body: IdeaSelectionInput):
        return select_reviewed_idea(store, idea_id, expected_hash=body.expected_hash,
                                    actor="local-operator", lessons=store.lessons("approved"))

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
    from .public_leads import register as register_public_leads; register_public_leads(app, store, secret=secret, public_origin=public)  # 독자 공개 신청(세션 예외는 PUBLIC_ROUTES 두 경로뿐)
    from .api_calendar_questions import register as register_calendar_questions; register_calendar_questions(app, store)  # 시험 일정·시의성, 독자 질문 수집
    from .api_youtube_oauth import register as register_youtube_oauth; register_youtube_oauth(app, store)  # YouTube 채널 연결(OAuth) — 토큰은 상태 폴더 밖 비밀 파일
    from .api_daily_collect import register as register_daily_collect; register_daily_collect(app, store)  # 매일 아침 뉴스 자동 수집 설정 — 저장만, 실행은 cron

    @app.get("/api/architecture")
    def architecture_overview():
        # 구조도 화면: 저장소 문서 + 실행 사실(커밋·배포·테스트·키 연결 여부·실측 비용). 읽기 전용.
        from .architecture import overview
        return overview(store)
    return app


app = create_app()
