"""검수 하네스 Layer 1: 모델을 부르지 않는 0원 코드 검사.

기존 deterministic_checks(무결성, 분량, 소제목, 근거 ID, 문체, 국어 규칙, 책 인용)에 글 유형별 규칙을 더하고,
규칙마다 통과/실패(rule_scores)를 돌려준다. 하네스는 이 값으로 (1) 유료 판정 호출을 건너뛸지,
(2) 고친 글이 더 나빠졌는지(통과하던 규칙이 실패로 바뀌었는지)를 판단한다.
"""
from __future__ import annotations

import re

# 글 유형별 순수 본문(주소, 근거 표시, 표 기호, 소제목 기호를 뺀 글자) 하한. 전체 원고 목표(1,350~1,650자)에 맞춘 출발점이다.
W_MIN_PROSE = {"W1": 1100, "W2": 800, "W3": 1100, "W4": 0}
DEFAULT_MIN_PROSE = 1000
# 말미에 붙는 자기 해설 꼬리말. 출처 목록은 내보낼 때 서버가 따로 붙인다.
TRAILING_DISCLAIMERS = ("실측한 결과는 아닙니다", "정보 제공 목적", "출처와 확인 범위", "효과에 대한 설명이며", "투자 권유가 아닙니다")
_URL = re.compile(r"https?://[^\s<>()\[\]]+")
_MD_LINK = re.compile(r"\[([^\]\n]*)\]\((?:https?://)[^)\s]+\)")
_CITE = re.compile(r"\[[A-Z]{1,3}\d{1,3}(?:\s*,\s*[A-Z]{1,3}\d{1,3})*\]")
_TABLE_RULE = re.compile(r"(?m)^\s*\|?\s*:?-{3,}:?\s*(\|\s*:?-{3,}:?\s*)+\|?\s*$")
_NUMBER_CLAIM = re.compile(r"\d[\d,.]*\s*(%|퍼센트|배|명|원|달러|점|시간|분|일|개월|년)")
# deterministic_checks가 돌려주는 문구를 규칙 이름으로 묶는다(문구가 바뀌면 이 표도 함께 고친다).
_CHECK_GROUPS = (
    ("length", ("자보다 짧아 원문 주제의 구체적인 설명",)),
    ("headings", ("소제목으로 읽기 흐름",)),
    ("citations", ("근거 ID를 원고에 연결", "근거 ID가 하나도 연결되지", "근거 ID를 별도 참고 목록", "존재하지 않는 근거 ID", "근거 ID 목록의 형식")),
    ("numbers", ("근거 묶음에 없는 숫자",)),
    ("hedges", ("한계, 단서 문장이",)),
    ("scenes", ("숏폼은 3~7개", "내레이션이 너무 길어", "장면 제목이 한국어가 아니에요")),
    ("book_quotes", ("풀어 쓰기만 할 수 있어요", "두 문장까지만 인용", "저자를 확인해 출처에")),
)


def pure_prose_length(markdown: str) -> int:
    text = _MD_LINK.sub(r"\1", markdown or "")
    text = _URL.sub("", text)
    text = _CITE.sub("", text)
    text = re.sub(r"(?m)^\s*#{1,6}\s*", "", text)
    text = re.sub(r"[|*_`>~-]", "", text)
    return len(re.sub(r"\s+", " ", text).strip())  # 읽히는 글자 수(띄어쓰기 한 칸 포함)


def _example_ids(evidence) -> set[str]:
    """사례·참고 칸 자료(사실 근거 아님): 운영자가 example 칸에 둔 자료와 Tavily 아이디어 칸 자료."""
    return {item["id"] for item in evidence if isinstance(item, dict) and item.get("id") and (
        item.get("idea_only") is True or "사례·참고" in str(item.get("claim", "")))}


