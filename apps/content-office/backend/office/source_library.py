"""자료 창고: 운영자가 넣은 링크·메모·파일을 문단으로 저장한다.

- 모델·유료 API를 부르지 않는다. 링크는 공개 HTTPS 주소만 feeds.fetch_public으로 읽는다.
- "초안 근거로 사용"은 운영자가 자료마다 직접 켠다. 켠 링크 자료는 공개 근거 검색(public_evidence)에 함께 잡히고,
  켠 메모·파일은 '내 글로 만들기'에서 불러올 수 있다. 이 표시는 승인⓪①②③을 만들거나 대신하지 않는다.
- 상태는 OFFICE_STATE_DIR/source-library/sources.sqlite3 에만 둔다(저장소에 넣지 않는다).
- 웹 페이지는 trafilatura로 표, 소제목, 코드를 살려 읽고, 원문 HTML과 소제목·표·코드·글자·숫자 수를 대조해
  떨어지면 예전 파서 결과로 저장하고 그 이유를 남긴다. robots.txt가 RAG 수집을 금지한 곳은 본문을 저장하지 않는다.
"""
from __future__ import annotations

import base64
import binascii
import hashlib
import io
import json
import math
import re
import secrets
import sqlite3
import unicodedata
import zipfile
from contextlib import closing
from dataclasses import dataclass, field
from datetime import date, datetime, timedelta, timezone
from html.parser import HTMLParser
from pathlib import Path
from time import monotonic
from urllib.parse import parse_qs, quote, urlsplit
from xml.etree import ElementTree

import requests

from .briefs import AXES
from .feeds import fetch_public, normalize_url
from .store import WorkflowError

AREAS = {key: axis["label"] for key, axis in AXES.items() if key != "source"}
ORIGINS = ("manual", "idea", "news", "artifact", "import", "research")
# 자료의 쓰임새. fact는 사실 주장을 받치는 근거, example은 출처와 함께 소개만 하는 다른 사람의 방법·사례다.
LANES = {"fact": "사실 근거", "example": "사례·참고"}
MAX_PAGE_BYTES = 3_000_000
MAX_FILE_BYTES = 8_000_000
MAX_MEMO_CHARS = 60_000
MAX_LINKS = 10
MAX_BULK = 1000
PASSAGE_CHARS = 900
BLOCK_CHARS = 1350  # 표와 코드 블록을 한 덩어리로 두는 한도(문단 상한 900자의 1.5배). 넘으면 머리행을 되풀이해 나눈다.
MIN_LINK_CHARS = 300  # 링크 본문이 이보다 짧으면 '완료'로 저장하지 않는다(빈 근거 막기).
MAX_PDF_PAGES = 400
LINK_SECONDS = 22
YOUTUBE_MESSAGE = ("유튜브는 클라우드 서버에서 자막을 가져오는 요청을 막습니다. 영상 설명란의 '스크립트 표시'에서 "
                   "자막을 복사해 '본문 붙여넣기'로 넣어 주세요.")
_BLOCKED_PAGE = re.compile(r"captcha|access denied|just a moment|브라우저 확인", re.I)
_WORD = re.compile(r"[^\W_]{2,}")
_REF = re.compile(r"[A-Za-z0-9_.:-]{1,160}")
_READ_ERRORS = (ValueError, OSError, requests.RequestException, zipfile.BadZipFile, ElementTree.ParseError, KeyError)
# robots.txt가 AI 학습·RAG용 수집이나 일반 봇을 막은 곳. 본문은 읽지 않고 주소와 제목만 남긴다(2026-11-24 점검).
_NO_BODY_HOSTS = {
    "blog.naver.com": "네이버 블로그는 robots.txt에서 AI 학습과 검색 증강 생성(RAG)용 수집을 금지해 본문을 저장하지 않습니다.",
    "news.naver.com": "네이버 뉴스는 robots.txt에서 자동 수집을 막아 본문을 저장하지 않습니다. 언론사 원문 주소를 넣어 주세요.",
    "news.daum.net": "다음 뉴스는 robots.txt에서 자동 수집을 막아 본문을 저장하지 않습니다. 언론사 원문 주소를 넣어 주세요.",
    "v.daum.net": "다음 뉴스는 robots.txt에서 자동 수집을 막아 본문을 저장하지 않습니다. 언론사 원문 주소를 넣어 주세요.",
}
_NO_BODY_TAIL = " 주소와 제목만 남겨 둡니다. 직접 쓴 글이면 '내 자료'로 표시한 뒤 본문을 붙여 넣어 주세요."
_INBOX_AREAS = {"AI와 자동화": ("B", False), "뇌과학과 마인드셋": ("C", False), "내 경험과 아이디어": ("D", True), "벤치마킹 영상": ("B", False)}

_SCHEMA = """
CREATE TABLE IF NOT EXISTS items(
  id TEXT PRIMARY KEY, kind TEXT NOT NULL, area TEXT NOT NULL, mine INTEGER NOT NULL DEFAULT 0,
  title TEXT NOT NULL, url TEXT, url_norm TEXT, status TEXT NOT NULL, note TEXT NOT NULL DEFAULT '',
  passages INTEGER NOT NULL DEFAULT 0, content_hash TEXT, file_name TEXT, body TEXT, pasted TEXT,
  origin TEXT NOT NULL DEFAULT 'manual', origin_ref TEXT, use_as_evidence INTEGER NOT NULL DEFAULT 0,
  lane TEXT NOT NULL DEFAULT 'fact',
  published_at TEXT, modified_at TEXT, collected_at TEXT, date_source TEXT, extractor TEXT,
  created_at TEXT NOT NULL, updated_at TEXT NOT NULL);
CREATE INDEX IF NOT EXISTS items_url ON items(url_norm);
CREATE INDEX IF NOT EXISTS items_hash ON items(content_hash);
CREATE TABLE IF NOT EXISTS passages(
  item_id TEXT NOT NULL REFERENCES items(id) ON DELETE CASCADE, seq INTEGER NOT NULL, text TEXT NOT NULL,
  locator TEXT, heading TEXT,
  PRIMARY KEY(item_id, seq));
CREATE TABLE IF NOT EXISTS passage_vectors(
  item_id TEXT NOT NULL, seq INTEGER NOT NULL, part INTEGER NOT NULL, start_char INTEGER NOT NULL, end_char INTEGER NOT NULL,
  model TEXT NOT NULL, vector BLOB NOT NULL, PRIMARY KEY(item_id, seq, part),
  FOREIGN KEY(item_id, seq) REFERENCES passages(item_id, seq) ON DELETE CASCADE);
CREATE TABLE IF NOT EXISTS library_migrations(name TEXT PRIMARY KEY, applied_at TEXT NOT NULL);
"""
_ADDED_COLUMNS = {
    "items": (("lane", "TEXT NOT NULL DEFAULT 'fact'"), ("published_at", "TEXT"), ("modified_at", "TEXT"), ("collected_at", "TEXT"),
              ("date_source", "TEXT"), ("extractor", "TEXT")),
    "passages": (("locator", "TEXT"), ("heading", "TEXT")),
}


class _Unreadable(WorkflowError):
    """본문을 못 읽었지만 제목은 알아낸 경우 제목을 함께 넘긴다."""

    def __init__(self, message: str, title: str | None = None):
        super().__init__(message)
        self.title = title


def library_path(root) -> Path:
    return Path(root) / "source-library" / "sources.sqlite3"


def _now() -> str:
    return datetime.now(timezone.utc).isoformat(timespec="seconds")


def _connect(root) -> sqlite3.Connection:
    path = library_path(root)
    path.parent.mkdir(parents=True, exist_ok=True)
    db = sqlite3.connect(path, timeout=20)
    db.row_factory = sqlite3.Row
    db.execute("PRAGMA journal_mode=WAL")
    db.execute("PRAGMA foreign_keys=ON")
    db.executescript(_SCHEMA)
    for table, columns in _ADDED_COLUMNS.items():
        present = {row["name"] for row in db.execute(f"PRAGMA table_info({table})")}
        for name, kind in columns:
            if name not in present:
                try:
                    db.execute(f"ALTER TABLE {table} ADD COLUMN {name} {kind}")
                except sqlite3.OperationalError:
                    pass  # 다른 요청이 방금 같은 칸을 만들었다.
    _migrate(db)
    return db


def _blocked_reason(url: str | None) -> str | None:
    """본문을 저장하지 않는 주소면 그 이유를 돌려준다."""
    host = (urlsplit(url).hostname or "").lower() if isinstance(url, str) else ""
    for blocked, reason in _NO_BODY_HOSTS.items():
        if host == blocked or host.endswith("." + blocked):
            return reason + _NO_BODY_TAIL
    return None


_MIGRATION = "link-body-gate-20261125"


