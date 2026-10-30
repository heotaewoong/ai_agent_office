"""뉴스레터 회차(③). 출고 승인②를 받은 원고 한 편에서 회차 마크다운을 만들고, 사람이 승인③한 뒤 오너가 자기 메일러로 보낸다.

- 회차는 `newsletter_issues` 표에 산다. 수신자는 이메일별 건수와 동의 사실의 해시만 남기고 이메일은 절대 넣지 않는다.
- `hash`는 내용(제목·마크다운·원고/출고 버전)의 해시다. 승인③은 내용과 동의 스냅샷을 묶은 `review_hash`에도 붙는다.
  현재 원고·오퍼·출고·파일·동의가 바뀌면 검토·내보내기·발송 기록을 막고 rebuild 뒤 다시 승인③을 받는다.
- 승인③은 오직 사람(actor)이 만든다. 승인·거절·발송 기록 어디에서도 메일을 보내지 않는다.
- `review_hash`는 회차 ID·내용 해시·수신자 스냅샷을 묶은 검토용 값이다. 읽을 때 계산하며, 옛 화면의 판정을 막는다.
"""
from __future__ import annotations

import hashlib
import json
import re

from .briefs import brief_for_job
from .exports import blog_markdown
from .leads import consent_snapshot
from .offers import require_campaign_packet, require_offer_ready, source_version
from .store import WorkflowError, canonical, digest, identifier, now

ISSUE_KEY_PATTERN = re.compile(r"^[A-Za-z0-9][A-Za-z0-9._-]{0,63}$")
MAX_SUBJECT = 150
UNSUBSCRIBE_LINE = "이 메일은 자료 신청 때 수신에 동의한 분께만 보내요. 더 받고 싶지 않으면 [수신거부 링크]를 눌러 주세요."
TABLE_SQL = "CREATE TABLE IF NOT EXISTS newsletter_issues(id TEXT PRIMARY KEY, issue_key TEXT UNIQUE NOT NULL, job_id TEXT NOT NULL, state TEXT NOT NULL, data TEXT NOT NULL, created_at TEXT NOT NULL, updated_at TEXT NOT NULL)"


def _ensure(db):
    db.execute(TABLE_SQL)


def _released_job(db, store, job_id):
    """youtube_delivery._released_video와 같은 출고 승인② 검사. 영상 파일 조건만 뺐다."""
    job = store._job(db, job_id)
    require_offer_ready(job.get("offer"))
    require_campaign_packet(job.get("source_packet"), job.get("offer"))
    manifest = job.get("manifest") or {}
    release = job.get("release_approval") or {}
    source = job.get("source_approval") or {}
    if (source_version(job.get("source_packet"), job.get("offer")) != job.get("source_hash")
            or source.get("decision") != "approved" or source.get("version") != job.get("source_hash")
            or source.get("selections") != job.get("selections")
            or release.get("decision") != "approved" or not release.get("outputs")
            or release.get("version") != manifest.get("hash") or manifest.get("source_hash") != job.get("source_hash")):
        raise WorkflowError("현재 제작물의 출고 승인②가 필요합니다. 뉴스레터 회차는 만들지 않았습니다")
    root = store.artifacts.resolve()
    for record in manifest.get("files", []):
        if not set(record.get("outputs", [])).intersection(release["outputs"]):
            continue
        try:
            path = (root / record["path"]).resolve()
            valid = path.is_relative_to(root) and path.is_file() and hashlib.sha256(path.read_bytes()).hexdigest() == record["sha256"]
        except (KeyError, OSError, TypeError, ValueError):
            valid = False
        if not valid:
            raise WorkflowError("출고 제작물이 변경되었거나 파일 검증에 실패했습니다. 다시 제작하고 출고 승인②를 받으세요")
    return job, release


def _offer_footer(offer):
    if not offer:
        return ""
    from .exports import offer_line
    lines = ["## 안내", "", offer_line(offer)]
    return "\n".join(lines) + "\n\n"


def build_markdown(job, subject):
    packet = job["source_packet"]
    brief = brief_for_job(job)
    text = f"# {subject}\n\n" + blog_markdown(packet).strip() + "\n\n"
    text += "## 오늘 할 일\n\n" + brief["outcome"].strip() + "\n\n**" + brief["cta"].strip() + "**\n\n"
    text += _offer_footer(job.get("offer"))
    return text + "---\n\n" + UNSUBSCRIBE_LINE + "\n"


def _content(job, release, subject):
    markdown = build_markdown(job, subject)
    content = {"subject": subject, "markdown": markdown, "source_hash": job["source_hash"], "release_version": release["version"], "release_outputs": sorted(release["outputs"])}
    return {**content, "hash": digest(content)}


