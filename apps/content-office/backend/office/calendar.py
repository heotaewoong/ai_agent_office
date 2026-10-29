"""시험 일정 캘린더와 시의성 점수.

config/exam_calendar.json에 프리셋별 시험 사건을 둔다. 가장 가까운 시험형 사건(필기·실기·응시·원서접수)이
운영자 확인과 공개 HTTPS 출처를 갖춘 경우에만 시의성에 반영한다. 45일 안이면 1.0,
120일에서 0.2까지 선형으로 내려가고 그 뒤는 0.2 바닥값이다. 발표는 시의성 계산에서 제외한다. 지난 사건은 무시한다.
캘린더가 없는 프리셋은 0.0, 항목 없이 baseline만 있는 프리셋(OPIc 상시 시험)은 baseline을 쓴다.
verified가 false인 날짜는 추정값이며 오너가 공식 공고로 확인해야 한다.
"""
from __future__ import annotations

import json
from datetime import date
from pathlib import Path

from .briefs import PRESETS
from .store import WorkflowError

CONFIG_PATH = Path(__file__).resolve().parents[1] / "config" / "exam_calendar.json"
KINDS = ("필기", "실기", "응시", "원서접수", "발표")
TIMELY_KINDS = ("필기", "실기", "응시", "원서접수")
FULL_DAYS = 45
FADE_DAYS = 120
FLOOR = 0.2


def load_calendar(path=CONFIG_PATH):
    path = Path(path)
    if not path.is_file():
        return {}
    try:
        raw = json.loads(path.read_text(encoding="utf-8"))
    except json.JSONDecodeError:
        raise WorkflowError(f"시험 일정 파일을 읽을 수 없습니다: {path.name}") from None
    if not isinstance(raw, dict):
        raise WorkflowError("exam_calendar.json은 {프리셋: {exams: [...]}} 형태의 객체여야 합니다")
    calendar = {}
    for preset, entry in raw.items():
        if preset.startswith("_") or not isinstance(entry, dict):
            continue
        exams = []
        for exam in entry.get("exams") or []:
            if not isinstance(exam, dict) or exam.get("kind") not in KINDS:
                raise WorkflowError(f"{preset} 일정 항목의 kind는 {', '.join(KINDS)} 중 하나여야 합니다")
            try:
                date.fromisoformat(str(exam.get("date")))
            except ValueError:
                raise WorkflowError(f"{preset} 일정 항목 {exam.get('name')!r}의 date는 YYYY-MM-DD여야 합니다") from None
            exams.append({
                "name": str(exam.get("name", "")),
                "date": str(exam["date"]),
                "kind": exam["kind"],
                "source_url": str(exam.get("source_url") or ""),
                "verified": exam.get("verified") is True,
                **({"note": str(exam["note"])} if exam.get("note") else {}),
            })
        calendar[preset] = {"baseline": float(entry.get("baseline") or 0.0), "note": str(entry.get("note") or ""), "exams": sorted(exams, key=lambda e: e["date"])}
    return calendar


def _calendar(calendar):
    return calendar if calendar is not None else load_calendar()


def _entry(preset, calendar):
    if not isinstance(preset, str) or preset not in PRESETS:
        raise WorkflowError(f"알 수 없는 독자 프리셋입니다: {preset!r}. 사용 가능: {', '.join(PRESETS)}")
    return _calendar(calendar).get(preset) or {"baseline": 0.0, "note": "", "exams": []}


def _upcoming(entry, today):
    rows = []
    for exam in entry["exams"]:
        days = (date.fromisoformat(exam["date"]) - today).days
        if days >= 0 and exam["kind"] in TIMELY_KINDS:
            rows.append({**exam, "days_left": days})
    return sorted(rows, key=lambda e: (e["days_left"], e["date"]))


def _curve(days):
    if days <= FULL_DAYS:
        return 1.0
    if days >= FADE_DAYS:
        return FLOOR
    return round(1.0 - (1.0 - FLOOR) * (days - FULL_DAYS) / (FADE_DAYS - FULL_DAYS), 3)


def _verified_source(exam):
    from .evidence import reference_url
    url = exam.get("source_url")
    if exam.get("verified") is not True or not isinstance(url, str) or any(char.isspace() for char in url):
        return False
    try:
        reference_url(url)
    except ValueError:
        return False
    return True


def next_exam(preset, today=None, calendar=None):
    today = today or date.today()
    entry = _entry(preset, calendar)
    rows = _upcoming(entry, today)
    if not rows:
        return None
    first = rows[0]
    return {"name": first["name"], "date": first["date"], "kind": first["kind"], "days_left": first["days_left"],
            "verified": first.get("verified") is True, "source_url": str(first.get("source_url") or ""),
            "note": str(first.get("note") or entry.get("note") or "")}


def timeliness(preset, today=None, calendar=None):
    today = today or date.today()
    entry = _entry(preset, calendar)
    rows = _upcoming(entry, today)
    if rows:
        return _curve(rows[0]["days_left"]) if _verified_source(rows[0]) else 0.0
    return min(max(entry["baseline"], 0.0), 1.0) if not entry["exams"] else 0.0


def calendar_for(preset, today=None, calendar=None):
    today = today or date.today()
    entry = _entry(preset, calendar)
    return {"preset": preset, "exams": entry["exams"], "next": next_exam(preset, today, calendar), "timeliness": timeliness(preset, today, calendar)}


def idea_preset(card):
    preset = card.get("brief_preset")
    if not preset and isinstance(card.get("brief"), dict):
        preset = card["brief"].get("preset")
    return preset if isinstance(preset, str) else None


def enrich_idea(card, today=None, calendar=None):
    """기획 카드에 시의성과 다음 참고 일정을 붙인다. 미확인 날짜는 명시하되 점수에는 가산하지 않는다."""
    preset = idea_preset(card)
    if not preset or preset not in PRESETS:
        return {**card, "timeliness": 0.0, "next_exam": None}
    today = today or date.today()
    nxt = next_exam(preset, today, calendar)
    return {**card, "timeliness": timeliness(preset, today, calendar), "next_exam": nxt}
