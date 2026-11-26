"""외부 조사: 주제가 어떤 주장을 하는지 보고 외부 조사가 필요한지 정하고, 무료 공개 출처에서 후보를 찾는다.

- 후보는 PubMed, OpenAlex, arXiv, GitHub의 공개 검색 API와 등록된 RSS에서만 찾는다. 이 모듈은 모델을 부르지 않는다.
  한글 주제의 영어 검색어는 호출한 쪽이 translate로 넘겨 준 함수(research_query)가 만들고, 없으면 낱말표를 쓴다.
- 찾은 것은 후보일 뿐이다. 운영자가 고른 것만 자료 창고에 들어가고 근거로 켜진다. 승인⓪①②③을 만들거나 대신하지 않는다.
- 자료는 두 칸으로 나눈다. fact(사실 근거: 공식 문서·논문·기관 공고)와 example(사례·참고: 운영자가 등록한 크리에이터).
- 글 유형(W1~W5)은 운영자가 고른다. 고르기 전에 제목으로 추측한 유형은 기본값으로만 보여 주고 조사 칸을 바꾸지 않는다.
"""
from __future__ import annotations

import hashlib
import json
import math
import os
import re
import secrets
import sqlite3
import unicodedata
from concurrent.futures import ThreadPoolExecutor
from contextlib import closing
from datetime import datetime, timezone
from pathlib import Path
from time import monotonic
from urllib.parse import quote_plus, urljoin, urlsplit

import requests

from .evidence_relevance import is_topic_candidate
from .feeds import fetch_public, normalize_url, parse_feed
from .source_library import AREAS, LANES, _clean, _connect, _now, _safe_xml, library_path
from .source_registry import load_sources
from .store import WorkflowError

SEARCH_SECONDS = 10
PER_PROVIDER = 4
MAX_TRUSTED = 60
_FEED_TTL = 600.0
_feed_cache: dict[str, tuple[float, list[dict]]] = {}
_ERRORS = (ValueError, OSError, requests.RequestException, KeyError, TypeError, AttributeError)

_CLAIMS = (
    ("research", "연구·효과", re.compile(r"뇌|기억|집중|인지|수면|도파민|연구|논문|실험|효과|과학적|심리학|사실일까|맞을까|근거 ?있|neuro|brain|memory|cognit", re.I)),
    ("fresh", "최신 정보", re.compile(r"버전|가격|요금|출시|업데이트|신기능|새 기능|비교|차이|\bvs\b|무료|유료|플랜|지원 종료|\bv?\d+\.\d+\b", re.I)),
    ("schedule", "일정·기준", re.compile(r"일정|접수|원서|합격 ?(?:기준|률|선)|응시료|시험일|개정|커트라인|응시 ?자격|정책|약관|규정|저작권|상업 ?(?:적|이용)|수익 ?창출|시행")),
    ("number", "수치", re.compile(r"\d+(?:\.\d+)?\s?(?:%|퍼센트|배|만 ?원|명|점)")),
    ("howto", "방법·사례", re.compile(r"방법|루틴|후기|꿀팁|노하우|하는 법|따라 ?하기|사용법|활용법|세팅|설정|가이드|팁")),
)
_AREA_HINTS = (
    ("A", re.compile(r"시험|자격증|산업기사|기사 ?(?:필기|실기)|토익|오픽|수능|편입|필기|실기|공무원|합격|(?i:\bopic\b|toeic|toefl|ielts)")),
    ("B", re.compile(r"(?<![A-Za-z0-9])(?:AI|MCP|RAG|API|TTS)(?![A-Za-z0-9])|GPT|Claude|Gemini|LLM|에이전트|자동화|Hermes|OpenClaw|프롬프트|n8n|코딩|챗봇|인공지능"
                     r"|OpenAI|옵시디언|Obsidian|노션|Notion|NotebookLM|Cursor|Perplexity|Zapier|Copilot|Codex|Lovable|Veo|Sora|Kling|Momentic"
                     r"|CodeRabbit|AGENTS\.md|ChatGPT|챗GPT|클로드|제미나이|퍼플렉시티|바이브 ?코딩|딥러닝|머신러닝|MoneyPrinter"
                     r"|(?<![A-Za-z0-9])(?-i:Make)(?![A-Za-z0-9])", re.I)),
    ("C", re.compile(r"뇌|기억|집중|학습|공부법|암기|복습|인지|수면|도파민|카페인|커피|졸음|낮잠|잠들기|자기 ?전(?:에|까지)|공부|포모도로|뽀모도로|백색 ?소음|멀티태스킹")),
    ("E", re.compile(r"꿀팁|생활|정리 ?정돈|집 ?정리|청소|절약|요리|살림|수리|고장")),
)
_AREA_FACT = {"A": ("official",), "B": ("official", "github", "arxiv"), "C": ("pubmed", "openalex"),
              "D": ("pubmed", "openalex"), "E": ("official",)}
_CLAIM_FACT = {"research": ("pubmed", "openalex"), "fresh": ("official", "github"), "schedule": ("official",)}
# Stable starting points for known exam entities. These links are candidates until the relevant section is reviewed.
_EXAM_OFFICIAL_PAGES = (
    (re.compile(r"오픽|\bopic\b", re.I), "OPIc 공식 평가 등급체계",
     "https://www.opic.co.kr/opics/servlet/controller.opic.site.about.AboutServlet?p_nav=3_1_1&p_process=move-page-valClass"),
    (re.compile(r"정보처리\s*기사"), "Q-Net 정보처리기사 종목 안내",
     "https://www.q-net.or.kr/crf005.do?id=crf00503&jmCd=1320&tabGbn=1"),
)
PROVIDERS = {"pubmed": "PubMed 논문", "openalex": "OpenAlex 공개 논문", "arxiv": "arXiv 논문", "github": "GitHub 저장소",
             "official": "공식 출처 새 글", "creator": "등록한 크리에이터", "tavily": "Tavily 검색"}
