"""Explicit private YouTube upload for a release-approved② video. No public visibility, no retries.

Protocol verified 2026-10-28: https://developers.google.com/youtube/v3/guides/using_resumable_upload_protocol
Video resource: https://developers.google.com/youtube/v3/docs/videos
The operator supplies YOUTUBE_CLIENT_ID / YOUTUBE_CLIENT_SECRET (shared) and one refresh token per channel
key (YOUTUBE_MAIN_KO_REFRESH_TOKEN, YOUTUBE_ENGLISH_REFRESH_TOKEN; legacy YOUTUBE_REFRESH_TOKEN still counts
for youtube_main_ko) through the runtime environment only. Access tokens live in memory for one call.
The brief language must match the channel locale before any request, the channel key is part of the
idempotency key, and a response channelId that differs from the registered one becomes needs_review.
Delivery states: created → accepted → private | failed | unknown | needs_review. An unknown result is
reconciled before anything is sent again; nothing is ever re-uploaded blindly.
"""
from __future__ import annotations

import argparse
import hashlib
import json
from contextlib import contextmanager

import requests

from .channels import CHANNELS, channel as channel_row, configured_youtube_channels, missing_credential_names, youtube_credentials
from .runtime import AlreadyRunning, ProcessLock, window_open
from .store import WorkflowError, canonical, digest, now

TOKEN_URL = "https://oauth2.googleapis.com/token"
UPLOAD_URL = "https://www.googleapis.com/upload/youtube/v3/videos?uploadType=resumable&part=snippet,status"
VIDEOS_URL = "https://www.googleapis.com/youtube/v3/videos"
QUOTA_UNITS_INSERT = 1600
QUOTA_NOTE = "2026-10-28 기준 업로드 전용 일일 버킷 100회·기타 10,000단위; 과거 1,600단위 환산은 참고값"
RESUMABLE_RETRY_CODES = (500, 502, 503, 504)
MAX_TITLE = 100
MAX_DESCRIPTION = 5000
MAX_TAG_CHARS = 500
LEDGER_KEY = "deliveries"
DEFAULT_CHANNEL = "youtube_main_ko"


def configured():
    """Credentials exist; this does not prove authentication, ownership, or permission to send."""
    return bool(configured_youtube_channels())


def _youtube_channel(store, channel_key):
    definition = CHANNELS.get(channel_key)
    if not definition or definition["platform"] != "youtube":
        raise WorkflowError(f"'{channel_key}'은(는) 등록된 YouTube 채널 키가 아닙니다. 채널 레지스트리를 확인하세요")
    return channel_row(store, channel_key)


def _require_channel_enabled(store, channel_key):
    row = _youtube_channel(store, channel_key)
    if row.get("publication_enabled") is not True:
        raise WorkflowError("이 채널의 전송 허용이 꺼져 있습니다. 운영자가 채널 설정을 확인하세요. 영상은 전송하지 않았습니다")
    return row


def _credentials(channel_key):
    credentials = youtube_credentials(channel_key)
    if credentials is None:
        raise WorkflowError("·".join(missing_credential_names(channel_key)) + f"이 설정되지 않았습니다({channel_key}). 채널 소유자가 실행 환경 파일에 넣거나 설정 화면의 'YouTube 연결'로 로그인한 뒤 다시 요청하세요")
    return credentials


def _require_language_match(store, job, row):
    language = ((job.get("source_packet") or {}).get("audience") or {}).get("language")
    if language not in ("ko", "en"):
        raise WorkflowError("승인 원고의 언어를 확인할 수 없습니다. 브리프만 바꾸지 말고 새 원고를 검수·제작하세요")
    if language != row["locale"]:
        raise WorkflowError(f"승인 원고 언어({language})와 채널 '{row['key']}' 언어({row['locale']})가 다릅니다. 브리프 변경은 기존 영상을 번역하지 않습니다")
    return language


def deliveries(store, job_id=None):
    ledger = store.setting(LEDGER_KEY, {})
    records = [record for record in ledger.values() if job_id is None or record.get("job_id") == job_id]
    return sorted(records, key=lambda record: record.get("created_at", ""))


@contextmanager
def _delivery_lock(store, key):
    try:
        with ProcessLock(store.root / "delivery-locks" / f"{digest(key)}.lock"):
            yield
    except AlreadyRunning:
        raise WorkflowError("같은 영상의 업로드 또는 대사가 진행 중입니다. 완료 뒤 기록을 확인하세요") from None


