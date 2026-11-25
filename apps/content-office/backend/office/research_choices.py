"""기획마다 사람이 고른 글 유형과 분야, 그리고 기획 카드에서 외부 조사 버튼을 누른 기록.

- 고른 값은 자료 창고 DB의 research_choices 표에 기획 ID마다 한 줄만 둔다. 기획 카드와 편집 해시, 승인은 바꾸지 않는다.
- 누른 기록에는 기획 ID, 그때 보여 준 추천(필수, 권장, 안 함), 고른 값인지 추측값인지, 찾은 후보 수만 남긴다. 제목과 검색어는 남기지 않는다.
- 추천과 실제로 누른 것이 얼마나 맞는지 나중에 보려고 모은다. 승인⓪①②③을 만들거나 대신하지 않는다.
"""
from __future__ import annotations

import json
import logging
import re
import sqlite3
from contextlib import closing
from datetime import datetime, timedelta, timezone

from .external_research import KINDS, VERDICTS
from .source_library import AREAS, _connect, _now, library_path
from .store import WorkflowError

MAX_CHOICES = 3000
MAX_CLICKS = 5000
_NEEDS = ("required", "recommended", "none")
_IDEA_ID = re.compile(r"[A-Za-z0-9_.:-]{1,160}")
_SCHEMA = """
CREATE TABLE IF NOT EXISTS research_choices(
  idea_id TEXT PRIMARY KEY, kind TEXT NOT NULL, area TEXT NOT NULL, updated_at TEXT NOT NULL);
CREATE TABLE IF NOT EXISTS research_clicks(
  id INTEGER PRIMARY KEY AUTOINCREMENT, idea_id TEXT NOT NULL, at TEXT NOT NULL, kind TEXT NOT NULL, area TEXT NOT NULL,
  kind_guessed INTEGER NOT NULL, area_guessed INTEGER NOT NULL, need TEXT NOT NULL, forced INTEGER NOT NULL,
  searched INTEGER NOT NULL, candidates INTEGER NOT NULL);
CREATE TABLE IF NOT EXISTS research_auto(
  idea_id TEXT PRIMARY KEY, key TEXT NOT NULL, at TEXT NOT NULL, verdict TEXT, top_score REAL,
  tavily INTEGER NOT NULL DEFAULT 0, tavily_day TEXT, result TEXT NOT NULL);
CREATE TABLE IF NOT EXISTS research_labels(
  idea_id TEXT PRIMARY KEY, label TEXT NOT NULL, suggested TEXT, verdict TEXT, at TEXT NOT NULL);
"""
# 예전 판에서 만든 research_clicks 표에 나중에 더한 칸.
_ADDED_CLICK_COLUMNS = (("verdict", "TEXT"), ("auto", "INTEGER NOT NULL DEFAULT 0"), ("top_score", "REAL"))
MAX_AUTO = 500
MAX_AUTO_RESULT_BYTES = 200_000
LABELS = ("correct", "wrong", "practice")
_KST = timezone(timedelta(hours=9))
_log = logging.getLogger(__name__)


def _idea_id(value) -> str:
    if not isinstance(value, str) or not _IDEA_ID.fullmatch(value):
        raise WorkflowError("기획을 찾을 수 없습니다. 목록을 새로 고쳐 주세요.")
    return value


def _ready(db) -> None:
    db.executescript(_SCHEMA)
    have = {row[1] for row in db.execute("PRAGMA table_info(research_clicks)")}
    for name, kind in _ADDED_CLICK_COLUMNS:
        if name not in have:
            db.execute(f"ALTER TABLE research_clicks ADD COLUMN {name} {kind}")


def _today() -> str:
    return datetime.now(_KST).strftime("%Y-%m-%d")


def _read_only(root):
    # 읽기만 하는 곳(기획 목록, 근거 찾기)에서는 표를 만들지 않는다. 아직 표가 없으면 sqlite3.Error로 빈 값이 된다.
    db = sqlite3.connect(f"{library_path(root).as_uri()}?mode=ro", uri=True, timeout=2)
    db.row_factory = sqlite3.Row
    return db


