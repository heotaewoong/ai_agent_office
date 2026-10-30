"""퀴즈(4지선다 5문항)·카드뉴스(6~8장) 라우트. api.create_app이 register(app, store)로 붙인다.

인증·CSRF는 api.py의 공통 미들웨어가 처리하고, WorkflowError는 409로 돌아간다.
퀴즈·카드 파일은 제작 manifest가 아니라 job["quiz"]·job["cards"]에 기록되므로
/api/artifacts/{id} 서빙은 이 모듈이 manifest 파일과 함께 맡는다(api.py의 같은 경로 라우트보다 먼저 등록해야 한다).
"""
from __future__ import annotations

from pydantic import BaseModel

import hashlib
import io
import json
import mimetypes
import zipfile

from fastapi import HTTPException
from fastapi.responses import FileResponse, Response

from .quiz import enqueue_output
from .runtime import window_open
from .store import WorkflowError

QUIZ_KEYS = ("version", "generated_at", "source_hash", "questions", "checks", "artifact_id")
SLIDE_KEYS = ("index", "title", "body", "artifact_id", "visual", "template", "background")


def quiz_payload(job):
    quiz = job.get("quiz")
    return {key: quiz.get(key) for key in QUIZ_KEYS} if quiz else None


def cards_payload(job):
    cards = job.get("cards")
    if not cards:
        return None
    return {"version": cards.get("version"), "generated_at": cards.get("generated_at"), "source_hash": cards.get("source_hash"), "slides": [{key: slide.get(key) for key in SLIDE_KEYS} for slide in cards.get("slides", [])], "checks": cards.get("checks")}


def artifact_records(job):
    """제작 manifest 파일 + 현재 원고의 퀴즈 JSON + 카드 PNG."""
    yield from (job.get("manifest") or {}).get("files", [])
    for output in ("quiz", "cards"):
        record = job.get(output) or {}
        if record.get("source_hash") != job.get("source_hash"):
            continue
        if output == "quiz" and record.get("artifact"):
            yield record["artifact"]
        for slide in record.get("slides", []) or []:
            if slide.get("artifact"):
                yield slide["artifact"]


def _verified_path(store, file):
    path = (store.artifacts / file["path"]).resolve()
    if not path.is_relative_to(store.artifacts.resolve()) or not path.is_file():
        raise HTTPException(404, "파일을 찾을 수 없습니다")
    if hashlib.sha256(path.read_bytes()).hexdigest() != file["sha256"]:
        raise HTTPException(409, "파일이 변경되어 재검수가 필요합니다")
    return path


def output_warnings(job):
    """출고② 전에 사람이 볼 비차단 경고. 퀴즈·카드 검사 문제점을 게이트 항목 형식으로 돌려준다."""
    items = []
    for output, label in (("quiz", "퀴즈"), ("cards", "카드뉴스")):
        record = job.get(output) or {}
        if record.get("source_hash") != job.get("source_hash"):
            continue
        for issue in (record.get("checks") or {}).get("issues", []):
            items.append({"level": "warn", "rule": f"{output}_check", "message": f"{label} v{record.get('version')}: {issue}"})
    return items


def with_output_warnings(report, job):
    items = output_warnings(job)
    if not items:
        return report
    merged = {**report, "items": [*report.get("items", []), *items]}
    merged["status"] = "warn" if merged.get("status") == "pass" else merged.get("status", "warn")
    return merged


class CardsRequest(BaseModel):
    images: bool | None = None


