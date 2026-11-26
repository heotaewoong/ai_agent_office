"""운영 질문 창의 읽기 전용 SQL 바닥 (2026-11-27, L6 준비).

모델이 SQL을 짜는 Text-to-SQL은 L6(12/20~)에서 붙인다. 이 모듈은 그 전에 필요한 안전장치와 검증된 질문만 만든다.
1. 운영 DB(office.sqlite3)를 읽기 전용으로 연다(URI mode=ro와 PRAGMA query_only). 운영 DB에는 아무것도 쓰지 않는다.
2. 작업 기록 JSON에서 필요한 칸만 꺼낸 임시 뷰(ops_*)를 그 연결 안에만 만든다. 연결을 닫으면 사라진다.
3. SQL 한 문장, SELECT나 WITH로 시작하는 것만 받는다. SQLite authorizer로 ops_* 뷰만 읽게 하고,
   원본 표 직접 읽기, ATTACH, PRAGMA, 쓰기, 재귀 CTE, 허용 목록 밖 함수는 거부한다. 결과는 최대 200줄, 2초가 넘으면 멈춘다.
4. 사람이 검증한 질문 5개는 SQL 틀로 답한다. 나중에 모델이 짠 SQL도 같은 run_select를 지나야 한다.
"""
from __future__ import annotations

import sqlite3
import time
from datetime import datetime, timedelta, timezone
from pathlib import Path

MAX_ROWS = 200
TIMEOUT_SECONDS = 2.0
VIEWS = {
    "ops_jobs": """SELECT id AS job_id,
        json_extract(data, '$.title') AS title,
        json_extract(data, '$.state') AS state,
        json_extract(data, '$.created_at') AS created_at,
        updated_at,
        json_extract(data, '$.source_packet.quality.harness.engine') AS review_engine,
        json_extract(data, '$.source_packet.quality.harness.w_type') AS w_type,
        json_extract(data, '$.source_packet.quality.harness.rolled_back') AS rolled_back,
        json_extract(data, '$.source_packet.quality.harness.judge_calls') AS judge_calls,
        json_extract(data, '$.source_packet.quality.harness.refine_calls') AS refine_calls,
        json_extract(data, '$.source_packet.quality.deterministic_checks.passed') AS rules_passed,
        json_extract(data, '$.source_packet.quality.harness.writer_checks.mode') AS writer_mode
        FROM jobs WHERE json_extract(data, '$.deleted_at') IS NULL""",
    "ops_writer_findings": """SELECT jobs.id AS job_id, issue.key AS rule, json_array_length(issue.value) AS problems,
        jobs.updated_at AS updated_at
        FROM jobs, json_each(jobs.data, '$.source_packet.quality.harness.writer_checks.issues') AS issue
        WHERE json_extract(jobs.data, '$.deleted_at') IS NULL""",
    "ops_approvals": "SELECT job_id, kind, decision, created_at FROM approvals",
    "ops_costs": "SELECT kind, state, reserved_krw, actual_krw, created_at FROM costs",
}
_BASE_TABLES = {"jobs", "approvals", "costs"}
_TABLE_FUNCTIONS = {"json_each", "json_tree"}
_FUNCTIONS = {"count", "sum", "total", "avg", "min", "max", "round", "abs", "coalesce", "ifnull", "nullif", "iif", "lower",
              "upper", "length", "substr", "substring", "instr", "replace", "trim", "ltrim", "rtrim", "printf", "format",
              "group_concat", "strftime", "date", "datetime", "julianday", "json_extract", "json_array_length", "like", "glob"}


class OpsQueryError(ValueError):
    """운영 질문 창이 받지 않는 SQL."""