# 한글 주제를 영어 논문·저장소 검색어로 옮길 때 쓰는 작은 낱말표. 여기에 없는 말은 운영자가 검색어를 직접 고친다.
_GLOSSARY = {
    "동기화": "sync", "뽀모도로": "pomodoro", "백색소음": "white noise", "백색 소음": "white noise", "회고": "retrospective",
    "스마트폰": "smartphone", "블루라이트": "blue light", "미루는": "procrastination", "수익 창출": "monetization", "저작권": "copyright",
    "상업적 이용": "commercial use", "요금": "pricing", "보안": "security", "권한": "permission",
    "간격 복습": "spaced repetition", "분산 학습": "distributed practice", "인출": "retrieval practice", "복습": "review learning",
    "암기": "memorization", "기억력": "memory", "기억": "memory", "작업 기억": "working memory", "집중력": "attention", "집중": "attention",
    "수면": "sleep", "낮잠": "nap", "도파민": "dopamine", "습관": "habit formation", "미루기": "procrastination", "동기": "motivation",
    "스트레스": "stress", "불안": "anxiety", "운동": "exercise", "명상": "meditation", "마음챙김": "mindfulness", "멀티태스킹": "multitasking",
    "학습": "learning", "공부": "learning", "시험": "exam", "필기": "note-taking", "독서": "reading", "자기 효능감": "self-efficacy",
    "성장 마인드셋": "growth mindset", "마인드셋": "mindset", "몰입": "flow state", "의지력": "self-control", "목표": "goal setting",
    "뇌": "brain", "신경가소성": "neuroplasticity", "인지": "cognition", "카페인": "caffeine", "휴식": "rest break", "포모도로": "pomodoro",
    "에이전트": "agent", "자동화": "automation", "프롬프트": "prompt", "검색 증강": "retrieval augmented generation", "임베딩": "embedding",
    "파인튜닝": "fine-tuning", "환각": "hallucination", "멀티 에이전트": "multi-agent", "코딩": "coding", "챗봇": "chatbot",
}
_STOP = {"방법", "하는", "하기", "위한", "그리고", "에서", "으로", "대한", "정리", "총정리", "완벽", "가이드", "이유", "차이", "비교", "추천",
         "the", "and", "for", "with", "how", "what", "why", "you", "your", "from", "this", "that", "are", "use", "using", "new"}
_PARTICLE = re.compile(r"(?<=[가-힣])(?:에서|으로|에게|이|가|은|는|을|를|에|의|로|와|과|도)$")
_SCHEMA = """
CREATE TABLE IF NOT EXISTS trusted_sources(
  id TEXT PRIMARY KEY, name TEXT NOT NULL, url TEXT NOT NULL, feed_url TEXT NOT NULL UNIQUE,
  area TEXT NOT NULL, lane TEXT NOT NULL, created_at TEXT NOT NULL);
"""


def guess_area(text: str) -> str:
    return next((area for area, pattern in _AREA_HINTS if pattern.search(text)), "D")


# 글 유형. 사람이 기획 카드에서 고른다. 고르기 전에는 제목으로 추측한 값을 기본값으로만 보여 준다.
KINDS = {"W1": "비교·벤치마킹", "W2": "공식 발표·공고 해설", "W3": "근거형 설명", "W4": "내 경험 후기", "W5": "범위 밖"}
_KIND_HINTS = (
    ("W5", re.compile(r"복용량|처방|먹어도 ?되|매수|매도|종목 ?추천")),  # 추측해도 조사 칸은 그대로다. 사람이 W5로 골라야 막힌다.
    ("W1", re.compile(r"비교|차이|\bvs\b|대안|벤치마크|벤치마킹|순위|고르는 ?법|뭐가 ?(?:나을|좋을)|어떤 ?게 ?(?:나을|좋을)", re.I)),
    ("W4", re.compile(r"후기|해 ?본|해 ?봤|써 ?본|써 ?보니|겪은|경험담|회고|수기|느낀 ?(?:것|점)|배운 ?것|그만두고"
                      r"|(?<![가-힣])(?:내가|제가|나의|내)(?![가-힣])")),
    ("W2", re.compile(r"발표(?! ?자료)|출시|공고|개정|시행|변경 ?사항|업데이트|새 ?기능|신기능|릴리스|\brelease\b|접수 ?일정|원서 ?접수|시험 ?일정", re.I)),
)
# 유형마다 글을 쓰기 전에 채울 빈칸. 조사 결과를 이 빈칸에 맞춰 보고, 보충 조사를 할 때도 이 빈칸만 묻는다.
_KIND_BLANKS = {
    "W1": ("비교할 대상과 버전", "비교 기준(가격, 기능, 난이도 등)", "대상마다 공식 문서나 원문", "가격과 버전을 확인한 날짜", "써 본 사람의 사례"),
    "W2": ("발표나 공고 원문", "발표한 곳과 날짜", "무엇이 바뀌었는지", "누구에게 영향이 있는지", "언제부터 적용되는지"),
    "W3": ("글의 핵심 주장", "주장을 받치는 연구나 공식 자료", "반대 근거나 한계", "독자가 따라 할 방법"),
    "W4": ("내가 한 일", "기간과 조건", "결과(숫자는 내 기록이 있을 때만)", "막혔던 점과 바꾼 점"),
    "W5": (),
}


def guess_kind(text: str) -> str:
    return next((kind for kind, pattern in _KIND_HINTS if pattern.search(unicodedata.normalize("NFKC", text or ""))), "W3")


def _apply_kind(plan: dict, kind: str) -> None:
    """사람이 고른 글 유형에 맞게 조사 칸을 고친다. W3은 주장 기준 그대로이고, W4는 '내 경험 중심'과 같다."""
    if kind == "W5":
        reason = "범위 밖 주제로 골라서 조사하지 않아요."
        plan.update(blocked=True, fact={"need": "none", "reason": reason, "providers": []}, example={"need": "none", "reason": reason})
    elif kind == "W2":
        plan["fact"] = {"need": "required", "reason": "발표나 공고를 풀어 쓰는 글이라 원문 확인이 꼭 필요해요.",
                        "providers": list(dict.fromkeys(["official", *plan["fact"]["providers"]]))}
        plan["example"] = {"need": "none", "reason": "원문이 먼저인 글이라 다른 사람 사례는 찾지 않아요."}
    elif kind == "W1":
        if plan["fact"]["need"] == "none":
            plan["fact"] = {"need": "recommended", "reason": "비교 글은 대상마다 공식 자료를 한 번 확인하는 게 좋아요.",
                            "providers": ["official", "github"] if plan["area"] == "B" else ["official"]}
        if plan["example"]["need"] == "none":
            plan["example"] = {"need": "recommended", "reason": "비교 글은 써 본 사람의 사례가 있으면 고르기 쉬워져요."}


