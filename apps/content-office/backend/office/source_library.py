"""자료 창고: 운영자가 넣은 링크·메모·파일을 문단으로 저장한다.

- 모델·유료 API를 부르지 않는다. 링크는 공개 HTTPS 주소만 feeds.fetch_public으로 읽는다.
- "초안 근거로 사용"은 운영자가 자료마다 직접 켠다. 켠 링크 자료는 공개 근거 검색(public_evidence)에 함께 잡히고,
  켠 메모·파일은 '내 글로 만들기'에서 불러올 수 있다. 이 표시는 승인⓪①②③을 만들거나 대신하지 않는다.
- 상태는 OFFICE_STATE_DIR/source-library/sources.sqlite3 에만 둔다(저장소에 넣지 않는다).
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
from datetime import datetime, timezone
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
ORIGINS = ("manual", "idea", "news", "artifact", "import")
MAX_PAGE_BYTES = 3_000_000
MAX_FILE_BYTES = 8_000_000
MAX_MEMO_CHARS = 60_000
MAX_LINKS = 10
MAX_BULK = 1000
PASSAGE_CHARS = 900
LINK_SECONDS = 22
YOUTUBE_MESSAGE = ("유튜브는 클라우드 서버에서 자막을 가져오는 요청을 막습니다. 영상 설명란의 '스크립트 표시'에서 "
                   "자막을 복사해 '본문 붙여넣기'로 넣어 주세요.")
_BLOCKED_PAGE = re.compile(r"captcha|access denied|just a moment|브라우저 확인", re.I)
_WORD = re.compile(r"[^\W_]{2,}")
_REF = re.compile(r"[A-Za-z0-9_.:-]{1,160}")
_READ_ERRORS = (ValueError, OSError, requests.RequestException, zipfile.BadZipFile, ElementTree.ParseError, KeyError)
_INBOX_AREAS = {"AI와 자동화": ("B", False), "뇌과학과 마인드셋": ("C", False), "내 경험과 아이디어": ("D", True), "벤치마킹 영상": ("B", False)}

_SCHEMA = """
CREATE TABLE IF NOT EXISTS items(
  id TEXT PRIMARY KEY, kind TEXT NOT NULL, area TEXT NOT NULL, mine INTEGER NOT NULL DEFAULT 0,
  title TEXT NOT NULL, url TEXT, url_norm TEXT, status TEXT NOT NULL, note TEXT NOT NULL DEFAULT '',
  passages INTEGER NOT NULL DEFAULT 0, content_hash TEXT, file_name TEXT, body TEXT, pasted TEXT,
  origin TEXT NOT NULL DEFAULT 'manual', origin_ref TEXT, use_as_evidence INTEGER NOT NULL DEFAULT 0,
  created_at TEXT NOT NULL, updated_at TEXT NOT NULL);
CREATE INDEX IF NOT EXISTS items_url ON items(url_norm);
CREATE INDEX IF NOT EXISTS items_hash ON items(content_hash);
CREATE TABLE IF NOT EXISTS passages(
  item_id TEXT NOT NULL REFERENCES items(id) ON DELETE CASCADE, seq INTEGER NOT NULL, text TEXT NOT NULL,
  PRIMARY KEY(item_id, seq));
CREATE TABLE IF NOT EXISTS passage_vectors(
  item_id TEXT NOT NULL, seq INTEGER NOT NULL, part INTEGER NOT NULL, start_char INTEGER NOT NULL, end_char INTEGER NOT NULL,
  model TEXT NOT NULL, vector BLOB NOT NULL, PRIMARY KEY(item_id, seq, part),
  FOREIGN KEY(item_id, seq) REFERENCES passages(item_id, seq) ON DELETE CASCADE);
