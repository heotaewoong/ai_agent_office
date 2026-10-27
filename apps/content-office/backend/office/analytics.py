"""성과 환류: 24시간·7일 스냅샷을 채널 기준선과 비교해 교훈 후보를 만든다.

교훈은 사람이 승인해야 기획 점수에 반영된다(darkzOGx/youtube-automation-agent 패턴).
CTR·노출수는 YouTube Analytics API에 없고 Reporting API 대량 보고서나 Studio 내보내기에만 있으므로 CSV 가져오기부터 시작한다.
"""
from __future__ import annotations

import csv
import statistics
from pathlib import Path

COLUMNS = {
    "external_id": ("Content", "콘텐츠"),
    "impressions": ("Impressions", "노출수"),
    "ctr": ("Impressions click-through rate (%)", "노출 클릭률(%)"),
    "views": ("Views", "조회수"),
    "engaged_views": ("Engaged views", "참여 조회수"),
    "avp": ("Average percentage viewed (%)", "평균 조회율(%)"),
    "avd_seconds": ("Average view duration", "평균 시청 지속 시간"),
}


def _number(value):
    value = (value or "").strip().replace(",", "")
    if ":" in value:
        seconds = 0
        for part in value.split(":"):
            seconds = seconds * 60 + int(part)
        return float(seconds)
    return float(value) if value else None


def parse_studio_csv(path):
    rows = []
    with Path(path).open(encoding="utf-8-sig", newline="") as handle:
        for raw in csv.DictReader(handle):
            row = {}
            for key, names in COLUMNS.items():
                cell = next((raw[n] for n in names if n in raw), None)
                row[key] = cell.strip() if key == "external_id" and cell else _number(cell) if cell is not None else None
            if row["external_id"] and row["external_id"].lower() not in ("total", "합계"):
                rows.append(row)
    return rows


def baseline(snapshots):
    ctr = [s["metrics"]["ctr"] for s in snapshots if s["metrics"].get("ctr")]
    avp = [s["metrics"]["avp"] for s in snapshots if s["metrics"].get("avp")]
    return {"ctr": statistics.median(ctr) if ctr else None, "avp": statistics.median(avp) if avp else None}


def propose_lessons(snapshot, base):
    m, lessons = snapshot["metrics"], []
    evidence = {"snapshot_id": snapshot["id"], "external_id": snapshot["external_id"], "period": snapshot["period"]}
    if m.get("ctr") and m.get("avp") and base.get("ctr") and base.get("avp"):
        if m["ctr"] < 0.8 * base["ctr"] and m["avp"] >= base["avp"]:
            lessons.append({"kind": "packaging", "hypothesis": "본 사람은 끝까지 봤지만 클릭이 적다: 다음 기획에서 제목·썸네일 3안 비교를 강화한다", "weight_change": {"factor": "outlier", "delta": 5}, "evidence": evidence})
        if m["ctr"] >= 1.2 * base["ctr"] and m["avp"] < 0.8 * base["avp"]:
            lessons.append({"kind": "promise_mismatch", "hypothesis": "클릭은 많고 유지가 낮다: 첫 1분이 제목의 약속을 이행하는지 점검한다", "weight_change": None, "evidence": evidence})
    if snapshot["channel"] == "shorts" and m.get("views") and m.get("engaged_views") is not None and m["engaged_views"] / m["views"] < 0.5:
        lessons.append({"kind": "hook", "hypothesis": "쇼츠 참여 조회 비율이 50% 미만: 3초 안 훅과 반복 연결을 바꾼다", "weight_change": None, "evidence": evidence})
    return lessons
