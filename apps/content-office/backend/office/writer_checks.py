"""글쓰기 0원 검사: 인용 대조, 방향 대조, AI 상투 표현, 고친 뒤 사실 유지, 원문 베끼기 (2026-11-27).

v2_harness의 0원 규칙(Layer 1)에 붙는다. 모델을 부르지 않아 비용이 없다.
방식 출처(코드 복사 없음): github.com/wonseokjung/connect-ai-writer 커밋 9057798 (MIT + Commons Clause)의
lib/check.mjs quoteMatch, directionNear, directionClashes와 lib/humanize.mjs compare, banned.json.
원문 베끼기(copy_overlap)는 github.com/wonseokjung/reversebusiness 커밋 d4b4712 (MIT)의
skill/reversebusiness/tools/check-clone.mjs 방식(낱말 다섯 개가 연달아 같으면 겹침)을 원고와 근거 원문에 맞게 다시 썼다.
오프라인 검증(evals/writer_checks.py, 같은 규칙): 승인 원고 14편으로 만든 고장 초안 30개를 모두 잡았고
(기존 0원 검사는 0개), 고치지 않은 대조군 10개에서 오탐이 없었다(2026-11-26).

모드: 설정 writer_checks, 없으면 환경 변수 HEOBRAIN_WRITER_CHECKS, 없으면 off
  off      검사하지 않는다. 결과가 예전과 같다.
  warn     찾은 것을 quality.harness.writer_checks에만 적는다. 규칙 점수, 고치기, 되돌리기는 그대로다.
  enforce  quote_exact, direction_cited, ai_tells, fact_keep, copy_overlap을 규칙 점수와 고칠 목록에 넣는다.
           고친 판이 직전 판의 숫자, 인용, 영문 이름, 방향을 잃으면 하네스가 직전 판으로 되돌린다.

알려진 한계
  - 한국어 따옴표 말을 영어 근거와 대조하지 않는다(번역 인용은 세기만 한다).
  - 방향 단어 목록에 없는 말(빠르다, 느리다 등)은 못 잡는다. 뜻 전체는 판정 모델과 사람이 본다.
  - 원문 문단(source_quote 등)이 없는 근거는 인용 대조를 건너뛴다.
  - 저자 원문 보존 글은 본문을 고치지 않으므로 본문 검사를 하지 않고 파생 문구의 상투 표현만 본다.
  - 베끼기 검사는 따옴표 안의 말을 빼고 본다(따옴표 인용은 quote_exact 몫). 조사만 바꾼 베끼기는 못 잡는다.
"""
from __future__ import annotations

import os
import re

from .store import WorkflowError

MODES = ("off", "warn", "enforce")
RULES = ("quote_exact", "direction_cited", "ai_tells", "fact_keep", "copy_overlap", "tell_score")
_ORIGINAL_KEYS = ("source_quote", "quote", "excerpt", "text", "passage")
CITE_GROUP = re.compile(r"\[([A-Z]{1,3}\d{1,3}(?:\s*,\s*[A-Z]{1,3}\d{1,3})*)\]")
NUM = re.compile(r"(?<![\w.])(\d+(?:,\d{3})*(?:\.\d+)?)(?!\.?\d)")
SENT = re.compile(r"\n+|(?<=[.!?。])\s+(?=\S)")
QUOTE = re.compile(r"[\"“‘]([^\"“”‘’\n]{6,}?)[\"”’]")
ATTRIB = re.compile(r"^\s*(?:이?라고|이?라며|하고\s?(?:말|밝|적|썼|강조|설명))")
NAME = re.compile(r"\b[A-Z][A-Za-z0-9.+\-]{2,}\b|\b[A-Za-z]+[0-9]+[A-Za-z0-9]*\b")
NAME_STOP = frozenset({"The", "This", "That", "And", "But", "For", "With", "From", "What", "When", "How", "Why"})
# 기존 style_issues가 보는 줄표, '~라고 생각합니다', 훈계, 과장 광고(OVERCLAIM_PHRASES)는 여기서 다시 보지 않는다.
AI_TELLS = ("알아보겠습니다", "알아보도록 하겠습니다", "살펴보겠습니다", "살펴보도록 하겠습니다", "결론적으로", "요약하자면",
            "정리하자면", "되어집니다", "되어진", "하는 것이 가능합니다", "혁신적인", "획기적인", "게임 체인저", "게임체인저",
            "패러다임", "시너지", "극대화", "새로운 지평", "본 글에서는", "본 포스팅에서는", "도움이 되셨길")
