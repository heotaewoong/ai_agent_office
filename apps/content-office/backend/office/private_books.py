"""개인 DB(책, 강의 자료) 근거: 사람이 기획 승인⓪에서 체크한 문단만 초안 근거가 된다.

- 개인 DB는 다른 계정(ihtwa)이 갖고 있다. 이 서버(ubuntu)는 systemd 소켓 다리(private_books_bridge.py)로 검색만 한다.
  다리는 책(book_text)과 강의 자료(course_material)만 돌려주고, 원본 위치(구글 드라이브 주소)는 내보내지 않는다.
- 검색어는 기획 제목이다. 개인 DB 문장은 외부 검색어(Tavily 등)에 넣지 않는다.
- 인용 규칙(설계 v2 5장): 내 말로 풀어 쓰기가 기본, 직접 인용은 근거 하나당 두 문장 이내, 출처(책은 저자, 제목, 쪽) 표시.
  예전 OCR이나 의심 OCR 문단, 강의 자료는 풀어 쓰기만 한다(quote_policy=paraphrase_only).
- 근거 ID는 (출처 ID, 조각 해시, 위치, 인용 해시)로 만든다. 같은 문단이면 다시 찾아도 같은 ID다.
"""
from __future__ import annotations

import hashlib
import json
import os
import re
import socket
import unicodedata

from .store import WorkflowError

BOOK_EVIDENCE_LIMIT = 4
# 관련 없는 질문에도 책 4권을 쥐여 주지 않도록 벡터 유사도(KURE cosine) 하한을 둔다(2026-11-27).
# P5 책 검색 골든셋 Dev 41문항으로 맞췄다: 답이 없는 질문 4개는 모두 0개가 되고, 답이 있는 질문 37개 중 31개는 후보가 남는다.
# 제목의 고유 이름(제품, 시험 등급 등)이 개인 DB에 없으면(low_coverage) 하한을 0.60으로 올린다. 이때 아예 0개로 막으면 답 있는 질문이 4개 더 빠졌다.
BOOK_MIN_COSINE = 0.54
BOOK_MIN_COSINE_MISSING_NAMES = 0.60
BOOK_SOURCE_KIND = "approved_book_evidence"
_SOCKET = "/run/heobrain-book-search/search.sock"
_TIMEOUT = 45.0  # 임베딩 서버가 꺼져 있으면 켜는 데 몇 초 걸린다(실측 cold start 3.1초).
_MAX_RESPONSE = 256 * 1024
_HEX64 = re.compile(r"[0-9a-f]{64}")
_HEX24 = re.compile(r"[0-9a-f]{24}")
_KINDS = {"book": "책", "course": "강의 자료"}
_POLICIES = ("quote_ok", "paraphrase_only")
_FIELDS = ("id", "book_id", "kind", "title", "author", "year", "printed_page", "file_page", "locator", "quote",
           "chunk_sha256", "quote_sha256", "quote_policy")


class BookEvidenceUnavailable(RuntimeError):
    """개인 DB 다리가 응답하지 않거나 검색할 수 없다."""


def book_evidence_id(book_id: str, chunk_sha256: str, locator: str, quote_sha256: str) -> str:
    identity = json.dumps(["book", book_id, chunk_sha256, locator, quote_sha256], ensure_ascii=False, separators=(",", ":"))
    return hashlib.sha256(identity.encode("utf-8")).hexdigest()


def _socket_path() -> str:
    return os.environ.get("HEOBRAIN_BOOK_SEARCH_SOCKET") or _SOCKET


