"""기획 은행: 신호를 점수화해 사람이 고를 후보를 정렬한다. 점수는 판단 보조이며 성과 예측이 아니다.

demand는 요청마다 최대값을 100으로 맞춘 상대값(네이버 데이터랩 등)이므로 같은 요청 안에서만 비교한다.
"""
from __future__ import annotations

import math

from .calendar import enrich_idea

# timeliness는 기본 다섯 요소를 100점으로 정규화한 뒤 가산점(최대 10점, 합계 100점 상한)으로 더한다.
# 캘린더가 있는 프리셋(brief.preset)의 카드만 0보다 큰 값을 받으므로 기존 카드 점수는 그대로다.
WEIGHTS = {"outlier": 30, "demand": 20, "evidence": 20, "fit": 20, "novelty": 10, "timeliness": 10}
BASE_FACTORS = ("outlier", "demand", "evidence", "fit", "novelty")
BAND_POINTS = {"10x+": 1.0, "5-10x": 0.8, "2-5x": 0.55, "under-2x": 0.2, "unknown": 0.0}
BLOCKING_FLAGS = {
    "ai_persona_real_person_ymyl": "실존 인물 AI 페르소나의 금융·법률·건강 발언(YouTube 2026-07 수익화 제외 유형)",
    "templated_series": "같은 템플릿 반복 위험(YouTube 비진정성 콘텐츠)",
    "no_primary_source": "1차 출처 없음",
}


def outlier_ratio(views, channel_avg_views):
    if not views or not channel_avg_views or channel_avg_views <= 0:
        return None
    return views / channel_avg_views


def outlier_band(ratio):
    if ratio is None:
        return "unknown"
    if ratio >= 10:
        return "10x+"
    if ratio >= 5:
        return "5-10x"
    if ratio >= 2:
        return "2-5x"
    return "under-2x"


def _number(value, default=0.0):
    try:
        number = float(value)
    except (TypeError, ValueError, OverflowError):
        return default
    return number if math.isfinite(number) else default


def effective_weights(weights=None, lessons=()):
    result = dict(weights or WEIGHTS)
    for lesson in lessons:
        change = lesson.get("weight_change") or {}
        if lesson.get("state") == "approved" and change.get("factor") in result:
            result[change["factor"]] = max(0, result[change["factor"]] + int(_number(change.get("delta"))))
    return result


def score_idea(card, weights=None, lessons=(), today=None, calendar=None):
    w = effective_weights(weights, lessons)
    card = enrich_idea(card, today, calendar)
    band = outlier_band(outlier_ratio(card.get("views"), card.get("channel_avg_views")))
    sources = int(_number(card.get("primary_sources")))
    parts = {
        "outlier": BAND_POINTS[band],
        "demand": min(max(_number(card.get("demand")), 0.0), 100.0) / 100,
        "evidence": min(sources, 3) / 3,
        "fit": min(max(_number(card.get("fit")), 0.0), 1.0),
        "novelty": 0.0 if card.get("covered_before") else 1.0,
        "timeliness": min(max(_number(card.get("timeliness")), 0.0), 1.0),
    }
    base = 100 * sum(w[k] * parts[k] for k in BASE_FACTORS) / (sum(w[k] for k in BASE_FACTORS) or 1)
    score = round(min(100.0, base + w.get("timeliness", 0) * parts["timeliness"]), 1)
    raw_flags = card.get("policy_flags")
    raw_flags = raw_flags if isinstance(raw_flags, (list, tuple, set)) else []
    flags = [f for f in raw_flags if f in BLOCKING_FLAGS] + ([] if sources else ["no_primary_source"])
    blocked = [BLOCKING_FLAGS[f] for f in dict.fromkeys(flags)]
    reasons = [f"이상치 {band}", f"수요 {_number(card.get('demand')):g}(상대값)", f"1차 출처 {sources}개"]
    return {**card, "score": 0.0 if blocked else score, "outlier_band": band, "parts": parts, "reasons": reasons, "blocked": blocked}


def rank_ideas(cards, weights=None, lessons=(), today=None, calendar=None):
    scored = [score_idea(card, weights, lessons, today, calendar) for card in cards]
    return sorted(scored, key=lambda c: (not c["blocked"], c["score"]), reverse=True)
