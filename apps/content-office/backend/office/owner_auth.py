"""Owner-PC delivery queue. This module never accepts or stores social credentials."""
from __future__ import annotations

from datetime import datetime, timezone
import hashlib
import json
import os
from pathlib import Path

from .store import WorkflowError, digest, now


def enabled():
    return os.environ.get("OFFICE_SOCIAL_AUTH_MODE") == "owner_pc"


def require_server_auth_allowed():
    if enabled():
        raise WorkflowError("소셜 로그인 정보는 본인 PC에만 저장합니다. PC 인증 실행기에서 연결하세요")


def available_keys():
    try:
        path = Path(os.environ["OFFICE_STATE_DIR"]) / "runtime/owner-auth-status.json"
        value = json.loads(path.read_text(encoding="utf-8"))
        age = (datetime.now(timezone.utc) - datetime.fromisoformat(value["checked_at"])).total_seconds()
        if not 0 <= age <= 600:
            return []
        return [key for key, ready in value["channels"].items() if ready is True]
    except (OSError, KeyError, TypeError, ValueError, AttributeError):
        return []


def stage_delivery(store, job_id, channel_key, actor):
    from .runtime import window_open
    from .youtube_delivery import _released_video, _require_channel_enabled, _require_language_match, _delivery_lock, _save, video_metadata
    if not enabled() or not window_open(store):
        raise WorkflowError("PC 전달 모드와 승인된 작업 시간을 확인하세요")
    store.require_source_approval(job_id)
    row = _require_channel_enabled(store, channel_key)
    if channel_key not in available_keys():
        raise WorkflowError("본인 PC 인증 실행기가 연결되지 않았습니다. 로그인 정보는 서버에 저장하지 않습니다")
    job, manifest, release, paths = _released_video(store, job_id)
    locale = _require_language_match(store, job, row)
    checksum = hashlib.sha256(paths["short.mp4"].read_bytes()).hexdigest()
    key = digest({"channel": "youtube", "channel_key": channel_key, "job_id": job_id, "asset_sha256": checksum, "manifest_hash": manifest["hash"]})
    record = {"id": "delivery_" + key[:16], "key": key, "channel": "youtube", "channel_key": channel_key,
              "job_id": job_id, "manifest_hash": manifest["hash"], "release_version": release["version"],
              "source_hash": job["source_hash"], "release_hash": digest(release), "locale": locale,
              "channel_hash": digest(row),
              "asset_sha256": checksum, "visibility": "private", "state": "pending_owner",
              "title": video_metadata(job, manifest, paths)["snippet"]["title"], "auth_location": "owner_pc",
              "reason": "본인 PC에서 비공개 업로드 검토 대기",
              "actor": str(actor)[:120], "created_at": now(), "updated_at": now()}
    with _delivery_lock(store, key):
        existing = store.setting("deliveries", {}).get(key)
        if existing:
            return existing
        return _save(store, record)


def export_pending(store):
    from .youtube_delivery import _released_video, video_metadata
    from .channels import channel
    from .runtime import window_open
    if not enabled() or not window_open(store):
        return []
    rows = []
    for record in store.setting("deliveries", {}).values():
        if record.get("state") != "pending_owner" or record.get("auth_location") != "owner_pc":
            continue
        job, manifest, release, paths = _released_video(store, record["job_id"])
        store.require_source_approval(job["id"])
        if (job["source_hash"], manifest["hash"], digest(release)) != (record["source_hash"], record["manifest_hash"], record["release_hash"]):
            continue
        if digest(channel(store, record["channel_key"])) != record["channel_hash"]:
            continue
        video = paths["short.mp4"]
        metadata = video_metadata(job, manifest, paths)
        rows.append({"delivery_key": record["key"], "channel_key": record["channel_key"], "job_id": job["id"],
                     "asset_path": video.relative_to(store.artifacts.resolve()).as_posix(),
                     "asset_sha256": record["asset_sha256"], "asset_size": video.stat().st_size,
                     "authorized_end": store.setting("work_window", {}).get("authorized_end"),
                     "title": metadata["snippet"]["title"], "description": metadata["snippet"]["description"]})
    return rows


def accept_receipt(store, key, receipt):
    from .youtube_delivery import _released_video, _save, _delivery_lock, video_metadata
    from .channels import channel
    import re
    if not isinstance(receipt, dict) or set(receipt) - {"state", "external_id", "content_hash", "channel_key", "verified_at"}:
        raise WorkflowError("PC 전달 결과 형식이 올바르지 않습니다")
    if receipt.get("state") != "platform_private" or not re.fullmatch(r"[A-Za-z0-9_-]{6,40}", receipt.get("external_id", "")):
        raise WorkflowError("검증된 비공개 전달 결과만 받을 수 있습니다")
    with _delivery_lock(store, key):
        row = store.setting("deliveries", {}).get(key)
        if not row or row.get("auth_location") != "owner_pc" or receipt.get("channel_key") != row["channel_key"]:
            raise WorkflowError("PC 전달 대상이 일치하지 않습니다")
        job, manifest, release, paths = _released_video(store, row["job_id"])
        if (job["source_hash"], manifest["hash"], digest(release)) != (row["source_hash"], row["manifest_hash"], row["release_hash"]):
            raise WorkflowError("PC 전달 중 원고·출고 판본이 변경됐습니다")
        if digest(channel(store, row["channel_key"])) != row["channel_hash"]:
            raise WorkflowError("PC 전달 중 대상 채널 설정이 변경됐습니다")
        original = video_metadata(job, manifest, paths)
        payload = {"snippet": {k: original["snippet"][k] for k in ("title", "description")}, "status": original["status"]}
        expected = hashlib.sha256(paths["short.mp4"].read_bytes() + json.dumps(payload, sort_keys=True).encode()).hexdigest()
        if receipt.get("content_hash") != expected:
            raise WorkflowError("PC에서 확인한 영상·메타데이터가 출고 판본과 다릅니다")
        if row["state"] == "private":
            if row.get("external_id") != receipt["external_id"]:
                raise WorkflowError("다른 업로드 결과로 기존 기록을 덮어쓸 수 없습니다")
            return row
        if row["state"] != "pending_owner":
            raise WorkflowError("PC 전달 대기 상태가 아닙니다")
        return _save(store, {**row, "state": "private", "external_id": receipt["external_id"], "privacy_status": "private", "owner_content_hash": receipt.get("content_hash"), "updated_at": now()})