def _ask(query: str, limit: int) -> dict:
    path = _socket_path()
    request = (json.dumps({"query": query, "limit": limit}, ensure_ascii=False) + "\n").encode("utf-8")
    try:
        with socket.socket(socket.AF_UNIX, socket.SOCK_STREAM) as conn:
            conn.settimeout(_TIMEOUT)
            conn.connect(path)
            conn.sendall(request)
            conn.shutdown(socket.SHUT_WR)
            chunks, size = [], 0
            while True:
                chunk = conn.recv(65536)
                if not chunk:
                    break
                size += len(chunk)
                if size > _MAX_RESPONSE:
                    raise BookEvidenceUnavailable("개인 DB 검색 응답이 너무 커요")
                chunks.append(chunk)
    except FileNotFoundError as error:
        raise BookEvidenceUnavailable("개인 DB 검색 다리가 이 서버에 설치되지 않았어요") from error
    except PermissionError as error:
        raise BookEvidenceUnavailable("개인 DB 검색 다리에 접근할 권한이 없어요") from error
    except (OSError, socket.timeout) as error:
        raise BookEvidenceUnavailable("개인 DB 검색이 응답하지 않아요. 잠시 뒤 다시 찾아 주세요") from error
    try:
        reply = json.loads(b"".join(chunks).decode("utf-8"))
    except (UnicodeError, ValueError) as error:
        raise BookEvidenceUnavailable("개인 DB 검색 응답을 읽지 못했어요") from error
    if not isinstance(reply, dict) or reply.get("status") != "ok" or not isinstance(reply.get("results"), list):
        message = reply.get("message") if isinstance(reply, dict) and isinstance(reply.get("message"), str) else ""
        raise BookEvidenceUnavailable(message[:200] or "개인 DB 검색이 실패했어요")
    return reply


def _page(value):
    return value if type(value) is int and 1 <= value <= 100_000 else None


def _one_line(value, limit):
    if not isinstance(value, str):
        return None
    value = " ".join(value.split())
    return value[:limit] if value else None


def _from_bridge(row) -> dict | None:
    """다리가 준 한 줄을 근거 후보로 바꾼다. 형식이 이상한 줄은 버린다."""
    if not isinstance(row, dict):
        return None
    kind, book_id, chunk_hash = row.get("kind"), row.get("book_id"), row.get("chunk_sha256")
    title, quote = _one_line(row.get("title"), 300), row.get("text")
    if (kind not in _KINDS or not isinstance(book_id, str) or not _HEX24.fullmatch(book_id)
            or not isinstance(chunk_hash, str) or not _HEX64.fullmatch(chunk_hash) or not title
            or not isinstance(quote, str) or not quote.strip() or len(quote) > 2400):
        return None
    quote = quote.strip()
    policy = "paraphrase_only" if kind == "course" or row.get("quote_policy") != "quote_ok" else "quote_ok"
    year = row.get("year") if type(row.get("year")) is int and 1900 <= row["year"] <= 2100 else None
    item = {"book_id": book_id, "kind": kind, "title": title, "author": _one_line(row.get("author"), 200), "year": year,
            "printed_page": _page(row.get("printed_page")), "file_page": _page(row.get("file_page")),
            "locator": _one_line(row.get("locator"), 120) or "", "quote": quote, "chunk_sha256": chunk_hash,
            "quote_sha256": hashlib.sha256(quote.encode("utf-8")).hexdigest(), "quote_policy": policy}
    item["id"] = book_evidence_id(book_id, chunk_hash, item["locator"], item["quote_sha256"])
    return {key: item[key] for key in _FIELDS}


def find_book_evidence(query: str, *, limit: int = BOOK_EVIDENCE_LIMIT) -> tuple[list[dict], str]:
    """기획 제목으로 개인 DB를 찾는다. (근거 후보, 검색 방식)을 돌려준다. 검색 방식은 hybrid 또는 text(임베딩을 못 쓸 때)."""
    query = " ".join(str(query or "").split())[:800]
    if not query:
        return [], "none"
    reply = _ask(query, max(1, min(int(limit), 6)))
    mode = reply.get("mode") if reply.get("mode") in ("hybrid", "text", "vector") else "unknown"
    floor = BOOK_MIN_COSINE_MISSING_NAMES if reply.get("low_coverage") is True else BOOK_MIN_COSINE
    rows, seen = [], set()
    for row in reply["results"]:
        cosine = row.get("cosine") if isinstance(row, dict) else None
        if isinstance(cosine, (int, float)) and cosine < floor:
            continue
        item = _from_bridge(row)
        if item and item["id"] not in seen:
            seen.add(item["id"])
            rows.append(item)
        if len(rows) == limit:
            break
    return checked_book_references(rows), mode