WATCH = ("다양한", "효과적인", "효과적으로", "에 있어서", "이를 통해", "함으로써", "단순히")
# 사용자 요청(11/27 계획표): 서양식 비유는 한국 일상 소재로, 강한 표현은 근거에 있을 때만. 둘 다 알림만 한다.
WESTERN = ("산장", "벽난로", "오두막", "캠프파이어", "추수감사절", "와인 셀러")
STRONG = ("최고", "최초", "1위", "보장", "평생", "100%")
FORMAL = re.compile(r"(습니다|입니다|됩니다)[.!?…]*$")
HAEYO = re.compile(r"(요|죠)[.!?…]*$")
ENDING = re.compile(r"([가-힣]{1,3})[.!?…]*$")
UP_KO = ("증가", "늘었", "늘어", "늘고", "늘린", "늘리", "늘면", "올랐", "올라", "오른", "오르", "상승", "많아", "커졌", "커지",
         "높아", "확대", "급증", "성장", "뛰었", "향상")
DOWN_KO = ("감소", "줄었", "줄어", "줄고", "줄인", "줄이", "줄면", "내렸", "내려", "떨어", "하락", "적어", "작아", "낮아", "축소",
           "급감", "빠졌", "단축", "절감")
UP_EN = re.compile(r"\b(up|more|increase[sd]?|increasing|rise[sn]?|rose|rising|grew|grow[sn]?|growing|higher|gain(?:ed|s)?|"
                   r"jump(?:ed|s)?|surge[sd]?|improve[sd]?)\b", re.I)
DOWN_EN = re.compile(r"\b(down|less|fewer|decrease[sd]?|decreasing|drop(?:ped|s)?|fell|fall(?:en|s)?|falling|lower|decline[sd]?|"
                     r"shrank|shrunk|reduce[sd]?|reduction|cut)\b", re.I)


def resolve_writer_checks(store=None) -> str:
    """사람이 고른 모드. 설정 → 환경 변수 → off. 모르는 값은 off로 두지 않고 막는다."""
    value = (store.setting("writer_checks") if store is not None else None) or os.environ.get("HEOBRAIN_WRITER_CHECKS") or "off"
    if value not in MODES:
        raise WorkflowError(f"글쓰기 0원 검사 모드는 {', '.join(MODES)} 중 하나여야 합니다")
    return value


# ---------- 공통 ----------
def _norm(text):
    return re.sub(r"[\s\W_]+", "", (text or "").lower())


def _num(text):
    return text.replace(",", "").rstrip("0").rstrip(".") if "." in text else text.replace(",", "")


def cited_ids(text):
    return [item.strip() for group in CITE_GROUP.findall(text or "") for item in group.split(",")]


def numbers_in(text):
    plain = CITE_GROUP.sub(" ", text or "")
    plain = re.sub(r"https?://\S+", " ", plain)
    plain = re.sub(r"(?m)^\s*\d+[.)]\s", " ", plain)  # 목록 번호는 사실 숫자로 세지 않는다
    return {_num(match) for match in NUM.findall(plain)}


def _paragraphs(body):
    return [part for part in re.split(r"\n\s*\n", body or "") if part.strip()]


def _hangul_ratio(text):
    letters = re.findall(r"[가-힣A-Za-z]", text or "")
    return sum(1 for char in letters if "가" <= char <= "힣") / len(letters) if letters else 0.0


def evidence_sources(packet):
    """{근거 ID: (주장과 원문을 합친 글, 원문 문단이 있는지)}. 원문 문단이 없으면 인용 대조를 하지 않는다."""
    sources = {}
    for item in packet.get("evidence") or []:
        if not isinstance(item, dict) or not item.get("id"):
            continue
        originals = [item[key] for key in _ORIGINAL_KEYS if isinstance(item.get(key), str) and item[key].strip()]
        claim = item.get("claim") if isinstance(item.get("claim"), str) else ""
        sources[str(item["id"])] = (" ".join([claim, *originals]).strip(), bool(originals))
    return sources