def _migrate(db: sqlite3.Connection) -> None:
    """한 번만 하는 데이터 정리: 본문이 300자 미만인 '완료' 링크와 저장 금지 주소의 본문을 내린다.

    이름을 library_migrations에 남겨 다시 하지 않는다. 여러 요청이 동시에 열어도 한 번만 바뀌도록 쓰기 잠금 안에서 확인한다.
    """
    if db.execute("SELECT 1 FROM library_migrations WHERE name=?", (_MIGRATION,)).fetchone():
        return
    db.execute("BEGIN IMMEDIATE")
    try:
        if not db.execute("SELECT 1 FROM library_migrations WHERE name=?", (_MIGRATION,)).fetchone():
            stamp = _now()
            rows = db.execute("SELECT i.id, i.url, i.mine, COALESCE(SUM(LENGTH(p.text)), 0) AS chars FROM items i "
                              "LEFT JOIN passages p ON p.item_id=i.id WHERE i.kind='link' AND i.status='done' GROUP BY i.id").fetchall()
            for row in rows:
                reason = None if row["mine"] else _blocked_reason(row["url"])
                if reason is None and row["chars"] < MIN_LINK_CHARS:
                    reason = (f"본문이 {row['chars']}자뿐이라 근거로 쓰지 않습니다. 다시 읽기를 누르거나 본문을 복사해 "
                              "'본문 붙여넣기'로 넣어 주세요.")
                if reason:
                    db.execute("DELETE FROM passages WHERE item_id=?", (row["id"],))
                    db.execute("UPDATE items SET status='needs_check', note=?, passages=0, use_as_evidence=0, updated_at=? WHERE id=?",
                               (reason[:300], stamp, row["id"]))
            db.execute("INSERT INTO library_migrations(name, applied_at) VALUES (?, ?)", (_MIGRATION, stamp))
        db.commit()
    except BaseException:
        db.rollback()
        raise


def _clean(text: str) -> str:
    return re.sub(r"[ \t ]+", " ", unicodedata.normalize("NFKC", text)).strip()


def split_passages(paragraphs, limit: int = PASSAGE_CHARS) -> list[str]:
    """짧은 문단은 이어 붙이고 긴 문단은 문장 끝에서 잘라, 검색 단위가 되는 문단 목록을 만든다."""
    passages, current = [], ""
    for paragraph in (_clean(value) for value in paragraphs):
        if not paragraph:
            continue
        while len(paragraph) > limit * 1.5:
            cut = max(paragraph.rfind(". ", 0, limit), paragraph.rfind("다. ", 0, limit) + 1, limit - 1) + 1
            if current:
                passages.append(current)
                current = ""
            passages.append(paragraph[:cut].strip())
            paragraph = paragraph[cut:].strip()
        if current and len(current) + len(paragraph) + 1 > limit:
            passages.append(current)
            current = paragraph
        else:
            current = f"{current}\n{paragraph}" if current else paragraph
    if current:
        passages.append(current)
    return passages


class _PageText(HTMLParser):
    _SKIP = {"script", "style", "noscript", "svg", "nav", "footer", "aside", "iframe", "template", "form", "button", "header"}
    _BLOCK = {"p", "li", "blockquote", "pre", "h1", "h2", "h3", "h4", "td", "dd", "dt", "figcaption", "div", "section", "article", "br", "tr"}

    def __init__(self):
        super().__init__(convert_charrefs=True)
        self.paragraphs: list[str] = []
        self.title = ""
        self.social_title = ""
        self._skip = 0
        self._in_title = False
        self._buffer: list[str] = []

    def close_block(self):
        text = _clean("".join(self._buffer))
        self._buffer = []
        if len(text) >= 2:
            self.paragraphs.append(text)

    def handle_starttag(self, tag, attrs):
        if tag in self._SKIP:
            self._skip += 1
        elif tag == "title":
            self._in_title = True
        elif tag == "meta":
            values = dict(attrs)
            if values.get("property") == "og:title" and values.get("content"):
                self.social_title = values["content"]
        if tag in self._BLOCK:
            self.close_block()

    def handle_endtag(self, tag):
        if tag in self._SKIP and self._skip:
            self._skip -= 1
        elif tag == "title":
            self._in_title = False
        if tag in self._BLOCK:
            self.close_block()

    def handle_data(self, data):
        if self._in_title:
            self.title += data
        elif not self._skip:
            self._buffer.append(data)


@dataclass
class _Block:
    """읽은 문서의 한 덩어리. kind는 para, heading, table, code. locator는 PDF 쪽처럼 조각이 넘지 않을 경계다."""
    text: str
    kind: str = "para"
    level: int = 0
    locator: str | None = None


@dataclass
class _Doc:
    title: str | None
    blocks: list[_Block]
    extractor: str
    note: str = ""
    dates: dict = field(default_factory=dict)  # published_at, modified_at, date_source


def _plain(paragraphs, extractor: str, title: str | None = None, locator: str | None = None) -> _Doc:
    return _Doc(title, [_Block(text, locator=locator) for text in paragraphs if isinstance(text, str) and text.strip()], extractor)


# ---------------------------------------------------------------- dates
_DATE_RE = re.compile(r"(\d{4})[-./년]\s*(\d{1,2})[-./월]\s*(\d{1,2})")
_PUBLISHED_KEYS = ("article:published_time", "og:published_time", "datepublished", "pubdate", "publishdate", "publish-date",
                   "date", "dc.date", "dc.date.issued", "dcterms.created", "dcterms.issued", "citation_publication_date", "citation_date")
_MODIFIED_KEYS = ("article:modified_time", "og:updated_time", "datemodified", "last-modified", "dcterms.modified", "dc.date.modified")
_META_RE = re.compile(r"<meta\b[^>]*>", re.I)
_ATTR_RE = re.compile(r"""([\w:.-]+)\s*=\s*("([^"]*)"|'([^']*)'|([^\s>]+))""")
_JSONLD_RE = re.compile(r"<script\b[^>]*type\s*=\s*[\"']application/ld\+json[\"'][^>]*>(.*?)</script>", re.I | re.S)
_TIME_RE = re.compile(r"<time\b[^>]*\bdatetime\s*=\s*[\"']([^\"']+)[\"']", re.I)


def _valid_date(value) -> str | None:
    """'YYYY-MM-DD'로 바꾼다. 2000-01-01, 1990년 이전, 내일 이후는 모르는 날짜로 본다."""
    if not isinstance(value, str):
        return None
    match = _DATE_RE.search(unicodedata.normalize("NFKC", value))
    if not match:
        return None
    try:
        found = date(int(match.group(1)), int(match.group(2)), int(match.group(3)))
    except ValueError:
        return None
    if found == date(2000, 1, 1) or found.year < 1990 or found > (datetime.now(timezone.utc) + timedelta(days=1)).date():
        return None
    return found.isoformat()


def _attrs(tag: str) -> dict:
    return {m.group(1).lower(): next((v for v in (m.group(3), m.group(4), m.group(5)) if v is not None), "")
            for m in _ATTR_RE.finditer(tag)}


def _walk_jsonld(node, found: dict) -> None:
    if isinstance(node, list):
        for value in node:
            _walk_jsonld(value, found)
    elif isinstance(node, dict):
        for key, slot in (("datePublished", "published"), ("dateCreated", "published"), ("uploadDate", "published"), ("dateModified", "modified")):
            if slot not in found and _valid_date(node.get(key)):
                found[slot] = _valid_date(node.get(key))
        for value in node.values():
            if isinstance(value, (dict, list)):
                _walk_jsonld(value, found)


def _page_dates(markup: str, fallback=None) -> dict:
    """발행일과 수정일을 JSON-LD, meta, time 태그 순으로 찾는다. 못 찾으면 trafilatura(htmldate) 추정값을 쓰고 출처를 적는다."""
    head = markup[:400_000]
    for source in ("json-ld", "meta", "time"):
        found: dict = {}
        if source == "json-ld":
            for block in _JSONLD_RE.findall(head)[:10]:
                try:
                    _walk_jsonld(json.loads(block.strip()), found)
                except (ValueError, RecursionError):
                    continue
        elif source == "meta":
            for tag in _META_RE.findall(head):
                values = _attrs(tag)
                key = (values.get("property") or values.get("name") or values.get("itemprop") or "").lower()
                content = values.get("content")
                if key in _PUBLISHED_KEYS and "published" not in found and _valid_date(content):
                    found["published"] = _valid_date(content)
                if key in _MODIFIED_KEYS and "modified" not in found and _valid_date(content):
                    found["modified"] = _valid_date(content)
        else:
            stamp = next((value for value in (_valid_date(v) for v in _TIME_RE.findall(head)) if value), None)
            if stamp:
                found["published"] = stamp
        if found.get("published"):
            return {"published_at": found["published"], "modified_at": found.get("modified"), "date_source": source}
    estimated = _valid_date(fallback)
    if estimated and estimated.endswith("-01-01"):
        estimated = None  # htmldate가 저작권 연도만 보고 1월 1일로 채운 값은 날짜로 쓰지 않는다(2026-11-25 실측).
    return {"published_at": estimated, "modified_at": None, "date_source": "htmldate" if estimated else None}


# ---------------------------------------------------------------- web pages
_SKIP_HTML = re.compile(r"<(script|style|noscript|template|svg)\b.*?</\1\s*>", re.I | re.S)
_FIGURE = re.compile(r"<figure\b[^>]*>.*?</figure\s*>", re.I | re.S)
_FIGCAPTION = re.compile(r"<figcaption\b[^>]*>(.*?)</figcaption\s*>", re.I | re.S)
_MD_STRONG = re.compile(r"(\*\*|__)(?=\S)(.+?)(?<=\S)\1")
_MD_EMPHASIS = re.compile(r"(?<![\w*])\*(?=\S)([^*\n]+?)(?<=\S)\*(?![\w*])")
_TAG = re.compile(r"<[^>]+>")
_MD_HEADING = re.compile(r"^(#{1,6})\s+(.+?)\s*#*\s*$")
_MD_FENCE = re.compile(r"^\s*(```|~~~)")
_MD_TABLE_SEP = re.compile(r"^\s*\|?\s*:?-{2,}:?\s*(\|\s*:?-{2,}:?\s*)*\|?\s*$")
_MD_IMAGE = re.compile(r"!\[([^\]]*)\]\([^)]*\)")
_DIGITS = re.compile(r"\d+(?:[.,]\d+)*")