def checked_book_references(references) -> list[dict]:
    """기획 카드나 작업에 저장된 책 근거를 다시 검사한다. 해시와 인용 규칙이 맞지 않으면 막는다."""
    if not isinstance(references, list) or len(references) > 8:
        raise WorkflowError("책 근거 목록의 판본을 다시 확인하세요")
    checked, seen = [], set()
    for entry in references:
        if not isinstance(entry, dict) or any(key not in entry for key in _FIELDS):
            raise WorkflowError("책 근거의 출처와 쪽을 다시 확인하세요")
        item = {key: entry[key] for key in _FIELDS}
        if (not isinstance(item["id"], str) or not _HEX64.fullmatch(item["id"]) or item["id"] in seen
                or not isinstance(item["book_id"], str) or not _HEX24.fullmatch(item["book_id"])
                or item["kind"] not in _KINDS or item["quote_policy"] not in _POLICIES
                or (item["kind"] == "course" and item["quote_policy"] != "paraphrase_only")
                or not isinstance(item["title"], str) or not item["title"].strip() or len(item["title"]) > 300
                or not (item["author"] is None or (isinstance(item["author"], str) and 0 < len(item["author"]) <= 200))
                or not (item["year"] is None or (type(item["year"]) is int and 1900 <= item["year"] <= 2100))
                or any(item[key] is not None and _page(item[key]) is None for key in ("printed_page", "file_page"))
                or not isinstance(item["locator"], str) or len(item["locator"]) > 120 or "\n" in item["locator"]
                or not isinstance(item["quote"], str) or not item["quote"].strip() or len(item["quote"]) > 2400
                or not isinstance(item["chunk_sha256"], str) or not _HEX64.fullmatch(item["chunk_sha256"])):
            raise WorkflowError("책 근거의 출처와 쪽을 다시 확인하세요")
        quote_hash = hashlib.sha256(item["quote"].encode("utf-8")).hexdigest()
        if quote_hash != item["quote_sha256"] or item["id"] != book_evidence_id(item["book_id"], item["chunk_sha256"], item["locator"], quote_hash):
            raise WorkflowError("책 근거의 원문 판본이 일치하지 않습니다")
        checked.append(item)
        seen.add(item["id"])
    return checked


def page_label(item: dict) -> str:
    """인쇄 쪽이 있으면 그 쪽, 없으면 PDF 파일 기준 쪽을 쓴다."""
    if item.get("printed_page"):
        return f"{item['printed_page']}쪽"
    if item.get("file_page"):
        return f"PDF {item['file_page']}쪽(파일 기준)"
    return ""


def book_citation(item: dict) -> str:
    """공개 글에 적는 출처 한 줄. 책은 『제목』, 저자, 쪽. 강의 자료는 「자료명」."""
    if item.get("kind") == "course":
        return f"강의 자료 「{item['title']}」"
    parts = [f"『{item['title']}』"]
    if item.get("author"):
        parts.append(item["author"])
    page = page_label(item)
    if page:
        parts.append(page)
    return ", ".join(parts)


