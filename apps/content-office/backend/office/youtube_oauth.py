"""YouTube 채널 연결(OAuth 2.0 웹 서버 흐름). 채널 소유자가 로그인해 refresh token을 받는다.

근거(2026-10-30 확인): https://developers.google.com/identity/protocols/oauth2/web-server
- 인증: https://accounts.google.com/o/oauth2/v2/auth (response_type=code, access_type=offline, prompt=consent,
  include_granted_scopes=false, state). 기존 Hermes 등 같은 프로젝트의 권한을 합치지 않는다.
- 교환: POST https://oauth2.googleapis.com/token (grant_type=authorization_code) → access_token·refresh_token·scope.
- 리디렉션 URI는 https이고 콘솔에 등록한 값과 정확히 같아야 한다.
- 동의 화면이 'Testing' 상태면 refresh token은 7일 뒤 만료된다(https://developers.google.com/identity/protocols/oauth2).
채널 ID: GET https://www.googleapis.com/youtube/v3/channels?part=id,snippet&mine=true (1단위).

연결은 발행이 아니다. 승인⓪①②③·비공개 업로드 규칙은 그대로이며, 토큰은 youtube_tokens 비밀 파일에만 둔다.
state는 1회용(10분)이고 DB에는 해시만 남긴다. Google에서 돌아오는 요청은 사이트 간 이동이라 SameSite=Strict
세션 쿠키가 오지 않으므로, 시작 요청(CSRF 검증된 세션)에서 이 경로 전용 SameSite=Lax 쿠키로 브라우저를 묶는다.
"""
from __future__ import annotations

import hashlib
import hmac
import json
import os
import secrets
import time
from urllib.parse import urlencode

import requests

from .channels import CHANNELS, SHARED_ENV, YOUTUBE_CHANNEL_ID, channel, env_refresh_token, registry, update_channel, youtube_credentials
from .store import WorkflowError, canonical, now
from .youtube_tokens import public_record, remove_token, save_token, stored_refresh_token, unsafe_location

AUTHORIZE_URL = "https://accounts.google.com/o/oauth2/v2/auth"
TOKEN_URL = "https://oauth2.googleapis.com/token"
CHANNELS_URL = "https://www.googleapis.com/youtube/v3/channels"
SCOPES = ("https://www.googleapis.com/auth/youtube.upload", "https://www.googleapis.com/auth/youtube.readonly")
SCOPE_POLICY = "youtube-only-v1"
CALLBACK_PATH = "/api/youtube/oauth/callback"
COOKIE_PATH = "/api/youtube/oauth"
BINDING_COOKIE = "hb_youtube_oauth"
STATE_SETTING = "youtube_oauth_states"
STATE_TTL = 600
MAX_PENDING = 20


class OAuthFailure(Exception):
    """콜백 실패. reason은 화면이 문구로 바꾸는 짧은 코드이고 비밀값을 담지 않는다."""

    def __init__(self, reason, channel_key=None):
        super().__init__(reason)
        self.reason = reason
        self.channel_key = channel_key


def _hash(value):
    return hashlib.sha256(value.encode("utf-8")).hexdigest()


def _youtube_key(key):
    definition = CHANNELS.get(key)
    if not definition or definition["platform"] != "youtube":
        raise WorkflowError(f"'{key}'은(는) 등록된 YouTube 채널 키가 아닙니다")
    return key


def client_configured():
    return os.environ.get("YOUTUBE_OAUTH_CLIENT_TYPE", "").strip().lower() != "installed" and all(os.environ.get(name) for name in SHARED_ENV)


def redirect_uri(origin):
    return origin + CALLBACK_PATH if origin else None


def require_ready(store, origin):
    if os.environ.get("YOUTUBE_OAUTH_CLIENT_TYPE", "").strip().lower() == "installed":
        raise WorkflowError("현재 인증 설정은 Desktop 앱(installed)입니다. 웹 화면의 YouTube 연결에는 웹 애플리케이션 클라이언트가 필요합니다. 저장된 Desktop 토큰은 업로드에 재사용할 수 있습니다")
    missing = [name for name in SHARED_ENV if not os.environ.get(name)]
    if missing:
        raise WorkflowError("·".join(missing) + "이 설정되지 않았습니다. Google Cloud의 OAuth 클라이언트(웹 애플리케이션) 값을 실행 환경 파일에 넣으세요")
    if not origin:
        raise WorkflowError("OFFICE_PUBLIC_ORIGIN(https 공개 주소)이 없습니다. Google 리디렉션 URI는 이 주소 + " + CALLBACK_PATH + "입니다")
    reason = unsafe_location(store.root)
    if reason:
        raise WorkflowError(f"OFFICE_SECRETS_FILE이 {reason}에 있습니다. 토큰 파일은 상태 폴더와 저장소 밖에 두세요")