def register(app, store):
    def require_open_window():
        if not window_open(store):
            raise WorkflowError("허용된 작업 시간이 종료됐습니다. 새 작업 세션을 시작한 뒤 요청하세요")

    def enqueue(job_id, kind, images=None):
        require_open_window()
        job = store.require_source_approval(job_id)
        task = enqueue_output(store, job, kind, images)
        return {"task_id": task["id"], "state": task["state"]}

    @app.post("/api/jobs/{job_id}/quiz", status_code=202)
    def request_quiz(job_id: str):
        return enqueue(job_id, "quiz")

    @app.get("/api/jobs/{job_id}/quiz")
    def get_quiz(job_id: str):
        return {"quiz": quiz_payload(store.job(job_id))}

    @app.post("/api/jobs/{job_id}/cards", status_code=202)
    def request_cards(job_id: str, body: CardsRequest | None = None):
        # images=True: 카드마다 주제 이미지 생성(OpenAI, 유료). None이면 제작 설정의 배경 이미지 프로필을 따른다.
        return enqueue(job_id, "cards", body.images if body else None)

    @app.get("/api/jobs/{job_id}/cards")
    def get_cards(job_id: str):
        return {"cards": cards_payload(store.job(job_id))}

    @app.get("/api/jobs/{job_id}/cards/archive")
    def cards_archive(job_id: str, version: int, source_hash: str):
        """현재 화면의 카드만 묶는 검토 ZIP. 출고 승인이나 장부를 변경하지 않는다."""
        job = store.job(job_id)
        cards = job.get("cards") or {}
        if not cards or cards.get("source_hash") != job.get("source_hash"):
            raise HTTPException(409, "현재 원고의 카드뉴스를 먼저 생성하세요")
        if cards.get("version") != version or cards.get("source_hash") != source_hash:
            raise HTTPException(409, "카드뉴스 버전이 바뀌었습니다. 새로고침 후 내려받으세요")
        slides = cards.get("slides") or []
        if not 6 <= len(slides) <= 8 or [s.get("index") for s in slides] != list(range(1, len(slides) + 1)):
            raise HTTPException(409, "카드 개수와 순서를 다시 확인하세요")
        files, seen, total = [], set(), 0
        for slide in slides:
            record = slide.get("artifact")
            if not record:
                raise HTTPException(409, "아직 이미지가 없는 카드가 있습니다")
            path = _verified_path(store, record)
            if path.suffix.lower() != ".png":
                raise HTTPException(409, "카드 이미지 형식을 다시 확인하세요")
            total += path.stat().st_size
            if total > 64 * 1024 * 1024:
                raise HTTPException(409, "카드뉴스 용량이 너무 큽니다. 개별 내려받기를 이용하세요")
            content = path.read_bytes()
            digest = hashlib.sha256(content).hexdigest()
            if digest != record.get("sha256") or len(content) > 64 * 1024 * 1024:
                raise HTTPException(409, "파일이 변경되어 재검수가 필요합니다")
            if digest in seen:
                raise HTTPException(409, "같은 이미지가 중복되어 있습니다. 다시 검토하세요")
            seen.add(digest)
            files.append((f"card-{slide['index']:02d}.png", content))
        metadata = {"purpose": "review_only", "release_approved": False,
                    "version": version, "source_hash": source_hash,
                    "checks": cards.get("checks"),
                    "slides": [{"index": s["index"], "title": s.get("title"), "body": s.get("body"),
                                "sha256": s["artifact"]["sha256"]} for s in slides]}
        buffer = io.BytesIO()
        with zipfile.ZipFile(buffer, "w", zipfile.ZIP_DEFLATED) as archive:
            for name, content in files:
                archive.writestr(name, content)
            archive.writestr("review.json", json.dumps(metadata, ensure_ascii=False, indent=2))
            archive.writestr("README.txt", "검토용 카드뉴스입니다. 출고 승인②를 대신하지 않습니다.\n검사 이슈와 게시 전 실제 이미지 전체를 확인하세요.\n")
        return Response(buffer.getvalue(), media_type="application/zip", headers={
            "Content-Disposition": f'attachment; filename="cards-review-v{version}.zip"',
            "Cache-Control": "private, no-store",
        })

    @app.get("/api/artifacts/{artifact_id}")
    def artifact(artifact_id: str):
        # api.py의 manifest 전용 라우트와 같은 규칙에 퀴즈·카드 파일을 더한 것. 먼저 등록된 이 라우트가 응답한다.
        if not artifact_id.startswith("asset_") or len(artifact_id) > 80:
            raise HTTPException(404, "파일을 찾을 수 없습니다")
        for job in store.jobs():
            for file in artifact_records(job):
                if file.get("id") == artifact_id:
                    path = _verified_path(store, file)
                    return FileResponse(path, media_type=mimetypes.guess_type(path.name)[0] or "application/octet-stream", filename=path.name, content_disposition_type="inline")
        raise HTTPException(404, "파일을 찾을 수 없습니다")