# 본문 영역이 정해져 있는 사이트. 메뉴, 인기 기사, 댓글 규칙이 본문보다 길어 두 추출기와 대조 기준이 함께 흔들리는 곳이다.
_MAIN_REGIONS = {"korea.kr": ("div.article_head", "div.view_cont")}
_HIDDEN_HEADING = re.compile(r"\b(blind|sr-only|screen-reader-text|visually-hidden|hidden_chk|skip)\b", re.I)


def _main_region(markup: str, url: str) -> str | None:
    """정해 둔 사이트면 제목과 본문 영역만 남긴 HTML을 돌려준다(head는 제목과 날짜 때문에 그대로 둔다)."""
    host = (urlsplit(url).hostname or "").lower()
    selectors = next((value for site, value in _MAIN_REGIONS.items() if host == site or host.endswith("." + site)), None)
    if not selectors:
        return None
    try:
        import lxml.html

        tree = lxml.html.fromstring(markup)
        main = tree.cssselect(selectors[-1])
        if not main or len(main[0].text_content().strip()) < 200:
            return None
        parts = [lxml.html.tostring(found[0], encoding="unicode") for found in (tree.cssselect(selector) for selector in selectors) if found]
    except Exception:  # noqa: BLE001 - 영역을 못 찾으면 페이지 전체로 읽는다.
        return None
    head = re.search(r"<head\b.*?</head\s*>", markup, re.I | re.S)
    return f"<html>{head.group(0) if head else ''}<body><article>{''.join(parts)}</article></body></html>"


def _source_counts(markup: str) -> dict:
    """원문 HTML의 본문 구조 수. 대조 관문의 기준이다. 메뉴, 머리말, 꼬리말, 옆 칸과 화면에 안 보이는 소제목은 세지 않는다."""
    try:
        import lxml.html

        tree = lxml.html.fromstring(markup)
        for node in tree.xpath("//script|//style|//noscript|//template|//svg|//nav|//header|//footer|//aside|//form"):
            node.drop_tree()
        headings = [node for node in tree.xpath("//h2|//h3|//h4")
                    if node.text_content().strip() and not _HIDDEN_HEADING.search(f"{node.get('class') or ''} {(node.getparent().get('class') or '') if node.getparent() is not None else ''}")]
        tables = [table for table in tree.xpath("//table") if len(table.xpath(".//tr")) >= 2 and table.xpath(".//td|.//th")]
        return {"headings": len(headings), "tables": len(tables), "code": len(tree.xpath("//pre"))}
    except Exception:  # noqa: BLE001 - 파싱이 안 되는 HTML은 예전 방식으로 센다.
        pass
    body = _SKIP_HTML.sub(" ", markup)
    tables = [t for t in re.findall(r"<table\b.*?</table\s*>", body, re.I | re.S) if len(re.findall(r"<tr\b", t, re.I)) >= 2 and re.search(r"<t[dh]\b", t, re.I)]
    return {"headings": len(re.findall(r"<h[2-4][\s>]", body, re.I)), "tables": len(tables), "code": len(re.findall(r"<pre[\s>]", body, re.I))}


_MD_ESCAPE = re.compile(r"\\([\\`*_{}\[\]()#+\-.!<>~])")


def _unformat(text: str) -> str:
    """trafilatura가 붙인 굵게·기울임 표시와 Markdown 이스케이프를 걷어 인용문에 기호가 남지 않게 한다."""
    return _MD_ESCAPE.sub(r"\1", _MD_EMPHASIS.sub(r"\1", _MD_STRONG.sub(r"\2", text)))


def _figures_to_paragraphs(markup: str) -> str:
    """trafilatura는 figure 안의 figcaption을 버린다. 설명 글을 figure 바로 뒤 문단으로 옮겨 남긴다."""
    def move(match):
        figure = match.group(0)
        captions = [_clean(_TAG.sub(" ", caption)) for caption in _FIGCAPTION.findall(figure)]
        rest = _FIGCAPTION.sub("", figure)
        return rest + "".join(f"<p>[그림 설명] {caption}</p>" for caption in captions if caption)
    return _FIGURE.sub(move, markup)


def _markdown_blocks(markdown: str) -> list[_Block]:
    """trafilatura Markdown을 소제목, 표, 코드, 문단 덩어리로 나눈다(heobrain_context와 같은 나눔)."""
    lines, blocks, index = markdown.splitlines(), [], 0
    while index < len(lines):
        line = lines[index]
        if not line.strip():
            index += 1
            continue
        heading = _MD_HEADING.match(line.strip())
        if heading:
            blocks.append(_Block(_clean(_unformat(heading.group(2)).strip("*_ ")), "heading", len(heading.group(1))))
            index += 1
            continue
        if _MD_FENCE.match(line):
            fence, buffer, index = _MD_FENCE.match(line).group(1), [line.rstrip()], index + 1
            while index < len(lines):
                buffer.append(lines[index].rstrip())
                index += 1
                if lines[index - 1].strip().startswith(fence):
                    break
            if buffer[-1].strip() != fence:
                buffer.append(fence)
            blocks.append(_Block("\n".join(buffer), "code"))
            continue
        if line.lstrip().startswith("|"):
            buffer = []
            while index < len(lines) and lines[index].lstrip().startswith("|"):
                buffer.append(_clean(_unformat(lines[index])))
                index += 1
            blocks.append(_Block("\n".join(buffer), "table"))
            continue
        buffer = []
        while index < len(lines) and lines[index].strip() and not _MD_HEADING.match(lines[index].strip()) \
                and not _MD_FENCE.match(lines[index]) and not lines[index].lstrip().startswith("|"):
            text = _MD_IMAGE.sub(lambda m: f"[그림] {m.group(1).strip()}" if len(m.group(1).strip()) >= 4 else "", lines[index])
            if text.strip():
                buffer.append(_clean(_unformat(text)))
            index += 1
        if buffer:
            blocks.append(_Block("\n".join(buffer)))
    return blocks


def _structure_counts(blocks: list[_Block]) -> dict:
    rows = sum(1 for block in blocks if block.kind == "table" for line in block.text.splitlines() if not _MD_TABLE_SEP.match(line))
    return {"headings": sum(block.kind == "heading" for block in blocks), "table_rows": rows,
            "code": sum(block.kind == "code" for block in blocks), "chars": sum(len(block.text) for block in blocks if block.kind != "heading"),
            "numbers": sum(len(_DIGITS.findall(block.text)) for block in blocks)}


def _trafilatura_doc(markup: str, url: str) -> tuple[list[_Block] | None, str | None]:
    """trafilatura 2.4.0으로 표, 소제목, 코드를 살린 Markdown을 뽑는다. figcaption은 버려지므로 미리 문단으로 옮긴다."""
    try:
        import trafilatura
    except ImportError:
        return None, None
    prepared = _figures_to_paragraphs(markup)
    try:
        markdown = trafilatura.extract(prepared, url=url, output_format="markdown", favor_recall=True, include_tables=True,
                                       include_images=True, include_links=False, include_formatting=True, include_comments=False,
                                       deduplicate=False)
        metadata = trafilatura.extract_metadata(markup, default_url=url)
    except Exception:  # noqa: BLE001 - 추출기 내부 오류는 예전 파서로 넘기는 사유일 뿐이다.
        return None, None
    estimated = getattr(metadata, "date", None) if metadata is not None else None
    return (_markdown_blocks(markdown) if markdown else None), estimated


def _readability_doc(markup: str, url: str) -> list[_Block] | None:
    """두 번째 구조 추출기: readability-lxml로 본문 영역을 고르고 markdownify로 Markdown을 만든다.
    trafilatura가 소제목이나 코드를 버리는 페이지(velog, 정부 보도자료 등)를 보완한다."""
    try:
        from markdownify import markdownify
        from readability import Document
    except ImportError:
        return None
    try:
        summary = Document(_figures_to_paragraphs(markup), url=url).summary(html_partial=True)
        markdown = markdownify(summary, heading_style="ATX", bullets="-", strip=["a"], table_infer_header=True,
                               escape_asterisks=False, escape_underscores=False)
    except Exception:  # noqa: BLE001 - 추출기 내부 오류는 다른 후보로 넘기는 사유일 뿐이다.
        return None
    return _markdown_blocks(markdown) if markdown and markdown.strip() else None


def _coverage(source: dict, blocks: list[_Block], legacy_chars: int) -> float:
    """원문 구조를 얼마나 살렸나(소제목, 표, 코드, 글자 각 0~1의 합). 두 추출기가 모두 관문을 통과하면 높은 쪽을 쓴다."""
    found = _structure_counts(blocks)
    return sum((
        min(1.0, found["headings"] / source["headings"]) if source["headings"] else 1.0,
        (1.0 if found["table_rows"] else 0.0) if source["tables"] else 1.0,
        min(1.0, found["code"] / source["code"]) if source["code"] else 1.0,
        min(1.0, found["chars"] / legacy_chars) if legacy_chars else 1.0,
    ))


