"""독자가 직접 쓰는 공개 리드마그넷 신청.

운영자 세션 없이 열리는 경로는 `PUBLIC_ROUTES` 두 개뿐이다(api.py 미들웨어가 이 목록만 세션·CSRF 검사에서 뺀다).
- 동의 문구와 버전은 서버 카탈로그(config/lead_magnets.json)가 정한다. 클라이언트는 본 버전과 체크 여부만 보낸다.
- 저장·마스킹·멱등은 leads.register_lead를 그대로 쓴다. 이메일은 leads 표에만 남는다.
- 응답은 이미 신청한 이메일인지, 함정 칸(hp)에 걸렸는지 드러내지 않는다(항상 같은 202 본문).
- IP별 신청 한도(시간당 5건·하루 20건)는 세션 비밀키로 만든 HMAC 해시로만 저장한다. 원본 IP는 저장하지 않는다.
- 자료 발송은 자동이 아니다. 운영자가 장부를 보고 직접 보낸 뒤 '전달 완료'로 기록한다.
"""
from __future__ import annotations

import hashlib
import hmac
import ipaddress
import json
import os
import time
from pathlib import Path
from typing import Literal
from urllib.parse import urlsplit

from fastapi import Request
from fastapi.responses import JSONResponse
from pydantic import BaseModel, ConfigDict, Field, ValidationError

from . import leads as leads_module
from .store import WorkflowError

CATALOG_PATH = Path(__file__).resolve().parent.parent / "config" / "lead_magnets.json"
PUBLIC_ROUTES = frozenset({("POST", "/api/public/leads"), ("GET", "/api/public/magnets")})
MAX_BODY = 2048
HOUR_LIMIT, DAY_LIMIT = 5, 20
HOUR, DAY = 3600, 86400
SUCCESS = {"status": "received", "message": "신청을 받았어요. 자료는 운영자가 확인 후 이메일로 보내 드려요."}
NO_STORE = {"Cache-Control": "no-store"}
TABLE_SQL = "CREATE TABLE IF NOT EXISTS public_lead_hits(ip_hash TEXT NOT NULL, at REAL NOT NULL)"
clock = time.time  # 테스트가 바꿔 끼운다


class PublicLeadInput(BaseModel):
    model_config = ConfigDict(extra="forbid")
    email: str = Field(min_length=3, max_length=254)
    magnet_key: str = Field(min_length=1, max_length=100)
    source: Literal["homepage", "youtube", "instagram", "threads", "blog", "newsletter", "other"]
    consent_version: str = Field(min_length=1, max_length=50)
    consent_checked: bool = Field(strict=True)
    hp: str = Field(default="", max_length=500)


def _origin(raw: str, name: str) -> str:
    value = raw.strip()
    value = value[:-1] if value.endswith("/") else value
    parts = urlsplit(value)
    if (parts.scheme != "https" or not parts.hostname or parts.username or parts.password or parts.path
            or parts.query or parts.fragment or "*" in value or value != f"https://{parts.netloc}"):
        raise WorkflowError(f"{name}은 https://호스트 형식의 주소여야 합니다 (경로·와일드카드·계정 정보 불가)")
    return value


def lead_allowed_origins() -> set[str]:
    """공개 신청 폼을 올려도 되는 추가 출처(예: https://www.heobrain.kr). 쉼표로 구분한다."""
    raw = os.environ.get("OFFICE_LEAD_ALLOWED_ORIGINS", "")
    return {_origin(item, "OFFICE_LEAD_ALLOWED_ORIGINS") for item in raw.split(",") if item.strip()}


def load_catalog() -> list[dict]:
    try:
        entries = json.loads(CATALOG_PATH.read_text(encoding="utf-8"))
    except (OSError, ValueError) as error:
        raise WorkflowError("리드마그넷 카탈로그를 읽지 못했습니다") from error
    if not isinstance(entries, list):
        raise WorkflowError("리드마그넷 카탈로그는 목록이어야 합니다")
    catalog = []
    for entry in entries:
        if not isinstance(entry, dict) or not leads_module.KEY_PATTERN.match(str(entry.get("key", ""))):
            raise WorkflowError("리드마그넷 카탈로그의 key 형식을 확인하세요")
        for field, limit in (("title", 200), ("description", 1000), ("consent_version", leads_module.MAX_CONSENT_VERSION), ("consent_text", leads_module.MAX_CONSENT_TEXT)):
            value = entry.get(field)
            if not isinstance(value, str) or not value.strip() or len(value) > limit:
                raise WorkflowError(f"리드마그넷 카탈로그 {entry['key']}의 {field}를 확인하세요")
        if not isinstance(entry.get("public"), bool):
            raise WorkflowError(f"리드마그넷 카탈로그 {entry['key']}의 public은 true/false여야 합니다")
        catalog.append({field: entry[field] for field in ("key", "title", "description", "consent_version", "consent_text", "public")})
    return catalog


def public_magnets() -> list[dict]:
    return [{k: v for k, v in entry.items() if k != "public"} for entry in load_catalog() if entry["public"]]


def _loopback(host: str) -> bool:
    try:
        return ipaddress.ip_address(host).is_loopback
    except ValueError:
        return False