def _save(store, record, *, reserve=False):
    with store.connection(transaction=True) as db:
        row = db.execute("SELECT value FROM settings WHERE key=?", (LEDGER_KEY,)).fetchone()
        ledger = json.loads(row[0]) if row else {}
        existing = ledger.get(record["key"])
        if reserve and existing:
            if existing["state"] in ("created", "accepted", "unknown"):
                raise WorkflowError("같은 영상의 업로드가 진행 중이거나 결과 불명입니다. 먼저 대사(reconcile)한 뒤 다시 요청하세요")
            if existing["state"] in ("private", "published", "needs_review"):
                return existing
        ledger[record["key"]] = record
        db.execute("INSERT OR REPLACE INTO settings VALUES(?,?)", (LEDGER_KEY, canonical(ledger)))
    return record


def _released_video(store, job_id):
    job = store.job(job_id)
    from .offers import require_offer_ready, require_campaign_packet
    require_offer_ready(job.get("offer"))
    require_campaign_packet(job.get("source_packet"), job.get("offer"))
    manifest = job.get("manifest") or {}
    release = job.get("release_approval") or {}
    if (release.get("decision") != "approved" or release.get("version") != manifest.get("hash")
            or manifest.get("source_hash") != job.get("source_hash") or "video" not in release.get("outputs", [])):
        raise WorkflowError("영상에 대한 현재 출고 승인②가 필요합니다. 업로드는 요청하지 않았습니다")
    files = {record["name"]: record for record in manifest.get("files", []) if "video" in record.get("outputs", [])}
    if "short.mp4" not in files:
        raise WorkflowError("출고 승인된 영상 파일이 제작물 목록에 없습니다")
    root = store.artifacts.resolve()
    paths = {}
    for name in ("short.mp4", "description.txt"):
        record = files.get(name)
        if not record:
            continue
        path = (root / record["path"]).resolve()
        if not path.is_relative_to(root) or not path.is_file() or hashlib.sha256(path.read_bytes()).hexdigest() != record["sha256"]:
            raise WorkflowError("제작물이 변경되었거나 파일 검증에 실패했습니다. 다시 제작하고 출고 승인②를 받으세요")
        paths[name] = path
    return job, manifest, release, paths



def _require_current_upload(store, record):
    if not window_open(store):
        raise WorkflowError("작업 시간이 종료됐습니다. 영상 바이트는 전송하지 않았습니다")
    _require_channel_enabled(store, record.get("channel_key", DEFAULT_CHANNEL))
    _, manifest, _, _ = _released_video(store, record["job_id"])
    if manifest.get("hash") != record.get("manifest_hash"):
        raise WorkflowError("출고 판본이 변경됐습니다. 영상 바이트는 전송하지 않았습니다")


def video_metadata(job, manifest, paths):
    plan = (job.get("source_packet") or {}).get("video", {})
    title = str(plan.get("title") or job.get("title") or "").strip()[:MAX_TITLE]
    if not title:
        raise WorkflowError("승인된 영상 제목이 없습니다")
    if "description.txt" in paths:
        description = paths["description.txt"].read_text(encoding="utf-8")
    else:
        description = str(plan.get("description", "")).strip()
    disclosure = str((manifest.get("media") or {}).get("voice_disclosure", "합성 음성"))
    if "합성 음성" not in description:
        description += f"\n\n이 영상의 내레이션은 {disclosure}입니다."
    clips = manifest.get("clips") or {}
    stock = clips.get("provider") == "pexels"
    if manifest.get("background") or (clips and not stock):
        description += "\n일부 화면은 생성 이미지·영상입니다."
    if stock and "Pexels" not in description:
        from .exports import stock_credit_line
        description += "\n" + stock_credit_line(clips.get("attributions"))
    description = description.strip()[:MAX_DESCRIPTION]
    tags, used = [], 0
    for tag in plan.get("tags", []) if isinstance(plan.get("tags"), list) else []:
        tag = str(tag).strip()
        if tag and used + len(tag) + 2 <= MAX_TAG_CHARS:
            tags.append(tag); used += len(tag) + 2
    return {"snippet": {"title": title, "description": description, "tags": tags},
            "status": {"privacyStatus": "private", "selfDeclaredMadeForKids": False}}