def _gate(source: dict, blocks: list[_Block] | None, legacy_chars: int, legacy_numbers: int) -> str | None:
    """구조 추출 결과를 원문과 맞춰 본다. 떨어지면 이유를 돌려준다(기준값은 2026-11-24 점검의 출발점)."""
    if not blocks:
        return "구조 추출 결과가 비어 있습니다"
    found = _structure_counts(blocks)
    if found["chars"] < MIN_LINK_CHARS:
        return f"구조 추출 본문이 {found['chars']}자뿐입니다"
    if legacy_chars >= 600 and found["chars"] < legacy_chars * 0.5:
        return f"구조 추출 글자가 {found['chars']:,}자로 예전 파서({legacy_chars:,}자)의 절반이 안 됩니다"
    if legacy_numbers >= 30 and found["numbers"] < legacy_numbers * 0.5:
        return f"숫자가 {found['numbers']}개로 예전 파서({legacy_numbers}개)의 절반이 안 됩니다"
    if source["headings"] >= 3 and found["headings"] == 0:
        return f"소제목 0개, 원문은 {source['headings']}개입니다"
    if source["tables"] >= 1 and found["table_rows"] == 0:
        return f"표 행 0개, 원문 표는 {source['tables']}개입니다"
    if source["code"] >= 1 and found["code"] == 0:
        return f"코드 블록 0개, 원문은 {source['code']}개입니다"
    return None


def _html_doc(markup: str, url: str) -> _Doc:
    original, markup = markup, (_main_region(markup, url) or markup)
    page = _PageText()
    page.feed(markup)
    page.close_block()
    legacy = [text for text in page.paragraphs if len(text) >= 25]
    title = _clean(page.social_title or page.title)[:200] or None
    if title and _BLOCKED_PAGE.search(title):
        raise _Unreadable("본문을 읽지 못했습니다. 로그인이 필요하거나 차단 안내 화면일 수 있습니다. 본문을 복사해 '본문 붙여넣기'로 넣어 주세요.")
    structured, estimated = _trafilatura_doc(markup, url)
    legacy_chars = sum(map(len, legacy))
    legacy_numbers = sum(len(_DIGITS.findall(text)) for text in legacy)
    source = _source_counts(markup)
    dates = _page_dates(original, estimated)
    # 미리 정한 한 번의 비교: 두 추출기를 함께 돌려 원문과 대조하고, 통과한 것 중 원문 구조를 더 살린 쪽을 쓴다.
    candidates = [("trafilatura-2.4.0", structured), ("readability-0.9", _readability_doc(markup, url))]
    judged = [(name, blocks, _gate(source, blocks, legacy_chars, legacy_numbers)) for name, blocks in candidates]
    passing = [(name, blocks) for name, blocks, reason in judged if reason is None]
    if passing:
        name, blocks = max(passing, key=lambda pair: _coverage(source, pair[1], legacy_chars))  # 같으면 앞의 trafilatura
        return _Doc(title, blocks, name, dates=dates)
    if legacy_chars < MIN_LINK_CHARS:
        raise _Unreadable("본문을 읽지 못했습니다. 로그인이 필요하거나 차단 안내 화면일 수 있습니다. 본문을 복사해 '본문 붙여넣기'로 넣어 주세요.",
                          title)
    tried = [f"{name.split('-')[0]}: {reason}" for name, blocks, reason in judged if blocks is not None]
    note = f"표와 소제목을 살리지 못해 예전 방식으로 저장했습니다({'; '.join(tried)})." if tried else ""
    doc = _plain(legacy, "html-parser", title)
    doc.note, doc.dates = note[:300], dates
    return doc



def page_text(markup: str, url: str) -> dict:
    """자료 창고 밖에서도 같은 방식으로 웹 본문을 읽는 공용 함수(2026-11-25).

    오늘의 뉴스 근거 수집(evidence), 기획 카드 공개 근거(public_discovery), 수집 때 읽기 확인(source_access)이 쓴다.
    두 추출기(trafilatura, readability)를 함께 돌려 원문 HTML과 대조하고, 표와 코드는 한 문단으로 둔다(너무 길면 머리행을
    되풀이해 나눈다). 문단은 빈 줄로 나눈다. 둘 다 관문에서 떨어지거나 본문을 못 읽으면 text를 비워 돌려주고,
    부른 쪽은 자기 예전 파서로 읽는다. 그래서 새 추출기가 실패해도 예전보다 나빠지지 않는다.
    """
    try:
        doc = _html_doc(markup, url or "")
    except _Unreadable as error:
        return {"text": "", "extractor": None, "note": str(error)[:300]}
    except Exception as error:  # noqa: BLE001 - 추출기 오류는 예전 파서로 넘기는 사유일 뿐이다.
        return {"text": "", "extractor": None, "note": f"구조 추출 오류: {type(error).__name__}"}
    if doc.extractor == "html-parser":
        return {"text": "", "extractor": None, "note": doc.note}
    parts: list[str] = []
    for block in doc.blocks:
        if block.kind in ("table", "code"):
            parts += [re.sub(r"\n\s*\n", "\n", piece) for piece in _split_block(block) if piece.strip()]
        elif block.text.strip():
            parts.append(re.sub(r"\n\s*\n", "\n", block.text.strip()))
    return {"text": "\n\n".join(parts)[:60000], "extractor": doc.extractor, "note": doc.note}


# ---------------------------------------------------------------- files
def _pdf_doc(data: bytes) -> _Doc:
    """PDF를 쪽마다 읽어 쪽 번호를 남긴다. 여러 쪽에 되풀이되는 머리말·워터마크 줄과 쪽 번호만 있는 줄은 뺀다."""
    try:
        import pypdf
    except ImportError as exc:
        raise WorkflowError("이 서버는 PDF를 읽지 못합니다. 글자를 복사해 '본문 붙여넣기'로 넣거나 txt, md, docx로 올려 주세요.") from exc
    reader = pypdf.PdfReader(io.BytesIO(data))
    total = len(reader.pages)
    texts = []
    for page in reader.pages[:MAX_PDF_PAGES]:
        try:
            texts.append(unicodedata.normalize("NFKC", page.extract_text() or ""))
        except Exception:  # noqa: BLE001 - 한 쪽이 깨져도 나머지 쪽은 읽는다.
            texts.append("")
    readable = [text for text in texts if len(text.strip()) >= 30 and text.count("�") <= len(text) * 0.05]
    counts: dict[str, int] = {}
    for text in readable:
        for line in {_clean(line) for line in text.splitlines() if 4 <= len(_clean(line)) <= 120}:
            counts[line] = counts.get(line, 0) + 1
    repeated = {line for line, count in counts.items() if len(readable) >= 3 and count >= max(3, len(readable) * 0.5)}
    blocks, empty = [], 0
    for number, text in enumerate(texts, 1):
        if len(text.strip()) < 30 or text.count("�") > len(text) * 0.05:
            empty += 1
            continue
        lines = [_clean(line) for line in text.splitlines()]
        lines = [line for line in lines if line not in repeated and not re.fullmatch(r"[-–— ]*\d{1,4}[-–— ]*(?:/\s*\d{1,4})?", line)]
        for paragraph in re.split(r"\n\s*\n", "\n".join(lines)):
            joined = " ".join(line for line in paragraph.splitlines() if line)
            if joined:
                blocks.append(_Block(joined, locator=f"p.{number}"))
    if sum(len(block.text) for block in blocks) < 200:
        raise WorkflowError("PDF에서 글자를 읽지 못했습니다. 스캔본이면 글자를 복사해 '본문 붙여넣기'로 넣어 주세요.")
    notes = []
    if empty:
        notes.append(f"{empty}쪽은 글자층이 없거나 깨져 읽지 못했습니다(그림이나 스캔).")
    if total > MAX_PDF_PAGES:
        notes.append(f"앞 {MAX_PDF_PAGES}쪽만 읽었습니다(전체 {total}쪽).")
    dates = {}
    try:
        info = reader.metadata
        created = getattr(info, "creation_date", None) if info else None
        modified = getattr(info, "modification_date", None) if info else None
        published = _valid_date(created.isoformat()) if created else None
        if published:
            dates = {"published_at": published, "modified_at": _valid_date(modified.isoformat()) if modified else None, "date_source": "pdf-metadata"}
    except Exception:  # noqa: BLE001 - 날짜 정보가 깨진 PDF도 본문은 저장한다.
        dates = {}
    return _Doc(None, blocks, "pypdf-7.1.1", " ".join(notes), dates)


_W = "{http://schemas.openxmlformats.org/wordprocessingml/2006/main}"
_HEADING_STYLE = re.compile(r"^(?:heading|제목)\s*(\d)$|^title$", re.I)


def _docx_text(node) -> str:
    parts = []
    for child in node.iter():
        if child.tag == _W + "t":
            parts.append(child.text or "")
        elif child.tag == _W + "tab":
            parts.append(" ")
        elif child.tag in (_W + "br", _W + "cr"):
            parts.append("\n")
    return _clean("".join(parts))


def _docx_table(table) -> list[_Block]:
    rows = []
    for row in table.findall(_W + "tr"):
        cells = [" ".join(_docx_text(paragraph) for paragraph in cell.iter(_W + "p")).replace("|", "/").replace("\n", " ").strip()
                 for cell in row.findall(_W + "tc")]
        if any(cells):
            rows.append(cells)
    if not rows:
        return []
    if max(map(len, rows)) == 1:
        return [_Block(cells[0]) for cells in rows if cells[0]]
    width = max(map(len, rows))
    rows = [cells + [""] * (width - len(cells)) for cells in rows]
    lines = ["| " + " | ".join(rows[0]) + " |", "|" + " --- |" * width] + ["| " + " | ".join(cells) + " |" for cells in rows[1:]]
    return [_Block("\n".join(lines), "table")]