# ---------- 인용 대조 ----------
def _bigrams(text):
    counts = {}
    for index in range(len(text) - 1):
        gram = text[index:index + 2]
        counts[gram] = counts.get(gram, 0) + 1
    return counts


def _dice(left, right):
    a, b = _bigrams(left), _bigrams(right)
    shared = sum(min(count, b.get(gram, 0)) for gram, count in a.items())
    total = sum(a.values()) + sum(b.values())
    return 2 * shared / total if total else 0.0


def quote_match(quote, source):
    """1이면 글자 그대로 있다(띄어쓰기, 문장부호 무시). 아니면 같은 길이 창을 밀며 두 글자 묶음 겹침의 최댓값."""
    q, s = _norm(quote), _norm(source)
    if not q:
        return 0.0
    if q in s:
        return 1.0
    best, length = 0.0, len(q)
    for index in range(0, max(1, len(s) - length + 5), 2):
        best = max(best, _dice(q, s[index:index + length + 2]))
    return best


def attributed_quotes(body):
    """인용 표지(~라고, ~라며)가 붙은 따옴표 말만 돌려준다. 강조용 따옴표는 대조하지 않는다."""
    found = []
    for paragraph in _paragraphs(body):
        ids = cited_ids(paragraph)
        for match in QUOTE.finditer(paragraph):
            if ATTRIB.match(paragraph[match.end():match.end() + 8]):
                found.append((match.group(1).strip(), ids, paragraph))
    return found


def quote_problems(body, sources):
    problems, translated, checked = [], 0, 0
    for quote, ids, _ in attributed_quotes(body):
        usable = [item for item in ids if item in sources and sources[item][1]]
        if not usable:
            continue  # 근거 번호가 없거나 원문 문단이 없는 근거는 근거 ID 검사와 판정 모델 몫이다
        source = " ".join(sources[item][0] for item in usable)
        if (_hangul_ratio(quote) > 0.5) != (_hangul_ratio(source) > 0.5):
            translated += 1
            continue
        checked += 1
        score = quote_match(quote, source)
        if score < 1:
            kind = "근거에 없는 인용" if score < 0.8 else "근거와 글자가 조금 다른 인용"
            problems.append(f"{kind}이에요: \"{quote[:40]}\" ({', '.join(usable)}, 일치 {round(score * 100)}%). 원문 그대로 옮기거나 따옴표 없이 풀어 쓰세요")
    return problems, translated, checked


# ---------- 방향 대조 ----------
def _direction_hits(window, at):
    hits = []
    for words, direction in ((UP_KO, "up"), (DOWN_KO, "down")):
        for word in words:
            index = window.find(word)
            while index >= 0:
                hits.append((abs(index - at), direction))
                index = window.find(word, index + 1)
    for pattern, direction in ((UP_EN, "up"), (DOWN_EN, "down")):
        for match in pattern.finditer(window):
            hits.append((abs(match.start() - at), direction))
    return hits


def direction_near(sentence, number):
    best = None
    for match in NUM.finditer(sentence):
        if _num(match.group(1)) != number:
            continue
        start, end = max(0, match.start() - 12), match.end() + 16
        for hit in _direction_hits(sentence[start:end], match.start() - start):
            if best is None or hit[0] < best[0]:
                best = hit
    return best[1] if best else None


def direction_clashes(text, source):
    source_sentences = [part for part in SENT.split(source or "") if part.strip()]
    clashes = []
    for sentence in SENT.split(CITE_GROUP.sub(" ", text or "")):
        for number in numbers_in(sentence):
            said = direction_near(sentence, number)
            if not said:
                continue
            there = [(part, direction_near(part, number)) for part in source_sentences if number in numbers_in(part)]
            there = [(part, direction) for part, direction in there if direction]
            if there and not any(direction == said for _, direction in there):
                clashes.append({"number": number, "said": said, "source": there[0][1], "sentence": sentence.strip()[:80]})
    return clashes


