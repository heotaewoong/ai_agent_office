"""채널 레지스트리: 오너가 준 공개 주소와 채널 키별 자격. 기본값은 발행 꺼짐이며 비밀값은 환경변수로만 전달한다.

URL 존재·소유권·발행 권한·실제 게시 성공은 각각 별도 상태다(설계서 4절 채널 원장).
운영자가 바꿀 수 있는 값(external_account_id·publication_enabled·public_url)만 설정 `channel_registry`에 저장하고,
정적 정의와 합쳐 돌려주므로 기본값은 저장소를 비워도 살아 있다. refresh token 같은 비밀은 저장소에 넣지 않는다.
refresh token은 환경변수가 먼저이고, 없으면 'YouTube 채널 연결'(OAuth)이 상태 폴더 밖 비밀 파일(youtube_tokens)에 둔 값을 쓴다.
"""
from __future__ import annotations

import os
import re

from .store import WorkflowError, now
from .youtube_tokens import stored_refresh_token

SETTING_KEY = "channel_registry"
EDITABLE_FIELDS = ("external_account_id", "publication_enabled", "public_url")
YOUTUBE_CHANNEL_ID = re.compile(r"^UC[A-Za-z0-9_-]{22}$")
SHARED_ENV = ("YOUTUBE_CLIENT_ID", "YOUTUBE_CLIENT_SECRET")
LEGACY_REFRESH_ENV = "YOUTUBE_REFRESH_TOKEN"  # youtube_main_ko 전용 하위 호환


def _channel(key, platform, label, locale, public_url=None, external_account_id=None, delivery="manual"):
    return {"key": key, "platform": platform, "label": label, "locale": locale, "public_url": public_url,
            "external_account_id": external_account_id, "delivery": delivery, "publication_enabled": False}


CHANNELS = {row["key"]: row for row in (
    _channel("youtube_main_ko", "youtube", "YouTube 메인", "ko", "https://www.youtube.com/@heo-brain", None, "youtube_api"),
    _channel("youtube_english", "youtube", "YouTube 영어", "en", "https://www.youtube.com/channel/UCc2CaOrPo-1dezowe7kklZA", "UCc2CaOrPo-1dezowe7kklZA", "youtube_api"),
    _channel("instagram_main", "instagram", "Instagram 메인", "ko", "https://www.instagram.com/titan.bears"),
    _channel("instagram_english", "instagram", "Instagram 영어", "en", "https://www.instagram.com/heobrain_english_lab"),
    _channel("threads_main", "threads", "Threads", "ko", "https://www.threads.net/@titan.bears"),
    _channel("linkedin_personal", "linkedin", "LinkedIn 개인", "ko", "https://www.linkedin.com/in/taewoong-heo-323b34366"),
    _channel("tistory_main", "tistory", "티스토리 블로그", "ko", "https://onethingflow.tistory.com"),
    _channel("naver_blog_main", "naver_blog", "네이버 블로그", "ko", "https://blog.naver.com/oneflowwhy"),
    _channel("x_main", "x", "X", "ko"),
    _channel("slack_internal", "slack", "Slack 내부 알림", "ko", None, "T0CBW3G1E77", "notify"),
    _channel("discord_contact", "discord", "Discord 연락", "ko", None, "1163846683814264882", "notify"),
    _channel("store", "store", "heobrain.kr", "ko", "https://www.heobrain.kr"),
)}


def channel_env_name(key):
    """채널 키별 refresh token 환경변수 이름(youtube_main_ko → YOUTUBE_MAIN_KO_REFRESH_TOKEN). 오류 안내에 그대로 쓴다."""
    name = key.upper()
    if name.startswith("YOUTUBE_"):
        name = name[len("YOUTUBE_"):]
    return "YOUTUBE_" + name + "_REFRESH_TOKEN"


def env_refresh_token(key):
    token = os.environ.get(channel_env_name(key))
    if not token and key == "youtube_main_ko":
        token = os.environ.get(LEGACY_REFRESH_ENV)
    return token or None