def _access_token(session, credentials):
    try:
        response = session.post(TOKEN_URL, data={**credentials, "grant_type": "refresh_token"}, timeout=(10, 30))
        if response.status_code != 200:
            raise WorkflowError(f"YouTube 인증 갱신 실패 HTTP {response.status_code}. 업로드는 시작하지 않았습니다")
        token = response.json().get("access_token")
    except requests.RequestException:
        raise WorkflowError("YouTube 인증 서버에 연결하지 못했습니다. 업로드는 시작하지 않았습니다") from None
    except (ValueError, TypeError, AttributeError):
        raise WorkflowError("YouTube 인증 응답을 읽지 못했습니다. 업로드는 시작하지 않았습니다") from None
    if not isinstance(token, str) or not token:
        raise WorkflowError("YouTube 접근 토큰을 받지 못했습니다. 업로드는 시작하지 않았습니다")
    return token


def _finalize(store, record, body):
    try:
        external_id = body["id"]
        status = body.get("status", {})
        if not isinstance(status, dict) or not isinstance(external_id, str) or not external_id:
            raise ValueError("id")
    except (KeyError, ValueError, TypeError, AttributeError):
        record.update(state="unknown", reason="upload_response_unreadable", updated_at=now())
        _save(store, record)
        raise WorkflowError("업로드 응답을 읽지 못해 결과 불명으로 남깁니다. 대사 후 다시 확인하세요") from None
    processing = body.get("processingDetails") if isinstance(body.get("processingDetails"), dict) else {}
    record.update(external_id=external_id, upload_status=status.get("uploadStatus"), privacy_status=status.get("privacyStatus"),
                  processing_status=processing.get("processingStatus"), updated_at=now())
    expected = channel_row(store, record.get("channel_key", DEFAULT_CHANNEL)).get("external_account_id")
    snippet = body.get("snippet") if isinstance(body.get("snippet"), dict) else {}
    actual = snippet.get("channelId")
    if expected and (not isinstance(actual, str) or not actual):
        record.update(state="unknown", reason="channel_unconfirmed")
        _save(store, record)
        store.event("delivery_needs_review", {"delivery_id": record["id"], "external_id": external_id, "reason": record["reason"]}, record["job_id"])
        raise WorkflowError("업로드 외부 ID는 받았지만 채널 ID를 확인하지 못했습니다. 재업로드하지 말고 대사하세요")
    if expected and isinstance(actual, str) and actual and actual != expected:
        record.update(state="needs_review", reason="channel_mismatch", response_channel_id=actual)
        _save(store, record)
        store.event("delivery_channel_mismatch", {"delivery_id": record["id"], "external_id": external_id, "channel_key": record.get("channel_key"), "expected_channel_id": expected, "response_channel_id": actual}, record["job_id"])
        raise WorkflowError(f"업로드된 채널 ID({actual})가 등록된 채널 '{record.get('channel_key')}'({expected})과 다릅니다. YouTube Studio에서 즉시 확인하세요")
    if status.get("privacyStatus") is None:
        record.update(state="unknown", reason="visibility_unconfirmed")
        _save(store, record)
        store.event("delivery_needs_review", {"delivery_id": record["id"], "external_id": external_id, "reason": record["reason"]}, record["job_id"])
        raise WorkflowError("업로드 외부 ID는 받았지만 비공개 여부를 확인하지 못했습니다. 재업로드하지 말고 대사하세요")
    if status.get("privacyStatus") != "private":
        record.update(state="needs_review", reason="visibility_mismatch")
        _save(store, record)
        store.event("delivery_visibility_mismatch", {"delivery_id": record["id"], "external_id": external_id, "privacy_status": status.get("privacyStatus")}, record["job_id"])
        raise WorkflowError("업로드 결과의 공개 범위가 private가 아닙니다. YouTube Studio에서 즉시 확인하세요")
    record.update(state="private", visibility="private", reason=None)
    _save(store, record)
    store.event("delivery_private", {"delivery_id": record["id"], "external_id": external_id, "channel": "youtube", "quota_units_estimate": QUOTA_UNITS_INSERT}, record["job_id"])
    return record


