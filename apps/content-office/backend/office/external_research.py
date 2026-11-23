"""외부 조사: 주제가 어떤 주장을 하는지 보고 외부 조사가 필요한지 정하고, 무료 공개 출처에서 후보를 찾는다.

- 모델·유료 API를 부르지 않는다. PubMed, OpenAlex, arXiv, GitHub의 공개 검색 API와 등록된 RSS만 읽는다.
- 찾은 것은 후보일 뿐이다. 운영자가 고른 것만 자료 창고에 들어가고 근거로 켜진다. 승인⓪①②③을 만들거나 대신하지 않는다.
- 자료는 두 칸으로 나눈다. fact(사실 근거: 공식 문서·논문·기관 공고)와 example(사례·참고: 운영자가 등록한 크리에이터).
"""
from __future__ import annotations

import hashlib
import json
import math
import re
import secrets
import sqlite3
import unicodedata
from concurrent.futures import ThreadPoolExecutor
from contextlib import closing
from time import monotonic
from urllib.parse import quote_plus, urljoin, urlsplit

import requests

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
    ("research", "연구·효과", re.compile(r"뇌|기억|집중|인지|수면|도파민|연구|논문|실험|효과|과학적|심리학|neuro|brain|memory|cognit", re.I)),
    ("fresh", "최신 정보", re.compile(r"버전|가격|요금|출시|업데이트|신기능|새 기능|비교|차이|\bvs\b|무료|유료|플랜|지원 종료|\bv?\d+\.\d+\b", re.I)),
    ("schedule", "일정·기준", re.compile(r"일정|접수|원서|합격 ?(?:기준|률|선)|응시료|시험일|개정|커트라인|응시 ?자격")),
    ("number", "수치", re.compile(r"\d+(?:\.\d+)?\s?(?:%|퍼센트|배|만 ?원|명|점)")),
    ("howto", "방법·사례", re.compile(r"방법|루틴|후기|꿀팁|노하우|하는 법|따라 ?하기|사용법|활용법|세팅|설정|가이드|팁")),
)
_AREA_HINTS = (
    ("A", re.compile(r"시험|자격증|산업기사|기사 ?(?:필기|실기)|토익|오픽|수능|편입|필기|실기|공무원|합격")),
    ("B", re.compile(r"\bAI\b|GPT|Claude|Gemini|LLM|에이전트|자동화|\bMCP\b|\bRAG\b|Hermes|OpenClaw|프롬프트|n8n|코딩|\bAPI\b|챗봇|인공지능", re.I)),
    ("C", re.compile(r"뇌|기억|집중|학습|공부법|암기|복습|인지|수면|도파민")),
    ("E", re.compile(r"꿀팁|생활|정리|청소|절약|요리|살림")),
)
_AREA_FACT = {"A": ("official",), "B": ("official", "github", "arxiv"), "C": ("pubmed", "openalex"),
              "D": ("pubmed", "openalex"), "E": ("official",)}
_CLAIM_FACT = {"research": ("pubmed", "openalex"), "fresh": ("official", "github"), "schedule": ("official",)}
PROVIDERS = {"pubmed": "PubMed 논문", "openalex": "OpenAlex 공개 논문", "arxiv": "arXiv 논문", "github": "GitHub 저장소",
             "official": "공식 출처 새 글", "creator": "등록한 크리에이터"}
