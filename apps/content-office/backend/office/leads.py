"""리드마그넷 동의 장부. 이메일은 이 모듈이 만드는 `leads` 표의 `email` 열에만 저장한다.

- 장부 밖으로 나가는 모든 레코드(API 응답·이벤트·뉴스레터 회차)는 마스킹한 이메일만 담는다.
- 자료(PDF 등) 발송은 오너가 자기 메일러에서 직접 하고 `mark_sent`로 기록만 남긴다. 여기서는 아무것도 보내지 않는다.
- 같은 이메일+자료 키는 한 건이다(멱등). 철회한 뒤 다시 신청하면 새 동의로 되살린다.
- 설계서 6절 11항: 퀴즈 결과 공개를 뉴스레터 구독과 묶지 않는다. 이 장부는 퀴즈와 무관하다.
"""
from __future__ import annotations

import json
import re

from .store import WorkflowError, canonical, digest, identifier, now

SOURCES = ("homepage", "youtube", "instagram", "threads", "blog", "newsletter", "other")
EMAIL_PATTERN = re.compile(r"^[A-Za-z0-9._%+-]+@[A-Za-z0-9-]+(\.[A-Za-z0-9-]+)+$")
KEY_PATTERN = re.compile(r"^[A-Za-z0-9][A-Za-z0-9._-]{0,99}$")
MAX_EMAIL = 254
MAX_CONSENT_TEXT = 2000
MAX_CONSENT_VERSION = 50
TABLE_SQL = "CREATE TABLE IF NOT EXISTS leads(id TEXT PRIMARY KEY, email TEXT NOT NULL, magnet_key TEXT NOT NULL, data TEXT NOT NULL, created_at TEXT NOT NULL, updated_at TEXT NOT NULL, UNIQUE(email, magnet_key))"


def mask_email(email: str) -> str:
    local, _, domain = email.partition("@")
    return (local[:1] or "*") + "***@" + domain


def normalise_email(email) -> str:
    value = str(email or "").strip().lower()
    if not value or len(value) > MAX_EMAIL or not EMAIL_PATTERN.match(value):
        raise WorkflowError("올바른 이메일 주소가 필요합니다")
    return value


def _magnet_key(value) -> str:
    key = str(value or "").strip()
    if not KEY_PATTERN.match(key):
        raise WorkflowError("자료 키는 영문·숫자·점·밑줄·하이픈 100자 이내여야 합니다")
    return key


def _ensure(db):
    db.execute(TABLE_SQL)


def _record(row) -> dict:
    """장부 행을 공개 가능한 레코드로 바꾼다. 원본 이메일은 포함하지 않는다."""
    data = json.loads(row["data"])
    return {"id": row["id"], "created_at": row["created_at"], "email_masked": mask_email(row["email"]), "magnet_key": row["magnet_key"], **data}


def _write(db, row_id, data):
    db.execute("UPDATE leads SET data=?, updated_at=? WHERE id=?", (canonical(data), now(), row_id))
    return _record(db.execute("SELECT * FROM leads WHERE id=?", (row_id,)).fetchone())


def _public_data(record: dict) -> dict:
    return {key: value for key, value in record.items() if key not in ("id", "created_at", "email_masked", "magnet_key")}


