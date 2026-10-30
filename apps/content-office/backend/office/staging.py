"""Current-release local staging. It never creates a platform draft or sends a file."""
from __future__ import annotations

import hashlib
import json
import re

from .channel_handoff import SOCIAL_TARGETS
from .channels import registry
from .exports import SOURCE_PHOTO_NAME_PATTERN
from .runtime import window_open
from .store import WorkflowError, digest, now

TARGETS = ("youtube_main_ko", "youtube_english", "tistory_main", "naver_blog_main",
           "threads_main", "linkedin_personal", "instagram_main", "instagram_english", "x_main")
BLOG_FILES = {"tistory_main": "tistory.html", "naver_blog_main": "naver.txt"}


def _context(store, job):
    rows = [row for row in registry(store) if row["key"] in TARGETS]
    manifest_hash = (job.get("manifest") or {}).get("hash")
    ledger = store.setting("deliveries", {})
    ledger = ledger if isinstance(ledger, dict) else {}
    deliveries = [r for r in ledger.values() if isinstance(r, dict) and r.get("job_id") == job["id"] and r.get("manifest_hash") == manifest_hash]
    context = {"source_hash": job.get("source_hash"), "manifest": job.get("manifest"),
               "source_approval": job.get("source_approval"), "selections": job.get("selections"),
               "release": job.get("release_approval"), "offer": job.get("offer"),
               "channels": rows, "deliveries": deliveries, "window_open": window_open(store)}
    return rows, deliveries, digest(context), context["window_open"]


def _verified_records(store, job):
    current = store.require_source_approval(job["id"])
    manifest, release = job.get("manifest") or {}, job.get("release_approval") or {}
    if current["source_hash"] != job.get("source_hash"):
        raise WorkflowError("검사 중 원고 판본이 변경되었습니다")
    if (release.get("decision") != "approved" or release.get("version") != manifest.get("hash")
            or manifest.get("source_hash") != job.get("source_hash") or not release.get("outputs")):
        raise WorkflowError("현재 완성품의 출고 승인②가 필요합니다")
    selected = set(release["outputs"])
    requested = {key for key, enabled in job["selections"].items() if enabled}
    completed = set(manifest.get("completed_outputs", requested))
    if not selected.issubset(requested & completed):
        raise WorkflowError("출고 승인한 출력과 현재 완성품이 다릅니다")
    root, verified = store.artifacts.resolve(), {}
    for record in manifest.get("files", []):
        outputs = record.get("outputs", [])
        if outputs and "shared" not in outputs and not selected.intersection(outputs):
            continue
        try:
            path = (root / record["path"]).resolve()
            if not path.is_relative_to(root) or not path.is_file():
                raise WorkflowError("출고 파일이 없거나 허용 경로 밖에 있습니다")
            checksum = hashlib.sha256()
            with path.open("rb") as content:
                for chunk in iter(lambda: content.read(1024 * 1024), b""):
                    checksum.update(chunk)
            if checksum.hexdigest() != record.get("sha256"):
                raise WorkflowError("출고 파일이 변경되었습니다. 재제작·재검수가 필요합니다")
            verified[record["name"]] = (record, path)
        except (OSError, KeyError, TypeError):
            raise WorkflowError("출고 파일 검증에 실패했습니다") from None
    latest = store.job(job["id"])
    if (latest.get("source_hash"), (latest.get("manifest") or {}).get("hash"), latest.get("release_approval")) != (job.get("source_hash"), manifest.get("hash"), job.get("release_approval")):
        raise WorkflowError("파일 검사 중 출고 판본이 변경되었습니다")
    return verified, selected


def _safe_file(record):
    result = {key: record[key] for key in ("name", "sha256", "size", "kind") if key in record}
    asset_id = record.get("id")
    if isinstance(asset_id, str) and re.fullmatch(r"asset_[a-zA-Z0-9_-]+", asset_id):
        result.update(id=asset_id, url="/api/artifacts/" + asset_id)
    return result