def _refresh_token(key):
    """환경변수(기존 방식)가 우선, 없으면 'YouTube 채널 연결'로 저장한 비밀 파일 값."""
    return env_refresh_token(key) or stored_refresh_token(key)


def youtube_credentials(key):
    """세 값이 모두 있을 때만 자격을 돌려준다. 저장소에는 절대 쓰지 않는다."""
    definition = CHANNELS.get(key)
    if not definition or definition["platform"] != "youtube":
        raise WorkflowError(f"'{key}'은(는) YouTube 채널이 아닙니다")
    client_id, client_secret = (os.environ.get(name) for name in SHARED_ENV)
    refresh_token = _refresh_token(key)
    if not (client_id and client_secret and refresh_token):
        return None
    return {"client_id": client_id, "client_secret": client_secret, "refresh_token": refresh_token}


def missing_credential_names(key):
    names = [name for name in SHARED_ENV if not os.environ.get(name)]
    if not _refresh_token(key):
        names.append(channel_env_name(key) + ("(또는 " + LEGACY_REFRESH_ENV + ")" if key == "youtube_main_ko" else ""))
    return names


def configured_youtube_channels():
    return [key for key, row in CHANNELS.items() if row["platform"] == "youtube" and youtube_credentials(key) is not None]


def _overrides(store):
    stored = store.setting(SETTING_KEY, {})
    return stored if isinstance(stored, dict) else {}


def _row(key, overrides):
    row = dict(CHANNELS[key])
    row.update({field: value for field, value in (overrides.get(key) or {}).items() if field in EDITABLE_FIELDS})
    row["credentials_configured"] = bool(row["platform"] == "youtube" and youtube_credentials(key) is not None)
    return row


def channel(store, key):
    if key not in CHANNELS:
        raise WorkflowError(f"등록되지 않은 채널입니다: {key}")
    return _row(key, _overrides(store))


def registry(store):
    overrides = _overrides(store)
    return [_row(key, overrides) for key in CHANNELS]


def _validate(key, field, value):
    if field == "publication_enabled":
        if not isinstance(value, bool):
            raise WorkflowError("publication_enabled 필드는 true/false여야 합니다")
        return value
    if value is None:
        return None
    if not isinstance(value, str):
        raise WorkflowError(f"{field} 필드는 문자열이어야 합니다")
    value = value.strip()
    if field == "public_url":
        if not value.startswith("https://") or len(value) > 500 or any(ch.isspace() for ch in value):
            raise WorkflowError("public_url은 https:// 주소여야 합니다")
        return value
    if CHANNELS[key]["platform"] == "youtube" and not YOUTUBE_CHANNEL_ID.match(value):
        raise WorkflowError("YouTube channel ID는 UC로 시작하는 24자 형식이어야 합니다")
    if len(value) > 200:
        raise WorkflowError("external_account_id가 너무 깁니다")
    return value


def update_channel(store, key, patch, actor):
    """운영자 설정만 바꾼다. 비밀값·플랫폼·언어는 바꿀 수 없고, 발행 여부도 사람 승인②를 대신하지 않는다."""
    if key not in CHANNELS:
        raise WorkflowError(f"등록되지 않은 채널입니다: {key}")
    if not isinstance(patch, dict) or not patch:
        raise WorkflowError("바꿀 필드가 없습니다")
    unknown = sorted(field for field in patch if field not in EDITABLE_FIELDS)
    if unknown:
        raise WorkflowError("바꿀 수 없는 필드입니다: " + ", ".join(unknown) + " (허용: " + ", ".join(EDITABLE_FIELDS) + ")")
    clean = {field: _validate(key, field, value) for field, value in patch.items()}
    overrides = _overrides(store)
    overrides[key] = {**(overrides.get(key) or {}), **clean, "updated_at": now(), "updated_by": str(actor)[:120]}
    store.set_setting(SETTING_KEY, overrides)
    store.event("channel_updated", {"key": key, "fields": clean, "actor": str(actor)[:120]})
    return _row(key, overrides)