def research_plan(title: str, summary: str = "", *, area: str | None = None, kind: str | None = None,
                  experience_first: bool = False) -> dict:
    """주제의 주장 종류와 분야, 사람이 고른 글 유형을 보고 어느 칸을 조사해야 하는지 정한다. 네트워크를 쓰지 않는다."""
    kind_guessed = kind not in KINDS
    if kind_guessed and experience_first:
        kind, kind_guessed = "W4", False  # '내 경험 중심' 스위치는 사람이 켠 것이라 고른 값으로 본다.
    elif kind_guessed:
        kind = guess_kind(f"{title or ''}\n{summary or ''}")
    experience_first = bool(experience_first) or (kind == "W4" and not kind_guessed)
    text = unicodedata.normalize("NFKC", f"{title or ''}\n{summary or ''}")
    guessed = area not in AREAS
    area = guess_area(text) if guessed else area
    claims = [{"id": key, "label": label} for key, label, pattern in _CLAIMS if pattern.search(text)]
    found = {claim["id"] for claim in claims}
    hard = [claim["label"] for claim in claims if claim["id"] != "howto"]
    plan = {"area": area, "area_label": AREAS[area], "area_guessed": guessed, "experience_first": bool(experience_first),
            "claims": claims, "warning": None}
    plan.update(kind=kind, kind_label=KINDS[kind], kind_guessed=kind_guessed, blanks=list(_KIND_BLANKS[kind]), blocked=False,
                needs_experience_source=kind == "W4" and not kind_guessed)
    if experience_first:
        if found & {"number", "research"}:
            plan["warning"] = "내 경험 중심 글이지만 수치나 연구 주장이 보여요. 그 부분은 근거를 붙이거나 내 경험으로 표현을 바꿔 주세요."
        plan["fact"] = {"need": "none", "reason": "내 경험 중심 글이라 외부 조사를 하지 않아요.", "providers": []}
        # 내 경험 글도 보조 근거는 찾는다. 원문은 그대로 두고, 사례 칸 자료만 참고 목록으로 붙인다(2026-11-26 사용자 승인).
        plan["example"] = {"need": "recommended", "reason": "내 경험 글이라 원문은 그대로 두고, 다른 사람 사례만 참고 목록으로 붙여요."}
    else:
        providers = list(dict.fromkeys([name for key in ("research", "fresh", "schedule") if key in found for name in _CLAIM_FACT[key]]
                                       + list(_AREA_FACT[area])))
        if hard:
            fact = {"need": "required", "reason": f"{', '.join(hard)} 주장이 있어서 사실 근거가 꼭 필요해요."}
        elif area == "C":
            fact = {"need": "required", "reason": "학습법과 뇌과학 글은 논문 근거가 꼭 필요해요."}
        elif area in ("A", "B"):
            fact = {"need": "recommended", "reason": f"{AREAS[area]} 글은 공식 출처를 한 번 확인하는 게 좋아요."}
        else:
            fact = {"need": "none", "reason": "수치나 연구 주장이 없어서 사실 조사는 건너뛰어요."}
        plan["fact"] = {**fact, "providers": providers if fact["need"] != "none" else []}
        if "howto" in found or area in ("B", "D", "E"):
            plan["example"] = {"need": "recommended", "reason": "해 본 사람의 방법과 사례가 있으면 글이 살아나요."}
        else:
            plan["example"] = {"need": "none", "reason": "사례보다 정확한 근거가 중요한 주제예요."}
    if not kind_guessed:
        _apply_kind(plan, kind)
    order = ("none", "recommended", "required")
    plan["need"] = max(plan["fact"]["need"], plan["example"]["need"], key=order.index)
    label = {"required": "외부 조사 필수", "recommended": "외부 조사 권장", "none": "외부 조사 안 함"}[plan["need"]]
    lead = plan["fact"] if plan["fact"]["need"] != "none" or plan["example"]["need"] == "none" else plan["example"]
    plan["summary"] = f"{label}: {lead['reason']}"
    return plan


def build_queries(title: str, query: str | None = None) -> dict:
    """영어 검색어(논문·저장소용)와 낱말 목록(RSS 글 고르기용)을 만든다. 운영자가 적은 검색어가 있으면 그것을 쓴다."""
    text = unicodedata.normalize("NFKC", title or "")
    custom = _clean(query or "")[:200]
    english = re.findall(r"[A-Za-z][A-Za-z0-9.+#-]{1,}", custom or text)
    translated = []
    if not custom:
        rest = text
        for korean, word in sorted(_GLOSSARY.items(), key=lambda pair: -len(pair[0])):
            compact = korean.replace(" ", "")
            if korean in rest or compact in rest:
                translated.append(word)
                rest = rest.replace(korean, " ").replace(compact, " ")
    english_query = " ".join(dict.fromkeys(word for word in [*english, *translated] if word.casefold() not in _STOP))[:200]
    words = []
    for word in re.findall(r"[^\W_]{2,}", f"{text} {custom} {' '.join(translated)}".casefold()):
        stem = _PARTICLE.sub("", word)
        words.append(stem if len(stem) >= 2 else word)
    names = " ".join(dict.fromkeys(word for word in english if word.casefold() not in _STOP))[:200]  # 제목에 적힌 제품·도구 이름
    return {"english": english_query, "names": names, "terms": [word for word in dict.fromkeys(words) if word not in _STOP][:24],
            "custom": bool(custom)}


# 이 낱말만으로 된 영어 검색어는 주제를 좁히지 못한다. 제품, 도구 이름이나 구체적인 개념이 하나라도 있으면 쓴다.
_GENERIC_ENGLISH = {"ai", "app", "apps", "tool", "tools", "agent", "agents", "learning", "study", "tips", "guide", "review",
                    "review learning", "coding", "automation", "productivity", "work", "data", "model", "models"}


def _too_generic(english: str) -> bool:
    words = [word for word in re.findall(r"[a-z0-9.+#-]+", (english or "").casefold()) if word]
    return bool(words) and all(word in _GENERIC_ENGLISH for word in words)


def _candidate(lane, provider, title, url, snippet="", year=None, source=None) -> dict | None:
    title, url = _clean(str(title or ""))[:240], str(url or "").strip()
    parts = urlsplit(url)
    if not title or parts.scheme != "https" or not parts.hostname or len(url) > 2048:
        return None
    host = parts.hostname.lower().removeprefix("www.").removeprefix("m.")
    return {"key": hashlib.sha256(normalize_url(url).encode()).hexdigest()[:20], "lane": lane, "provider": provider,
            "provider_label": source or PROVIDERS[provider], "title": title, "url": url, "snippet": _clean(str(snippet or ""))[:320],
            "year": year if isinstance(year, int) else None, "needs_paste": host in ("youtube.com", "youtu.be")}


def _json(fetch, url):
    return json.loads(fetch(url, maximum=1_500_000)[0].decode("utf-8"))


def _year(value) -> int | None:
    text = str(value or "")[:4]
    return int(text) if text.isdigit() else None


def _pubmed(fetch, english, alternatives=()):
    base = "https://eutils.ncbi.nlm.nih.gov/entrez/eutils/"
    ids = []
    for query in (english, *alternatives[:2]):  # PubMed는 낱말을 모두 담은 논문만 찾는다. 없으면 같이 만든 다른 검색어로 넘어간다.
        found = _json(fetch, f"{base}esearch.fcgi?db=pubmed&retmode=json&retmax={PER_PROVIDER}&sort=relevance&term={quote_plus(query)}")
        ids = [value for value in found["esearchresult"].get("idlist", []) if str(value).isdigit()][:PER_PROVIDER]
        if ids:
            break
    if not ids:
        return []
    rows = _json(fetch, f"{base}esummary.fcgi?db=pubmed&retmode=json&id={','.join(ids)}")["result"]
    results = []
    for ident in ids:
        row = rows.get(ident) or {}
        date = str(row.get("pubdate") or "")
        results.append(_candidate("fact", "pubmed", row.get("title"), f"https://pubmed.ncbi.nlm.nih.gov/{ident}/",
                                  " · ".join(part for part in (row.get("source"), date) if part), _year(date)))
    return results