def direction_problems(body, sources):
    labels = {"up": "늘었다", "down": "줄었다"}
    problems = []
    for paragraph in _paragraphs(body):
        ids = [item for item in cited_ids(paragraph) if item in sources]
        if not ids:
            continue
        for clash in direction_clashes(paragraph, " ".join(sources[item][0] for item in ids)):
            problems.append(f"숫자 {clash['number']}의 방향이 근거와 반대예요: 원고는 '{labels[clash['said']]}', "
                            f"근거({', '.join(ids)})는 '{labels[clash['source']]}'예요. 문장: {clash['sentence']}")
    return problems


# ---------- 고친 뒤 사실 유지 ----------
def _names(text):
    return {word for word in NAME.findall(CITE_GROUP.sub(" ", text or "")) if word not in NAME_STOP}


def fact_keep(before, after, sources=None, allowed=()):
    """직전 판(before)의 숫자, 인용, 영문 이름이 사라졌거나 같은 숫자의 방향이 뒤집혔으면 잃은 것으로 센다.
    allowed: 고치라고 받은 문장. 그 안의 숫자, 인용, 이름은 빠져도 된다.
    sources: 직전 판에서 이미 근거와 안 맞던 숫자는 빠져도 된다(고친 결과일 수 있어서)."""
    allowed_text = " ".join(str(item) for item in allowed or ())
    may_drop = set(numbers_in(allowed_text))
    if sources:
        whole = numbers_in(" ".join(text for text, _ in sources.values()))
        for paragraph in _paragraphs(before):
            ids = [item for item in cited_ids(paragraph) if item in sources]
            cited = numbers_in(" ".join(sources[item][0] for item in ids)) if ids else None
            for number in numbers_in(paragraph):
                if number not in whole or (cited is not None and number not in cited):
                    may_drop.add(number)
    lost = [("숫자", number) for number in sorted(numbers_in(before) - numbers_in(after)) if number not in may_drop]
    for quote, _, _ in attributed_quotes(before):
        if _norm(quote) not in _norm(after) and quote not in allowed_text:
            lost.append(("인용", quote[:30]))
    lost += [("이름", name) for name in sorted(_names(before) - _names(after)) if name not in allowed_text]
    for clash in direction_clashes(after, before):
        lost.append(("방향", f"{clash['number']} {clash['source']}→{clash['said']}"))
    return lost


# ---------- 원문 베끼기 ----------
COPY_RUN = 5  # 낱말 다섯 개가 연달아 같으면 베낀 것으로 본다(reversebusiness 기본값)
COPY_RUN_LATIN = 8  # 한글이 없는 영어 구간은 용어·제목이 많아 여덟 개부터 본다(운영 원고 14편 대조, 2026-11-27)
# 낱말: 숫자+단위(40점, 2026년, 15%), 영문 덩어리(route-to-sink 같은 붙임표 용어는 한 낱말), 한글 덩어리.
WORD = re.compile(r"[0-9]+(?:[.,][0-9]+)*[가-힣%]*|[a-z]+(?:[-'’][a-z0-9]+)*[0-9]*|[가-힣]+|[぀-ヿ一-鿿]+")
ANY_QUOTE = re.compile(r"[\"“‘「『][^\"“”‘’「」『』\n]*[\"”’」』]")


def _tokens(text):
    """(낱말, 시작, 끝). 소문자로 비교하고, 보여 줄 때는 원래 글자를 쓴다."""
    return [(match.group(0), match.start(), match.end()) for match in WORD.finditer((text or "").lower())]


def _meaningful(run):
    """숫자로 시작하는 낱말과 한 글자 낱말이 절반을 넘는 구간(날짜, 목록 번호)은 베끼기로 세지 않는다."""
    thin = sum(1 for word in run if word[0].isdigit() or len(word) == 1)
    return thin * 2 < len(run)


def copy_runs(text, original, size=COPY_RUN):
    """text 안에서 original과 낱말 size개 이상 연달아 같은 구간들. 겹치는 구간은 하나로 묶고 text의 원래 글자로 돌려준다."""
    mine, theirs = _tokens(text), [word for word, _, _ in _tokens(original)]
    words = [word for word, _, _ in mine]
    if len(words) < size or len(theirs) < size:
        return []
    grams = {tuple(theirs[index:index + size]) for index in range(len(theirs) - size + 1)}
    runs, index = [], 0
    while index <= len(words) - size:
        if tuple(words[index:index + size]) in grams:
            end = index + size
            while end < len(words) and tuple(words[end - size + 1:end + 1]) in grams:
                end += 1
            run = words[index:end]
            latin_only = not any(re.search(r"[가-힣぀-ヿ一-鿿]", word) for word in run)
            if _meaningful(run) and (not latin_only or len(run) >= COPY_RUN_LATIN):
                runs.append(text[mine[index][1]:mine[end - 1][2]])
            index = end
        else:
            index += 1
    return runs