def begin(store, channel_key, origin):
    """1회용 state를 만들고 Google 동의 화면 주소와 브라우저 묶음 값을 돌려준다."""
    _youtube_key(channel_key)
    require_ready(store, origin)
    state, binding = secrets.token_urlsafe(32), secrets.token_urlsafe(32)
    current = time.time()
    with store.connection(transaction=True) as db:
        row = db.execute("SELECT value FROM settings WHERE key=?", (STATE_SETTING,)).fetchone()
        pending = json.loads(row[0]) if row else {}
        pending = {k: v for k, v in pending.items() if isinstance(v, dict) and v.get("expires_at", 0) > current}
        pending[_hash(state)] = {"channel_key": channel_key, "binding_hash": _hash(binding), "scope_policy": SCOPE_POLICY, "created_at": now(), "expires_at": current + STATE_TTL}
        newest = sorted(pending.items(), key=lambda item: item[1]["expires_at"])[-MAX_PENDING:]
        db.execute("INSERT OR REPLACE INTO settings VALUES(?,?)", (STATE_SETTING, canonical(dict(newest))))
    params = {"client_id": os.environ["YOUTUBE_CLIENT_ID"], "redirect_uri": redirect_uri(origin), "response_type": "code",
              "scope": " ".join(SCOPES), "access_type": "offline", "prompt": "consent select_account",
              "include_granted_scopes": "false", "state": state}
    store.event("youtube_oauth_started", {"channel_key": channel_key, "actor": "local-operator"})
    return AUTHORIZE_URL + "?" + urlencode(params), binding


def _consume(store, state):
    """state를 꺼내며 지운다. 이후 단계가 실패해도 같은 state는 다시 쓸 수 없다."""
    with store.connection(transaction=True) as db:
        row = db.execute("SELECT value FROM settings WHERE key=?", (STATE_SETTING,)).fetchone()
        pending = json.loads(row[0]) if row else {}
        record = pending.pop(_hash(state), None)
        if record is not None:
            db.execute("INSERT OR REPLACE INTO settings VALUES(?,?)", (STATE_SETTING, canonical(pending)))
    return record if isinstance(record, dict) else None


def _json(response):
    body = response.json()
    if not isinstance(body, dict):
        raise ValueError("body")
    return body


def _exchange(transport, code, origin, key):
    data = {"code": code, "client_id": os.environ["YOUTUBE_CLIENT_ID"], "client_secret": os.environ["YOUTUBE_CLIENT_SECRET"],
            "redirect_uri": redirect_uri(origin), "grant_type": "authorization_code"}
    try:
        response = transport.post(TOKEN_URL, data=data, timeout=(10, 30))
        body = _json(response) if response.status_code == 200 else None
    except (requests.RequestException, ValueError, TypeError, AttributeError):
        body = None
    access = body.get("access_token") if body else None
    if not isinstance(access, str) or not access:
        raise OAuthFailure("token_exchange", key)
    granted = set(str(body.get("scope") or "").split())
    if not set(SCOPES) <= granted:
        raise OAuthFailure("scope_missing", key)
    if granted != set(SCOPES):
        # 공유 프로젝트의 토큰을 revoke하면 기존 Hermes 연결까지 끊길 수 있다. 저장만 거부한다.
        raise OAuthFailure("scope_unexpected", key)
    refresh = body.get("refresh_token")
    if not isinstance(refresh, str) or not refresh:
        raise OAuthFailure("no_refresh_token", key)
    return access, refresh, sorted(granted)