def save_choice(root, idea_id: str, *, kind: str, area: str) -> dict:
    """사람이 고른 글 유형과 분야를 저장한다. 같은 기획에 다시 고르면 덮어쓴다."""
    _idea_id(idea_id)
    if kind not in KINDS:
        raise WorkflowError("글 유형을 골라 주세요.")
    if area not in AREAS:
        raise WorkflowError("분야를 골라 주세요.")
    updated = _now()
    with closing(_connect(root)) as db, db:
        _ready(db)
        db.execute("INSERT INTO research_choices VALUES (?,?,?,?) ON CONFLICT(idea_id) DO UPDATE SET "
                   "kind=excluded.kind, area=excluded.area, updated_at=excluded.updated_at", (idea_id, kind, area, updated))
        db.execute("DELETE FROM research_choices WHERE idea_id NOT IN "
                   "(SELECT idea_id FROM research_choices ORDER BY updated_at DESC LIMIT ?)", (MAX_CHOICES,))
    return {"idea_id": idea_id, "kind": kind, "kind_label": KINDS[kind], "area": area, "area_label": AREAS[area], "updated_at": updated}


def load_choices(root) -> dict[str, dict]:
    """기획 ID마다 고른 {kind, area}. 아직 고른 적이 없거나 DB를 읽지 못하면 빈 값이고, 화면은 추측값을 보여 준다."""
    try:
        with closing(_read_only(root)) as db:
            rows = db.execute("SELECT idea_id, kind, area FROM research_choices").fetchall()
    except sqlite3.Error:
        return {}
    return {row["idea_id"]: {"kind": row["kind"], "area": row["area"]} for row in rows
            if row["kind"] in KINDS and row["area"] in AREAS}


def load_choice(root, idea_id: str) -> dict | None:
    try:
        with closing(_read_only(root)) as db:
            row = db.execute("SELECT kind, area FROM research_choices WHERE idea_id=?", (idea_id,)).fetchone()
    except sqlite3.Error:
        return None
    return {"kind": row["kind"], "area": row["area"]} if row and row["kind"] in KINDS and row["area"] in AREAS else None


def log_click(root, idea_id: str, plan: dict, *, forced: bool, searched: bool, candidates: int,
              verdict: dict | None = None, auto: bool = False) -> bool:
    """기획 카드의 외부 조사 한 줄(사람이 눌렀든 자동이든). 기록하지 못해도 조사 결과는 그대로 돌려준다."""
    try:
        verdict = verdict if isinstance(verdict, dict) and verdict.get("verdict") in VERDICTS else {}
        top = verdict.get("top_score")
        row = (_idea_id(idea_id), _now(), str(plan.get("kind") or ""), str(plan.get("area") or ""),
               int(plan.get("kind_guessed") is not False), int(plan.get("area_guessed") is not False),
               str(plan.get("need") or ""), int(bool(forced)), int(bool(searched)), max(0, int(candidates)),
               verdict.get("verdict"), int(bool(auto)), float(top) if isinstance(top, (int, float)) else None)
        with closing(_connect(root)) as db, db:
            _ready(db)
            db.execute("INSERT INTO research_clicks(idea_id,at,kind,area,kind_guessed,area_guessed,need,forced,searched,candidates,"
                       "verdict,auto,top_score) VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?)", row)
            db.execute("DELETE FROM research_clicks WHERE id <= (SELECT MAX(id) FROM research_clicks) - ?", (MAX_CLICKS,))
    except (WorkflowError, sqlite3.Error, TypeError, ValueError) as error:
        _log.warning("외부 조사 클릭을 기록하지 못했습니다: %s", error)
        return False
    return True