def _openalex(fetch, english):
    data = _json(fetch, "https://api.openalex.org/works?search=" + quote_plus(english) + "&filter=open_access.is_oa:true,type:article"
                 f"&per-page={PER_PROVIDER}&select=title,publication_year,doi,open_access,primary_location,cited_by_count")
    results = []
    for row in data.get("results", []):
        location = row.get("primary_location") or {}
        open_url = (row.get("open_access") or {}).get("oa_url") or ""
        readable = "ncbi.nlm.nih.gov" in open_url and not open_url.lower().endswith(".pdf")
        url = open_url if readable else location.get("landing_page_url") or row.get("doi")
        journal = (location.get("source") or {}).get("display_name")
        cited = row.get("cited_by_count")
        results.append(_candidate("fact", "openalex", row.get("title"), url,
                                  " · ".join(part for part in (journal, f"인용 {cited:,}회" if isinstance(cited, int) else None) if part),
                                  row.get("publication_year")))
    return results


def _arxiv(fetch, english):
    # 낱말을 모두 담은 컴퓨터과학 논문만 찾는다. 낱말 하나만 같은 다른 분야 논문이 섞이지 않게 한다.
    words = "+AND+".join("all:" + quote_plus(word) for word in english.split()[:6])
    raw = fetch(f"https://export.arxiv.org/api/query?search_query={words}+AND+cat:cs.*"
                f"&start=0&max_results={PER_PROVIDER}&sortBy=relevance", maximum=1_500_000)[0]
    space = "{http://www.w3.org/2005/Atom}"
    results = []
    for entry in _safe_xml(raw).iter(space + "entry"):
        match = re.search(r"arxiv\.org/abs/(\d{4}\.\d{4,5})", entry.findtext(space + "id") or "")
        if match:
            results.append(_candidate("fact", "arxiv", entry.findtext(space + "title"), f"https://arxiv.org/abs/{match.group(1)}",
                                      entry.findtext(space + "summary"), _year(entry.findtext(space + "published"))))
    return results


def _github(fetch, english):
    """이름이 한두 개면(제품 비교 글) 이름마다 별이 가장 많은 저장소를, 낱말이 많으면 낱말을 모두 담은 저장소를 찾는다."""
    names = [word for word in english.split() if len(word) >= 3]
    searches = [f"{quote_plus(name)}+in:name&sort=stars&order=desc&per_page=3" for name in names] if 1 <= len(names) <= 3 \
        else [f"{quote_plus(english)}&per_page=8"]
    results, seen = [], set()
    for search in searches:
        picked = 0
        for row in _json(fetch, "https://api.github.com/search/repositories?q=" + search).get("items", []):
            stars = row.get("stargazers_count")
            if not isinstance(stars, int) or stars < 50 or row.get("archived") or row.get("html_url") in seen:
                continue
            seen.add(row.get("html_url"))
            pushed = str(row.get("pushed_at") or "")
            results.append(_candidate("fact", "github", row.get("full_name"), row.get("html_url"),
                                      f"{row.get('description') or ''} · 별 {stars:,}개" + (f" · {pushed[:10]} 갱신" if pushed else ""),
                                      _year(pushed)))
            picked += 1
            if len(searches) > 1 and picked == 2:
                break
    return results[:PER_PROVIDER]


def _feed_entries(fetch, source) -> list[dict]:
    cached = _feed_cache.get(source["feed_url"])
    if cached and monotonic() - cached[0] < _FEED_TTL:
        return cached[1]
    raw = fetch(source["feed_url"], maximum=3_000_000)[0]
    entries = [{"title": row["title"], "url": row["url"], "summary": row.get("summary") or "", "published_at": row.get("published_at") or "",
                "source": source["name"]} for row in parse_feed(raw, {"id": "research", "name": source["name"]})[:60]]
    _feed_cache[source["feed_url"]] = (monotonic(), entries)
    return entries


def _pick_feed_entries(entries, terms, lane, provider):
    """등록된 출처의 새 글 가운데 주제 낱말이 맞는 글만 고른다. 어느 글에나 나오는 흔한 낱말만 맞은 글은 버린다."""
    if not entries or not terms:
        return []
    texts = [f"{entry['title']} {entry['summary']}".casefold() for entry in entries]
    frequency = {term: sum(term in text for text in texts) for term in terms}
    rare = max(1, len(texts) * 0.3)
    scored = []
    for entry, text in zip(entries, texts):
        matched = [term for term in terms if term in text]
        # 제목 낱말이 셋 이상이면 두 낱말 이상 맞아야 한다. "ChatGPT" 한 낱말만 맞은 다른 주제 새 글을 거른다(2026-11-27 운영 실측).
        # "ai", "agent" 같은 넓은 낱말은 두 낱말 조건에 세지 않는다.
        if len(terms) >= 3 and len([term for term in matched if term not in _GENERIC_ENGLISH]) < 2:
            continue
        if any(frequency[term] <= rare for term in matched):
            scored.append((sum(math.log(1 + len(texts) / frequency[term]) for term in matched), entry))
    scored.sort(key=lambda row: row[1]["published_at"], reverse=True)
    scored.sort(key=lambda row: -row[0])
    return [_candidate(lane, provider, entry["title"], entry["url"], entry["summary"], _year(entry["published_at"]), entry["source"])
            for _, entry in scored[:PER_PROVIDER]]


def _official_sources(area: str) -> list[dict]:
    segment = "exam" if area == "A" else "ai"
    return [{"name": row["name"], "feed_url": row["url"]} for row in load_sources() if "format" not in row and row["segment"] == segment]


def _feeds(fetch, sources, terms, lane, provider):
    entries, failed = [], 0
    for source in sources:
        try:
            entries += _feed_entries(fetch, source)
        except (*_ERRORS, SyntaxError):
            failed += 1
    if sources and failed == len(sources):
        raise ValueError("등록된 출처를 읽지 못했습니다.")
    return _pick_feed_entries(entries, terms, lane, provider)


def list_trusted(root) -> list[dict]:
    with closing(_connect(root)) as db:
        db.executescript(_SCHEMA)
        return [{**dict(row), "area_label": AREAS.get(row["area"], row["area"]), "lane_label": LANES.get(row["lane"], row["lane"])}
                for row in db.execute("SELECT * FROM trusted_sources ORDER BY created_at DESC, id")]


def _is_feed(raw: bytes, kind: str = "") -> bool:
    return "xml" in (kind or "").lower() or raw[:600].lstrip().lower().startswith((b"<?xml", b"<rss", b"<feed"))