def _issue(row):
    issue = {"id": row["id"], "issue_key": row["issue_key"], "job_id": row["job_id"], "state": row["state"], **json.loads(row["data"]), "created_at": row["created_at"], "updated_at": row["updated_at"]}
    issue["review_hash"] = digest({"issue_id": issue["id"], "content_hash": issue["hash"], "recipients_hash": issue["recipients_hash"]})
    return issue


def _load(db, issue_id):
    _ensure(db)
    row = db.execute("SELECT * FROM newsletter_issues WHERE id=?", (issue_id,)).fetchone()
    if not row:
        raise WorkflowError("뉴스레터 회차를 찾을 수 없습니다")
    return _issue(row)


def _require_current_issue(db, store, current):
    job, release = _released_job(db, store, current["job_id"])
    if any(current.get(key) != value for key, value in _content(job, release, current["subject"]).items()):
        raise WorkflowError("회차의 원고·오퍼 또는 출고 판본이 변경되었습니다. 다시 만든(rebuild) 뒤 승인③을 받으세요")
    if any(current.get(key) != value for key, value in consent_snapshot(store, db=db).items()):
        raise WorkflowError("수신자 또는 동의 내용이 변경되었습니다. 다시 만든(rebuild) 뒤 승인③을 받으세요")


def _require_issue_approval(current):
    approval = current.get("approval") or {}
    if (current["state"] != "approved" or approval.get("decision") != "approved"
            or approval.get("version") != current["hash"] or approval.get("review_hash") != current["review_hash"]):
        raise WorkflowError("현재 회차 내용과 수신자에 대한 승인③이 필요합니다. 필요하면 다시 만든(rebuild) 뒤 검토하세요")


def _write(db, issue):
    data = {key: value for key, value in issue.items() if key not in ("id", "issue_key", "job_id", "state", "created_at", "updated_at", "review_hash")}
    db.execute("UPDATE newsletter_issues SET state=?, data=?, updated_at=? WHERE id=?", (issue["state"], canonical(data), now(), issue["id"]))
    return _load(db, issue["id"])


def _subject(job, subject):
    value = str(subject or "").strip() or str(job.get("source_packet", {}).get("title") or job.get("title") or "").strip()
    if not value or len(value) > MAX_SUBJECT:
        raise WorkflowError(f"회차 제목은 1~{MAX_SUBJECT}자여야 합니다")
    return value


def build_issue(store, job_id, *, issue_key, subject, actor, auto=False):
    key = str(issue_key or "").strip()
    if not ISSUE_KEY_PATTERN.match(key):
        raise WorkflowError("회차 키는 영문·숫자·점·밑줄·하이픈 64자 이내여야 합니다 (예: 2026-11-w1)")
    with store.connection(transaction=True) as db:
        _ensure(db)
        if db.execute("SELECT 1 FROM newsletter_issues WHERE issue_key=?", (key,)).fetchone():
            raise WorkflowError(f"회차 키 '{key}'는 이미 있습니다. 다른 회차 키를 쓰거나 기존 회차를 다시 만드세요")
        job, release = _released_job(db, store, job_id)
        recipients = consent_snapshot(store, db=db)
        content = _content(job, release, _subject(job, subject))
        issue_id = identifier("issue")
        data = {**content, **recipients, "built_at": now(), "approval": None, "sent_at": None}
        db.execute("INSERT INTO newsletter_issues VALUES(?,?,?,?,?,?,?)", (issue_id, key, job_id, "draft", canonical(data), now(), now()))
        store._event(db, "newsletter_built", {"issue_id": issue_id, "issue_key": key, "hash": content["hash"], "recipient_count": recipients["recipient_count"], "actor": actor, "auto": bool(auto), "next_action": "회차를 읽고 승인③한 뒤 오너가 메일러에서 직접 보냅니다"}, job_id)
        return _load(db, issue_id)


def auto_build_issue(store, job_id, *, actor):
    """출고 승인②가 기록된 직후 파이프라인이 부른다. 초안(draft)만 만들며 승인③은 만들지 않는다.

    작업에는 포맷 선택(formats.plan_formats)이 저장되지 않으므로 출고된 모든 작업을 대상으로 본다.
    같은 출고 버전의 미발송 회차가 이미 있으면 다시 만들지 않는다. 실패는 승인②를 막지 않고 이벤트로만 남긴다.
    """
    try:
        job = store.job(job_id)
        release_version = (job.get("release_approval") or {}).get("version")
        existing = [i for i in issues(store) if i["job_id"] == job_id]
        if any(i["release_version"] == release_version and i["state"] != "sent_manual" for i in existing):
            return None
        used = {i["issue_key"] for i in issues(store)}
        n = len(existing) + 1
        while f"{job_id}-v{n}" in used:
            n += 1
        return build_issue(store, job_id, issue_key=f"{job_id}-v{n}", subject=None, actor=actor, auto=True)
    except WorkflowError as error:
        store.event("newsletter_auto_build_skipped", {"reason": str(error), "actor": actor}, job_id)
        return None


