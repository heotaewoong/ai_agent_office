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


# 한계 문장 흩어짐(2026-11-27): 문단마다 '다만 ~라 일반화하면 안 돼요'가 붙으면 AI가 쓴 글처럼 읽혀요.
HEDGE = re.compile(r"(일반화|일반 성과|따로 (확인|검증)|별도 (확인|검증)|단정(하면|하기) (안|어렵)|그대로 (믿|읽|받아들)|바탕으로 정리|독립(적인)? (성능 )?검증|보정(되지 않|하지는 않|이 아니)|데모 (결과|성격)|실제 (로봇|환경|성능|실물)[^.]{0,14}(아니|않|필요))")


def hedge_spread(body: str) -> dict:
    """한계, 단서 문장 수와 그 문장이 들어간 소제목 구역 수."""
    found = caveat_report(body)
    return {"sentences": len(found["caveats"]), "sections": len({section for section, _ in found["caveats"]})}


# 단서 문장 2차(2026-11-28): 11-27 단어 목록은 표현만 바뀐 단서(넓혀 읽으면, 보장하는 것은 아니에요, 범위 안에서만 읽어야,
# 말할 수는 없어요)를 하나도 못 잡았어요. 낱말 대신 '읽는 법을 지시하는 말', '보장 부정', '역접 시작 + 한계 낱말'을 봐요.
# 면책(BOILERPLATE): 독자가 할 일이 바뀌지 않는 문장. 읽는 법 지시와 보장 부정이에요. 있으면 지워요.
BOILERPLATE = re.compile(
    r"보장(하|되|해|할)?(는|진|지는|지도|지|한다는|할 수)\s*(것은|건|게)?\s*(않|아니|없|못)"
    r"|(성과|효과|결과|성공|성능)(를|을)?\s*보장(하지|하진|하는 것은|하는 건|할 수는|할 순)"
    r"|(넓혀|확대해|일반화해|그대로)\s*(읽|해석|받아들|보|적용)[가-힣]*\s*(안\s*돼|안\s*되|면\s*안|지\s*말|기\s*어렵|선\s*안|서는\s*안)"
    r"|(범위|조건|환경|맥락|기준|안)(으로|에서|에서는)?만\s*(읽|해석|받아들|봐|보아|이해)"
    r"|(말할|단정할|장담할|기대할|일반화할)\s*수(는|가)?\s*없(어요|습니다|다|죠)\s*[.!]?\s*$"
    r"|(참고용|참고로만)\s*(으로)?\s*(읽|보|봐|삼)"
    r"|(신중하게|조심해서|주의해서)\s*(읽|해석|받아들|봐|보)")
# 한계 낱말: 역접으로 시작하는 문장에 이게 있으면 단서 문장으로 세요.
_LIMIT_WORDS = re.compile(r"범위|조건|전제|한계|일반화|일반 |보장|환경|표본|실험|검증|확인되지|아직|외부|실제 ")
CONTRAST_OPENER = re.compile(r"^\s*(다만|하지만|그러나|그렇지만|그런데|단,|단 |물론)")
_CAVEAT_HEADING = re.compile(r"한계|읽어야|만 읽|믿고 읽|어디까지 (믿|읽)")
# 근거가 말한 내용을 전하는 문장('근거는 ~받아들이기 어렵다고 말해요')은 면책이 아니라 내용이에요.
_REPORTED = re.compile(r"(다고|라고|다는|라는)\s*(말|보고|밝|설명|지적|정리|결론|주장|봐|본|점|뜻)")
_SENTENCES = re.compile(r"(?<=[.!?。])\s+|(?<=[요다])\s+(?=[가-힣A-Z\"“'‘(\[])")
CAVEAT_LIMITS = {"total": 2, "contrast_openers": 2}


def _body_sentences(body: str):
    """(구역 번호, 문장) 목록과 소제목 목록. 표 줄과 근거 표기는 빼요."""
    section, rows, headings = 0, [], []
    for line in str(body or "").splitlines():
        stripped = line.strip()
        if re.match(r"^#{1,6}\s", stripped):
            section += 1
            headings.append((section, re.sub(r"^#{1,6}\s*", "", stripped)))
            continue
        if not stripped or stripped.startswith("|"):
            continue
        text = CITE.sub("", re.sub(r"^\s*(?:[-*>]|\d+[.)])\s+", "", stripped)).strip()
        rows.extend((section, sentence.strip()) for sentence in _SENTENCES.split(text) if len(sentence.strip()) > 3)
    return rows, headings, section


def caveat_report(body: str) -> dict:
    """본문의 단서 문장, 면책 문장, 역접 시작 문장, 한계 소제목. 모델을 부르지 않아요."""
    rows, headings, last_section = _body_sentences(body)
    caveats, boilerplate, openers = [], [], []
    for section, sentence in rows:
        opener = CONTRAST_OPENER.match(sentence)
        if opener:
            openers.append((section, sentence))
        if BOILERPLATE.search(sentence) and not _REPORTED.search(sentence[BOILERPLATE.search(sentence).end():]):
            boilerplate.append((section, sentence))
            caveats.append((section, sentence))
        elif HEDGE.search(sentence) or (opener and _LIMIT_WORDS.search(sentence)):
            caveats.append((section, sentence))
    # 한계만 다루는 소제목은 글 끝 한 곳(마지막 소제목)이면 괜찮아요. 중간에 끼면 글이 경고문처럼 읽혀요.
    caveat_headings = [(section, text) for section, text in headings if _CAVEAT_HEADING.search(text) and section != last_section]
    return {"caveats": caveats, "boilerplate": boilerplate, "contrast_openers": openers, "caveat_headings": caveat_headings}


def caveat_issues(body: str) -> list[str]:
    """고치기로 보낼 지적. 문장을 그대로 짚어 줘서 고치는 모델이 다른 곳을 건드리지 않게 해요."""
    found = caveat_report(body)
    issues = []
    if found["boilerplate"]:
        listed = " / ".join(f"'{sentence[:60]}'" for _, sentence in found["boilerplate"][:6])
        issues.append(f"한계, 단서 문장이 독자에게 쓸모없는 면책 문장이에요({len(found['boilerplate'])}개): {listed}. 지우세요. "
                      "출처는 문장 주어('저자들은 ~라고 보고했어요')로 이미 드러나요")
    total = len(found["caveats"])
    if total > CAVEAT_LIMITS["total"]:
        listed = " / ".join(f"'{sentence[:40]}'" for _, sentence in found["caveats"][:6])
        issues.append(f"한계, 단서 문장이 {total}개예요(글 전체 2개까지): {listed}. 독자의 판단을 바꾸는 한계 하나만 남기고 나머지는 지우세요")
    for _, text in found["caveat_headings"]:
        issues.append(f"한계, 단서 문장만 다루는 소제목이 글 중간에 있어요: '## {text}'. 이 구역은 내용 설명으로 바꾸고, 남길 한계는 글 끝에 한 번만 쓰세요")
    if len(found["contrast_openers"]) > CAVEAT_LIMITS["contrast_openers"]:
        issues.append(f"'다만', '하지만'으로 시작하는 문장이 {len(found['contrast_openers'])}개예요(글 전체 2개까지). 앞 문장을 뒤집는 덧붙임 대신 한 문장으로 합치거나 지우세요")
    return issues