def book_evidence_items(evidence: list[dict], references: list[dict]) -> list[dict]:
    """승인한 책 문단을 원고 근거 목록(E 번호)에 붙인다. 주소 대신 book://출처ID를 쓴다."""
    last = max((int(item["id"][1:]) for item in evidence if re.fullmatch(r"E[0-9]{1,3}", str(item.get("id", "")))), default=0)
    items = []
    for index, source in enumerate(references, 1):
        paraphrase = source["quote_policy"] == "paraphrase_only"
        rule = ("원문 문장을 옮기지 말고 내 말로 풀어 쓰기만 함" if paraphrase
                else "직접 인용은 두 문장 이내, 출처(저자, 제목, 쪽)를 밝힘")
        items.append({
            "id": f"E{last + index}", "url": f"book://{source['book_id']}", "title": source["title"],
            "book_title": source["title"], "book_kind": source["kind"], "author": source["author"], "year": source["year"],
            "printed_page": source["printed_page"], "file_page": source["file_page"], "source_locator": source["locator"],
            "citation": book_citation(source),
            "claim": f"기획 승인⓪에서 선택한 개인 DB {_KINDS[source['kind']]} 문단",
            "scope": f"{_KINDS[source['kind']]}의 해당 부분 서술. 독립 검증 미실시. {rule}",
            "quote_policy": source["quote_policy"], "independent_source_checked": False, "numbers": [],
            "source_quote": source["quote"], "quote_sha256": source["quote_sha256"], "chunk_sha256": source["chunk_sha256"],
            "reference_id": source["id"], "source_kind": BOOK_SOURCE_KIND,
        })
    return [*evidence, *items]


def is_traceable_book(item: dict) -> bool:
    """책 근거는 https 주소 대신 서지 정보로 추적한다. 책은 쪽이 있어야 하고, 강의 자료는 자료명만 있으면 된다."""
    if item.get("source_kind") != BOOK_SOURCE_KIND or not str(item.get("url", "")).startswith("book://"):
        return False
    if not isinstance(item.get("book_title"), str) or not item["book_title"].strip() or not isinstance(item.get("source_quote"), str):
        return False
    if item.get("book_kind") == "book":
        return bool(item.get("printed_page") or item.get("file_page"))
    return item.get("book_kind") == "course"


def _normal(text: str) -> str:
    return " ".join(unicodedata.normalize("NFKC", text or "").split())


_SENTENCE_END = re.compile(r"(?<=[.!?。])\s+|\n+")


def _sentences(text: str) -> list[str]:
    return [part for part in (_normal(piece) for piece in _SENTENCE_END.split(text or "")) if len(part) >= 12]


def _copied_run(quote: str, text: str, width: int = 30) -> bool:
    """원문의 연속된 30자 이상이 그대로 들어갔는지 본다(문장 경계와 무관하게)."""
    if len(quote) < width:
        return False
    return any(quote[start:start + width] in text for start in range(0, len(quote) - width + 1, 5))


def book_quote_issues(evidence: list[dict], texts: list[str]) -> list[str]:
    """책 근거의 인용 규칙을 본다. 경고로 보여 주고, 사람이 승인①에서 확인한다."""
    joined = _normal(" ".join(text for text in texts if isinstance(text, str)))
    issues = []
    for item in evidence:
        if not isinstance(item, dict) or item.get("source_kind") != BOOK_SOURCE_KIND:
            continue
        label = item.get("citation") or item.get("book_title") or "책 근거"
        quote = _normal(item.get("source_quote", ""))
        copied = [sentence for sentence in _sentences(item.get("source_quote", "")) if sentence in joined]
        if item.get("quote_policy") == "paraphrase_only":
            if copied or _copied_run(quote, joined):
                issues.append(f"[{item.get('id')}] {label}은(는) 풀어 쓰기만 할 수 있어요. 원문을 그대로 옮긴 부분을 내 말로 바꿔 주세요")
        elif len(copied) > 2:
            issues.append(f"[{item.get('id')}] {label} 직접 인용이 {len(copied)}문장이에요. 근거 하나당 두 문장까지만 인용해 주세요")
        if item.get("book_kind") == "book" and not item.get("author"):
            issues.append(f"[{item.get('id')}] 『{item.get('book_title')}』의 저자를 확인해 출처에 적어 주세요")
    return issues