def click_stats(root) -> dict:
    """추천별로 몇 번 눌렀는지 센다. 추천이 '안 함'인데 누른 것은 사람이 그래도 찾아본 경우다."""
    stats = {"clicks": 0, "by_need": dict.fromkeys(_NEEDS, 0), "chosen_kind": 0, "forced": 0, "found_any": 0}
    try:
        with closing(_read_only(root)) as db:
            rows = db.execute("SELECT need, COUNT(*) AS clicks, SUM(kind_guessed=0) AS chosen, SUM(forced) AS forced, "
                              "SUM(candidates>0) AS found FROM research_clicks GROUP BY need").fetchall()
    except sqlite3.Error:
        return stats
    for row in rows:
        if row["need"] in stats["by_need"]:
            stats["by_need"][row["need"]] += row["clicks"]
        stats["clicks"] += row["clicks"]
        stats["chosen_kind"] += row["chosen"] or 0
        stats["forced"] += row["forced"] or 0
        stats["found_any"] += row["found"] or 0
    return stats


def _one(db, sql: str, arguments=()):
    try:
        return db.execute(sql, arguments).fetchone()
    except sqlite3.Error:  # 아직 표가 없는 창고
        return None


def load_auto(root, idea_id: str) -> dict | None:
    """기획마다 한 줄 저장해 둔 자동 조사 결과. 같은 기획을 다시 열면 이것을 돌려주고 밖으로 다시 찾지 않는다."""
    try:
        with closing(_read_only(root)) as db:
            row = _one(db, "SELECT key, at, verdict, top_score, tavily, tavily_day, result FROM research_auto WHERE idea_id=?", (idea_id,))
    except sqlite3.Error:
        return None
    if not row:
        return None
    try:
        result = json.loads(row["result"])
    except ValueError:
        result = None
    return {"key": row["key"], "at": row["at"], "verdict": row["verdict"], "top_score": row["top_score"],
            "tavily": bool(row["tavily"]), "tavily_day": row["tavily_day"], "result": result if isinstance(result, dict) else None}


def auto_tavily_today(root) -> int:
    """오늘(한국 시간) 자동으로 Tavily를 부른 기획 수."""
    try:
        with closing(_read_only(root)) as db:
            row = _one(db, "SELECT COUNT(*) FROM research_auto WHERE tavily_day=?", (_today(),))
    except sqlite3.Error:
        return 0
    return int(row[0]) if row else 0


def save_auto(root, idea_id: str, key: str, result: dict, *, tavily: bool) -> bool:
    try:
        _idea_id(idea_id)
        text = json.dumps(result, ensure_ascii=False, separators=(",", ":"))
        if len(text.encode("utf-8")) > MAX_AUTO_RESULT_BYTES:
            return False
        verdict = result.get("verdict") if isinstance(result.get("verdict"), dict) else {}
        with closing(_connect(root)) as db, db:
            _ready(db)
            before = db.execute("SELECT tavily, tavily_day FROM research_auto WHERE idea_id=?", (idea_id,)).fetchone()
            day = _today() if tavily else (before["tavily_day"] if before else None)
            db.execute("INSERT INTO research_auto(idea_id,key,at,verdict,top_score,tavily,tavily_day,result) VALUES (?,?,?,?,?,?,?,?) "
                       "ON CONFLICT(idea_id) DO UPDATE SET key=excluded.key, at=excluded.at, verdict=excluded.verdict, "
                       "top_score=excluded.top_score, tavily=excluded.tavily, tavily_day=excluded.tavily_day, result=excluded.result",
                       (idea_id, key, _now(), verdict.get("verdict"), verdict.get("top_score"),
                        int(bool(tavily or (before and before["tavily"]))), day, text))
            db.execute("DELETE FROM research_auto WHERE idea_id NOT IN (SELECT idea_id FROM research_auto ORDER BY at DESC LIMIT ?)", (MAX_AUTO,))
    except (WorkflowError, sqlite3.Error, TypeError, ValueError) as error:
        _log.warning("자동 조사 결과를 저장하지 못했습니다: %s", error)
        return False
    return True


