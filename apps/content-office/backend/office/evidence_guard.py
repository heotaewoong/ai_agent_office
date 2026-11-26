"""근거 문단 지키기(2026-11-26): 숨긴 글자 지우기, 지시처럼 보이는 문장 표시, 핵심 문장 표시, 발행일 정리.

- strip_hidden_markup: 사람 눈에 안 보이게 숨긴 글(0 글씨, 투명, 배경 없는 흰 글씨, 화면 밖 좌표)을 본문 추출 전에 지운다.
  display:none은 지우지 않는다. 탭이나 펼치기 안의 진짜 본문도 그렇게 숨겨 두는 페이지가 많아서다.
- strip_invisible: 폭 없는 공백, 방향 제어, 태그 문자처럼 보이지 않는 문자를 지운다.
- instruction_flags: "이전 지시 무시" 같은 문장을 찾아 사람에게 보여 줄 표시만 돌려준다. 막지는 않는다.
- key_sentence: 문단 안에서 기획 제목과 가장 가까운 문장을 고른다(글자 두 개 묶음 겹침, 0원, 모델 호출 없음).
- published_date: 발행일 문자열을 YYYY-MM-DD로 정리한다.
"""
from __future__ import annotations

import re
from datetime import date

_INVISIBLE = re.compile("[­᠎​-‏‪-‮⁠-⁤⁦-⁩﻿\U000e0000-\U000e007f]")
_HIDDEN_STYLE = re.compile(
    r"font-size\s*:\s*0(?:\.0+)?(?:px|pt|em|rem|%)?\s*(?:!important\s*)?(?:;|$)"
    r"|opacity\s*:\s*0(?:\.0+)?\s*(?:!important\s*)?(?:;|$)"
    r"|(?:left|top|text-indent|margin-left)\s*:\s*-\d{4,}(?:\.\d+)?(?:px|pt|em|rem)",
    re.I)
_WHITE_TEXT = re.compile(r"(?<![-\w])color\s*:\s*(?:#fff(?:fff)?\b|white\b|rgba?\(\s*255\s*,\s*255\s*,\s*255\s*[,)])", re.I)
_BACKGROUND = re.compile(r"background", re.I)
_HINT = re.compile(r"font-size|opacity|-\d{4,}|color\s*:", re.I)

_FLAG_PATTERNS = tuple(re.compile(pattern, re.I) for pattern in (
    r"\b(?:ignore|disregard|forget|override)\b[^.\n]{0,40}\b(?:previous|prior|above|earlier|all|any)\b[^.\n]{0,30}\b(?:instructions?|prompts?|rules?|directions?)\b",
    r"\b(?:system prompt|developer message|new instructions?)\b",
    r"\byou are now\b",
    r"(?:이전|앞의|위의|기존|모든)\s*(?:지시|명령|지침|규칙|프롬프트)[^.\n]{0,12}(?:무시|잊어|따르지\s*마)",
    r"(?:지시|명령|지침)[^.\n]{0,6}(?:무시하|따르지\s*마)",
    r"시스템\s*프롬프트",
    r"(?:이|해당)\s*(?:원고|글|문서|콘텐츠)[^.\n]{0,12}(?:통과|승인)(?:시키|시켜|하세요|해라|처리)",
))
_SENTENCE_SPLIT = re.compile(r"(?<=[.!?。])\s+|\n+")
_DATE = re.compile(r"(\d{4})-(\d{2})-(\d{2})")


def strip_invisible(text: str) -> str:
    return _INVISIBLE.sub("", text) if isinstance(text, str) else text


def strip_invisible_deep(value):
    """모델에 넘기는 묶음(dict, list) 안의 모든 글자에서 보이지 않는 문자를 지운다."""
    if isinstance(value, str):
        return strip_invisible(value)
    if isinstance(value, list):
        return [strip_invisible_deep(item) for item in value]
    if isinstance(value, dict):
        return {key: strip_invisible_deep(item) for key, item in value.items()}
    return value


def _hidden(style: str) -> bool:
    if _HIDDEN_STYLE.search(style):
        return True
    return bool(_WHITE_TEXT.search(style)) and not _BACKGROUND.search(style)


def strip_hidden_markup(markup: str) -> str:
    """숨긴 글이 든 요소를 지운 HTML을 돌려준다. 숨긴 요소가 없거나 읽지 못하면 원래 HTML을 그대로 돌려준다."""
    if not isinstance(markup, str) or "style" not in markup or not _HINT.search(markup):
        return markup
    try:
        import lxml.html
    except ImportError:
        return markup
    try:
        tree = lxml.html.document_fromstring(markup)
    except Exception:  # noqa: BLE001 - 고칠 수 없는 HTML은 원래대로 넘기고 추출기에 맡긴다.
        return markup
    removed = 0
    for element in tree.xpath("//*[@style]"):
        if element.getparent() is not None and _hidden(element.get("style") or ""):
            element.drop_tree()  # 꼬리 글(tail)은 남긴다.
            removed += 1
    if not removed:
        return markup
    return lxml.html.tostring(tree, encoding="unicode")


def instruction_flags(text: str) -> list[str]:
    """지시처럼 보이는 문장 조각(최대 3개, 80자)을 돌려준다."""
    if not isinstance(text, str) or not text:
        return []
    found = []
    for pattern in _FLAG_PATTERNS:
        for match in pattern.finditer(text):
            start = max(0, match.start() - 10)
            snippet = re.sub(r"\s+", " ", text[start:match.end() + 10]).strip()[:80]
            if snippet and snippet not in found:
                found.append(snippet)
            if len(found) == 3:
                return found
    return found


def _bigrams(text: str) -> set[str]:
    letters = re.sub(r"[^0-9a-z가-힣]", "", text.lower())
    return {letters[i:i + 2] for i in range(len(letters) - 1)}


def key_sentence(query: str, quote: str, *, minimum: float = 0.15) -> str | None:
    """문장이 둘 이상인 문단에서 기획 제목과 글자 두 개 묶음이 가장 많이 겹치는 문장을 고른다. 없으면 None."""
    if not isinstance(query, str) or not isinstance(quote, str):
        return None
    wanted = _bigrams(query)
    sentences = [part.strip() for part in _SENTENCE_SPLIT.split(quote) if 15 <= len(part.strip()) <= 400]
    if not wanted or len(sentences) < 2:
        return None
    best, score = None, 0.0
    for sentence in sentences:
        overlap = len(wanted & _bigrams(sentence)) / len(wanted)
        if overlap > score:
            best, score = sentence, overlap
    return best if best and score >= minimum and best in quote else None


def published_date(value) -> str | None:
    """'2025-03-01T09:00:00+09:00' 같은 값을 '2025-03-01'로. 날짜가 아니면 None."""
    if not isinstance(value, str):
        return None
    match = _DATE.match(value.strip())
    if not match:
        return None
    try:
        return date(int(match[1]), int(match[2]), int(match[3])).isoformat()
    except ValueError:
        return None


def days_old(published: str | None, today: date | None = None) -> int | None:
    day = published_date(published)
    if day is None:
        return None
    return ((today or date.today()) - date.fromisoformat(day)).days