def issues(store):
    with store.connection() as db:
        _ensure(db)
        return [_issue(row) for row in db.execute("SELECT * FROM newsletter_issues ORDER BY created_at DESC, id DESC")]


def issue(store, issue_id):
    with store.connection() as db:
        return _load(db, issue_id)


def export_issue(store, issue_id):
    """현재 출고·동의에 연결된 검토 원문만 내보낸다. 초안은 검토용으로 내려받을 수 있다."""
    with store.connection(transaction=True) as db:
        current = _load(db, issue_id)
        _require_current_issue(db, store, current)
        if current["state"] == "rejected":
            raise WorkflowError("거절한 회차는 내보낼 수 없습니다. 다시 검토하세요")
        if current["state"] == "approved":
            _require_issue_approval(current)
        return current


def review_issue(store, issue_id, decision, *, expected_hash, actor, note=None):
    """승인③. 사람 검토자가 기록하며 아무것도 보내지 않는다."""
    if decision not in ("approve", "reject") or not str(actor or "").strip():
        raise WorkflowError("유효한 회차 판정(approve·reject)과 검토자가 필요합니다")
    note_text = str(note).strip()[:500] if note else None
    with store.connection(transaction=True) as db:
        current = _load(db, issue_id)
        if expected_hash != current["review_hash"]:
            raise WorkflowError("회차 내용 또는 수신자 묶음이 변경되었습니다. 다시 불러와 확인한 뒤 검토하세요")
        if current["state"] == "approved":
            raise WorkflowError("이미 승인③한 회차입니다. 내용을 바꾸려면 다시 만든(rebuild) 뒤 검토하세요")
        if current["state"] == "sent_manual":
            raise WorkflowError("이미 발송 기록이 남은 회차는 다시 검토하지 않습니다")
        _require_current_issue(db, store, current)
        state = "approved" if decision == "approve" else "rejected"
        record = {"stage": "③", "decision": state, "actor": actor, "at": now(), "note": note_text, "version": current["hash"], "review_hash": current["review_hash"]}
        db.execute("INSERT INTO approvals VALUES(?,?,?,?,?,?,?,?)", (identifier("approval"), current["job_id"], "newsletter", current["hash"], state, actor, canonical({**record, "issue_id": issue_id}), now()))
        current.update(state=state, approval=record)
        store._event(db, "newsletter_reviewed", {"issue_id": issue_id, "issue_key": current["issue_key"], "decision": state, "actor": actor, "note": note_text, "hash": current["hash"], "sent": False}, current["job_id"])
        return _write(db, current)


def rebuild_issue(store, issue_id, *, actor):
    """원고·동의 스냅샷을 다시 계산한다. 내용·동의 또는 승인 결속이 달라지면 승인③을 지운다."""
    with store.connection(transaction=True) as db:
        current = _load(db, issue_id)
        if current["state"] == "sent_manual":
            raise WorkflowError("발송 기록이 남은 회차는 다시 만들지 않습니다. 새 회차 키로 만드세요")
        job, release = _released_job(db, store, current["job_id"])
        recipients = consent_snapshot(store, db=db)
        content = _content(job, release, current["subject"])
        changed = content["hash"] != current["hash"]
        recipients_changed = any(current.get(key) != value for key, value in recipients.items())
        approval = current.get("approval") or {}
        approval_stale = bool(approval) and (approval.get("review_hash") != current["review_hash"]
                                             or approval.get("version") != current["hash"] or approval.get("decision") != current["state"])
        current.update(**content, **recipients, built_at=now())
        if changed or recipients_changed or approval_stale:
            current.update(state="draft", approval=None)
        store._event(db, "newsletter_rebuilt", {"issue_id": issue_id, "issue_key": current["issue_key"], "content_changed": changed, "recipients_changed": recipients_changed, "recipient_count": recipients["recipient_count"], "actor": actor}, current["job_id"])
        return _write(db, current)


def mark_sent(store, issue_id, *, actor):
    """현재 원고·출고·동의와 승인③을 확인하고 오너의 수동 발송 기록만 남긴다."""
    if not str(actor or "").strip():
        raise WorkflowError("발송을 확인한 담당자가 필요합니다")
    with store.connection(transaction=True) as db:
        current = _load(db, issue_id)
        _require_issue_approval(current)
        _require_current_issue(db, store, current)
        current.update(state="sent_manual", sent_at=now())
        store._event(db, "newsletter_sent_manual", {"issue_id": issue_id, "issue_key": current["issue_key"], "recipient_count": current["recipient_count"], "recipients_hash": current["recipients_hash"], "hash": current["hash"], "actor": actor}, current["job_id"])
        return _write(db, current)