def staging_view(store, job_id):
    job = store.job(job_id)
    rows, ledger, context_hash, opened = _context(store, job)
    source = job.get("source_packet") or {}
    audience = source.get("audience")
    language = audience.get("language") if isinstance(audience, dict) else None
    blockers, verified, selected = [], {}, set()
    try:
        verified, selected = _verified_records(store, job)
    except WorkflowError as error:
        blockers.append(str(error))
    manifest = job.get("manifest") or {}
    current_release = not blockers
    items = []
    for row in rows:
        key, platform = row["key"], row["platform"]
        local_issues = list(blockers)
        if language not in ("ko", "en") or language != row.get("locale"):
            local_issues.append("승인 원고 언어와 대상 채널 언어가 다르거나 미확인입니다. 자동 번역하지 않았습니다")
        if not row.get("public_url"):
            local_issues.append("대상 채널의 공개 주소를 확인하세요")
        required = ["short.mp4", "description.txt"] if platform == "youtube" else [BLOG_FILES.get(key) or SOCIAL_TARGETS[key][0]]
        if key == "tistory_main":
            required.extend(name for name in verified if name in ("source-original.md", "source-photos.json") or SOURCE_PHOTO_NAME_PATTERN.fullmatch(name))
            if source.get("preserve_original") is True:
                required.extend(["source-original.md", "source-photos.json"])
                cache = verified.get("source-photos.json")
                if cache:
                    try:
                        if cache[1].stat().st_size > 1024 * 1024:
                            raise ValueError("photo_manifest_too_large")
                        snapshot = json.loads(cache[1].read_text(encoding="utf-8"))
                        if not isinstance(snapshot, dict):
                            raise ValueError("invalid_photo_manifest")
                        photos = snapshot.get("photos")
                        if snapshot.get("version") != 1 or not isinstance(photos, list) or len(photos) > 8:
                            raise ValueError("invalid_photo_manifest")
                        for photo in photos:
                            name = photo.get("filename") if isinstance(photo, dict) else None
                            if not isinstance(name, str) or not SOURCE_PHOTO_NAME_PATTERN.fullmatch(name):
                                raise ValueError("invalid_photo_name")
                            required.append(name)
                    except (OSError, UnicodeError, ValueError, TypeError):
                        local_issues.append("원문 사진의 의존 파일 목록을 확인하지 못했습니다. 출고 묶음을 재검수하세요")
            required = list(dict.fromkeys(required))
        output = "video" if platform == "youtube" else "blog"
        if output not in selected:
            local_issues.append(f"{output} 출력이 현재 출고 승인②에 포함되지 않았습니다")
        available = [name for name in required if name in verified and output in verified[name][0].get("outputs", [])]
        if len(available) != len(required):
            local_issues.append("필수 파일이 아직 없거나 현재 출고 대상이 아닙니다")
        if key in SOCIAL_TARGETS and current_release:
            if available:
                try:
                    path = verified[available[0]][1]
                    if path.stat().st_size > 2 * 1024 * 1024:
                        raise ValueError("text_too_large")
                    text = path.read_text(encoding="utf-8")
                    if len(text.rstrip()) > SOCIAL_TARGETS[key][1]:
                        local_issues.append("앱의 보수적 글자 수 기준을 넘었습니다. 조건·근거를 유지해 검토하세요")
                except (OSError, UnicodeError, ValueError):
                    local_issues.append("채널 텍스트를 정상적인 검토 범위로 읽지 못했습니다")
            captured = next((r for r in (manifest.get("production_contract") or {}).get("channel_registry", []) if r.get("key") == key), None)
            if not captured or any(captured.get(field) != row.get(field) for field in ("platform", "locale", "public_url")):
                local_issues.append("제작 후 대상 채널 설정이 바뀌었거나 미확인입니다. 현재 설정으로 제작·출고 검토하세요")
        if platform == "instagram":
            media = [name for name, (record, _) in verified.items()
                     if (name == "short.mp4" and "video" in selected)
                     or (name.startswith("scene-") and name.endswith(".png") and "cards" in selected and "cards" in record.get("outputs", []))]
            required.append("출고 승인된 영상 또는 장면 카드")
            if not media:
                local_issues.append("캡션 외에 출고 승인한 영상·카드 파일이 필요합니다")
            available.extend(media)
        issues = list(local_issues)
        local_ready = not local_issues and key != "x_main"
        external_state, external_id, external_created = "not_connected", None, False
        upload_status, processing_status = None, None
        status = "local_ready" if local_ready else "blocked"
        can_upload = False
        if platform == "youtube":
            external_state = "not_attempted" if row.get("credentials_configured") else "not_connected"
            if not row.get("external_account_id"):
                issues.append("대상 YouTube 채널 ID가 등록되지 않아 소유 채널 일치를 확인하지 못했습니다. 연결 화면에서 확인하세요")
            if not row.get("credentials_configured"):
                issues.append("YouTube OAuth 연결이 필요합니다. 자격 정보 존재만으로 실제 계정 인증을 보증하지 않습니다")
            if row.get("publication_enabled") is not True:
                issues.append("이 채널의 전송 허용이 꺼져 있습니다. 운영자가 채널 설정을 확인하세요")
            if not opened:
                issues.append("작업 시간이 닫혀 있습니다. 외부 전송은 시작하지 않습니다")
            asset = verified.get("short.mp4", ({}, None))[0].get("sha256")
            matching = [r for r in ledger if asset and r.get("channel_key", "youtube_main_ko") == key and r.get("asset_sha256") == asset]
            priority = {"created": 4, "accepted": 4, "unknown": 4, "needs_review": 3, "private": 2}
            delivery = max(matching, key=lambda r: (priority.get(r.get("state"), 0), r.get("updated_at", "")), default=None)
            if delivery:
                candidate_id = delivery.get("external_id")
                external_id = candidate_id if isinstance(candidate_id, str) and re.fullmatch(r"[A-Za-z0-9_-]{5,64}", candidate_id) else None
                upload_status = delivery.get("upload_status") if isinstance(delivery.get("upload_status"), str) else None
                processing_status = delivery.get("processing_status") if isinstance(delivery.get("processing_status"), str) else None
                state = delivery.get("state")
                if state == "private" and delivery.get("privacy_status") == "private" and external_id:
                    external_state, external_created = "private", True
                    if local_ready: status = "private"
                elif state in ("created", "accepted", "unknown", "private"):
                    external_state = "unknown"
                    if local_ready: status = "unknown"
                    issues.append("기존 전송 결과가 불명입니다. 재업로드하지 말고 업로드 원장에서 대사하세요")
                elif state == "needs_review":
                    external_state = "needs_review"
                    if local_ready: status = "needs_review"
                    issues.append("기존 전송 기록에 사람의 검토가 필요합니다")
                elif state == "failed":
                    external_state = "needs_review"
                    if local_ready: status = "needs_review"
                    issues.append("기존 업로드 장부의 실패 사유를 확인하세요. 자동으로 재전송하지 않습니다")
            can_upload = local_ready and bool(row.get("credentials_configured")) and row.get("publication_enabled") is True and opened and external_state == "not_attempted"
        else:
            issues.append("로컬 출고 파일만 준비합니다. 플랫폼 임시저장·예약 API는 연결하지 않았습니다")
            if key == "tistory_main" and any(SOURCE_PHOTO_NAME_PATTERN.fullmatch(name) for name in required):
                issues.append("HTML과 사진·원문·사진 목록은 같은 승인 ZIP으로 함께 전달하세요. HTML 한 파일만으로는 사진이 열리지 않습니다")
        if key == "x_main":
            status, local_ready = "paused", False
            issues = ["사용자 요청으로 X 채널은 보류했습니다"]
        items.append({"channel_key": key, "label": row["label"], "platform": platform, "locale": row["locale"],
                      "source_language": language, "public_url": row.get("public_url"), "status": status,
                      "local_ready": local_ready, "required_files": required,
                      "files": [_safe_file(verified[name][0]) for name in dict.fromkeys(available)] if current_release and key != "x_main" else [],
                      "blockers": issues, "external_state": external_state, "external_draft_created": external_created,
                      "external_id": external_id, "upload_status": upload_status, "processing_status": processing_status,
                      "can_upload_private": can_upload})
    base = {"job_id": job_id, "source_hash": job.get("source_hash"), "manifest_hash": manifest.get("hash"),
            "current_release": current_release, "blockers": blockers, "channels": items, "context_hash": context_hash,
            "notes": ["현재 원고·오퍼·출고 승인②·파일 해시로 매번 계산한 로컬 준비 상태입니다",
                      "로컬 준비 완료는 외부 임시저장·업로드·공개 완료를 뜻하지 않습니다",
                      "YouTube만 기존 비공개 전송기를 사용하며 실제 외부 호출은 별도 요청·인증·작업 시간 검사를 거칩니다",
                      "X는 보류이며 Slack·Discord 프로필과 스토어 주소는 배포 채널에 섞지 않습니다"]}
    stage_hash = digest(base)
    recorded = job.get("channel_staging") or {}
    return {**base, "stage_hash": stage_hash, "recorded_at": recorded.get("recorded_at"),
            "recorded_current": recorded.get("stage_hash") == stage_hash}