def _docx_doc(data: bytes) -> _Doc:
    """docx 본문을 순서대로 읽는다. 제목 스타일은 소제목으로, 표는 머리행 있는 표로 둔다."""
    with zipfile.ZipFile(io.BytesIO(data)) as archive:
        entry = archive.getinfo("word/document.xml")
        if entry.file_size > 30_000_000:
            raise WorkflowError("문서가 너무 큽니다.")
        tree = ElementTree.fromstring(archive.read(entry))
        try:
            core = archive.read("docProps/core.xml") if archive.getinfo("docProps/core.xml").file_size < 1_000_000 else b""
        except KeyError:
            core = b""
    body = tree.find(_W + "body")
    blocks: list[_Block] = []
    for node in (list(body) if body is not None else []):
        if node.tag == _W + "p":
            text = _docx_text(node)
            if not text:
                continue
            style = node.find(f"{_W}pPr/{_W}pStyle")
            match = _HEADING_STYLE.match((style.get(_W + "val") or "") if style is not None else "")
            blocks.append(_Block(text, "heading", int(match.group(1) or 1)) if match else _Block(text))
        elif node.tag == _W + "tbl":
            blocks.extend(_docx_table(node))
    dates = {}
    if core:
        try:
            meta = ElementTree.fromstring(core)
            created = next((n.text for n in meta.iter() if n.tag.endswith("}created")), None)
            modified = next((n.text for n in meta.iter() if n.tag.endswith("}modified")), None)
            if _valid_date(created):
                dates = {"published_at": _valid_date(created), "modified_at": _valid_date(modified), "date_source": "docx-core"}
        except ElementTree.ParseError:
            dates = {}
    return _Doc(None, blocks, "docx-xml", dates=dates)


# ---------------------------------------------------------------- passages
def _cut_long(text: str, limit: int) -> list[str]:
    pieces = []
    while len(text) > limit * 1.5:
        cut = max(text.rfind(". ", 0, limit), text.rfind("다. ", 0, limit) + 1, limit - 1) + 1
        pieces.append(text[:cut].strip())
        text = text[cut:].strip()
    return pieces + ([text] if text else [])


def _split_block(block: _Block) -> list[str]:
    """표와 코드는 한 덩어리로 둔다. 한도를 넘으면 표는 머리행을 되풀이해 행으로, 코드는 줄로 나눈다."""
    if len(block.text) <= BLOCK_CHARS:
        return [block.text]
    lines = block.text.splitlines()
    if block.kind == "table":
        head = lines[:2] if len(lines) > 1 and _MD_TABLE_SEP.match(lines[1]) else lines[:1]
        body, pieces, current = lines[len(head):], [], []
        for line in body:
            if current and len("\n".join(head + current + [line])) > BLOCK_CHARS:
                pieces.append("\n".join(head + current))
                current = []
            current.append(line[:BLOCK_CHARS - 200])
        return pieces + (["\n".join(head + current)] if current else [])
    fence = lines[0] if lines and _MD_FENCE.match(lines[0]) else None
    inner = lines[1:-1] if fence else lines
    pieces, current = [], []
    for line in inner:
        if current and len("\n".join(current + [line])) > BLOCK_CHARS - 20:
            pieces.append(current)
            current = []
        current.append(line[:BLOCK_CHARS - 40])
    pieces += [current] if current else []
    closing_fence = lines[-1].strip() if fence else ""
    return ["\n".join(([fence] if fence else []) + part + ([closing_fence] if fence else [])) for part in pieces]


def _chunk_blocks(blocks: list[_Block], limit: int = PASSAGE_CHARS) -> list[tuple[str, str | None, str | None]]:
    """덩어리를 검색 문단으로 묶는다. 소제목에서 새 문단을 시작하고 쪽(locator)을 넘지 않는다. (본문, 쪽, 소제목 경로)를 돌려준다."""
    out: list[tuple[str, str | None, str | None]] = []
    current: list[str] = []
    size, locator, heading_at_start, path = 0, None, None, {}

    def heading_path():
        value = " > ".join(path[level] for level in sorted(path))
        return value[:160] or None

    def flush():
        nonlocal current, size
        text = "\n".join(current).strip()
        if text and not all(line.strip() in path.values() for line in current):
            out.append((text, locator, heading_at_start))
        current, size = [], 0

    for block in blocks:
        if block.locator != locator:
            flush()
            locator = block.locator
        if block.kind == "heading":
            if size >= 150 and not all(line in path.values() for line in current):
                flush()
            for level in [level for level in path if level >= block.level]:
                del path[level]
            path[block.level] = block.text[:80]
            if not current:
                heading_at_start = heading_path()
            current.append(block.text)
            size += len(block.text) + 1
            continue
        pieces = _split_block(block) if block.kind in ("table", "code") else _cut_long(_clean(block.text), limit)
        for piece in pieces:
            if not piece:
                continue
            atomic = block.kind in ("table", "code")
            if current and size + len(piece) + 1 > (BLOCK_CHARS if atomic else limit):
                headings_only = all(line in path.values() for line in current)
                if not headings_only:
                    flush()
            if not current:
                heading_at_start = heading_path()
            current.append(piece)
            size += len(piece) + 1
    flush()
    return out


def _safe_xml(raw: bytes):
    """공개 기관 XML의 DOCTYPE 한 줄만 걷어 내고, 엔티티 선언이 남아 있으면 읽지 않는다."""
    raw = re.sub(rb"<!DOCTYPE[^\[>]*>", b"", raw, count=1)
    if b"<!DOCTYPE" in raw or b"<!ENTITY" in raw:
        raise WorkflowError("문서 형식을 확인할 수 없습니다.")
    return ElementTree.fromstring(raw)


def _host(parts) -> str:
    return (parts.hostname or "").lower().removeprefix("www.").removeprefix("m.")


def _youtube_id(parts) -> str | None:
    host = _host(parts)
    if host == "youtu.be":
        return parts.path.strip("/").split("/")[0] or None
    if host in ("youtube.com", "music.youtube.com"):
        if parts.path == "/watch":
            return (parse_qs(parts.query).get("v") or [None])[0]
        match = re.match(r"/(shorts|live|embed)/([\w-]{6,})", parts.path)
        return match.group(2) if match else None
    return None


def _ncbi_target(parts) -> tuple[str, str] | None:
    host = (parts.hostname or "").lower()
    match = re.search(r"/articles/(PMC\d+)", parts.path)
    if match and host in ("pmc.ncbi.nlm.nih.gov", "www.ncbi.nlm.nih.gov"):
        return "pmc", match.group(1)[3:]
    match = re.fullmatch(r"/(\d+)/?", parts.path)
    if match and host == "pubmed.ncbi.nlm.nih.gov":
        return "pubmed", match.group(1)
    return None


def _arxiv_id(parts) -> str | None:
    if _host(parts) != "arxiv.org":
        return None
    match = re.fullmatch(r"/(?:pdf|abs)/(\d{4}\.\d{4,5}(?:v\d+)?)(?:\.pdf)?/?", parts.path)
    return match.group(1) if match else None


def _youtube_title(video: str, fetch) -> str | None:
    try:
        watch = quote(f"https://www.youtube.com/watch?v={video}", safe="")
        raw, _, _ = fetch(f"https://www.youtube.com/oembed?format=json&url={watch}", maximum=100_000)
        title = json.loads(raw.decode("utf-8")).get("title")
        return _clean(title)[:200] if isinstance(title, str) and title.strip() else None
    except (*_READ_ERRORS, json.JSONDecodeError, UnicodeDecodeError, AttributeError):
        return None


def _ncbi_date(tree, database: str) -> dict:
    for path in ((".//ArticleDate", ".//PubDate") if database == "pubmed" else (".//pub-date[@pub-type='epub']", ".//pub-date")):
        node = tree.find(path)
        if node is None:
            continue
        parts = [(node.findtext(name) or node.findtext(name.lower()) or "").strip() for name in ("Year", "Month", "Day")]
        months = {m: i for i, m in enumerate(("jan", "feb", "mar", "apr", "may", "jun", "jul", "aug", "sep", "oct", "nov", "dec"), 1)}
        month = months.get(parts[1][:3].lower(), parts[1]) if parts[1] else ""
        found = _valid_date(f"{parts[0]}-{month or 1}-{parts[2] or 1}") if parts[0] else None
        if found:
            return {"published_at": found, "modified_at": None, "date_source": "ncbi-xml"}
    return {}


def _read_ncbi(database: str, ident: str, fetch) -> _Doc:
    """PubMed·PMC는 기관이 제공하는 E-utilities XML로 읽는다(기사 화면을 긁지 않는다)."""
    query = f"db={database}&id={ident}&retmode=xml" + ("&rettype=abstract" if database == "pubmed" else "")
    raw, _, _ = fetch("https://eutils.ncbi.nlm.nih.gov/entrez/eutils/efetch.fcgi?" + query, maximum=MAX_PAGE_BYTES)
    tree = _safe_xml(raw)

    def text(node):
        return _clean("".join(node.itertext()))

    if database == "pubmed":
        heading = tree.find(".//ArticleTitle")
        paragraphs = [(f"{node.get('Label')}: " if node.get("Label") else "") + text(node) for node in tree.iter("AbstractText")]
    else:
        heading = tree.find(".//article-title")
        paragraphs = [text(node) for section in (tree.find(".//abstract"), tree.find(".//body")) if section is not None
                      for node in section.iter("p")]
    if sum(map(len, paragraphs)) < 300:
        raise _Unreadable("이 논문은 공개 본문이 없습니다. 초록이나 본문을 복사해 '본문 붙여넣기'로 넣어 주세요.",
                          text(heading)[:200] if heading is not None else None)
    doc = _plain(paragraphs, "ncbi-eutils", (text(heading)[:200] if heading is not None else None))
    doc.dates = _ncbi_date(tree, database)
    return doc


