"""독자 질문 수집: 홈페이지·댓글·DM·이메일로 들어온 질문을 모아 묶고, 사람이 고를 기획 후보로 바꾼다.

이름·이메일 같은 개인정보는 받지 않는다(출처와 채널 키만). 비슷한 질문은 정규화한 앞 40자로 묶어 수요 신호로 쓴다.
변환된 기획은 1차 출처 0개로 저장되므로 선택⓪ 전에 오너가 출처를 붙여야 한다. 에이전트가 승인을 만들지 않는다.
"""
from __future__ import annotations

import re
import unicodedata

from .briefs import DEFAULT_PRESET, MAX_FIELD_LENGTH, build_brief
from .ideas import score_idea
from .store import WorkflowError

SOURCES = ("homepage", "comment", "dm", "email", "other")
MIN_LENGTH = 5
MAX_LENGTH = 1000
GROUP_KEY_LENGTH = 40
TITLE_LENGTH = 60


def group_key(text):
    normalised = unicodedata.normalize("NFKC", str(text or "")).lower()
    return re.sub(r"[^\w]|_", "", normalised)[:GROUP_KEY_LENGTH]


def _validate(source, text, channel_key):
    if source not in SOURCES:
        raise WorkflowError(f"질문 출처는 {', '.join(SOURCES)} 중 하나여야 합니다")
    text = " ".join(str(text or "").split())
    if len(text) < MIN_LENGTH or len(text) > MAX_LENGTH:
        raise WorkflowError(f"질문은 {MIN_LENGTH}자 이상 {MAX_LENGTH}자 이하여야 합니다")
    if channel_key is not None and not isinstance(channel_key, str):
        raise WorkflowError("channel_key는 문자열이거나 비워야 합니다")
    return text, (channel_key.strip() or None) if channel_key else None


def receive_question(store, source, text, channel_key=None):
    text, channel_key = _validate(source, text, channel_key)
    row = store.save_question({"source": source, "text": text, "channel_key": channel_key, "group_key": group_key(text)})
    store.event("question_received", {"question_id": row["id"], "group_key": row["group_key"], "source": source})
    return row


def _groups(rows):
    groups = {}
    for row in sorted(rows, key=lambda r: (r["created_at"], r["id"])):
        group = groups.setdefault(row["group_key"], {"group_key": row["group_key"], "sample_text": row["text"], "count": 0, "question_ids": []})
        group["count"] += 1
        group["question_ids"].append(row["id"])
    return sorted(groups.values(), key=lambda g: -g["count"])


def list_questions(store):
    rows = store.questions()
    return {"questions": rows, "groups": _groups(rows)}


def convert_question(store, question_id, brief_preset=None, title=None, lessons=()):
    question = store.question(question_id)
    if not question:
        raise WorkflowError("질문을 찾을 수 없습니다")
    group = next(g for g in _groups(store.questions()) if g["group_key"] == question["group_key"])
    chosen = " ".join(str(title or "").split()) or group["sample_text"]
    card = {
        "title": chosen[:TITLE_LENGTH].strip(),
        "source_url": None,
        "origin": "question",
        "demand": min(100, 20 * group["count"]),
        "primary_sources": 0,
        "fit": 0.7,
        "policy_flags": [],
        "question_group": group["group_key"],
        "question_ids": group["question_ids"],
        "brief": build_brief(brief_preset or DEFAULT_PRESET, {"problem": question["text"][:MAX_FIELD_LENGTH]}),
    }
    idea = store.save_idea(score_idea(card, lessons=lessons))
    store.mark_questions_converted(group["group_key"], idea["id"])
    store.event("question_converted", {"group_key": group["group_key"], "idea_id": idea["id"], "question_ids": group["question_ids"]})
    return idea
