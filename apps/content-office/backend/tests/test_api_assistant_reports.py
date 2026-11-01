import pytest
from fastapi.testclient import TestClient

from office.api import create_app
from office.store import Store


def test_assistant_reports_empty_read_does_not_create_work(tmp_path):
    store = Store(tmp_path)
    client = TestClient(create_app(store), base_url="http://localhost:8510")
    response = client.get("/api/assistant/reports")
    assert response.status_code == 200
    assert response.json() == {"reports": []}
    assert store.jobs() == []
    with store.connection() as db:
        assert db.execute("SELECT count(*) FROM tasks").fetchone()[0] == 0
        assert db.execute(
            "SELECT count(*) FROM settings WHERE key LIKE 'assistant_report:%'"
        ).fetchone()[0] == 0


def test_assistant_reports_projects_only_safe_display_fields(tmp_path):
    from office.assistant_reports import import_report
    store = Store(tmp_path)
    job = store.create_job({"id": "article_fixture", "title": "Synthetic only"})
    data = {"work_id": "work_fixture", "request_id": "report_fixture",
            "title": "비서 팀 검토", "collaboration_kind": "dm_review",
            "participants": ["lumi", "ethan", "ada"],
            "facts": ["합성 검증 자료로 응답 형식을 검사함"],
            "limitations": ["실제 모델 실행 검증이 아님"],
            "job_id": job["id"], "source_hash": None,
            "evidence": [{"id": "evidence_not_for_display", "sha256": "a" * 64}]}
    record = import_report(store, data, verify_evidence=lambda eid, sha: eid == "evidence_not_for_display" and sha == "a" * 64)
    client = TestClient(create_app(store), base_url="http://localhost:8510")
    response = client.get("/api/assistant/reports")
    assert response.status_code == 200
    assert response.json() == {"reports": [{
        "id": data["request_id"], "work_id": data["work_id"], "title": data["title"],
        "summary": data["facts"][0], "scope": "dm_review", "reported_at": record["created_at"],
        "participants": data["participants"], "limitations": data["limitations"], "evidence_count": 1,
    }]}
    assert "evidence_not_for_display" not in response.text
    assert job["id"] not in response.text
    assert "source_hash" not in response.text
    assert store.job(job["id"]) == job


def test_duplicate_limitations_are_deduplicated_only_in_display_projection(tmp_path):
    from office.assistant_reports import get_report, import_report

    store = Store(tmp_path)
    data = {"work_id": "work_duplicates", "request_id": "report_duplicates",
            "title": "협업 검토", "collaboration_kind": "dm_review",
            "participants": ["lumi", "ada"], "facts": ["검증된 참조"],
            "limitations": ["승인 아님", "실행 미확인", "승인 아님", "실행 미확인"],
            "evidence": [{"id": "receipt", "sha256": "a" * 64}]}
    original = import_report(store, data, verify_evidence=lambda *_: True)
    with store.connection() as db:
        before = db.execute("SELECT value FROM settings WHERE key=?",
                            ("assistant_report:request:report_duplicates",)).fetchone()[0]
    client = TestClient(create_app(store), base_url="http://localhost:8510")
    response = client.get("/api/assistant/reports")
    assert response.status_code == 200
    assert response.json()["reports"][0]["limitations"] == ["승인 아님", "실행 미확인"]
    assert get_report(store, data["request_id"]) == original
    with store.connection() as db:
        assert db.execute("SELECT value FROM settings WHERE key=?",
                          ("assistant_report:request:report_duplicates",)).fetchone()[0] == before


def test_minimal_references_do_not_block_or_hide_latest_twenty_collaborations(tmp_path):
    from office.assistant_reports import import_report

    store = Store(tmp_path)
    client = TestClient(create_app(store), base_url="http://localhost:8510")
    minimal = {"work_id": "work_reference", "request_id": "reference_only",
               "facts": ["검증된 참조"], "limitations": ["사람 승인 아님"],
               "evidence": [{"id": "receipt", "sha256": "a" * 64}]}
    import_report(store, minimal, verify_evidence=lambda *_: True)
    assert client.get("/api/assistant/reports").json() == {"reports": []}
    for index in range(21):
        import_report(store, {**minimal, "request_id": f"collaboration_{index}",
                             "title": "명시적 협업", "collaboration_kind": "dm_review",
                             "participants": ["lumi", "ada"]}, verify_evidence=lambda *_: True)
    for index in range(21):
        import_report(store, {**minimal, "request_id": f"reference_{index}"},
                      verify_evidence=lambda *_: True)
    response = client.get("/api/assistant/reports")
    assert response.status_code == 200
    assert [row["id"] for row in response.json()["reports"]] == [
        f"collaboration_{index}" for index in range(20, 0, -1)]
    with store.connection() as db:
        assert db.execute("SELECT count(*) FROM settings WHERE key GLOB 'assistant_report:request:*'").fetchone()[0] == 43


@pytest.mark.parametrize("stored", ["not json", "null", "[]", "{}"])
def test_corrupt_report_is_an_error_not_empty_success(tmp_path, stored):
    store = Store(tmp_path)
    with store.connection(transaction=True) as db:
        db.execute("INSERT INTO settings VALUES(?,?)", ("assistant_report:request:broken", stored))
    client = TestClient(create_app(store), base_url="http://localhost:8510")
    response = client.get("/api/assistant/reports")
    assert response.status_code == 409
    assert "reports" not in response.json()
    assert "not json" not in response.text


def test_similarly_named_unrelated_settings_are_not_read_as_reports(tmp_path):
    store = Store(tmp_path)
    with store.connection(transaction=True) as db:
        db.execute("INSERT INTO settings VALUES(?,?)", ("assistantXreport:request:other", "not json"))
    client = TestClient(create_app(store), base_url="http://localhost:8510")
    response = client.get("/api/assistant/reports")
    assert response.status_code == 200
    assert response.json() == {"reports": []}