def _find_feed(url: str, fetch) -> tuple[str, bytes]:
    """채널이나 블로그 주소에서 RSS 주소를 찾는다. 주소가 이미 RSS면 그대로 쓴다."""
    raw, final_url, kind = fetch(url, maximum=3_000_000)
    if _is_feed(raw, kind):
        return final_url, raw
    markup = raw.decode("utf-8", "replace")
    for tag in re.findall(r"<link\b[^>]*>", markup, re.I):
        match = re.search(r"""href=["']([^"']+)""", tag, re.I)
        if match and re.search(r"application/(?:rss|atom)\+xml", tag, re.I):
            feed_url = urljoin(final_url, match.group(1).replace("&amp;", "&"))
            return feed_url, fetch(feed_url, maximum=3_000_000)[0]
    for path in ("/feed", "/rss", "/rss.xml", "/atom.xml", "/feed.xml"):
        try:
            feed_url = urljoin(final_url, path)
            body, _, body_kind = fetch(feed_url, maximum=3_000_000)
            if _is_feed(body, body_kind):
                return feed_url, body
        except _ERRORS:
            continue
    raise WorkflowError("이 주소에서 새 글 목록(RSS)을 찾지 못했습니다. 유튜브 채널 주소나 블로그의 RSS 주소를 넣어 주세요.")


def add_trusted(root, url: str, *, area: str, lane: str, name: str | None = None, fetch=None) -> dict:
    url = url.strip() if isinstance(url, str) else ""
    parts = urlsplit(url)
    if parts.scheme != "https" or not parts.hostname or len(url) > 2048:
        raise WorkflowError("https://로 시작하는 공개 주소를 넣어 주세요.")
    if area not in AREAS:
        raise WorkflowError("분야를 골라 주세요.")
    if lane not in LANES:
        raise WorkflowError("사실 근거용인지 사례·참고용인지 골라 주세요.")
    if fetch is None:
        deadline = monotonic() + 20

        def fetch(target, *, maximum):
            return fetch_public(target, maximum=maximum, deadline=deadline)
    try:
        feed_url, raw = _find_feed(url, fetch)
        entries = parse_feed(raw, {"id": "research", "name": "출처"})
    except WorkflowError:
        raise
    except (*_ERRORS, SyntaxError) as exc:
        raise WorkflowError("이 주소를 읽지 못했습니다. 주소를 확인해 주세요.") from exc
    if not entries:
        raise WorkflowError("이 주소의 새 글 목록이 비어 있습니다. 주소를 확인해 주세요.")
    heading = re.search(rb"<title[^>]*>\s*(?:<!\[CDATA\[)?(.*?)(?:\]\]>)?\s*</title>", raw[:8000], re.S)
    found = _clean(re.sub(r"<[^>]+>", "", heading.group(1).decode("utf-8", "replace")))[:120] if heading else ""
    label = _clean(name or "")[:120] or found or parts.hostname
    row = (secrets.token_hex(8), label, url, feed_url, area, lane, _now())
    with closing(_connect(root)) as db, db:
        db.executescript(_SCHEMA)
        if db.execute("SELECT COUNT(*) FROM trusted_sources").fetchone()[0] >= MAX_TRUSTED:
            raise WorkflowError(f"출처는 {MAX_TRUSTED}곳까지 등록할 수 있습니다.")
        if db.execute("SELECT 1 FROM trusted_sources WHERE feed_url=?", (feed_url,)).fetchone():
            raise WorkflowError("이미 등록한 출처입니다.")
        db.execute("INSERT INTO trusted_sources VALUES (?,?,?,?,?,?,?)", row)
    return {"id": row[0], "name": label, "url": url, "feed_url": feed_url, "area": area, "lane": lane, "created_at": row[6],
            "area_label": AREAS[area], "lane_label": LANES[lane], "recent": len(entries)}


def delete_trusted(root, source_id: str) -> dict:
    with closing(_connect(root)) as db, db:
        db.executescript(_SCHEMA)
        if db.execute("DELETE FROM trusted_sources WHERE id=?", (source_id,)).rowcount == 0:
            raise WorkflowError("출처를 찾을 수 없습니다. 목록을 새로 고쳐 주세요.")
    return {"deleted": source_id}


def stored_urls(root) -> set[str]:
    try:
        with closing(sqlite3.connect(f"{library_path(root).as_uri()}?mode=ro", uri=True, timeout=2)) as db:
            return {row[0] for row in db.execute(
                "SELECT url_norm FROM items WHERE url_norm IS NOT NULL AND status IN ('done','working','pending','needs_check')")}
    except sqlite3.Error:
        return set()


def library_fact_sources(root, title: str, *, area=None) -> int | None:
    """사실 근거용 자료에서 검색된 후보 URL 수로, 주장 확인 결과가 아니다."""
    try:
        from .public_evidence import PublicEvidenceUnavailable, find_library_evidence
        from .source_library import example_urls
    except ImportError:
        return None
    try:
        examples = example_urls(root)
        return len({row["url"] for row in find_library_evidence(title, root=root, limit=6, area=area) if row["url"] not in examples})
    except PublicEvidenceUnavailable:
        return None


# 자료 창고 판정(CRAG의 맞음, 애매, 틀림). 2026-11-25 골든셋 v4 Dev 50문항을 운영 창고(근거 링크 38건)에 돌려 정했다.
# 정답 문서가 창고에 있는 23문항의 1등 유사도는 0.42~0.78(가운데 0.60), 없는 27문항은 0.38~0.61(가운데 0.49)이었다.
# 0.62 이상을 '맞음'으로 두면 정답이 없는데 '맞음'이라 한 문항이 0/27이고, 0.48 미만 '틀림'에는 정답이 있는 문항이 1/23 들어간다.
# 하한을 넘은 후보 수는 두 집단이 갈리지 않아 쓰지 않는다. 문항이 50개뿐이라 사람이 누른 맞음, 틀림 기록으로 다시 본다.
VERDICT_CORRECT_SCORE = 0.62
VERDICT_INCORRECT_SCORE = 0.48
VERDICTS = {"correct": "맞음", "ambiguous": "애매", "incorrect": "틀림"}


def library_judgement(root, title: str, *, area=None) -> dict:
    """창고 후보 주소 수와 1등 후보의 유사도. 창고를 지금 볼 수 없으면 둘 다 None이다."""
    unknown = {"fact_sources": None, "top_score": None}
    try:
        from .public_evidence import PublicEvidenceUnavailable, find_library_evidence_scored
        from .source_library import example_urls
    except ImportError:
        return unknown
    try:
        rows, top = find_library_evidence_scored(title, root=root, exclude_urls=tuple(example_urls(root)), limit=6, area=area)
    except PublicEvidenceUnavailable:
        return unknown
    # 제목에 적힌 도구, 제품 이름(4자 이상)이 후보 어디에도 없으면 유사도가 높아도 딱지를 한 단계 낮춘다.
    names = [name for name in build_queries(title)["names"].split() if len(name) >= 4]
    seen = " ".join(f"{row.get('title', '')} {row.get('quote', '')}" for row in rows).casefold()
    missing = bool(names and rows and not any(name.casefold() in seen for name in names))
    top_rows = [{"url": row["url"], "paragraph": row.get("paragraph"), "title": str(row.get("title", ""))[:160]} for row in rows[:6]]
    return {"fact_sources": len({row["url"] for row in rows}), "top_score": top, "names_missing": missing, "top": top_rows}


