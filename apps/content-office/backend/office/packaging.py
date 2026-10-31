"""패키징 우선: 대본 전에 제목 3안·썸네일 3안·훅·로그라인을 정한다.

근거: Ali Abdaal '제목·썸네일·훅을 모르면 대본을 쓰지 않는다', Paddy Galloway 한 장 기획,
YouTube Test & Compare(제목·썸네일 최대 3안, 시청 시간 기준 승자).
"""
from __future__ import annotations

import re

from .store import WorkflowError, digest

TITLE_MAX = 45       # 내부 기준: 모바일 목록에서 잘리지 않게(공식 상한 100자)
THUMB_TEXT_MAX = 12  # 실제 한글 폰트 레이어로 얹는 글자 수
HOOK_MAX = 120
PACKAGING_SCHEMA = {
    "type": "object",
    "properties": {
        "titles": {"type": "array", "minItems": 3, "maxItems": 3, "items": {"type": "string"}},
        "thumbnails": {"type": "array", "minItems": 3, "maxItems": 3, "items": {"type": "object", "properties": {"text": {"type": "string"}, "visual": {"type": "string"}}, "required": ["text", "visual"], "additionalProperties": False}},
        "hook": {"type": "string"},
        "logline": {"type": "string"},
        "reasons": {"type": "array", "minItems": 2, "maxItems": 3, "items": {"type": "string"}},
    },
    "required": ["titles", "thumbnails", "hook", "logline", "reasons"],
    "additionalProperties": False,
}


def _tokens(text):
    return set(re.findall(r"[0-9a-z가-힣]{2,}", text.lower()))


def _carries_promise(title, hook):
    title_tokens, hook_tokens = _tokens(title), _tokens(hook)
    if title_tokens & hook_tokens:
        return True
    # 조사가 붙은 한국어 어절("블로그를"/"블로그")은 앞 2글자 일치로 같은 말로 본다
    return any(t[:2] == h[:2] for t in title_tokens for h in hook_tokens)


def validate_packaging(brief):
    issues = []
    titles, thumbs = brief.get("titles", []), brief.get("thumbnails", [])
    if len(titles) != 3:
        issues.append("제목은 비교용 3안이 필요합니다")
    issues += [f"제목 {i + 1}안이 {TITLE_MAX}자를 넘습니다" for i, t in enumerate(titles) if len(t) > TITLE_MAX]
    issues += [f"제목 {i + 1}안이 비어 있습니다" for i, t in enumerate(titles) if not str(t).strip()]
    if len(thumbs) != 3:
        issues.append("썸네일은 비교용 3안이 필요합니다")
    issues += [f"썸네일 {i + 1}안 글자가 {THUMB_TEXT_MAX}자를 넘습니다" for i, t in enumerate(thumbs) if len(t.get("text", "")) > THUMB_TEXT_MAX]
    issues += [f"썸네일 {i + 1}안 글자가 비어 있습니다" for i, t in enumerate(thumbs) if not str(t.get("text", "")).strip()]
    hook = brief.get("hook", "").strip()
    if not 0 < len(hook) <= HOOK_MAX:
        issues.append(f"훅은 1~{HOOK_MAX}자로 씁니다")
    if not brief.get("logline", "").strip():
        issues.append("로그라인이 없습니다")
    if not 2 <= len(brief.get("reasons", [])) <= 3:
        issues.append("통할 이유는 2~3개입니다")
    chosen = brief.get("chosen_title") or (titles[0] if titles else "")
    if chosen and hook and not _carries_promise(chosen, hook):
        issues.append("훅이 제목의 약속을 이어받지 않습니다")
    return {"passed": not issues, "issues": issues}


def attach_packaging(store, job_id, brief, actor):
    report = validate_packaging(brief)
    if not report["passed"]:
        raise WorkflowError("패키징 보완 필요: " + " / ".join(report["issues"]))
    record = {**brief, "packaging_hash": digest(brief), "selected_by": actor}
    store.update_job(job_id, packaging=record)
    store.event("packaging_selected", {"packaging_hash": record["packaging_hash"], "actor": actor}, job_id)
    return record


def require_packaging(job):
    if job["article"].get("origin") == "idea" and not job.get("packaging") and not (job.get("source_packet") or {}).get("body") and not str(job.get("title") or "").strip():
        raise WorkflowError("기획에서 시작한 작업은 패키징(제목·썸네일·훅)을 먼저 정해야 합니다")