def _read_page(url: str, fetch) -> _Doc:
    raw, final_url, content_type = fetch(url, maximum=MAX_PAGE_BYTES)
    blocked = _blocked_reason(final_url)
    if blocked:
        raise _Unreadable(blocked)
    kind = (content_type or "").lower()
    if "pdf" in kind or urlsplit(final_url).path.lower().endswith(".pdf"):
        return _pdf_doc(raw)
    charset = re.search(r"charset=([\w-]+)", kind)
    try:
        markup = raw.decode(charset.group(1) if charset else "utf-8", "replace")
    except LookupError:
        markup = raw.decode("utf-8", "replace")
    return _html_doc(markup, final_url)


def _read_link(url: str, fetch) -> _Doc:
    blocked = _blocked_reason(url)
    if blocked:
        raise _Unreadable(blocked)
    parts = urlsplit(url)
    video = _youtube_id(parts)
    if video:
        raise _Unreadable(YOUTUBE_MESSAGE, _youtube_title(video, fetch))
    target = _ncbi_target(parts)
    if target:
        return _read_ncbi(*target, fetch)
    paper = _arxiv_id(parts)
    if paper:
        for candidate in (f"https://arxiv.org/html/{paper}", f"https://arxiv.org/abs/{paper}"):
            try:
                return _read_page(candidate, fetch)
            except _READ_ERRORS:
                continue
        raise _Unreadable("arXiv에서 이 논문의 HTML판과 초록을 읽지 못했습니다. 본문을 복사해 '본문 붙여넣기'로 넣어 주세요.")
    return _read_page(url, fetch)


def _file_doc(name: str, data: bytes) -> _Doc:
    lowered = name.lower()
    if lowered.endswith(".pdf"):
        return _pdf_doc(data)
    if lowered.endswith(".docx"):
        return _docx_doc(data)
    if lowered.endswith(".md"):
        return _Doc(None, _markdown_blocks(data.decode("utf-8", "replace")), "markdown")
    if lowered.endswith(".txt"):
        return _plain(re.split(r"\n\s*\n", data.decode("utf-8", "replace")), "text")
    raise WorkflowError("txt, md, docx, pdf 파일만 넣을 수 있습니다.")


def _view(row: sqlite3.Row) -> dict:
    return {
        "id": row["id"], "kind": row["kind"], "area": row["area"], "area_label": AREAS.get(row["area"], row["area"]),
        "mine": bool(row["mine"]), "title": row["title"], "url": row["url"], "status": row["status"],
        "note": row["note"], "passages": row["passages"], "use_as_evidence": bool(row["use_as_evidence"]),
        "pasted": row["pasted"] is not None, "origin": row["origin"], "origin_ref": row["origin_ref"],
        "lane": row["lane"] if row["lane"] in LANES else "fact", "lane_label": LANES.get(row["lane"], LANES["fact"]),
        "file_name": row["file_name"], "created_at": row["created_at"], "updated_at": row["updated_at"],
        **{key: (row[key] if key in row.keys() else None) for key in ("published_at", "modified_at", "collected_at", "date_source", "extractor")},
    }


def _item(db: sqlite3.Connection, item_id: str) -> sqlite3.Row:
    row = db.execute("SELECT * FROM items WHERE id=?", (item_id,)).fetchone()
    if row is None:
        raise WorkflowError("자료를 찾을 수 없습니다. 목록을 새로 고쳐 주세요.")
    return row


def _labels(area, origin, origin_ref) -> tuple[str, str, str | None]:
    if area not in AREAS:
        raise WorkflowError("분야를 골라 주세요.")
    if origin not in ORIGINS:
        raise WorkflowError("자료를 넣은 경로를 확인할 수 없습니다.")
    if origin_ref is not None and (not isinstance(origin_ref, str) or not _REF.fullmatch(origin_ref)):
        raise WorkflowError("연결된 항목을 확인할 수 없습니다.")
    return area, origin, origin_ref


def _insert(db, *, kind, area, mine, title, url=None, file_name=None, body=None, origin="manual", origin_ref=None, lane="fact") -> str:
    if lane not in LANES:
        raise WorkflowError("사실 근거용인지 사례·참고용인지 골라 주세요.")
    item_id = secrets.token_hex(10)
    stamp = _now()
    db.execute(
        "INSERT INTO items(id, kind, area, mine, title, url, url_norm, status, file_name, body, origin, origin_ref, lane, created_at, updated_at) "
        "VALUES (?,?,?,?,?,?,?, 'pending', ?,?,?,?,?,?,?)",
        (item_id, kind, area, int(bool(mine)), title, url, normalize_url(url) if url else None, file_name, body,
         origin, origin_ref, lane, stamp, stamp))
    return item_id


def _store_passages(db, item_id: str, document, title: str | None = None, *, minimum: int = 80) -> None:
    """읽은 문서를 검색 문단으로 나눠 저장한다. document는 _Doc이거나 문단 문자열 목록이다."""
    from .evidence_relevance import is_evidence_noise

    doc = document if isinstance(document, _Doc) else _plain(document, "text")
    if db.execute("SELECT kind FROM items WHERE id=?", (item_id,)).fetchone()[0] == "link":
        doc.blocks = [block for block in doc.blocks if block.kind != "para" or not is_evidence_noise(block.text)]
    passages = _chunk_blocks(doc.blocks)
    chars = sum(len(text) for text, _, _ in passages)
    if chars < minimum:
        if minimum > 80:
            raise WorkflowError(f"본문이 {chars}자뿐이라 저장하지 않았습니다. 로그인이 필요하거나 본문이 그림일 수 있습니다. "
                                "본문을 복사해 '본문 붙여넣기'로 넣어 주세요.")
        raise WorkflowError("저장할 본문이 너무 짧습니다. 내용을 조금 더 넣어 주세요.")
    content_hash = hashlib.sha256("\n".join(text for text, _, _ in passages).encode("utf-8")).hexdigest()
    same = db.execute("SELECT title FROM items WHERE content_hash=? AND id<>? AND status='done'", (content_hash, item_id)).fetchone()
    if same:
        db.execute("UPDATE items SET status='duplicate', note=?, content_hash=?, passages=0, updated_at=? WHERE id=?",
                   (f"'{same['title']}'과 내용이 같아 다시 저장하지 않았습니다.", content_hash, _now(), item_id))
        return
    db.execute("DELETE FROM passages WHERE item_id=?", (item_id,))
    db.executemany("INSERT INTO passages(item_id, seq, text, locator, heading) VALUES (?,?,?,?,?)",
                   [(item_id, number, text, locator, heading) for number, (text, locator, heading) in enumerate(passages, 1)])
    dates = doc.dates or {}
    stamp = _now()
    db.execute("UPDATE items SET status='done', note=?, passages=?, content_hash=?, title=COALESCE(?, title), published_at=?, modified_at=?, "
               "collected_at=?, date_source=?, extractor=?, updated_at=? WHERE id=?",
               (doc.note[:300], len(passages), content_hash, title, dates.get("published_at"), dates.get("modified_at"), stamp,
                dates.get("date_source"), doc.extractor, stamp, item_id))


def _bounded_fetch():
    """한 자료를 읽는 데 쓰는 시간을 화면 요청 제한(30초) 안으로 묶는다."""
    deadline = monotonic() + LINK_SECONDS

    def fetch(url, *, maximum):
        return fetch_public(url, maximum=maximum, deadline=deadline)
    return fetch


def _read_item(root, item_id: str, fetch=None) -> dict:
    """한 자료를 읽어 문단으로 저장한다. 실패는 예외로 올리지 않고 '확인 필요'와 사유로 남긴다."""
    fetch = fetch or _bounded_fetch()
    with closing(_connect(root)) as db:
        with db:
            row = _item(db, item_id)
            db.execute("UPDATE items SET status='working', updated_at=? WHERE id=?", (_now(), item_id))
        found_title = None
        try:
            title, minimum = None, 80
            if row["kind"] == "link":
                document = _read_link(row["url"], fetch)
                title, minimum = (document.title if row["title"] == row["url"] else None), MIN_LINK_CHARS
            elif row["kind"] == "file":
                document = _file_doc(row["file_name"], base64.b64decode(row["body"]))
            else:
                document = _plain(re.split(r"\n\s*\n", row["body"]), "memo")
            with db:
                _store_passages(db, item_id, document, title, minimum=minimum)
        except _READ_ERRORS as exc:
            found_title = getattr(exc, "title", None) if row["title"] == row["url"] else None
            reason = str(exc) if isinstance(exc, WorkflowError) else f"가져오지 못했습니다({type(exc).__name__}). 주소를 확인하거나 본문을 붙여 넣어 주세요."
            with db:
                db.execute("UPDATE items SET status='needs_check', note=?, use_as_evidence=0, title=COALESCE(?, title), updated_at=? WHERE id=?",
                           (reason[:300], found_title, _now(), item_id))
        return _view(_item(db, item_id))


def _turn_on(root, item_id: str) -> dict:
    with closing(_connect(root)) as db, db:
        db.execute("UPDATE items SET use_as_evidence=1, updated_at=? WHERE id=? AND status='done'", (_now(), item_id))
        return _view(_item(db, item_id))