def client_ip(request: Request) -> str:
    """같은 컴퓨터의 프록시(nginx→Next.js)를 거친 요청만 X-Forwarded-For를 믿는다.

    오른쪽부터 loopback 프록시 주소를 건너뛴 첫 주소가 실제 독자다. 왼쪽 값은 독자가 위조할 수 있다.
    """
    peer = request.client.host if request.client else ""
    if not _loopback(peer):
        return peer or "unknown"
    for hop in reversed(request.headers.get("X-Forwarded-For", "").split(",")):
        hop = hop.strip()
        if hop and not _loopback(hop):
            return hop
    return peer


def _within_limit(store, ip_hash: str) -> bool:
    """한도 안이면 이번 시도를 기록하고 True. 한도를 넘은 시도는 기록하지 않는다."""
    at = clock()
    with store.connection(transaction=True) as db:
        db.execute(TABLE_SQL)
        db.execute("DELETE FROM public_lead_hits WHERE at <= ?", (at - DAY,))
        hour = db.execute("SELECT COUNT(*) FROM public_lead_hits WHERE ip_hash=? AND at > ?", (ip_hash, at - HOUR)).fetchone()[0]
        day = db.execute("SELECT COUNT(*) FROM public_lead_hits WHERE ip_hash=?", (ip_hash,)).fetchone()[0]
        if hour >= HOUR_LIMIT or day >= DAY_LIMIT:
            return False
        db.execute("INSERT INTO public_lead_hits VALUES(?,?)", (ip_hash, at))
        return True


def _reject(status: int, detail: str):
    return JSONResponse({"detail": detail}, status_code=status, headers=NO_STORE)


async def _read_limited(request: Request) -> bytes | None:
    declared = request.headers.get("Content-Length")
    if declared and (not declared.isdigit() or int(declared) > MAX_BODY):
        return None
    chunks, size = [], 0
    async for chunk in request.stream():
        size += len(chunk)
        if size > MAX_BODY:
            return None
        chunks.append(chunk)
    return b"".join(chunks)


def register(app, store, *, secret: bytes, public_origin: str | None):
    def ip_hash(request: Request) -> str:
        return hmac.new(secret, b"public-lead-ip:" + client_ip(request).encode(), hashlib.sha256).hexdigest()

    @app.get("/api/public/magnets")
    def list_public_magnets():
        try:
            return JSONResponse({"magnets": public_magnets()}, headers=NO_STORE)
        except WorkflowError:
            return _reject(503, "지금은 자료 목록을 불러올 수 없어요. 잠시 뒤 다시 시도해 주세요.")

    @app.post("/api/public/leads")
    async def public_lead(request: Request):
        raw = await _read_limited(request)
        if raw is None:
            return _reject(413, "신청 내용이 너무 커요.")
        if not _within_limit(store, ip_hash(request)):
            return _reject(429, "신청이 너무 잦아요. 잠시 뒤 다시 시도해 주세요.")
        try:
            data = json.loads(raw)
        except ValueError:
            return _reject(422, "신청 내용을 읽지 못했어요.")
        if isinstance(data, dict) and isinstance(data.get("hp"), str) and data["hp"].strip():
            return JSONResponse(SUCCESS, status_code=202, headers=NO_STORE)  # 함정 칸: 저장하지 않고 같은 응답
        try:
            body = PublicLeadInput.model_validate(data)
        except ValidationError as error:
            fields = {str(e.get("loc", ("",))[0]) for e in error.errors()}
            if "consent_checked" in fields:
                return _reject(422, "개인정보 수집·이용 동의에 체크해 주세요.")
            if "email" in fields:
                return _reject(422, "이메일 주소를 확인해 주세요.")
            return _reject(422, "신청 내용을 확인해 주세요.")
        if body.consent_checked is not True:
            return _reject(422, "개인정보 수집·이용 동의에 체크해 주세요.")
        try:
            magnet = next((m for m in load_catalog() if m["key"] == body.magnet_key and m["public"]), None)
        except WorkflowError:
            return _reject(503, "지금은 신청을 받을 수 없어요. 잠시 뒤 다시 시도해 주세요.")
        if magnet is None:
            return _reject(422, "신청할 수 없는 자료예요.")
        if body.consent_version != magnet["consent_version"]:
            return _reject(422, "동의 문구가 바뀌었어요. 페이지를 새로고침한 뒤 다시 확인해 주세요.")
        try:
            leads_module.register_lead(store, email=body.email, magnet_key=magnet["key"], source=body.source, consent_version=magnet["consent_version"], consent_text=magnet["consent_text"])
        except WorkflowError:
            return _reject(422, "이메일 주소를 확인해 주세요.")
        store.event("lead_public_signup", {"magnet_key": magnet["key"], "source": body.source})
        return JSONResponse(SUCCESS, status_code=202, headers=NO_STORE)

    @app.get("/api/leads/public-form")
    def public_form_links():
        # 운영자 화면용: 공개 신청 링크를 만들 재료. 건수·이메일은 담지 않는다.
        return {"public_origin": public_origin, "magnets": public_magnets(), "sources": list(leads_module.SOURCES)}