def deliver_youtube(store, job_id, *, actor, session=None, channel_key=DEFAULT_CHANNEL):
    if not window_open(store):
        raise WorkflowError("허용된 작업 시간이 종료됐습니다. 업로드는 시작하지 않았습니다")
    session = session or requests
    row = _require_channel_enabled(store, channel_key)
    job, manifest, release, paths = _released_video(store, job_id)
    credentials = _credentials(channel_key)
    locale = _require_language_match(store, job, row)
    video_path = paths["short.mp4"]
    data = video_path.read_bytes()
    asset_sha = hashlib.sha256(data).hexdigest()
    key = digest({"channel": "youtube", "channel_key": channel_key, "job_id": job_id, "asset_sha256": asset_sha, "manifest_hash": manifest["hash"]})
    metadata = video_metadata(job, manifest, paths)
    record = {"id": "delivery_" + key[:16], "key": key, "channel": "youtube", "channel_key": channel_key, "locale": locale, "job_id": job_id, "asset_sha256": asset_sha,
              "manifest_hash": manifest["hash"], "release_version": release["version"], "idempotency_key": key,
              "title": metadata["snippet"]["title"], "visibility": "private", "state": "created", "actor": str(actor)[:120],
              "quota_units_estimate": QUOTA_UNITS_INSERT, "quota_note": QUOTA_NOTE, "created_at": now(), "updated_at": now()}
    with _delivery_lock(store, key):
        return _upload_youtube(store, record, data, metadata, credentials, session)


def _upload_youtube(store, record, data, metadata, credentials, session):
    _require_channel_enabled(store, record["channel_key"])
    record = _save(store, record, reserve=True)
    if record["state"] != "created":
        return record
    job_id = record["job_id"]
    store.event("delivery_created", {"delivery_id": record["id"], "channel": "youtube", "channel_key": record["channel_key"], "visibility": "private"}, job_id)
    try:
        _require_channel_enabled(store, record["channel_key"])
        token = _access_token(session, credentials)
    except WorkflowError:
        record.update(state="failed", reason="oauth_before_upload_failed", updated_at=now())
        _save(store, record)
        store.event("delivery_failed", {"delivery_id": record["id"], "reason": record["reason"]}, job_id)
        raise
    headers = {"Authorization": "Bearer " + token, "Content-Type": "application/json; charset=UTF-8",
               "X-Upload-Content-Length": str(len(data)), "X-Upload-Content-Type": "video/mp4"}
    try:
        if not window_open(store):
            raise WorkflowError("인증을 기다리는 동안 작업 시간이 종료됐습니다. 업로드는 시작하지 않았습니다")
        _require_channel_enabled(store, record["channel_key"])
        _, current_manifest, _, _ = _released_video(store, job_id)
        if current_manifest["hash"] != record["manifest_hash"]:
            raise WorkflowError("인증을 기다리는 동안 출고 판본이 변경되었습니다. 현재 제작물을 확인한 뒤 다시 요청하세요")
    except WorkflowError:
        record.update(state="failed", reason="release_changed_before_upload", updated_at=now())
        _save(store, record)
        store.event("delivery_failed", {"delivery_id": record["id"], "reason": record["reason"]}, job_id)
        raise
    try:
        start = session.post(UPLOAD_URL, headers=headers, json=metadata, timeout=(10, 60))
    except requests.RequestException:
        record.update(state="unknown", reason="start_network_result_unknown", updated_at=now()); _save(store, record)
        raise WorkflowError("업로드 세션 시작 결과가 불명입니다. 자동 재전송하지 않으며 대사가 필요합니다") from None
    if start.status_code != 200 or not start.headers.get("Location"):
        record.update(state="failed", reason=f"start_http_{start.status_code}", updated_at=now()); _save(store, record)
        store.event("delivery_failed", {"delivery_id": record["id"], "reason": record["reason"]}, job_id)
        raise WorkflowError(f"YouTube 업로드 세션 시작 실패 HTTP {start.status_code}. 할당량·권한을 확인한 뒤 다시 요청하세요")
    record.update(state="accepted", session_uri=start.headers["Location"], updated_at=now()); _save(store, record)
    try:
        _require_current_upload(store, record)
    except WorkflowError:
        record.update(reason="conditions_changed_before_bytes", updated_at=now()); _save(store, record)
        raise
    try:
        upload = session.put(record["session_uri"], headers={"Authorization": "Bearer " + token, "Content-Length": str(len(data)), "Content-Type": "video/mp4"}, data=data, timeout=(10, 600))
    except requests.RequestException:
        record.update(state="unknown", reason="upload_network_result_unknown", updated_at=now()); _save(store, record)
        raise WorkflowError("업로드 결과가 불명입니다. 세션을 보존했고 대사(reconcile)로 이어서 확인합니다") from None
    if upload.status_code in (200, 201):
        try:
            body = upload.json()
        except (ValueError, TypeError):
            body = {}
        return _finalize(store, record, body)
    if upload.status_code in RESUMABLE_RETRY_CODES:
        record.update(state="unknown", reason=f"upload_http_{upload.status_code}", updated_at=now()); _save(store, record)
        raise WorkflowError(f"YouTube 업로드 중 서버 오류 HTTP {upload.status_code}. 결과 불명으로 남겼고 대사(reconcile)로 이어서 확인합니다")
    record.update(state="failed", reason=f"upload_http_{upload.status_code}", updated_at=now()); _save(store, record)
    store.event("delivery_failed", {"delivery_id": record["id"], "reason": record["reason"]}, job_id)
    raise WorkflowError(f"YouTube 업로드 실패 HTTP {upload.status_code}. 자동 재시도하지 않습니다")