"""


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
    return db


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


def _pdf_paragraphs(data: bytes) -> list[str]:
    try:
        import pypdf
    except ImportError as exc:
        raise WorkflowError("이 서버는 PDF를 읽지 못합니다. 글자를 복사해 '본문 붙여넣기'로 넣거나 txt, md, docx로 올려 주세요.") from exc
    pages = pypdf.PdfReader(io.BytesIO(data)).pages[:400]
    paragraphs = [part for page in pages for part in re.split(r"\n\s*\n", page.extract_text() or "") if part.strip()]
    if sum(map(len, paragraphs)) < 200:
        raise WorkflowError("PDF에서 글자를 읽지 못했습니다. 스캔본이면 글자를 복사해 '본문 붙여넣기'로 넣어 주세요.")
    return paragraphs


def _docx_paragraphs(data: bytes) -> list[str]:
    space = "{http://schemas.openxmlformats.org/wordprocessingml/2006/main}"
    with zipfile.ZipFile(io.BytesIO(data)) as archive:
        entry = archive.getinfo("word/document.xml")
        if entry.file_size > 30_000_000:
            raise WorkflowError("문서가 너무 큽니다.")
        tree = ElementTree.fromstring(archive.read(entry))
    return ["".join(node.text or "" for node in paragraph.iter(space + "t")) for paragraph in tree.iter(space + "p")]


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


def _read_ncbi(database: str, ident: str, fetch) -> tuple[str | None, list[str]]:
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
    return (text(heading)[:200] if heading is not None else None), paragraphs


def _read_page(url: str, fetch) -> tuple[str | None, list[str]]:
    raw, final_url, content_type = fetch(url, maximum=MAX_PAGE_BYTES)
    kind = (content_type or "").lower()
    if "pdf" in kind or urlsplit(final_url).path.lower().endswith(".pdf"):
        return None, _pdf_paragraphs(raw)
    charset = re.search(r"charset=([\w-]+)", kind)
    try:
        markup = raw.decode(charset.group(1) if charset else "utf-8", "replace")
    except LookupError:
        markup = raw.decode("utf-8", "replace")
    page = _PageText()
    page.feed(markup)
    page.close_block()
    paragraphs = [text for text in page.paragraphs if len(text) >= 25]
    title = _clean(page.social_title or page.title)[:200]
    if sum(map(len, paragraphs)) < 300 or _BLOCKED_PAGE.search(title):
        raise _Unreadable("본문을 읽지 못했습니다. 로그인이 필요하거나 차단 안내 화면일 수 있습니다. 본문을 복사해 '본문 붙여넣기'로 넣어 주세요.",
                          None if _BLOCKED_PAGE.search(title) else title or None)
    return title or None, paragraphs


def _read_link(url: str, fetch) -> tuple[str | None, list[str]]:
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


def _file_paragraphs(name: str, data: bytes) -> list[str]:
    lowered = name.lower()
    if lowered.endswith(".pdf"):
        return _pdf_paragraphs(data)
    if lowered.endswith(".docx"):
        return _docx_paragraphs(data)
    if lowered.endswith((".txt", ".md")):
        return re.split(r"\n\s*\n", data.decode("utf-8", "replace"))
    raise WorkflowError("txt, md, docx, pdf 파일만 넣을 수 있습니다.")


def _view(row: sqlite3.Row) -> dict:
    return {
        "id": row["id"], "kind": row["kind"], "area": row["area"], "area_label": AREAS.get(row["area"], row["area"]),
        "mine": bool(row["mine"]), "title": row["title"], "url": row["url"], "status": row["status"],
        "note": row["note"], "passages": row["passages"], "use_as_evidence": bool(row["use_as_evidence"]),
        "pasted": row["pasted"] is not None, "origin": row["origin"], "origin_ref": row["origin_ref"],
        "file_name": row["file_name"], "created_at": row["created_at"], "updated_at": row["updated_at"],
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


def _insert(db, *, kind, area, mine, title, url=None, file_name=None, body=None, origin="manual", origin_ref=None) -> str:
    item_id = secrets.token_hex(10)
    stamp = _now()
    db.execute(
        "INSERT INTO items(id, kind, area, mine, title, url, url_norm, status, file_name, body, origin, origin_ref, created_at, updated_at) "
        "VALUES (?,?,?,?,?,?,?, 'pending', ?,?,?,?,?,?)",
        (item_id, kind, area, int(bool(mine)), title, url, normalize_url(url) if url else None, file_name, body,
         origin, origin_ref, stamp, stamp))
    return item_id


def _store_passages(db, item_id: str, paragraphs, title: str | None = None) -> None:
    passages = split_passages(paragraphs)
    if sum(map(len, passages)) < 80:
        raise WorkflowError("저장할 본문이 너무 짧습니다. 내용을 조금 더 넣어 주세요.")
    content_hash = hashlib.sha256("\n".join(passages).encode("utf-8")).hexdigest()
    same = db.execute("SELECT title FROM items WHERE content_hash=? AND id<>? AND status='done'", (content_hash, item_id)).fetchone()
    if same:
        db.execute("UPDATE items SET status='duplicate', note=?, content_hash=?, passages=0, updated_at=? WHERE id=?",
                   (f"'{same['title']}'과 내용이 같아 다시 저장하지 않았습니다.", content_hash, _now(), item_id))
        return
    db.execute("DELETE FROM passages WHERE item_id=?", (item_id,))
    db.executemany("INSERT INTO passages(item_id, seq, text) VALUES (?,?,?)",
                   [(item_id, number, text) for number, text in enumerate(passages, 1)])
    db.execute("UPDATE items SET status='done', note='', passages=?, content_hash=?, title=COALESCE(?, title), updated_at=? WHERE id=?",
               (len(passages), content_hash, title, _now(), item_id))


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
            title = None
            if row["kind"] == "link":
                title, paragraphs = _read_link(row["url"], fetch)
                if row["title"] != row["url"]:
                    title = None
            elif row["kind"] == "file":
                paragraphs = _file_paragraphs(row["file_name"], base64.b64decode(row["body"]))
            else:
                paragraphs = re.split(r"\n\s*\n", row["body"])
            with db:
                _store_passages(db, item_id, paragraphs, title)
        except _READ_ERRORS as exc:
            found_title = getattr(exc, "title", None) if row["title"] == row["url"] else None
            reason = str(exc) if isinstance(exc, WorkflowError) else f"가져오지 못했습니다({type(exc).__name__}). 주소를 확인하거나 본문을 붙여 넣어 주세요."
            with db:
                db.execute("UPDATE items SET status='needs_check', note=?, use_as_evidence=0, title=COALESCE(?, title), updated_at=? WHERE id=?",
                           (reason[:300], found_title, _now(), item_id))
        return _view(_item(db, item_id))


def add_links(root, urls, *, area, mine=False, origin="manual", origin_ref=None, title=None, fetch=None) -> list[dict]:
    area, origin, origin_ref = _labels(area, origin, origin_ref)
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
                                                    title=_clean(title)[:200] if title and len(cleaned) == 1 else url)
        if existing:
            results.append({"url": url, "result": "exists", "item": _view(existing)})
        else:
            results.append({"url": url, "result": "added", "item": _read_item(root, item_id, fetch)})
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
            db.execute("UPDATE items SET pasted=?, updated_at=? WHERE id=?", (text, _now(), item_id))
            _store_passages(db, item_id, re.split(r"\n\s*\n", text), title)
        return _view(_item(db, item_id))


def update_item(root, item_id: str, changes: dict) -> dict:
    allowed = {"use_as_evidence", "area", "mine", "title"}
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
        item["passage_texts"] = [row["text"] for row in db.execute("SELECT text FROM passages WHERE item_id=? ORDER BY seq", (item_id,))]
        return item


def vector_status(root) -> dict:
    """근거로 켠 링크 자료 가운데 공개 근거 검색에 들어갈 준비(벡터 계산)가 끝난 문단 수."""
    from .public_evidence import PUBLIC_MODEL, library_worker_available

    with closing(_connect(root)) as db:
        total, ready = db.execute(
            "SELECT COUNT(*), COALESCE(SUM(EXISTS(SELECT 1 FROM passage_vectors v WHERE v.item_id=p.item_id AND v.seq=p.seq AND v.model=?)), 0) "
            "FROM passages p JOIN items i ON i.id=p.item_id WHERE i.status='done' AND i.use_as_evidence=1 AND i.kind='link'",
            (PUBLIC_MODEL,)).fetchone()
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
                    "origin, origin_ref, created_at, updated_at) VALUES (?,?,?,?,?,?,?, 'done', ?,?,?,?, 'import', ?,?,?)",
                    (item_id, row["kind"], area, int(mine), title, url, norm, len(chunks), content_hash,
                     row.get("file_name") if isinstance(row.get("file_name"), str) else None,
                     row.get("body") if row["kind"] == "memo" and isinstance(row.get("body"), str) else None,
                     source, stamp, _now()))
                db.executemany("INSERT INTO passages(item_id, seq, text) VALUES (?,?,?)",
                               [(item_id, number, text) for number, text in enumerate(chunks, 1)])
            results.append({"source": source, "result": "imported", "id": item_id, "title": title, "area": area, "passages": len(chunks)})
    return results
