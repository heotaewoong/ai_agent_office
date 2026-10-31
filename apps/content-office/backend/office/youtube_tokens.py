"""YouTube 채널 연결로 받은 refresh token 파일. 저장소·상태 DB·화면·이벤트에는 절대 넣지 않는다.

경로: OFFICE_SECRETS_FILE, 기본 ~/.config/heobrain-content-office/youtube-tokens.json (상태 폴더 밖).
형식: {channel_key: {refresh_token, channel_id, connected_at, scopes}}. 파일은 0600, 폴더는 0700으로
만든다(Windows는 POSIX 권한이 없어 사용자 프로필 폴더의 기본 ACL에 맡긴다). 쓰기는 같은 폴더의 임시
파일 → os.replace로 원자적으로 바꾼다. 이 모듈은 channels.py가 가져다 쓰므로 channels를 import하지 않는다.
"""
from __future__ import annotations

import json
import os
import secrets
from contextlib import contextmanager
from pathlib import Path

from .runtime import AlreadyRunning, ProcessLock
from .store import WorkflowError

DEFAULT_PATH = Path("~/.config/heobrain-content-office/youtube-tokens.json")
PUBLIC_FIELDS = ("channel_id", "connected_at", "scopes")


def _code_root():
    """git 저장소 루트(있으면), 없으면 배포된 backend 폴더. 비밀 파일은 이 안에 둘 수 없다."""
    here = Path(__file__).resolve()
    for parent in here.parents:
        if (parent / ".git").exists():
            return parent
    return here.parents[1]


def secrets_path():
    raw = os.environ.get("OFFICE_SECRETS_FILE", "").strip()
    return (Path(raw) if raw else DEFAULT_PATH).expanduser().resolve()


def unsafe_location(state_root):
    """비밀 파일이 상태 폴더나 저장소 안에 있으면 그 이유를, 안전하면 None을 돌려준다."""
    path = secrets_path()
    if path.is_relative_to(Path(state_root).resolve()):
        return "상태 폴더 안"
    if path.is_relative_to(_code_root()):
        return "코드 저장소 안"
    return None


def _read():
    from .owner_auth import enabled
    if enabled():
        return {}
    try:
        data = json.loads(secrets_path().read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return {}
    return data if isinstance(data, dict) else {}


def _write(data):
    from .owner_auth import require_server_auth_allowed
    require_server_auth_allowed()
    path = secrets_path()
    path.parent.mkdir(mode=0o700, parents=True, exist_ok=True)
    temp = path.with_name(f".{path.name}.{secrets.token_hex(6)}.tmp")
    fd = os.open(temp, os.O_WRONLY | os.O_CREAT | os.O_EXCL, 0o600)
    try:
        with os.fdopen(fd, "w", encoding="utf-8") as handle:
            json.dump(data, handle, ensure_ascii=False, indent=2, sort_keys=True)
            handle.flush()
            os.fsync(handle.fileno())
        os.replace(temp, path)
    finally:
        if temp.exists():
            temp.unlink()
    try:
        os.chmod(path, 0o600)
    except OSError:
        pass


def stored_refresh_token(key):
    record = _read().get(key)
    token = record.get("refresh_token") if isinstance(record, dict) else None
    return token if isinstance(token, str) and token else None


def public_record(key):
    """토큰을 뺀 연결 정보(채널 ID·연결 시각·권한 범위). 없으면 None."""
    record = _read().get(key)
    if not isinstance(record, dict) or not stored_refresh_token(key):
        return None
    return {field: record.get(field) for field in PUBLIC_FIELDS}


@contextmanager
def _locked():
    path = secrets_path()
    path.parent.mkdir(mode=0o700, parents=True, exist_ok=True)
    try:
        with ProcessLock(path.with_name(path.name + ".lock")):
            yield
    except AlreadyRunning:
        raise WorkflowError("다른 YouTube 연결 저장이 진행 중입니다. 잠시 뒤 다시 시도하세요") from None


def save_token(key, record):
    with _locked():
        data = _read()
        data[key] = {"refresh_token": record["refresh_token"], **{field: record.get(field) for field in PUBLIC_FIELDS}}
        _write(data)


def remove_token(key):
    with _locked():
        data = _read()
        if key not in data:
            return False
        del data[key]
        _write(data)
        return True