def copy_problems(body, packet):
    """따옴표 밖 본문이 근거 원문 문단(source_quote 등)과 낱말 다섯 개 이상 연달아 같으면 알린다.
    오너가 직접 쓴 글(source_kind=owner_supplied)은 내 글이라 베끼기로 보지 않는다."""
    text = ANY_QUOTE.sub(" ", CITE_GROUP.sub(" ", body or ""))
    problems = []
    for item in packet.get("evidence") or []:
        if not isinstance(item, dict) or not item.get("id") or item.get("source_kind") == "owner_supplied":
            continue
        original = " ".join(item[key] for key in _ORIGINAL_KEYS if isinstance(item.get(key), str))
        for run in copy_runs(text, original)[:2]:
            problems.append(f"근거 {item['id']} 원문과 낱말 {len(_tokens(run))}개가 연달아 같아요: \"{run[:50]}\". "
                            "따옴표로 인용하거나 내 말로 풀어 쓰세요")
    return problems


# ---------- AI 상투 표현 ----------
def _overclaims():
    try:
        from .editorial import OVERCLAIM_PHRASES
    except ImportError:  # 단독 검사에서는 기존 목록이 없을 수 있다
        return ()
    return OVERCLAIM_PHRASES


def tell_problems(texts):
    joined = "\n".join(text for text in texts if isinstance(text, str))
    covered = set(_overclaims())
    problems = [f"AI가 쓴 티가 나는 표현 '{phrase}'은(는) 쓰지 않아요. 말하듯 바꾸세요" for phrase in AI_TELLS
                if phrase not in covered and phrase in joined]
    notes = [f"자주 보이는 표현 '{phrase}'" for phrase in WATCH if phrase in joined]
    dots = joined.count("·")
    if joined and dots * 1000 / len(joined) > 3:
        notes.append(f"중간점 {dots}개(1,000자당 {round(dots * 1000 / len(joined), 1)}개)")
    can = len(re.findall(r"할\s?수\s?있습니다", joined))
    if can >= 3:
        notes.append(f"'~할 수 있습니다' {can}번")
    return problems, notes


def _sentences(text):
    rows = [part.strip() for part in SENT.split(CITE_GROUP.sub(" ", text or ""))]
    return [row for row in rows if len(row) >= 4 and not row.startswith(("#", "|", "-", "*", ">"))]


def rhythm_notes(text, evidence_text=""):
    """말투 리듬(connect-ai-writer humanize의 리듬 검사 방식): 같은 끝이 4번, 해요체 사이 습니다체, 비슷한 문장 길이.
    모두 알림이고 막지 않는다."""
    notes, sentences = [], _sentences(text)
    endings = [match.group(1) for sentence in sentences if (match := ENDING.search(re.sub(r"[\"'”’)\]]+$", "", sentence)))]
    run = 1
    for before, after in zip(endings, endings[1:]):
        run = run + 1 if after == before else 1
        if run == 4:
            notes.append(f"같은 문장 끝 '{after}': 4번 이어져요. 끝맺음을 바꿔 보세요")
            break
    formal = sum(1 for sentence in sentences if FORMAL.search(sentence))
    haeyo = sum(1 for sentence in sentences if HAEYO.search(sentence))
    if formal >= 2 and haeyo >= formal:
        notes.append(f"해요체 사이에 습니다체 문장 {formal}개가 섞였어요")
    lengths = [len(sentence) for sentence in sentences]
    if len(lengths) >= 8:
        mean = sum(lengths) / len(lengths)
        spread = (sum((length - mean) ** 2 for length in lengths) / len(lengths)) ** 0.5
        if mean and spread / mean < 0.2:
            notes.append("문장 길이가 거의 같아요. 짧은 문장과 긴 문장을 섞으세요")
    notes += [f"서양식 비유 '{word}': 한국 일상 소재로 바꿔 보세요" for word in WESTERN if word in text]
    notes += [f"강한 표현 '{word}': 근거에서 찾지 못했어요" for word in STRONG if word in text and word not in (evidence_text or "")]
    return notes


