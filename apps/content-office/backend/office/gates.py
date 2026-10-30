"""출고 전 품질·정책 게이트. 재현 가능한 규칙으로 막고, 애매하면 경고로 사람에게 넘긴다.

근거: Google '제목·메타 설명·대체 텍스트까지 사실 확인', YouTube 비진정성 콘텐츠(2025-07-15)와
2026-07-16 수익화 제외 유형, 사실적 합성 콘텐츠 고지 규정.
"""
from __future__ import annotations

import re

from .brand import banned_claim_hits

NUMBER = re.compile(r"\d{1,3}(?:,\d{3})+(?:\.\d+)?|\d+(?:[.,]\d+)?")
REALISTIC_KINDS = {"realistic_person", "realistic_event", "realistic_place", "voice_clone_other"}
YMYL_TOPICS = {"finance", "law", "health"}


def _numbers(text):
    # Encoded source URLs are identifiers, not numerical claims or supporting evidence.
    text = re.sub(r"https?://[^\s<>\[\]()]+", "", text or "")
    return {re.sub(r"(?<=\d),(?=\d)", "", n) for n in NUMBER.findall(text or "")}


def narration(packet):
    return " ".join((scene.get("narration") or "") for scene in ((packet.get("video") or {}).get("scenes") or []) if isinstance(scene, dict))


def metadata_fact_check(packet):
    evidence = _numbers(" ".join(e.get("claim", "") + " " + " ".join(e.get("numbers", [])) for e in packet.get("evidence", [])))
    body = _numbers(packet.get("body", ""))
    video = packet.get("video") or {}
    fields = {"블로그 제목": packet.get("title") or "", "영상 제목": video.get("title") or "", "영상 설명": video.get("description") or "", "태그": " ".join(video.get("tags") or [])}
    if isinstance(packet.get('channel_posts'), dict):
        fields.update({f'SNS {key}': text for key, text in packet['channel_posts'].items() if isinstance(text, str)})
    thumbs = [t for t in (video.get("thumbnails") or []) if isinstance(t, dict)]
    for index, thumb in enumerate(thumbs, 1):
        fields[f"썸네일 {index} 제목"] = thumb.get("title") or ""
        fields[f"썸네일 {index} 보조"] = thumb.get("subtitle") or ""
    items = []
    for name, text in fields.items():
        for number in sorted(_numbers(text) - evidence):
            level = "warn" if number in body else "block"
            items.append({"level": level, "rule": "metadata_numbers", "message": f"{name}의 숫자 {number}: {'본문에만 있음' if level == 'warn' else '근거·본문에 없음'}"})
    return items


def _shingles(text, n=3):
    words = re.findall(r"[0-9a-z가-힣]+", (text or "").lower())
    return {tuple(words[i:i + n]) for i in range(max(0, len(words) - n + 1))}


def similarity(a, b):
    sa, sb = _shingles(a), _shingles(b)
    return len(sa & sb) / len(sa | sb) if sa and sb else 0.0


def inauthentic_risk(packet, previous_packets, threshold=0.5):
    current = narration(packet)
    worst = max((similarity(current, narration(p)) for p in previous_packets), default=0.0)
    if worst >= threshold:
        return [{"level": "block", "rule": "inauthentic_template", "message": f"이전 영상과 대본 유사도 {worst:.2f}: 템플릿 반복은 수익화 제외 유형"}]
    return []


def disclosure_decision(assets):
    reasons = [asset.get("label", asset["kind"]) for asset in assets if asset.get("kind") in REALISTIC_KINDS]
    return {"youtube_altered_content": bool(reasons), "reasons": reasons}


def ymyl_persona(packet, assets):
    if packet.get("topic") in YMYL_TOPICS and any(asset.get("kind") == "ai_persona_real_person" for asset in assets):
        return [{"level": "block", "rule": "ymyl_ai_persona", "message": "실존 인물 AI 페르소나가 금융·법률·건강을 말하는 영상은 만들지 않습니다"}]
    return []


def korean_grammar(packet):
    """출고 직전 국어 확인. 사람이 원고를 고친 뒤에도 현재 문장을 다시 검사한다. 막지 않고 경고로 보인다."""
    from .korean import check_texts
    video = packet.get("video") or {}
    texts = [packet.get("title"), packet.get("body"), video.get("title"), video.get("description")]
    texts += [s.get(k) for s in (video.get("scenes") or []) if isinstance(s, dict) for k in ("narration", "caption")]
    texts += [t.get(k) for t in (video.get("thumbnails") or []) if isinstance(t, dict) for k in ("title", "subtitle")]
    items = [{"level": "warn", "rule": "korean_grammar", "message": f"국어 규칙: {issue}"} for issue in check_texts([t or "" for t in texts])[:12]]
    korean = (packet.get("quality") or {}).get("korean")
    if korean and not korean.get("passed"):
        items.append({"level": "warn", "rule": "korean_review", "message": f"국어 검수 미통과: 교정 제안 {len(korean.get('corrections') or [])}건을 원고 화면에서 확인하세요"})
    return items


def run_gates(packet, previous_packets=(), assets=(), brand=None):
    items = metadata_fact_check(packet) + inauthentic_risk(packet, previous_packets) + ymyl_persona(packet, assets) + korean_grammar(packet)
    if brand:
        video = packet.get("video") or {}
        thumbs = [t for t in (video.get("thumbnails") or []) if isinstance(t, dict)]
        parts = [packet.get("title"), packet.get("body"), narration(packet), video.get("title"), video.get("description"), " ".join(video.get("tags") or [])]
        parts += [t.get(key) for t in thumbs for key in ("title", "subtitle")]
        text = " ".join(part or "" for part in parts)
        items += [{"level": "block", "rule": "banned_claim", "message": f"금지 주장: {hit}"} for hit in banned_claim_hits(text, brand)]
    status = "block" if any(i["level"] == "block" for i in items) else "warn" if items else "pass"
    return {"status": status, "items": items, "disclosure": disclosure_decision(assets)}