def add_links(root, urls, *, area, mine=False, origin="manual", origin_ref=None, title=None, fetch=None,
              lane="fact", use_as_evidence=False) -> list[dict]:
    """use_as_evidence는 운영자가 외부 조사 후보에서 직접 고른 자료에만 쓴다. 본문을 읽은 자료만 근거로 켠다."""
    area, origin, origin_ref = _labels(area, origin, origin_ref)
    if lane not in LANES:
        raise WorkflowError("사실 근거용인지 사례·참고용인지 골라 주세요.")
    cleaned = list(dict.fromkeys(url.strip() for url in urls if isinstance(url, str) and url.strip()))
    if not cleaned:
        raise WorkflowError("링크를 한 개 이상 넣어 주세요.")
    if len(cleaned) > MAX_LINKS:
        raise WorkflowError(f"링크는 한 번에 {MAX_LINKS}개까지 넣을 수 있습니다.")
    results = []
    for url in cleaned:
        parts = urlsplit(url)
        if parts.scheme != "https" or not parts.hostname or len(url) > 2048:
            results.append({"url": url, "result": "rejected", "reason": "https://로 시작하는 공개 주소만 넣을 수 있습니다."})
            continue
        with closing(_connect(root)) as db, db:
            existing = db.execute("SELECT * FROM items WHERE url_norm=? AND status IN ('done','working','pending')", (normalize_url(url),)).fetchone()
            item_id = None if existing else _insert(db, kind="link", area=area, mine=mine, url=url, origin=origin, origin_ref=origin_ref,
                                                    lane=lane, title=_clean(title)[:200] if title and len(cleaned) == 1 else url)
        if existing:
            item = _turn_on(root, existing["id"]) if use_as_evidence else _view(existing)
            results.append({"url": url, "result": "exists", "item": item})
        else:
            item = _read_item(root, item_id, fetch)
            results.append({"url": url, "result": "added", "item": _turn_on(root, item_id) if use_as_evidence else item})
    return results


def add_memo(root, title, text, *, area, mine=True, origin="manual", origin_ref=None) -> dict:
    area, origin, origin_ref = _labels(area, origin, origin_ref)
    title, text = _clean(title or "")[:200], (text or "").strip()
    if not title or not text:
        raise WorkflowError("제목과 내용을 모두 적어 주세요.")
    if len(text) > MAX_MEMO_CHARS:
        raise WorkflowError(f"메모는 {MAX_MEMO_CHARS:,}자까지 넣을 수 있습니다. 나눠서 넣어 주세요.")
    with closing(_connect(root)) as db, db:
        item_id = _insert(db, kind="memo", area=area, mine=mine, title=title, body=text, origin=origin, origin_ref=origin_ref)
    return _read_item(root, item_id)


def add_file(root, name, content_base64, *, area, mine=False, origin="manual", origin_ref=None) -> dict:
    area, origin, origin_ref = _labels(area, origin, origin_ref)
    name = _clean(Path(name or "").name)[:200]
    if not name.lower().endswith((".txt", ".md", ".docx", ".pdf")):
        raise WorkflowError("txt, md, docx, pdf 파일만 넣을 수 있습니다.")
    try:
        data = base64.b64decode(content_base64 or "", validate=True)
    except (binascii.Error, ValueError) as exc:
        raise WorkflowError("파일을 읽지 못했습니다. 다시 올려 주세요.") from exc
    if not data or len(data) > MAX_FILE_BYTES:
        raise WorkflowError(f"파일은 {MAX_FILE_BYTES // 1_000_000}MB까지 넣을 수 있습니다.")
    with closing(_connect(root)) as db, db:
        item_id = _insert(db, kind="file", area=area, mine=mine, title=name, file_name=name,
                          body=base64.b64encode(data).decode("ascii"), origin=origin, origin_ref=origin_ref)
    return _read_item(root, item_id)


def retry_item(root, item_id: str, *, fetch=None) -> dict:
    with closing(_connect(root)) as db:
        if _item(db, item_id)["status"] != "needs_check":
            raise WorkflowError("확인이 필요한 자료만 다시 읽을 수 있습니다.")
    return _read_item(root, item_id, fetch)


def reread_item(root, item_id: str, *, fetch=None) -> dict:
    """이미 저장된 링크를 지금 규칙(구조 추출, 원문 대조, 날짜)으로 다시 읽는다.

    새로 못 읽었거나, 새 본문이 예전 본문의 절반이 안 되면 예전 본문을 그대로 둔다(나빠지지 않게).
    근거 사용 여부, 분야, 쓰임새, 제목은 바꾸지 않는다. 바뀐 문단의 벡터는 다시 계산해야 한다.
    """
    fetch = fetch or _bounded_fetch()
    with closing(_connect(root)) as db:
        row = _item(db, item_id)
        if row["kind"] != "link" or row["status"] != "done":
            raise WorkflowError("본문이 저장된 링크만 다시 읽을 수 있습니다.")
        old_chars = db.execute("SELECT COALESCE(SUM(LENGTH(text)), 0) FROM passages WHERE item_id=?", (item_id,)).fetchone()[0]
        old_hash = row["content_hash"]
        try:
            document = _read_link(row["url"], fetch)
        except _READ_ERRORS as exc:
            return {"id": item_id, "result": "kept", "reason": str(exc)[:200] if isinstance(exc, WorkflowError) else type(exc).__name__}
        new_chars = sum(len(text) for text, _, _ in _chunk_blocks(document.blocks))
        if old_chars >= 600 and new_chars < old_chars * 0.5:
            return {"id": item_id, "result": "kept", "reason": f"새 본문 {new_chars:,}자가 예전 {old_chars:,}자의 절반이 안 됩니다"}
        try:
            with db:
                _store_passages(db, item_id, document, None, minimum=MIN_LINK_CHARS)
        except WorkflowError as exc:
            return {"id": item_id, "result": "kept", "reason": str(exc)[:200]}
        after = _item(db, item_id)
        return {"id": item_id, "result": "same" if after["content_hash"] == old_hash else "updated", "status": after["status"],
                "extractor": after["extractor"], "old_chars": old_chars, "new_chars": new_chars, "passages": after["passages"]}


def fill_text(root, item_id: str, text: str, title: str | None = None) -> dict:
    """읽지 못한 링크·파일에 운영자가 복사한 본문을 붙여 넣는다. 링크 주소는 출처로 그대로 남긴다."""
    text = (text or "").strip() if isinstance(text, str) else ""
    if len(text) < 80:
        raise WorkflowError("본문을 80자 이상 붙여 넣어 주세요.")
    if len(text) > MAX_MEMO_CHARS:
        raise WorkflowError(f"본문은 {MAX_MEMO_CHARS:,}자까지 넣을 수 있습니다.")
    title = _clean(title)[:200] if isinstance(title, str) and title.strip() else None
    with closing(_connect(root)) as db:
        with db:
            row = _item(db, item_id)
            if row["kind"] == "memo" or row["status"] != "needs_check":
                raise WorkflowError("확인이 필요한 링크나 파일에만 본문을 붙여 넣을 수 있습니다.")
            if row["kind"] == "link" and not row["mine"] and _blocked_reason(row["url"]):
                raise WorkflowError("이 주소는 robots.txt가 수집을 막아 본문을 저장하지 않습니다. 직접 쓴 글이면 먼저 '내 자료'로 표시해 주세요.")
            db.execute("UPDATE items SET pasted=?, updated_at=? WHERE id=?", (text, _now(), item_id))
            _store_passages(db, item_id, _plain(re.split(r"\n\s*\n", text), "pasted"), title)
        return _view(_item(db, item_id))


def update_item(root, item_id: str, changes: dict) -> dict:
    allowed = {"use_as_evidence", "area", "mine", "title", "lane"}
    if not changes or set(changes) - allowed:
        raise WorkflowError("바꿀 수 없는 항목입니다.")
    with closing(_connect(root)) as db, db:
        row = _item(db, item_id)
        if "use_as_evidence" in changes:
            if not isinstance(changes["use_as_evidence"], bool):
                raise WorkflowError("근거 사용 여부를 확인할 수 없습니다.")
            if changes["use_as_evidence"] and row["status"] != "done":
                raise WorkflowError("본문이 저장된 자료만 근거로 쓸 수 있습니다.")
            db.execute("UPDATE items SET use_as_evidence=? WHERE id=?", (int(changes["use_as_evidence"]), item_id))
        if "area" in changes:
            if changes["area"] not in AREAS:
                raise WorkflowError("분야를 골라 주세요.")
            db.execute("UPDATE items SET area=? WHERE id=?", (changes["area"], item_id))
        if "lane" in changes:
            if changes["lane"] not in LANES:
                raise WorkflowError("사실 근거용인지 사례·참고용인지 골라 주세요.")
            db.execute("UPDATE items SET lane=? WHERE id=?", (changes["lane"], item_id))
        if "mine" in changes:
            if not isinstance(changes["mine"], bool):
                raise WorkflowError("내 자료 여부를 확인할 수 없습니다.")
            db.execute("UPDATE items SET mine=? WHERE id=?", (int(changes["mine"]), item_id))
        if "title" in changes:
            title = _clean(changes["title"])[:200] if isinstance(changes["title"], str) else ""
            if not title:
                raise WorkflowError("제목을 적어 주세요.")
            db.execute("UPDATE items SET title=? WHERE id=?", (title, item_id))
        db.execute("UPDATE items SET updated_at=? WHERE id=?", (_now(), item_id))
        return _view(_item(db, item_id))


