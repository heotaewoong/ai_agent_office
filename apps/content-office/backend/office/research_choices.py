"""기획마다 사람이 고른 글 유형과 분야, 그리고 기획 카드에서 외부 조사 버튼을 누른 기록.

- 고른 값은 자료 창고 DB의 research_choices 표에 기획 ID마다 한 줄만 둔다. 기획 카드와 편집 해시, 승인은 바꾸지 않는다.
- 누른 기록에는 기획 ID, 그때 보여 준 추천(필수, 권장, 안 함), 고른 값인지 추측값인지, 찾은 후보 수만 남긴다. 제목과 검색어는 남기지 않는다.
- 추천과 실제로 누른 것이 얼마나 맞는지 나중에 보려고 모은다. 승인⓪①②③을 만들거나 대신하지 않는다.
"""
from __future__ import annotations

import logging
import re
import sqlite3
from contextlib import closing

from .external_research import KINDS
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
"""
_log = logging.getLogger(__name__)


def _idea_id(value) -> str:
    if not isinstance(value, str) or not _IDEA_ID.fullmatch(value):
        raise WorkflowError("기획을 찾을 수 없습니다. 목록을 새로 고쳐 주세요.")
    return value


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
        db.executescript(_SCHEMA)
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


def log_click(root, idea_id: str, plan: dict, *, forced: bool, searched: bool, candidates: int) -> bool:
    """기획 카드에서 외부 조사를 누른 기록 한 줄. 기록하지 못해도 조사 결과는 그대로 돌려준다."""
    try:
        row = (_idea_id(idea_id), _now(), str(plan.get("kind") or ""), str(plan.get("area") or ""),
               int(plan.get("kind_guessed") is not False), int(plan.get("area_guessed") is not False),
               str(plan.get("need") or ""), int(bool(forced)), int(bool(searched)), max(0, int(candidates)))
        with closing(_connect(root)) as db, db:
            db.executescript(_SCHEMA)
            db.execute("INSERT INTO research_clicks(idea_id,at,kind,area,kind_guessed,area_guessed,need,forced,searched,candidates) "
                       "VALUES (?,?,?,?,?,?,?,?,?,?)", row)
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