# 한글 주제를 영어 논문·저장소 검색어로 옮길 때 쓰는 작은 낱말표. 여기에 없는 말은 운영자가 검색어를 직접 고친다.
_GLOSSARY = {
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


def research_plan(title: str, summary: str = "", *, area: str | None = None, experience_first: bool = False) -> dict:
    """주제의 주장 종류와 분야를 보고 어느 칸을 조사해야 하는지 정한다. 네트워크를 쓰지 않는다."""
    text = unicodedata.normalize("NFKC", f"{title or ''}\n{summary or ''}")
    guessed = area not in AREAS
    area = guess_area(text) if guessed else area
    claims = [{"id": key, "label": label} for key, label, pattern in _CLAIMS if pattern.search(text)]
    found = {claim["id"] for claim in claims}
    hard = [claim["label"] for claim in claims if claim["id"] != "howto"]
    plan = {"area": area, "area_label": AREAS[area], "area_guessed": guessed, "experience_first": bool(experience_first),
            "claims": claims, "warning": None}
    if experience_first:
        if found & {"number", "research"}:
            plan["warning"] = "내 경험 중심 글이지만 수치나 연구 주장이 보여요. 그 부분은 근거를 붙이거나 내 경험으로 표현을 바꿔 주세요."
        plan["fact"] = {"need": "none", "reason": "내 경험 중심 글이라 외부 조사를 하지 않아요.", "providers": []}
        plan["example"] = {"need": "none", "reason": "내 경험 중심 글이라 다른 사람 사례를 찾지 않아요."}
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
    return {"english": english_query, "terms": [word for word in dict.fromkeys(words) if word not in _STOP][:24], "custom": bool(custom)}


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


def _pubmed(fetch, english):
    base = "https://eutils.ncbi.nlm.nih.gov/entrez/eutils/"
    found = _json(fetch, f"{base}esearch.fcgi?db=pubmed&retmode=json&retmax={PER_PROVIDER}&sort=relevance&term={quote_plus(english)}")
    ids = [value for value in found["esearchresult"].get("idlist", []) if str(value).isdigit()][:PER_PROVIDER]
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


def library_fact_sources(root, title: str) -> int | None:
    """자료 창고에서 이 주제에 맞는 사실 근거가 서로 다른 출처로 몇 개 있는지 센다. 검색을 못 하면 None."""
    try:
        from .public_evidence import PublicEvidenceUnavailable, find_library_evidence
        from .source_library import example_urls
    except ImportError:
        return None
    try:
        examples = example_urls(root)
        return len({row["url"] for row in find_library_evidence(title, root=root, limit=6) if row["url"] not in examples})
    except PublicEvidenceUnavailable:
        return None


def run_research(root, title: str, *, summary: str = "", area: str | None = None, experience_first: bool = False,
                 query: str | None = None, force: bool = False, fetch=None, fact_sources=library_fact_sources) -> dict:
    """기준에 따라 외부 후보를 찾는다. 창고 근거가 충분하거나 조사가 필요 없는 주제는 force가 아니면 밖으로 나가지 않는다."""
    title = _clean(title or "")[:300]
    if not title:
        raise WorkflowError("주제를 확인할 수 없습니다.")
    plan = research_plan(title, summary, area=area, experience_first=experience_first)
    queries = build_queries(title, query)
    hits = fact_sources(root, title)
    library = {"fact_sources": hits, "sufficient": hits is not None and hits >= 2}
    result = {"plan": plan, "queries": queries, "library": library, "candidates": [], "notes": [], "searched": False}
    if not force and plan["need"] == "none":
        return result
    if not force and library["sufficient"] and plan["example"]["need"] == "none":
        result["notes"].append(f"자료 창고에서 서로 다른 출처의 근거 {hits}개가 맞아서 외부 조사를 건너뛰었어요.")
        return result
    if fetch is None:
        deadline = monotonic() + SEARCH_SECONDS

        def fetch(url, *, maximum):
            return fetch_public(url, maximum=maximum, deadline=deadline)
    fact = list(plan["fact"]["providers"]) or (list(_AREA_FACT[plan["area"]]) if force else [])
    if library["sufficient"] and not force:
        fact = []
        result["notes"].append(f"사실 근거는 자료 창고에 {hits}개가 맞아서 사례만 찾았어요.")
    trusted = list_trusted(root)
    jobs = {}
    api = {"pubmed": _pubmed, "openalex": _openalex, "arxiv": _arxiv, "github": _github}
    for name in fact:
        if name in api:
            if queries["english"]:
                jobs[name] = (api[name], (fetch, queries["english"]))
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
    found, seen = [], set()
    with ThreadPoolExecutor(max_workers=6) as pool:
        futures = {name: pool.submit(function, *arguments) for name, (function, arguments) in jobs.items()}
        for name, future in futures.items():
            try:
                rows = [row for row in future.result() if row]
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
    return result