def register_lead(store, *, email, magnet_key, source, consent_version, consent_text):
    """동의와 함께 신청을 기록한다. (레코드, 새로 만들었는지) 를 돌려준다."""
    address = normalise_email(email)
    key = _magnet_key(magnet_key)
    if source not in SOURCES:
        raise WorkflowError("신청 경로는 " + "·".join(SOURCES) + " 중 하나입니다")
    version = str(consent_version or "").strip()
    text = str(consent_text or "").strip()
    if not version or len(version) > MAX_CONSENT_VERSION:
        raise WorkflowError("동의 문구 버전이 필요합니다")
    if not text or len(text) > MAX_CONSENT_TEXT:
        raise WorkflowError("동의 문구 원문이 필요합니다")
    with store.connection(transaction=True) as db:
        _ensure(db)
        row = db.execute("SELECT * FROM leads WHERE email=? AND magnet_key=?", (address, key)).fetchone()
        if row:
            existing = _record(row)
            if existing["consent"]["withdrawn_at"] is None:
                return existing, False
            data = _public_data(existing)
            data["consent"] = {"version": version, "granted_at": now(), "withdrawn_at": None}
            data["consent_text"] = text
            data["source"] = source
            record = _write(db, existing["id"], data)
            store._event(db, "lead_consent_renewed", {"lead_id": record["id"], "magnet_key": key, "source": source, "consent_version": version})
            return record, False
        record_id = identifier("lead")
        data = {"source": source, "consent": {"version": version, "granted_at": now(), "withdrawn_at": None}, "consent_text": text, "delivery": {"state": "pending", "sent_at": None}}
        db.execute("INSERT INTO leads VALUES(?,?,?,?,?,?)", (record_id, address, key, canonical(data), now(), now()))
        store._event(db, "lead_registered", {"lead_id": record_id, "magnet_key": key, "source": source, "consent_version": version, "next_action": "오너가 자료를 직접 보낸 뒤 '보냄'으로 기록합니다"})
        return _record(db.execute("SELECT * FROM leads WHERE id=?", (record_id,)).fetchone()), True


def _load(db, lead_id):
    _ensure(db)
    row = db.execute("SELECT * FROM leads WHERE id=?", (lead_id,)).fetchone()
    if not row:
        raise WorkflowError("신청 기록을 찾을 수 없습니다")
    return _record(row)


def withdraw_lead(store, lead_id):
    with store.connection(transaction=True) as db:
        record = _load(db, lead_id)
        if record["consent"]["withdrawn_at"]:
            return record
        data = _public_data(record)
        data["consent"] = {**data["consent"], "withdrawn_at": now()}
        updated = _write(db, lead_id, data)
        store._event(db, "lead_withdrawn", {"lead_id": lead_id, "magnet_key": record["magnet_key"]})
        return updated


def mark_sent(store, lead_id, actor):
    """오너가 자료를 직접 보냈다고 확인한다. 여기서 메일을 보내지는 않는다."""
    if not str(actor or "").strip():
        raise WorkflowError("보냄을 확인한 담당자가 필요합니다")
    with store.connection(transaction=True) as db:
        record = _load(db, lead_id)
        if record["delivery"]["state"] == "sent_manual":
            return record
        data = _public_data(record)
        data["delivery"] = {"state": "sent_manual", "sent_at": now()}
        updated = _write(db, lead_id, data)
        store._event(db, "lead_sent_manual", {"lead_id": lead_id, "magnet_key": record["magnet_key"], "actor": actor})
        return updated


def leads(store):
    """마스킹한 레코드 목록, 최신순."""
    with store.connection() as db:
        _ensure(db)
        return [_record(row) for row in db.execute("SELECT * FROM leads ORDER BY created_at DESC, id DESC")]


def summary(store):
    records = leads(store)
    by_magnet, by_source = {}, {}
    for record in records:
        by_magnet[record["magnet_key"]] = by_magnet.get(record["magnet_key"], 0) + 1
        by_source[record["source"]] = by_source.get(record["source"], 0) + 1
    withdrawn = sum(1 for record in records if record["consent"]["withdrawn_at"])
    return {"total": len(records), "consented": len(records) - withdrawn, "withdrawn": withdrawn, "by_magnet": by_magnet, "by_source": by_source}


def consent_snapshot(store, *, db=None):
    """이메일별 수신자 수와 현재 동의 사실의 해시. 원문과 이메일은 밖으로 내보내지 않는다.

    신청 장부는 이메일+자료별로 보존한다. 같은 주소의 중복 신청도 동의 내용·철회가 바뀌면
    해시는 달라지지만 뉴스레터 수신자 수는 한 명이다. 이전 ID 전용 해시는 재작성해야 한다.
    """
    if db is None:
        with store.connection() as connection:
            return consent_snapshot(store, db=connection)
    _ensure(db)
    recipients = {}
    for row in db.execute("SELECT * FROM leads ORDER BY id"):
        data = json.loads(row["data"])
        if data["consent"]["withdrawn_at"] is None:
            recipients.setdefault(row["email"], []).append({"id": row["id"], "magnet_key": row["magnet_key"],
                                                          "consent": data["consent"], "consent_text": data["consent_text"]})
    return {"recipient_count": len(recipients), "recipients_hash": digest(recipients)}
