"""0원 사실 대조 규칙 한 곳(2026-11-27). 출력 골든셋 채점기(evals/output_golden.py)와 같은 규칙이에요.

1. claim_quote_mismatches: 근거 뽑기가 만든 주장의 숫자와 영문 고유 토큰이 연결한 원문 문단에 있는지(P4).
2. numbers_not_in_evidence: 원고 본문 숫자가 근거 묶음 어디에도 없는지(P5). 목록 번호, 소제목, 근거 ID, 주소는 빼요.

모델을 부르지 않아요. 규칙을 바꾸면 evals/output_golden.py의 같은 함수도 같이 고쳐요.
"""
from __future__ import annotations

import re

NUM = re.compile(r"(?<![\w.])(\d+(?:\.\d+)?)(?!\.?\d)")
MARKER = re.compile(r"(?:^|(?<=\s))\d+[.)]\s", re.M)  # '1) 2.' 같은 목록 번호
CITE = re.compile(r"\[[A-Z]{1,3}\d{1,3}(?:\s*,\s*[A-Z]{1,3}\d{1,3})*\]")
URL = re.compile(r"https?://\S+|\]\([^)]*\)")
LATIN = re.compile(r"[A-Za-z][A-Za-z0-9\-]*")
# 원고가 글을 나누려고 쓰는 숫자(3가지, 2단계, 첫 1번째)는 사실 숫자가 아니에요.
STRUCTURE = re.compile(r"(\d+)\s*(?:가지|단계|번째|부|장면|편)(?![가-힣]*(?:원|명|개사))")
NUMWORD = {"one": "1", "two": "2", "three": "3", "four": "4", "five": "5", "six": "6", "seven": "7", "eight": "8",
           "nine": "9", "ten": "10", "eleven": "11", "twelve": "12"}
GENERIC = {"AI"}


def _numwords(text: str) -> str:
    return re.sub(r"\b(" + "|".join(NUMWORD) + r")\b", lambda m: NUMWORD[m.group(1).lower()], text, flags=re.I)


def _plain(number: str) -> str:
    return number.replace(",", "")


def has_number(number: str, text: str) -> bool:
    """1,500과 1500은 같은 숫자로 봐요."""
    flat = re.sub(r"(?<=\d),(?=\d{3})", "", text)
    return re.search(rf"(?<![\d.]){re.escape(_plain(number))}(?!\d|\.\d)", flat) is not None


def claim_tokens(claim: str) -> tuple[list[str], list[str]]:
    flat = re.sub(r"(?<=\d),(?=\d{3})", "", claim)
    nums = NUM.findall(MARKER.sub(" ", flat))
    names = [t for t in LATIN.findall(claim) if t[0].isupper() or any(ch.isupper() or ch.isdigit() for ch in t)]
    return nums, sorted(set(names))


def _name_ok(token: str, quote: str) -> bool:
    if token in GENERIC or token.lower() in quote.lower():
        return True
    if token.isupper() and 2 <= len(token) <= 6:  # Model Context Protocol = MCP 같은 약자
        for run in re.findall(r"(?:[A-Z][a-z]+[\s-]+){1,5}[A-Z][a-z]+", quote):
            if "".join(word[0] for word in re.split(r"[\s-]+", run)) == token:
                return True
    return False


def claim_quote_mismatches(claim: str, quote: str, *, numbers=(), context: str = "") -> list[str]:
    """주장(과 주장이 적은 numbers)에 있는데 문단에 없는 숫자와 영문 이름. context는 기사 제목처럼 같이 봐도 되는 글이에요."""
    text = _numwords(f"{quote} {context}")
    joined = " ".join([claim, *map(str, numbers or ())])
    nums, names = claim_tokens(joined)
    has_latin = bool(re.search(r"[A-Za-z]{3,}", quote))
    missing = [n for n in nums if not has_number(n, text) and not _unit_converted(n, joined, text)]
    if has_latin:  # 한국어로만 쓴 원문에 영어 이름을 붙인 번역은 따지지 않아요
        missing += [t for t in names if not _name_ok(t, f"{quote} {context}")]
    return list(dict.fromkeys(missing))


def evidence_text(evidence) -> str:
    parts = []
    for item in evidence or []:
        if isinstance(item, dict):
            parts += [str(item.get(key, "")) for key in ("claim", "source_quote", "key_sentence", "title", "scope")]
            parts += [str(value) for value in item.get("numbers") or []]
    return _numwords(" ".join(parts))


def numbers_not_in_evidence(packet: dict, *, extra_text: str = "") -> list[str]:
    """본문 숫자 중 근거 묶음에 없는 것(문맥 조각과 함께). 원문 보존 원고는 보지 않아요."""
    if packet.get("preserve_original") is True:
        return []
    allowed = evidence_text(packet.get("evidence")) + " " + _numwords(extra_text)
    found = []
    for line in str(packet.get("body") or "").splitlines():
        if re.match(r"^\s*#", line):
            continue
        clean = STRUCTURE.sub(" ", MARKER.sub(" ", CITE.sub(" ", URL.sub(" ", line))))
        clean = re.sub(r"(?<=\d),(?=\d{3})", "", clean)
        for match in NUM.finditer(clean):
            number = match.group(1)
            if not has_number(number, allowed):
                snippet = clean[max(0, match.start() - 12):match.end() + 8].strip()
                found.append(f"{number} ({snippet})")
    return list(dict.fromkeys(found))


def _significant(number: str) -> str:
    return number.replace(",", "").replace(".", "").strip("0")


def _unit_converted(number: str, claim: str, text: str) -> bool:
    """43억 = 4.3 billion, 1.5만 = 15,000처럼 한국어 단위로 바꾼 숫자는 유효 숫자가 같으면 같은 숫자로 봐요."""
    if not re.search(rf"(?<![\d.]){re.escape(number)}\s*(?:억|만|천|조)", claim):
        return False
    digits = _significant(number)
    return bool(digits) and any(_significant(found) == digits for found in NUM.findall(re.sub(r"(?<=\d),(?=\d{3})", "", text)))


def triage_claim(claim: str, numbers, paragraph: int, supplied: dict, *, context: str = "") -> dict:
    """근거 뽑기 결과 한 줄을 0원으로 분류해요(P4).

    - ok: 숫자와 영문 이름이 연결한 문단(또는 제목, 날짜 같은 기사 정보)에 있어요.
    - relink: 다른 문단 하나에 모두 있어요. 그 문단으로 고쳐 연결해요(모델 호출 없음).
    - retry_numbers: 숫자가 받은 원문 어디에도 없어요. 한 번 다시 뽑고, 그래도 없으면 뺄 후보예요.
    - flag_names: 숫자는 맞고 영문 이름만 원문에 없어요(번역, 상식 보탬). 빼지 않고 표시만 해요.
    """
    quote = supplied.get(paragraph, "")
    missing = claim_quote_mismatches(claim, quote, numbers=numbers, context=context)
    if not missing:
        return {"action": "ok", "missing": []}
    for number, text in supplied.items():
        if number != paragraph and not claim_quote_mismatches(claim, text, numbers=numbers, context=context):
            return {"action": "relink", "missing": missing, "paragraph": number}
    whole = " ".join(supplied.values()) + " " + context
    nums, _ = claim_tokens(" ".join([claim, *map(str, numbers or ())]))
    absent_numbers = [n for n in nums if not has_number(n, _numwords(whole)) and not _unit_converted(n, claim, whole)]
    if absent_numbers:
        return {"action": "retry_numbers", "missing": missing, "absent_numbers": absent_numbers}
    return {"action": "flag_names", "missing": missing}