def suggest_label(verdict: str | None, saved_external: int) -> str | None:
    """화면이 미리 골라 둘 값. '맞음' 판정인데 바깥 자료를 창고에 넣었거나, '애매·틀림' 판정인데 넣지 않았으면 판정이 빗나갔다고 본다."""
    if verdict not in VERDICTS:
        return None
    return "correct" if (verdict == "correct") != (saved_external > 0) else "wrong"


def _label_state(db, idea_id: str) -> dict:
    auto = _one(db, "SELECT verdict, top_score FROM research_auto WHERE idea_id=?", (idea_id,))
    label = _one(db, "SELECT label FROM research_labels WHERE idea_id=?", (idea_id,))
    saved = _one(db, "SELECT COUNT(*) FROM items WHERE origin='research' AND origin_ref=?", (idea_id,))
    verdict = auto["verdict"] if auto and auto["verdict"] in VERDICTS else None
    count = int(saved[0]) if saved else 0
    return {"idea_id": idea_id, "verdict": verdict, "verdict_label": VERDICTS.get(verdict), "top_score": auto["top_score"] if auto else None,
            "label": label["label"] if label and label["label"] in LABELS else None, "suggested": suggest_label(verdict, count),
            "saved_external": count}


def load_label(root, idea_id: str) -> dict:
    """승인⓪ 화면에 보여 줄 판정과 사람이 매긴 답(맞음, 틀림, 연습)."""
    _idea_id(idea_id)
    try:
        with closing(_read_only(root)) as db:
            return _label_state(db, idea_id)
    except sqlite3.Error:
        return {"idea_id": idea_id, "verdict": None, "verdict_label": None, "top_score": None, "label": None, "suggested": None, "saved_external": 0}


def save_label(root, idea_id: str, label: str) -> dict:
    """사람이 승인⓪에서 매긴 답. 맞음과 틀림은 판정 채점에 쓰고, 연습은 채점에서 뺀다. 승인을 만들거나 바꾸지 않는다."""
    _idea_id(idea_id)
    if label not in LABELS:
        raise WorkflowError("맞음, 틀림, 연습 중에서 골라 주세요.")
    with closing(_connect(root)) as db, db:
        _ready(db)
        state = _label_state(db, idea_id)
        db.execute("INSERT INTO research_labels(idea_id,label,suggested,verdict,at) VALUES (?,?,?,?,?) ON CONFLICT(idea_id) DO UPDATE SET "
                   "label=excluded.label, suggested=excluded.suggested, verdict=excluded.verdict, at=excluded.at",
                   (idea_id, label, state["suggested"], state["verdict"], _now()))
        return {**state, "label": label}


def verdict_stats(root) -> dict:
    """판정마다 사람이 맞음, 틀림을 몇 번 눌렀는지. 연습은 따로 세고 맞은 비율에는 넣지 않는다."""
    stats = {"labeled": 0, "practice": 0, "by_verdict": {key: {"correct": 0, "wrong": 0} for key in VERDICTS},
             "changed_from_suggestion": 0, "agreement": None}
    try:
        with closing(_read_only(root)) as db:
            rows = db.execute("SELECT verdict, label, suggested FROM research_labels").fetchall()
    except sqlite3.Error:
        return stats
    for row in rows:
        if row["label"] == "practice":
            stats["practice"] += 1
        elif row["label"] in ("correct", "wrong") and row["verdict"] in VERDICTS:
            stats["labeled"] += 1
            stats["by_verdict"][row["verdict"]][row["label"]] += 1
            stats["changed_from_suggestion"] += int(row["suggested"] in ("correct", "wrong") and row["suggested"] != row["label"])
    right = sum(row["correct"] for row in stats["by_verdict"].values())
    stats["agreement"] = round(right / stats["labeled"], 3) if stats["labeled"] else None
    return stats
