"""Read-only secretary report projection; never an executor or approval API."""
import json
import sqlite3

from fastapi import FastAPI

from .assistant_reports import _validate
from .store import WorkflowError


def _summary(record):
    fields = {"work_id", "request_id", "facts", "limitations", "evidence", "job_id",
              "source_hash", "title", "collaboration_kind", "participants"}
    data = _validate({key: value for key, value in record.items() if key in fields})
    if record.get("scope") != "verified_reference_not_approval":
        raise WorkflowError("검증 보고의 참조 유형을 확인해 주세요")
    # Valid minimal references are not explicit collaboration reports. Validate
    # first so missing/partial metadata never masks a corrupt stored record.
    if not {"title", "collaboration_kind", "participants"} <= data.keys():
        return None
    return {
        "id": data["request_id"], "work_id": data["work_id"], "title": data["title"],
        "summary": " ".join(data["facts"][:3]), "scope": data["collaboration_kind"],
        "reported_at": record["created_at"], "participants": data["participants"],
        "limitations": list(dict.fromkeys(data["limitations"])), "evidence_count": len(data["evidence"]),
    }


def register(app: FastAPI, store):
    @app.get("/api/assistant/reports")
    def list_reports():
        try:
            with store.connection() as db:
                rows = db.execute(
                    "SELECT value FROM settings WHERE key GLOB ? "
                    "ORDER BY json_extract(value, '$.created_at') DESC, key",
                    ("assistant_report:request:*",),
                ).fetchall()
            # Apply the display limit after validation and classification: newer
            # references cannot crowd out reports, nor hide corrupt records.
            summaries = [_summary(json.loads(row[0])) for row in rows]
            return {"reports": [summary for summary in summaries if summary is not None][:20]}
        except (sqlite3.DatabaseError, ValueError, TypeError, KeyError, AttributeError):
            raise WorkflowError("비서 보고 기록의 형식을 확인할 수 없습니다") from None