def library_verdict(hits: int | None, top_score: float | None, names_missing: bool = False) -> dict | None:
    """창고 검색 결과만 보고 붙이는 딱지다. 모델을 부르지 않는다. 창고를 못 봤으면 None이고 예전 기준(주장 종류)을 따른다."""
    if hits is None:
        return None
    if not hits or top_score is None or top_score < VERDICT_INCORRECT_SCORE:
        key, reason = "incorrect", "자료 창고에 이 주제와 가까운 근거가 없어요."
    elif top_score >= VERDICT_CORRECT_SCORE:
        key, reason = "correct", "자료 창고에 이 주제와 아주 가까운 근거가 있어요."
    else:
        key, reason = "ambiguous", "자료 창고에 비슷한 근거는 있지만 충분한지 애매해요."
    if names_missing and key != "incorrect":
        key = "ambiguous" if key == "correct" else "incorrect"
        reason = "제목의 도구나 제품 이름이 창고 근거에 없어요. 비슷한 글일 수 있어요."
    return {"verdict": key, "label": VERDICTS[key], "top_score": top_score, "reason": reason}


def run_research(root, title: str, **options) -> dict:
    """조사 한 번을 끝까지 기록한다. 바깥 호출이 0회여도 종료 기록을 남겨서 '안 찾음'과 '기록 누락'을 구별한다."""
    from .research_trace import record_research
    started, result, error = monotonic(), None, None
    try:
        result = _run_research(root, title, **options)
        return result
    except Exception as exc:
        error = type(exc).__name__
        raise
    finally:
        trace = result.pop("_trace", None) if isinstance(result, dict) else None
        record_research(root, title, options, result, trace, error, int((monotonic() - started) * 1000))


def _run_research(root, title: str, *, summary: str = "", area: str | None = None, kind: str | None = None, experience_first: bool = False,
                 query: str | None = None, force: bool = False, fetch=None, fact_sources=library_fact_sources, translate=None,
                 auto: bool = False) -> dict:
    """외부 조사 필요 여부는 기획의 주장으로 결정한다. auto면 자료 창고 판정(맞음, 애매, 틀림)이 먼저다."""
    title = _clean(title or "")[:300]
    if not title:
        raise WorkflowError("주제를 확인할 수 없습니다.")
    plan = research_plan(title, summary, area=area, kind=kind, experience_first=experience_first)
    queries = build_queries(title, query)
    if plan["blocked"]:  # 범위 밖으로 고른 주제는 '그래도 찾아보기'를 눌러도 창고와 바깥 모두 찾지 않는다.
        return {"plan": plan, "queries": queries, "library": {"fact_sources": None, "sufficient": False}, "candidates": [],
                "notes": ["범위 밖 주제로 골라서 밖으로 찾지 않았어요. 글 유형을 바꾸면 다시 찾을 수 있어요."], "searched": False, "verdict": None}
    library_query = f"{title} {query.strip()}" if query and query.strip() else title
    trace_library = None
    if fact_sources is library_fact_sources:
        judged = library_judgement(root, library_query, area=plan["area"])
        trace_library = {key: judged.get(key) for key in ("fact_sources", "top_score", "names_missing", "top")}
        hits = judged["fact_sources"]
        # 내 경험 중심 글은 외부 조사를 하지 않으므로 창고 판정도 붙이지 않는다.
        verdict = None if plan["experience_first"] else library_verdict(hits, judged["top_score"], judged.get("names_missing", False))
    else:
        hits, verdict = fact_sources(root, library_query), None
    library = {"fact_sources": hits, "sufficient": False}
    result = {"plan": plan, "queries": queries, "library": library, "candidates": [], "notes": [], "searched": False, "verdict": verdict,
              "_trace": {"library": trace_library, "skipped_by_verdict": False, "jobs": []}}
    if re.search(r"쿠폰|할인\s*코드|\bpromo\s*code\b", f"{title} {summary}", re.I):
        result["notes"].append("쿠폰 발급·상품 적용·만료는 스토어 확인 항목이에요. 공개 자료로 확인 완료 처리하지 않아요.")
    if auto and verdict:
        # 자동 조사: 창고 판정이 '맞음'이면 밖으로 찾지 않는다. 발표·공고 글(W2)은 창고에 있어도 최신 원문을 확인한다.
        if verdict["verdict"] == "correct" and not (plan["kind"] == "W2" and not plan["kind_guessed"]):
            result["notes"].append("자료 창고에 맞는 근거가 있어서 밖으로 찾지 않았어요. 부족하면 '다시 찾기'를 눌러 주세요.")
            result["_trace"]["skipped_by_verdict"] = True
            return result
        force = force or verdict["verdict"] != "correct"
    if not force and plan["need"] == "none":
        return result
    if fetch is None:
        deadline = monotonic() + SEARCH_SECONDS

        def fetch(url, *, maximum):
            return fetch_public(url, maximum=maximum, deadline=deadline)
    fact = list(plan["fact"]["providers"]) or (list(_AREA_FACT[plan["area"]]) if force else [])
    trusted = list_trusted(root)
    jobs = {}
    direct = [_candidate("fact", "official", label, url, source="공식 안내 페이지")
              for match, label, url in _EXAM_OFFICIAL_PAGES
              if "official" in fact and plan["area"] == "A" and match.search(title)]
    if "official" in fact and plan["area"] == "A" and "편입" in title:
        result["notes"].append("편입 일정은 지원 대학 입학처의 해당 학년도 모집요강을 출처 확인·보완에 저장해 주세요.")
    api = {"pubmed": _pubmed, "openalex": _openalex, "arxiv": _arxiv, "github": _github}
    if translate and not queries["custom"] and any(name in api for name in fact):
        made = translate(title)  # 한글 주제일 때만 영어 검색어를 만들어 온다. 못 만들면 낱말표 검색어를 그대로 쓴다.
        if made.get("queries"):
            queries = {**queries, "english": made["queries"][0], "alternatives": made["queries"][1:], "translated": True}
            result["queries"] = queries
        elif made.get("note"):
            result["notes"].append(made["note"])
    generic = _too_generic(queries["english"]) and not queries["custom"]
    if generic and any(name in api for name in fact):
        # 낱말표로 만든 검색어가 "AI", "learning"처럼 너무 넓으면 논문, 저장소 검색이 주제와 상관없는 결과만 준다(2026-11-27 운영 실측).
        result["notes"].append(f"영어 검색어가 너무 넓어서({queries['english'] or '없음'}) 논문과 저장소는 찾지 않았어요. 검색어 칸에 구체적인 영어 낱말을 적고 다시 찾아 주세요.")
    for name in fact:
        if name in api:
            wanted = (queries["names"] or queries["english"]) if name == "github" else queries["english"]
            if name == "github" and queries["names"] and not _too_generic(queries["names"]):
                generic_name = False
            else:
                generic_name = generic
            if wanted and generic_name:
                continue
            if wanted:
                jobs[name] = (api[name], (fetch, wanted, tuple(queries.get("alternatives") or ())) if name == "pubmed" else (fetch, wanted))
            else:
                result["notes"].append(f"{PROVIDERS[name]}: 영어 검색어가 필요해요. 검색어 칸에 영어 낱말을 적고 다시 찾아 주세요.")
        else:
            sources = _official_sources(plan["area"]) + [row for row in trusted if row["lane"] == "fact" and row["area"] == plan["area"]]
            if sources:
                jobs["official"] = (_feeds, (fetch, sources, queries["terms"], "fact", "official"))
            else:
                result["notes"].append("공식 출처: 이 분야에 등록된 공식 출처가 없어요. 자료 창고의 '믿는 출처'에 기관 공지 주소를 등록해 주세요.")
    if plan["example"]["need"] != "none" or force:
        creators = [row for row in trusted if row["lane"] == "example" and row["area"] == plan["area"]]
        if creators:
            jobs["creator"] = (_feeds, (fetch, creators, queries["terms"], "example", "creator"))
        else:
            result["notes"].append("사례·참고: 이 분야에 등록한 크리에이터가 없어요. 자료 창고의 '믿는 출처'에서 추가할 수 있어요.")
    found = [row for row in direct if row]
    seen = {value for row in found for value in (row["key"], re.sub(r"[\W_]+", "", row["title"].casefold()))}
    with ThreadPoolExecutor(max_workers=6) as pool:
        futures = {name: pool.submit(function, *arguments) for name, (function, arguments) in jobs.items()}
        for name, future in futures.items():
            try:
                rows = [row for row in future.result() if row and is_topic_candidate(title, row["title"], row["snippet"])]
            except (*_ERRORS, SyntaxError):
                result["notes"].append(f"{PROVIDERS[name]}: 지금 응답이 없어요. 잠시 뒤 다시 찾아 주세요.")
                continue
            if not rows:
                result["notes"].append(f"{PROVIDERS[name]}: 맞는 자료를 찾지 못했어요.")
            for row in rows:
                same_title = re.sub(r"[\W_]+", "", row["title"].casefold())  # 같은 논문이 두 곳에서 다른 주소로 나온다.
                if row["key"] not in seen and same_title not in seen:
                    seen.update((row["key"], same_title))
                    found.append(row)
    stored = stored_urls(root) if found else set()
    result["candidates"] = [{**row, "in_library": normalize_url(row["url"]) in stored} for row in found]
    result["searched"] = bool(jobs)
    result["_trace"]["jobs"] = sorted(jobs)
    return result


