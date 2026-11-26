"""운영 질문 창 바닥: 읽기 전용 연결, 임시 뷰, 검증된 질문 5개, 쓰기와 원본 표 읽기 거부."""
import hashlib
import json
import sqlite3

import pytest

from office.ops_sql import QUESTIONS, OpsQueryError, answer, run_select
from office.store import Store
from test_agent_editorial import FullProvider, evidence_job
from test_harness import verdict

EMPTY = {"quote_exact": [], "direction_cited": [], "ai_tells": [], "fact_keep": []}


def seeded(tmp_path):
    store = Store(tmp_path)
    db = store.db_path
    connection = sqlite3.connect(db)

    def job(job_id, engine, w_type, rolled, passed, issues, updated, deleted=False):
        harness = {"engine": engine, "w_type": w_type, "rolled_back": rolled, "judge_calls": 1, "refine_calls": 1}
        if issues is not None:
            harness["writer_checks"] = {"mode": "warn", "issues": issues}
        data = {"id": job_id, "title": f"원고 {job_id}", "state": "source_review", "created_at": updated,
                "source_packet": {"quality": {"deterministic_checks": {"passed": passed}, "harness": harness}}}
        if deleted:
            data["deleted_at"] = updated
        connection.execute("INSERT INTO jobs(id, data, updated_at) VALUES(?,?,?)", (job_id, json.dumps(data, ensure_ascii=False), updated))

    job("J1", "v2_harness", "W3", False, True, {**EMPTY, "quote_exact": ["q"], "direction_cited": ["a", "b"]}, "2026-11-20T10:00:00+09:00")
    job("J2", "v2_harness", "W1", True, False, {**EMPTY, "direction_cited": ["c"], "ai_tells": ["t"]}, "2026-11-21T10:00:00+09:00")
    job("J3", "legacy", None, None, True, None, "2026-11-22T10:00:00+09:00")
    job("J4", "v2_harness", "W2", False, True, {**EMPTY, "direction_cited": ["z"]}, "2026-11-23T10:00:00+09:00", deleted=True)
    job("J5", "v2_harness", "W3", False, True, {**EMPTY, "fact_keep": ["f"]}, "2026-10-30T10:00:00+09:00")
    connection.execute("INSERT INTO approvals(id, job_id, kind, version, decision, actor, data, created_at) "
                       "VALUES('a1','J1','source','v1','changes_requested','owner','{}','2026-11-20T11:00:00+09:00')")
    connection.execute("INSERT INTO approvals(id, job_id, kind, version, decision, actor, data, created_at) "
                       "VALUES('a2','J2','source','v1','approved','owner','{}','2026-11-21T11:00:00+09:00')")
    for row in (("c1", "draft", "settled", 30, 25, "2026-11-20T10:00:00+09:00"), ("c2", "judge", "reserved", 12, None, "2026-11-21T10:00:00+09:00"),
                ("c3", "draft", "settled", 30, 40, "2026-10-21T10:00:00+09:00")):
        connection.execute("INSERT INTO costs(id, kind, state, reserved_krw, actual_krw, data, created_at, updated_at) VALUES(?,?,?,?,?,'{}',?,?)",
                           (*row, row[-1]))
    connection.commit()
    connection.close()
    return db


def test_five_checked_questions_answer_from_the_views(tmp_path):
    db = seeded(tmp_path)
    assert len(QUESTIONS) == 5
    assert answer(db, "rules_this_month", month="2026-11")["rows"] == [["direction_cited", 3, 2], ["ai_tells", 1, 1], ["quote_exact", 1, 1]]
    assert answer(db, "direction_by_type")["rows"] == [["W1", 1], ["W3", 1]]
    assert answer(db, "rejected_but_rules_passed")["rows"] == [[1]]
    assert answer(db, "rollback_rate")["rows"] == [[1, 3, 33.3]]
    result = answer(db, "cost_this_month", month="2026-11")
    assert result["rows"] == [["draft", 25, 1], ["judge", 12, 1]] and result["question"].startswith("이번 달 모델 비용")
    with pytest.raises(OpsQueryError):
        answer(db, "drop_everything")


@pytest.mark.parametrize("sql", [
    "DELETE FROM ops_jobs", "UPDATE jobs SET data='x'", "INSERT INTO jobs(id, data, updated_at) VALUES('a','b','c')",
    "PRAGMA table_info(jobs)", "ATTACH DATABASE ':memory:' AS x", "SELECT * FROM jobs", "SELECT data FROM approvals",
    "SELECT 1; SELECT 2", "SELECT load_extension('x')", "SELECT * FROM sqlite_master", "SELECT * FROM settings",
    "WITH RECURSIVE c(x) AS (SELECT 1 UNION ALL SELECT x + 1 FROM c) SELECT x FROM c", "SELECT randomblob(10)",
    "SELECT * FROM ops_jobs, jobs", "WITH x AS (SELECT 1) DELETE FROM jobs",
])
def test_writes_raw_tables_and_unknown_functions_are_refused(tmp_path, sql):
    db = seeded(tmp_path)
    before = hashlib.sha256(db.read_bytes()).hexdigest()
    with pytest.raises(OpsQueryError):
        run_select(db, sql)
    assert hashlib.sha256(db.read_bytes()).hexdigest() == before


def test_rows_are_capped_and_ctes_work(tmp_path):
    db = seeded(tmp_path)
    capped = run_select(db, "SELECT job_id FROM ops_jobs ORDER BY job_id", limit=2)
    assert capped["rows"] == [["J1"], ["J2"]] and capped["truncated"] is True
    assert run_select(db, "WITH x AS (SELECT job_id FROM ops_jobs) SELECT count(*) FROM x")["rows"] == [[4]]


def test_views_read_the_real_packet_written_by_prepare_source(tmp_path, monkeypatch):
    from office.editorial import prepare_source
    monkeypatch.delenv("HEOBRAIN_EDITORIAL_ENGINE", raising=False)
    monkeypatch.delenv("HEOBRAIN_WRITER_CHECKS", raising=False)
    store = Store(tmp_path)
    store.set_setting("editorial_engine", "v2_harness")
    store.set_setting("writer_checks", "warn")
    job = evidence_job(store)

    class Routed(FullProvider):
        model = "gemini-3.8-flash"
        judge_model = "gpt-5.4-mini"

        def generate(self, role, messages, schema, options=None):
            if role == "judge":
                self.roles.append(role)
                return verdict()
            return super().generate(role, messages, schema, options)
    prepare_source(store, job["id"], provider=Routed("AI 도구 비교"))
    jobs = run_select(store.db_path, "SELECT job_id, review_engine, writer_mode FROM ops_jobs WHERE job_id = :id", {"id": job["id"]})
    assert jobs["rows"] == [[job["id"], "v2_harness", "warn"]]
    rules = run_select(store.db_path, "SELECT rule FROM ops_writer_findings WHERE job_id = :id ORDER BY rule", {"id": job["id"]})
    from office.writer_checks import RULES
    assert [row[0] for row in rules["rows"]] == sorted(RULES)