def reconcile_youtube(store, job_id, delivery_id, *, session=None):
    if not window_open(store):
        raise WorkflowError("허용된 작업 시간이 종료됐습니다. 새 작업 시간을 지정한 뒤 대사하세요")
    session = session or requests
    record = next((r for r in deliveries(store, job_id) if r["id"] == delivery_id), None)
    if not record:
        raise WorkflowError("해당 업무의 업로드 기록이 없습니다")
    with _delivery_lock(store, record["key"]):
        record = next(r for r in deliveries(store, job_id) if r["id"] == delivery_id)
        return _reconcile_youtube(store, job_id, record, session)


def _reconcile_youtube(store, job_id, record, session):
    if record["state"] == "created":
        record.update(state="unknown", reason="interrupted_before_session_saved", updated_at=now())
        _save(store, record)
        store.event("delivery_needs_review", {"delivery_id": record["id"], "reason": record["reason"]}, job_id)
    if not record.get("session_uri") and not record.get("external_id"):
        raise WorkflowError("대사할 세션이나 외부 ID가 없어 결과를 확정할 수 없습니다. YouTube Studio에서 직접 확인하세요. 자동 재전송하지 않습니다")
    token = _access_token(session, _credentials(record.get("channel_key", DEFAULT_CHANNEL)))
    if record["state"] in ("accepted", "unknown") and record.get("session_uri") and not record.get("external_id"):
        _, manifest, _, paths = _released_video(store, job_id)
        data = paths["short.mp4"].read_bytes()
        if hashlib.sha256(data).hexdigest() != record["asset_sha256"]:
            raise WorkflowError("업로드 중이던 영상 파일이 변경되었습니다. 대사를 중단합니다")
        total = len(data)
        try:
            status = session.put(record["session_uri"], headers={"Authorization": "Bearer " + token, "Content-Length": "0", "Content-Range": f"bytes */{total}"}, timeout=(10, 60))
            if status.status_code in (200, 201):
                return _finalize(store, record, status.json())
            if status.status_code == 308:
                received = status.headers.get("Range", "")
                first = int(received.split("-")[-1]) + 1 if received.startswith("bytes=") else 0
                _require_current_upload(store, record)
                resumed = session.put(record["session_uri"], headers={"Authorization": "Bearer " + token, "Content-Length": str(total - first), "Content-Type": "video/mp4", "Content-Range": f"bytes {first}-{total - 1}/{total}"}, data=data[first:], timeout=(10, 600))
                if resumed.status_code in (200, 201):
                    return _finalize(store, record, resumed.json())
                if resumed.status_code in RESUMABLE_RETRY_CODES or resumed.status_code == 308:
                    record.update(reason=f"resume_http_{resumed.status_code}", updated_at=now()); _save(store, record)
                    raise WorkflowError("이어 올리기가 아직 끝나지 않았습니다. 결과 불명을 유지하며 다시 대사하세요")
                record.update(state="failed", reason=f"resume_http_{resumed.status_code}", updated_at=now()); _save(store, record)
                raise WorkflowError(f"이어 올리기 실패 HTTP {resumed.status_code}. 새 업로드는 운영자가 다시 요청합니다")
            if status.status_code == 404:
                record.update(state="failed", reason="session_expired", updated_at=now()); _save(store, record)
                raise WorkflowError("업로드 세션이 만료되었습니다. 새 업로드는 운영자가 다시 요청합니다")
            record.update(reason=f"status_http_{status.status_code}", updated_at=now()); _save(store, record)
            raise WorkflowError(f"업로드 상태 확인 HTTP {status.status_code}. 결과 불명을 유지합니다")
        except requests.RequestException:
            raise WorkflowError("업로드 상태 확인 중 연결이 끊겼습니다. 결과 불명을 유지합니다") from None
        except WorkflowError:
            raise
        except (ValueError, TypeError):
            raise WorkflowError("업로드 상태 응답을 읽지 못했습니다. 결과 불명을 유지합니다") from None
    if record.get("external_id"):
        try:
            listing = session.get(VIDEOS_URL, headers={"Authorization": "Bearer " + token}, params={"part": "snippet,status,processingDetails", "id": record["external_id"]}, timeout=(10, 30))
            items = listing.json().get("items", []) if listing.status_code == 200 else []
        except (requests.RequestException, ValueError, TypeError, AttributeError):
            raise WorkflowError("YouTube 영상 상태를 조회하지 못했습니다. 기록은 그대로 둡니다") from None
        if not items:
            record.update(state="needs_review", reason="video_not_found", updated_at=now()); _save(store, record)
            store.event("delivery_needs_review", {"delivery_id": record["id"], "reason": "video_not_found"}, job_id)
            return record
        status = items[0].get("status", {})
        record.update(upload_status=status.get("uploadStatus"), privacy_status=status.get("privacyStatus"),
                      processing_status=items[0].get("processingDetails", {}).get("processingStatus"), reconciled_at=now(), updated_at=now())
        expected = channel_row(store, record.get("channel_key", DEFAULT_CHANNEL)).get("external_account_id")
        snippet = items[0].get("snippet") if isinstance(items[0].get("snippet"), dict) else {}
        actual = snippet.get("channelId")
        if expected and actual != expected:
            reason = "channel_mismatch" if isinstance(actual, str) and actual else "channel_unconfirmed"
            if record["state"] != "needs_review":
                record.update(state="needs_review" if reason == "channel_mismatch" else "unknown", reason=reason, response_channel_id=actual)
            _save(store, record)
            return record
        privacy = status.get("privacyStatus")
        if privacy is None and record["state"] != "needs_review":
            record.update(state="unknown", reason="visibility_unconfirmed")
        elif privacy != "private" and record["state"] != "needs_review":
            record.update(state="needs_review", reason="visibility_mismatch")
            store.event("delivery_visibility_mismatch", {"delivery_id": record["id"], "external_id": record["external_id"], "privacy_status": privacy}, job_id)
        elif privacy == "private" and record.get("reason") in ("visibility_unconfirmed", "channel_unconfirmed"):
            record.update(state="private", visibility="private", reason=None)
            store.event("delivery_private", {"delivery_id": record["id"], "external_id": record["external_id"], "channel": "youtube", "reconciled": True}, job_id)
        _save(store, record)
        return record
    raise WorkflowError("대사할 세션이나 외부 ID가 없는 기록입니다")


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("command", choices=["status", "deliver", "reconcile"])
    parser.add_argument("--job", required=True)
    parser.add_argument("--delivery")
    parser.add_argument("--channel", default=DEFAULT_CHANNEL, help="채널 키 (youtube_main_ko·youtube_english)")
    args = parser.parse_args()
    from .bootstrap import default_store
    store = default_store()
    try:
        if args.command == "deliver":
            print(canonical(deliver_youtube(store, args.job, actor="local-operator-cli", channel_key=args.channel)))
        elif args.command == "reconcile":
            if not args.delivery:
                parser.error("reconcile 명령에는 --delivery가 필요합니다")
            print(canonical(reconcile_youtube(store, args.job, args.delivery)))
        else:
            print(canonical({"configured": configured(), "channels": configured_youtube_channels(), "deliveries": deliveries(store, args.job)}))
    except WorkflowError as error:
        parser.exit(1, str(error) + "\n")


if __name__ == "__main__":
    main()