def tell_score(text):
    """AI 티 점수(1,000자당): 상투 표현 3점, 자주 보이는 표현 1점. 막지 않고 고친 뒤 올랐는지만 본다."""
    if not text:
        return 0.0
    points = sum(3 * text.count(phrase) for phrase in AI_TELLS) + sum(text.count(phrase) for phrase in WATCH)
    return round(points * 1000 / len(text), 2)


def number_trace(body, sources, limit=40):
    """승인① 화면의 숫자 출처 표: 문단의 숫자마다 그 문단이 단 근거에 같은 숫자가 있는지. 막지 않는다."""
    rows = []
    for paragraph in _paragraphs(body):
        ids = [item for item in cited_ids(paragraph) if item in sources]
        for sentence in SENT.split(paragraph):
            for number in sorted(numbers_in(sentence)):
                found = next((item for item in ids if number in numbers_in(sources[item][0])), None)
                rows.append({"number": number, "sentence": re.sub(r"\s+([.!?])", r"\1", CITE_GROUP.sub("", sentence)).strip()[:90], "cited": ids, "found_in": found})
                if len(rows) >= limit:
                    return rows
    return rows


def _texts(packet, preserve):
    try:
        from .editorial import packet_texts
        source = {**packet, "body": ""} if preserve else packet
        return list(packet_texts(source))
    except ImportError:
        return [] if preserve else [packet.get("body") or ""]


def writer_findings(packet, *, previous_body=None, allowed_sentences=()):
    """규칙별 문제 목록과 막지 않는 알림. 모델 호출은 없다."""
    preserve = packet.get("preserve_original") is True
    body = packet.get("body") or ""
    sources = evidence_sources(packet)
    issues = {name: [] for name in RULES}
    translated = checked = 0
    if not preserve:
        issues["quote_exact"], translated, checked = quote_problems(body, sources)
        issues["direction_cited"] = direction_problems(body, sources)
        issues["copy_overlap"] = copy_problems(body, packet)
        if isinstance(previous_body, str) and previous_body and previous_body != body:
            lost = fact_keep(previous_body, body, sources, allowed_sentences)
            if lost:
                issues["fact_keep"].append("고친 판이 직전 판에 있던 사실을 잃었어요: " + ", ".join(f"{kind} {value}" for kind, value in lost[:8]))
            before, after = tell_score(previous_body), tell_score(body)
            if after > before + 0.5:
                issues["tell_score"].append(f"고친 판이 AI 티 점수가 올랐어요(1,000자당 {before} → {after}). 직전 판 말투로 돌아가세요")
    texts = _texts(packet, preserve)
    issues["ai_tells"], notes = tell_problems(texts)
    notes += rhythm_notes("\n".join(texts), " ".join(text for text, _ in sources.values()))
    trace = [] if preserve else number_trace(body, sources)
    return {"issues": issues, "notes": notes, "quotes_checked": checked, "quotes_translated": translated,
            "tell_score": tell_score(body), "number_trace": trace}


def apply_writer_checks(result, packet, *, mode, previous_body=None, allowed_sentences=()):
    """validate_packet 결과에 붙인다. warn은 기록만, enforce는 규칙 점수와 고칠 목록에 넣는다."""
    if mode not in ("warn", "enforce"):
        return result
    findings = writer_findings(packet, previous_body=previous_body, allowed_sentences=allowed_sentences)
    result = {**result, "writer_checks": {"mode": mode, **findings}}
    if mode == "enforce":
        problems = [problem for name in RULES for problem in findings["issues"][name]]
        scores = {**result["rule_scores"], **{name: not findings["issues"][name] for name in RULES}}
        issues = list(dict.fromkeys([*result["issues"], *problems]))
        result.update(rule_scores=scores, issues=issues, passed=not issues,
                      warnings=[issue for issue in issues if issue not in result["blocking"]] + list(result.get("notes") or []))
    return result