QUESTIONS = {
    "rules_this_month": {
        "label": "이번 달 0원 검사에서 가장 많이 걸린 규칙 3개는?",
        "sql": "SELECT rule, SUM(problems) AS problems, COUNT(DISTINCT job_id) AS jobs FROM ops_writer_findings "
               "WHERE problems > 0 AND substr(updated_at, 1, 7) = :month GROUP BY rule ORDER BY problems DESC, rule LIMIT 3"},
    "direction_by_type": {
        "label": "방향 대조에 걸린 원고는 어느 글 유형이 많았어?",
        "sql": "SELECT COALESCE(j.w_type, '미지정') AS w_type, COUNT(DISTINCT f.job_id) AS jobs FROM ops_writer_findings f "
               "JOIN ops_jobs j ON j.job_id = f.job_id WHERE f.rule = 'direction_cited' AND f.problems > 0 "
               "GROUP BY 1 ORDER BY jobs DESC, w_type"},
    "rejected_but_rules_passed": {
        "label": "승인①에서 반려됐는데 0원 검사는 다 통과한 원고는 몇 건이야? (지금 원고 기준)",
        "sql": "SELECT COUNT(DISTINCT a.job_id) AS jobs FROM ops_approvals a JOIN ops_jobs j ON j.job_id = a.job_id "
               "WHERE a.kind = 'source' AND a.decision <> 'approved' AND j.rules_passed = 1"},
    "rollback_rate": {
        "label": "v2 검수에서 고친 판이 되돌려진 원고는 몇 건이고 비율은?",
        "sql": "SELECT SUM(rolled_back = 1) AS rolled_back, COUNT(*) AS v2_jobs, "
               "ROUND(100.0 * SUM(rolled_back = 1) / COUNT(*), 1) AS pct FROM ops_jobs WHERE review_engine = 'v2_harness'"},
    "cost_this_month": {
        "label": "이번 달 모델 비용은 어디에 얼마나 썼어? (정산 전은 예약액)",
        "sql": "SELECT kind, SUM(COALESCE(actual_krw, reserved_krw)) AS krw, COUNT(*) AS calls FROM ops_costs "
               "WHERE substr(created_at, 1, 7) = :month GROUP BY kind ORDER BY krw DESC, kind"},
}


def _authorizer(action, arg1, arg2, _database, source):
    if action == sqlite3.SQLITE_SELECT:
        return sqlite3.SQLITE_OK
    if action == sqlite3.SQLITE_FUNCTION:
        return sqlite3.SQLITE_OK if str(arg2 or "").lower() in _FUNCTIONS else sqlite3.SQLITE_DENY
    if action == sqlite3.SQLITE_READ:
        table = str(arg1 or "")
        if table in VIEWS or table in _TABLE_FUNCTIONS or (table in _BASE_TABLES and source in VIEWS):
            return sqlite3.SQLITE_OK
    return sqlite3.SQLITE_DENY


def _connect(db_path):
    path = Path(db_path).resolve()
    if not path.is_file():
        raise OpsQueryError("운영 DB 파일이 없어요")
    connection = sqlite3.connect(path.as_uri() + "?mode=ro", uri=True, timeout=5)
    for name, body in VIEWS.items():  # 임시 뷰는 이 연결의 temp 영역에만 생기고 운영 DB 파일에는 쓰지 않는다
        connection.execute(f"CREATE TEMP VIEW {name} AS {body}")
    connection.execute("PRAGMA query_only = ON")
    connection.set_authorizer(_authorizer)
    return connection


def _single_select(sql):
    text = (sql or "").strip()
    if text.endswith(";"):
        text = text[:-1].rstrip()
    if not text or ";" in text:
        raise OpsQueryError("SQL은 한 문장만 받아요")
    head = text.split(None, 1)[0].lower()
    if head not in ("select", "with"):
        raise OpsQueryError("SELECT나 WITH로 시작하는 읽기 질문만 받아요")
    return text


def run_select(db_path, sql, params=None, *, limit=MAX_ROWS):
    """읽기 전용으로 SQL 한 문장을 돌린다. 막힌 것은 OpsQueryError로 알린다."""
    text = _single_select(sql)
    limit = max(1, min(int(limit), MAX_ROWS))
    connection = _connect(db_path)
    deadline = time.monotonic() + TIMEOUT_SECONDS
    connection.set_progress_handler(lambda: 1 if time.monotonic() > deadline else 0, 10_000)
    try:
        cursor = connection.execute(f"SELECT * FROM ({text}) LIMIT {limit + 1}", params or {})
        columns = [item[0] for item in cursor.description or ()]
        rows = [list(row) for row in cursor.fetchall()]
    except sqlite3.DatabaseError as error:
        message = str(error)
        if "interrupted" in message:
            raise OpsQueryError("2초 안에 끝나지 않아 멈췄어요. 범위를 좁혀 주세요") from error
        if "not authorized" in message or "prohibited" in message or "readonly" in message:
            raise OpsQueryError("ops_* 뷰를 읽는 SELECT만 받아요") from error
        raise OpsQueryError(f"SQL을 실행하지 못했어요: {message}") from error
    finally:
        connection.close()
    return {"sql": text, "columns": columns, "rows": rows[:limit], "truncated": len(rows) > limit}


def answer(db_path, question_id, *, month=None):
    """사람이 검증한 질문에 SQL 틀로 답한다. month는 'YYYY-MM'(기본: 한국 시각 이번 달)."""
    if question_id not in QUESTIONS:
        raise OpsQueryError("모르는 질문이에요")
    question = QUESTIONS[question_id]
    month = month or datetime.now(timezone(timedelta(hours=9))).strftime("%Y-%m")
    params = {"month": month} if ":month" in question["sql"] else {}
    return {"question": question["label"], **run_select(db_path, question["sql"], params)}