def set_evidence(root, ids, value) -> dict:
    """여러 자료의 '초안 근거로 사용'을 한 번에 바꾼다. 켤 때는 본문이 저장된 자료만 바꾼다."""
    if not isinstance(value, bool):
        raise WorkflowError("근거 사용 여부를 확인할 수 없습니다.")
    if not isinstance(ids, list) or any(not isinstance(item_id, str) for item_id in ids):
        raise WorkflowError("자료 목록을 확인할 수 없습니다.")
    ids = list(dict.fromkeys(ids))
    if not ids or len(ids) > MAX_BULK:
        raise WorkflowError(f"자료는 한 번에 1개에서 {MAX_BULK}개까지 바꿀 수 있습니다.")
    stamp = _now()
    with closing(_connect(root)) as db, db:
        rows = db.execute(f"SELECT id, status FROM items WHERE id IN ({','.join('?' * len(ids))})", ids).fetchall()
        targets = [row["id"] for row in rows if not value or row["status"] == "done"]
        db.executemany("UPDATE items SET use_as_evidence=?, updated_at=? WHERE id=?", [(int(value), stamp, item_id) for item_id in targets])
    return {"changed": len(targets), "skipped": len(ids) - len(targets)}


def delete_item(root, item_id: str) -> dict:
    with closing(_connect(root)) as db, db:
        _item(db, item_id)
        db.execute("DELETE FROM items WHERE id=?", (item_id,))
    return {"deleted": item_id}


def item_detail(root, item_id: str) -> dict:
    with closing(_connect(root)) as db:
        item = _view(_item(db, item_id))
        rows = db.execute("SELECT text, locator, heading FROM passages WHERE item_id=? ORDER BY seq", (item_id,)).fetchall()
        item["passage_texts"] = [row["text"] for row in rows]
        item["passage_places"] = [{"locator": row["locator"], "heading": row["heading"]} for row in rows]
        return item


def example_urls(root) -> frozenset[str]:
    """사례·참고 칸에 둔 링크 주소. 초안에서 이 자료는 사실 근거가 아니라 소개할 사례로만 다룬다."""
    path = library_path(root)
    if not path.is_file():
        return frozenset()
    try:
        with closing(sqlite3.connect(path.as_uri() + "?mode=ro", uri=True, timeout=2)) as db:
            return frozenset(row[0] for row in db.execute("SELECT url FROM items WHERE lane='example' AND url IS NOT NULL"))
    except sqlite3.Error:
        return frozenset()


def vector_status(root) -> dict:
    """근거로 켠 링크 자료 가운데 공개 근거 검색에 들어갈 준비(벡터 계산)가 끝난 문단 수."""
    from .public_evidence import LIBRARY_MODEL, library_worker_available

    with closing(_connect(root)) as db:
        total, ready = db.execute(
            "SELECT COUNT(*), COALESCE(SUM(EXISTS(SELECT 1 FROM passage_vectors v WHERE v.item_id=p.item_id AND v.seq=p.seq AND v.model=?)), 0) "
            "FROM passages p JOIN items i ON i.id=p.item_id WHERE i.status='done' AND i.use_as_evidence=1 AND i.kind='link'",
            (LIBRARY_MODEL,)).fetchone()
    return {"passages": total, "ready": ready, "pending": total - ready, "available": library_worker_available(root)}


def library_overview(root) -> dict:
    with closing(_connect(root)) as db:
        items = [_view(row) for row in db.execute("SELECT * FROM items ORDER BY created_at DESC, id LIMIT 1000")]
    ready = [item for item in items if item["status"] == "done"]
    return {
        "areas": [{"id": key, "label": label, "items": sum(item["area"] == key for item in items)} for key, label in AREAS.items()],
        "items": items,
        "stats": {
            "items": len(items), "ready": len(ready), "passages": sum(item["passages"] for item in ready),
            "evidence": sum(item["use_as_evidence"] for item in ready),
            "needs_check": sum(item["status"] == "needs_check" for item in items),
        },
        "vectors": vector_status(root),
        "lanes": [{"id": key, "label": label} for key, label in LANES.items()],
        "limits": {"links": MAX_LINKS, "file_mb": MAX_FILE_BYTES // 1_000_000, "memo_chars": MAX_MEMO_CHARS},
    }


def search_library(root, query: str, *, area: str | None = None, evidence_only: bool = False, limit: int = 8) -> list[dict]:
    """창고 화면의 키워드 검색(BM25). 초안 근거 검색은 public_evidence가 같은 문단을 뜻으로 찾는다."""
    terms = list(dict.fromkeys(_WORD.findall(unicodedata.normalize("NFKC", query or "").casefold())))[:16]
    if area is not None and area not in AREAS:
        raise WorkflowError("분야를 골라 주세요.")
    if not terms:
        return []
    with closing(_connect(root)) as db:
        rows = db.execute(
            "SELECT p.item_id, p.seq, p.text, i.title, i.url, i.area, i.mine, i.kind, i.use_as_evidence FROM passages p "
            "JOIN items i ON i.id=p.item_id WHERE i.status='done' AND (? IS NULL OR i.area=?) AND (?=0 OR i.use_as_evidence=1)",
            (area, area, int(evidence_only))).fetchall()
    if not rows:
        return []
    texts = [(row["title"] + "\n" + row["text"]).casefold() for row in rows]
    average = sum(map(len, texts)) / len(texts)
    frequency = {term: sum(term in text for text in texts) for term in terms}
    scored = []
    for row, text in zip(rows, texts):
        score = 0.0
        for term in terms:
            count = text.count(term)
            if count:
                rarity = math.log(1 + (len(rows) - frequency[term] + 0.5) / (frequency[term] + 0.5))
                score += rarity * count * 2.2 / (count + 1.2 * (0.25 + 0.75 * len(text) / average))
        if score > 0:
            scored.append((score, row))
    scored.sort(key=lambda pair: (-pair[0], pair[1]["item_id"], pair[1]["seq"]))
    return [{
        "item_id": row["item_id"], "paragraph": row["seq"], "title": row["title"], "url": row["url"],
        "area": row["area"], "area_label": AREAS.get(row["area"], row["area"]), "mine": bool(row["mine"]), "kind": row["kind"],
        "use_as_evidence": bool(row["use_as_evidence"]), "text": row["text"][:700], "score": round(score, 2),
        "matched": [term for term in terms if term in row["text"].casefold()],
    } for score, row in scored[:max(1, min(limit, 20))]]


def import_inbox(root, rows) -> list[dict]:
    """예전 자료함(별도 서비스)에서 내보낸 자료를 그대로 옮긴다. 같은 주소·같은 본문은 다시 넣지 않는다."""
    if not isinstance(rows, list):
        raise WorkflowError("가져올 자료 목록을 확인할 수 없습니다.")
    results = []
    with closing(_connect(root)) as db:
        for row in rows:
            source = row.get("id") if isinstance(row, dict) else None
            chunks = row.get("chunks") if isinstance(row, dict) else None
            if (not isinstance(source, str) or not _REF.fullmatch(source) or row.get("kind") not in ("link", "memo", "file")
                    or not isinstance(chunks, list) or not all(isinstance(text, str) and text.strip() for text in chunks)):
                results.append({"source": source, "result": "rejected", "reason": "형식이 맞지 않습니다."})
                continue
            if row.get("status") != "done" or not chunks:
                results.append({"source": source, "result": "skipped", "reason": "본문이 저장되지 않은 자료입니다."})
                continue
            url = row.get("url") if isinstance(row.get("url"), str) and row["url"].startswith("https://") else None
            blocked = _blocked_reason(url) if row["kind"] == "link" else None
            if blocked:
                results.append({"source": source, "result": "skipped", "reason": blocked})
                continue
            if row["kind"] == "link" and sum(len(text.strip()) for text in chunks) < MIN_LINK_CHARS:
                results.append({"source": source, "result": "skipped", "reason": f"본문이 {MIN_LINK_CHARS}자보다 짧아 근거로 옮기지 않았습니다."})
                continue
            norm = normalize_url(url) if url else None
            content_hash = hashlib.sha256("\n".join(chunks).encode("utf-8")).hexdigest()
            existing = db.execute("SELECT id, title FROM items WHERE (? IS NOT NULL AND url_norm=?) OR content_hash=?",
                                  (norm, norm, content_hash)).fetchone()
            if existing:
                results.append({"source": source, "result": "exists", "id": existing["id"], "title": existing["title"]})
                continue
            area, mine = _INBOX_AREAS.get(row.get("grp"), ("B", False))
            title = _clean(str(row.get("title") or url or "가져온 자료"))[:200]
            created = row.get("created_at")
            stamp = (datetime.fromtimestamp(created, timezone.utc).isoformat(timespec="seconds")
                     if isinstance(created, (int, float)) and not isinstance(created, bool) else _now())
            item_id = secrets.token_hex(10)
            with db:
                db.execute(
                    "INSERT INTO items(id, kind, area, mine, title, url, url_norm, status, passages, content_hash, file_name, body, "
                    "origin, origin_ref, extractor, created_at, updated_at) VALUES (?,?,?,?,?,?,?, 'done', ?,?,?,?, 'import', ?, 'inbox-import', ?,?)",
                    (item_id, row["kind"], area, int(mine), title, url, norm, len(chunks), content_hash,
                     row.get("file_name") if isinstance(row.get("file_name"), str) else None,
                     row.get("body") if row["kind"] == "memo" and isinstance(row.get("body"), str) else None,
                     source, stamp, _now()))
                db.executemany("INSERT INTO passages(item_id, seq, text) VALUES (?,?,?)",
                               [(item_id, number, text) for number, text in enumerate(chunks, 1)])
            results.append({"source": source, "result": "imported", "id": item_id, "title": title, "area": area, "passages": len(chunks)})
    return results