def _record_staging(store, job_id, view, expected_hash, actor):
    if not str(actor or "").strip():
        raise WorkflowError("로컬 준비 기록을 남긴 담당자가 필요합니다")
    if view["stage_hash"] != expected_hash:
        raise WorkflowError("출고 판본·파일·채널 상태가 바뀌었습니다. 최신 준비 상태를 다시 확인하세요")
    if not view["current_release"]:
        raise WorkflowError("현재 출고 승인②와 파일 검증을 마친 뒤 로컬 배포 대기를 기록하세요")
    with store.connection(transaction=True) as db:
        job = store._job(db, job_id)
        if _context(store, job)[2] != view["context_hash"]:
            raise WorkflowError("로컬 준비 기록 중 원고·오퍼·출고 또는 채널 상태가 바뀌었습니다")
        _verified_records(store, job)
        existing = job.get("channel_staging") or {}
        if existing.get("stage_hash") != expected_hash:
            job["channel_staging"] = {key: value for key, value in view.items() if key not in ("recorded_at", "recorded_current")}
            job["channel_staging"].update(recorded_at=now(), actor=actor)
            store._write_job(db, job)
            store._event(db, "channel_staging_prepared", {"stage_hash": expected_hash, "manifest_hash": view["manifest_hash"],
                         "local_ready": sum(r["local_ready"] for r in view["channels"]), "external_sent": False, "actor": actor}, job_id)
    return staging_view(store, job_id)


def prepare_staging(store, job_id, expected_hash, actor):
    return _record_staging(store, job_id, staging_view(store, job_id), expected_hash, actor)


def auto_prepare_staging(store, job_id, actor):
    """Runs after approval② commits. A local-record failure must not undo that approval."""
    try:
        view = staging_view(store, job_id)
        return _record_staging(store, job_id, view, view["stage_hash"], actor)
    except Exception as error:
        message = str(error) if isinstance(error, WorkflowError) else "로컬 준비 기록에 실패했습니다. 현재 상태를 다시 확인하세요"
        try:
            store.event("channel_staging_prepare_skipped", {"reason": message, "external_sent": False, "actor": actor}, job_id)
        except Exception:
            # Approval has already committed; even a failed diagnostic write must not reverse it.
            pass
        return None