def _mine(transport, access, key):
    try:
        response = transport.get(CHANNELS_URL, headers={"Authorization": "Bearer " + access}, params={"part": "id,snippet", "mine": "true"}, timeout=(10, 30))
        items = _json(response).get("items") if response.status_code == 200 else None
    except (requests.RequestException, ValueError, TypeError, AttributeError):
        items = None
    if not isinstance(items, list):
        raise OAuthFailure("channel_lookup", key)
    if not items:
        raise OAuthFailure("no_channel", key)
    if len(items) > 1:
        raise OAuthFailure("channel_ambiguous", key)
    item = items[0] if isinstance(items[0], dict) else {}
    channel_id = item.get("id")
    if not isinstance(channel_id, str) or not YOUTUBE_CHANNEL_ID.match(channel_id):
        raise OAuthFailure("channel_lookup", key)
    snippet = item.get("snippet") if isinstance(item.get("snippet"), dict) else {}
    title = snippet.get("title") if isinstance(snippet.get("title"), str) else ""
    return channel_id, title[:100]


def finish(store, *, origin, state, code, error, binding, transport=None):
    """콜백 처리. 성공하면 채널 키를 돌려주고, 실패하면 아무것도 저장하지 않은 채 OAuthFailure를 던진다."""
    transport = transport or requests
    if not state or len(state) > 200:
        raise OAuthFailure("state")
    record = _consume(store, state)
    if not record or record.get("expires_at", 0) < time.time() or record.get("channel_key") not in CHANNELS:
        raise OAuthFailure("state")
    key = record["channel_key"]
    if not binding or not hmac.compare_digest(_hash(binding), str(record.get("binding_hash", ""))):
        raise OAuthFailure("session", key)
    if error:
        raise OAuthFailure("denied" if error == "access_denied" else "google_error", key)
    if record.get("scope_policy") != SCOPE_POLICY:
        raise OAuthFailure("scope_changed", key)
    if not code or len(code) > 2000:
        raise OAuthFailure("google_error", key)
    try:
        require_ready(store, origin)
    except WorkflowError:
        raise OAuthFailure("config", key) from None
    access, refresh, scopes = _exchange(transport, code, origin, key)
    channel_id, title = _mine(transport, access, key)
    expected = channel(store, key).get("external_account_id")
    if expected and expected != channel_id:
        raise OAuthFailure("channel_mismatch", key)
    if any(row["key"] != key and row["platform"] == "youtube" and row.get("external_account_id") == channel_id for row in registry(store)):
        raise OAuthFailure("channel_in_use", key)
    try:
        save_token(key, {"refresh_token": refresh, "channel_id": channel_id, "connected_at": now(), "scopes": scopes})
    except (OSError, WorkflowError):
        raise OAuthFailure("save_failed", key) from None
    if not expected:
        update_channel(store, key, {"external_account_id": channel_id}, actor="youtube-oauth")
    store.event("youtube_channel_connected", {"channel_key": key, "channel_id": channel_id, "channel_title": title, "scopes": scopes, "actor": "local-operator"})
    return key


def disconnect(store, channel_key):
    """비밀 파일에 저장한 토큰만 지운다. 환경 파일의 토큰은 운영자가 직접 지운다."""
    _youtube_key(channel_key)
    if not stored_refresh_token(channel_key):
        if env_refresh_token(channel_key):
            raise WorkflowError("이 채널은 실행 환경 파일의 refresh token을 쓰고 있어 화면에서 해제할 수 없습니다. 환경 파일에서 지우세요")
        raise WorkflowError("저장된 YouTube 연결이 없습니다")
    remove_token(channel_key)
    store.event("youtube_channel_disconnected", {"channel_key": channel_key, "actor": "local-operator"})
    return channel_status(store, channel_key)


def channel_status(store, key):
    record = public_record(key)
    source = "env" if env_refresh_token(key) else "file" if record else None
    return {"key": key, "label": CHANNELS[key]["label"], "source": source, "connected": youtube_credentials(key) is not None,
            "file_stored": record is not None, "channel_id": (record or {}).get("channel_id") or channel(store, key).get("external_account_id"),
            "connected_at": (record or {}).get("connected_at")}


def status(store, origin):
    """화면용 연결 상태. 값은 돌려주지 않고 설정 여부만 알린다."""
    return {"client_configured": client_configured(), "public_origin_configured": bool(origin), "redirect_uri": redirect_uri(origin),
            "secrets_location_ok": unsafe_location(store.root) is None,
            "channels": [channel_status(store, key) for key, row in CHANNELS.items() if row["platform"] == "youtube"]}
