"""판정 모델 보정: 사람이 통과/실패를 붙인 30건 이상과 판정 모델의 답을 비교한다(TPR, TNR).

- TPR: 사람이 통과라고 한 원고를 판정자도 통과라고 한 비율. 낮으면 좋은 원고를 괜히 고치게 된다.
- TNR: 사람이 실패라고 한 원고를 판정자도 실패라고 한 비율. 낮으면 나쁜 원고가 통과한다(더 위험).
- 둘 다 기준(기본 0.85)을 넘기 전에는 판정 결과를 자동 결정에 쓰지 않고 사람 확인용 의견으로만 둔다.
"""
from __future__ import annotations

from pathlib import Path

MIN_PAIRS = 30


def compute_judge_calibration(pairs: list[dict], *, min_tpr: float = 0.85, min_tnr: float = 0.85, axis: str | None = None) -> dict:
    rows = [(bool(row["human"]), bool(row["judge"])) for row in pairs if isinstance(row, dict) and "human" in row and "judge" in row
            and (axis is None or row.get("axis") == axis)]
    if len(rows) < MIN_PAIRS:
        raise ValueError(f"사람 라벨이 {MIN_PAIRS}건 이상 필요합니다(지금 {len(rows)}건)")
    tp = sum(human and judge for human, judge in rows)
    fn = sum(human and not judge for human, judge in rows)
    tn = sum(not human and not judge for human, judge in rows)
    fp = sum(not human and judge for human, judge in rows)
    tpr = round(tp / (tp + fn), 4) if tp + fn else None
    tnr = round(tn / (tn + fp), 4) if tn + fp else None
    short = [name for name, value, floor in (("TPR", tpr, min_tpr), ("TNR", tnr, min_tnr)) if value is None or value < floor]
    return {"axis": axis, "total": len(rows), "tp": tp, "fn": fn, "tn": tn, "fp": fp, "tpr": tpr, "tnr": tnr,
            "agreement": round((tp + tn) / len(rows), 4), "calibrated": not short,
            "note": "기준을 넘었어요" if not short else f"{', '.join(short)}가 기준보다 낮아요. 기준표(harness_rubric.md)를 고친 뒤 다시 재요"}


def write_report(root, result: dict, *, day: str) -> Path:
    path = Path(root) / "evals" / "reports" / f"{day}-judge-calibration.md"
    path.parent.mkdir(parents=True, exist_ok=True)
    lines = [f"# 판정 모델 보정 {day}", "", f"- 건수: {result['total']}", f"- TPR: {result['tpr']}", f"- TNR: {result['tnr']}",
             f"- 일치율: {result['agreement']}", f"- 판정: {result['note']}", ""]
    path.write_text("\n".join(lines), encoding="utf-8")
    return path