# Tavily: 사람이 '한 번 더 찾기'를 누를 때만 1회 검색한다. 공식 주소를 찾는 길잡이로 쓰고, 공식이 아닌 블로그와
# 크리에이터 글은 '사례·참고' 칸(사실 근거 아님)으로만 보여 준다. 검색어는 기획 제목이나 운영자가 적은 검색어뿐이고,
# 개인 DB 문장은 넣지 않는다(Tavily가 입력을 보관할 수 있음). 자동 재시도와 유료 대체 경로는 없다.
TAVILY_URL = "https://api.tavily.com/search"
TAVILY_MONTHLY_CAP = 900       # 무료 월 1,000크레딧 중 여유를 남긴다. basic 검색 1회 = 1크레딧.
TAVILY_MAX_RESULTS = 8
TAVILY_SECONDS = 15
_TAVILY_KEY_FILE = Path("~/.config/heobrain-content-office/tavily.key")
_OFFICIAL_SUFFIX = (".go.kr", ".gov", ".or.kr", ".ac.kr", ".edu", ".int", ".re.kr", ".mil")
_OFFICIAL_HOSTS = ("korea.kr", "arxiv.org", "pubmed.ncbi.nlm.nih.gov", "ncbi.nlm.nih.gov", "github.com", "openai.com",
                   "anthropic.com", "ai.google.dev", "blog.google", "deepmind.google", "huggingface.co", "microsoft.com",
                   "nvidia.com", "apple.com", "meta.com", "q-net.or.kr", "who.int", "nih.gov", "nature.com", "science.org")
_OFFICIAL_PREFIX = ("docs.", "developer.", "developers.", "support.", "help.", "learn.", "platform.")


def tavily_key() -> str | None:
    """키는 환경 변수나 상태 폴더 밖의 0600 파일에서만 읽는다. 화면, 기록, 응답에는 넣지 않는다."""
    value = os.environ.get("TAVILY_API_KEY", "").strip()
    if not value:
        path = Path(os.environ.get("TAVILY_KEY_FILE") or _TAVILY_KEY_FILE).expanduser()
        try:
            value = path.read_text(encoding="utf-8").strip() if path.is_file() and not path.stat().st_mode & 0o077 else ""
        except OSError:
            value = ""
    return value if re.fullmatch(r"tvly-[A-Za-z0-9_-]{8,120}", value) else None


def _usage_path(root) -> Path:
    return Path(library_path(root)).parent / "tavily_usage.json"


def tavily_usage(root) -> dict:
    month = datetime.now(timezone.utc).strftime("%Y-%m")
    try:
        data = json.loads(_usage_path(root).read_text(encoding="utf-8"))
    except (OSError, ValueError):
        data = {}
    calls = data.get("calls") if isinstance(data, dict) and data.get("month") == month and type(data.get("calls")) is int else 0
    return {"month": month, "calls": calls, "cap": TAVILY_MONTHLY_CAP, "remaining": max(0, TAVILY_MONTHLY_CAP - calls),
            "has_key": tavily_key() is not None}


def _count_tavily_call(root) -> dict:
    usage = tavily_usage(root)
    path = _usage_path(root)
    path.parent.mkdir(parents=True, exist_ok=True)
    temp = path.with_suffix(".tmp")
    temp.write_text(json.dumps({"month": usage["month"], "calls": usage["calls"] + 1}), encoding="utf-8")
    os.replace(temp, path)
    return {**usage, "calls": usage["calls"] + 1, "remaining": max(0, usage["remaining"] - 1)}


# 이름이 제품명과 같아도 공식이 아닌 곳(영상, SNS, 블로그, 커뮤니티).
_SOCIAL_HOSTS = ("youtube.com", "youtu.be", "instagram.com", "threads.com", "threads.net", "tiktok.com", "facebook.com", "x.com",
                 "twitter.com", "reddit.com", "medium.com", "tistory.com", "naver.com", "daum.net", "velog.io", "brunch.co.kr")