def extra_rule_issues(packet: dict, *, w_type: str | None = None) -> dict[str, list[str]]:
    """글 유형별 추가 규칙. {규칙 이름: [문제 설명]}을 돌려준다. 빈 목록이면 통과다."""
    body = packet.get("body") or ""
    preserve = packet.get("preserve_original") is True
    evidence = [item for item in packet.get("evidence") or [] if isinstance(item, dict)]
    found: dict[str, list[str]] = {"prose_length": [], "disclaimer": [], "duplicate_url": [], "comparison_table": [],
                                   "example_numbers": [], "w_scope": []}
    if w_type == "W5":
        found["w_scope"].append("범위 밖(W5) 주제는 원고를 만들지 않아요. 글 유형을 다시 골라 주세요")
    if w_type == "W4" and any(item.get("source_kind") == "approved_book_evidence" for item in evidence):
        found["w_scope"].append("내 경험 글(W4)에는 개인 DB 책 근거를 쓰지 않아요. 경험 원문만으로 써 주세요")
    if not preserve:
        minimum = W_MIN_PROSE.get(w_type or "", DEFAULT_MIN_PROSE)
        length = pure_prose_length(body)
        if minimum and length < minimum:
            found["prose_length"].append(f"주소와 근거 표시를 뺀 본문이 {length}자예요. {w_type or '이 글'} 기준 {minimum}자 이상으로 설명을 채워 주세요")
        tail = body[-240:]
        hit = next((phrase for phrase in TRAILING_DISCLAIMERS if phrase in tail), None)
        if hit:
            found["disclaimer"].append(f"본문 끝에 '{hit}' 같은 해설 꼬리말이 있어요. 출처 목록은 서버가 붙이니 본문에서는 빼 주세요")
        urls = [url.rstrip(".,)") for url in _URL.findall(body)]
        repeated = sorted({url for url in urls if urls.count(url) > 1})
        if repeated:
            found["duplicate_url"].append(f"본문에 같은 주소가 여러 번 나와요: {', '.join(repeated[:3])}")
        if w_type == "W1" and not _TABLE_RULE.search(body):
            found["comparison_table"].append("비교 글(W1)인데 비교표가 없어요. 대상과 비교축을 표로 보여 주세요")
        examples = _example_ids(evidence)
        if examples:
            for sentence in re.split(r"(?<=[.!?])\s+|\n+", body):
                cited = {item.strip() for group in re.findall(r"\[([A-Z0-9,\s]+)\]", sentence) for item in group.split(",")}
                if cited and cited <= examples and _NUMBER_CLAIM.search(sentence):
                    found["example_numbers"].append(f"사례·참고 자료만으로 수치를 말한 문장이 있어요: {sentence.strip()[:80]}")
                    break
    return found


def validate_packet(packet: dict, *, base_checks: dict, w_type: str | None = None, style=(), korean=()) -> dict:
    """기존 검사 결과(base_checks)와 추가 규칙을 합쳐 규칙별 통과/실패를 만든다. 모델 호출은 없다."""
    issues = [str(issue) for issue in base_checks.get("issues", [])]
    blocking = [str(issue) for issue in base_checks.get("blocking", [])]
    extra = extra_rule_issues(packet, w_type=w_type)
    scores = {"integrity": not blocking}
    for name, markers in _CHECK_GROUPS:
        scores[name] = not any(marker in issue for issue in issues for marker in markers)
    scores["style"] = not list(style)
    scores["korean"] = not list(korean)
    for name, problems in extra.items():
        scores[name] = not problems
    extra_issues = [problem for problems in extra.values() for problem in problems]
    if extra["w_scope"]:
        blocking = [*blocking, *extra["w_scope"]]
    all_issues = list(dict.fromkeys([*issues, *extra_issues]))
    # 고치기로 보내지 않는 확인 의견(안 쓴 근거, warn 모드 숫자 경고)은 사람에게만 보여 줘요.
    notes = [str(note) for note in base_checks.get("notes", []) if str(note) not in all_issues]
    return {"passed": not all_issues, "blocking": list(dict.fromkeys(blocking)), "issues": all_issues,
            "warnings": [issue for issue in all_issues if issue not in blocking] + notes, "notes": notes, "rule_scores": scores}