_SECOND_LEVEL = ("co", "or", "go", "ac", "ne", "re", "com", "org", "net", "gov", "edu")
# 한글로 적는 제품, 서비스 이름과 그 회사 주소 이름. 제목에 한글 이름만 있어도 공식 사이트를 알아보게 한다.
_PRODUCT_NAMES = {"옵시디언": ("obsidian",), "노션": ("notion",), "챗gpt": ("openai", "chatgpt"), "오픈ai": ("openai",),
                  "클로드": ("anthropic", "claude"), "제미나이": ("google", "gemini"), "커서": ("cursor",), "슬랙": ("slack",),
                  "피그마": ("figma",), "캔바": ("canva",), "깃허브": ("github",), "허깅페이스": ("huggingface",),
                  "오픽": ("opic",), "토익": ("toeic", "ets"), "엔비디아": ("nvidia",), "앤트로픽": ("anthropic",)}


def _site_name(host: str) -> str:
    """example.co.kr → example, obsidian.md → obsidian, docs.anthropic.com → anthropic."""
    parts = host.lower().removeprefix("www.").split(".")
    if len(parts) >= 3 and parts[-2] in _SECOND_LEVEL and len(parts[-1]) == 2:
        return parts[-3]
    return parts[-2] if len(parts) >= 2 else host


def _official_host(host: str, trusted_hosts=frozenset(), title: str = "") -> bool:
    host = host.lower().removeprefix("www.")
    if (host in trusted_hosts or host.endswith(_OFFICIAL_SUFFIX) or host.startswith(_OFFICIAL_PREFIX)
            or any(host == name or host.endswith("." + name) for name in _OFFICIAL_HOSTS)):
        return True
    if any(host == name or host.endswith("." + name) for name in _SOCIAL_HOSTS):
        return False
    # 기획 제목의 제품, 서비스 이름과 주소 이름이 같으면 그 회사의 공식 사이트로 본다(예: 옵시디언 글의 obsidian.md).
    name = _site_name(host)
    text = unicodedata.normalize("NFKC", title or "")
    words = {word.casefold() for word in re.findall(r"[A-Za-z][A-Za-z0-9]{3,}", text)}
    folded = text.casefold().replace(" ", "")
    words.update(alias for korean, aliases in _PRODUCT_NAMES.items() if korean in folded for alias in aliases)
    return len(name) >= 4 and name in words


def _tavily(query: str, key: str, *, post=None, trusted_hosts=frozenset(), title: str = "") -> list[dict]:
    post = post or requests.post
    response = post(TAVILY_URL, json={"query": query[:400], "search_depth": "basic", "max_results": TAVILY_MAX_RESULTS,
                                      "include_answer": False, "include_raw_content": False, "include_images": False},
                    headers={"Authorization": f"Bearer {key}", "Content-Type": "application/json"}, timeout=TAVILY_SECONDS)
    if response.status_code in (401, 403):
        raise PermissionError("tavily key rejected")
    if response.status_code in (429, 432, 433):
        raise OverflowError("tavily limit")
    response.raise_for_status()
    rows = []
    for item in (response.json().get("results") or [])[:TAVILY_MAX_RESULTS]:
        if not isinstance(item, dict):
            continue
        url = str(item.get("url") or "")
        host = (urlsplit(url).hostname or "").lower()
        official = _official_host(host, trusted_hosts, title or query)
        row = _candidate("fact" if official else "example", "tavily", item.get("title"), url, item.get("content") or "",
                         source="Tavily 검색: 공식으로 보이는 주소(원문 확인 필요)" if official else "Tavily 검색(사례·참고 칸, 사실 근거 아님)")
        if row:
            rows.append({**row, "idea_only": not official})
    return rows


def run_tavily(root, title: str, *, query: str | None = None, post=None) -> dict:
    """사람이 누른 Tavily 1회 검색. 키가 없거나 이번 달 한도를 넘으면 부르지 않는다."""
    title = _clean(title or "")[:300]
    if not title:
        raise WorkflowError("주제를 확인할 수 없습니다.")
    # 운영자가 검색어를 안 적었으면 제목 뒤에 '공식'을 붙여 공식 안내를 먼저 찾게 한다(2026-11-25 시험: 옵시디언 공식 도움말 0건 → 4건).
    wanted = _clean(query or "")[:200] or f"{title} 공식"
    usage = tavily_usage(root)
    result = {"queries": {"tavily": wanted}, "candidates": [], "notes": [], "searched": False, "tavily": usage}
    key = tavily_key()
    if key is None:
        result["notes"].append("Tavily 키가 아직 없어요. 키를 넣으면 이 버튼으로 한 번 더 찾을 수 있어요.")
        return result
    if usage["remaining"] <= 0:
        result["notes"].append(f"Tavily 이번 달 사용량({usage['cap']}회)을 다 써서 부르지 않았어요.")
        return result
    result["tavily"] = _count_tavily_call(root)  # 실패해도 1회로 센다(무료 한도를 넘지 않게 보수적으로).
    trusted_hosts = frozenset((urlsplit(row["url"]).hostname or "").lower().removeprefix("www.")
                              for row in list_trusted(root) if row.get("lane") == "fact")
    try:
        rows = _tavily(wanted, key, post=post, trusted_hosts=trusted_hosts, title=f"{title} {wanted}")
    except PermissionError:
        result["notes"].append("Tavily가 키를 받지 않았어요. 키를 다시 확인해 주세요.")
        return result
    except OverflowError:
        result["notes"].append("Tavily 사용 한도에 걸렸어요. 다음 달에 다시 쓸 수 있어요.")
        return result
    except (*_ERRORS, SyntaxError):
        result["notes"].append("Tavily가 지금 응답이 없어요. 자동으로 다시 부르지 않아요. 잠시 뒤 다시 눌러 주세요.")
        return result
    rows = [row for row in rows if is_topic_candidate(title, row["title"], row["snippet"])]
    from .source_library import _blocked_reason
    readable = [row for row in rows if not _blocked_reason(row["url"])]
    if len(readable) < len(rows):
        result["notes"].append(f"네이버 블로그와 뉴스 같은 robots.txt 차단 주소 {len(rows) - len(readable)}건은 근거로 쓸 수 없어서 뺐어요.")
    rows = readable
    stored = stored_urls(root) if rows else set()
    result["candidates"] = [{**row, "in_library": normalize_url(row["url"]) in stored} for row in rows]
    result["searched"] = True
    if not rows:
        result["notes"].append("Tavily: 주제에 맞는 자료를 찾지 못했어요.")
    else:
        result["notes"].append("Tavily 결과 중 공식 주소가 아닌 글은 사례·참고 칸이에요. 사실 근거로 쓰려면 원문을 직접 확인해 주세요.")
    return result
