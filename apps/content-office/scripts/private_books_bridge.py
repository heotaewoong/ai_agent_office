#!/usr/bin/env python3
"""개인 책 DB 검색 다리: 콘텐츠 오피스(ubuntu)가 개인 DB(ihtwa 소유)를 읽기 전용으로 찾게 해 준다.

설치 위치와 실행:
- 이 파일을 ihtwa 계정의 /home/ihtwa/.local/share/heobrain-ai-agent-index/bridge/에 복사해 둔다.
  ubuntu가 고칠 수 있는 곳의 코드를 ihtwa 권한으로 돌리지 않기 위해서다.
- systemd 서비스 heobrain-book-search.service(User=ihtwa, Group=ubuntu)가 띄우고,
  /run/heobrain-book-search/search.sock(0660)을 연다. ubuntu 그룹만 연결할 수 있다.

하는 일:
- 요청 한 줄(JSON) {"query": "...", "limit": 4}를 받아, 개인 DB의 기존 검색 명령(rag_index.py query, 벡터 + 키워드 섞기)을 돌린다.
- 책(book_text)과 강의 자료(course_material)만 돌려준다. 이력서, 프로젝트 보고서, 코드 같은 다른 개인 자료는 내보내지 않는다.
- 원본 위치(구글 드라이브 주소)는 내보내지 않고 출처 ID(해시 24자리)만 준다.
- 쓰기는 하지 않는다(임베딩 서버 켜기는 기존 embed_server.py가 한다).
- 저자 같은 서지 정보는 index 폴더의 book_catalog.json({"책 제목": {"author": "...", "year": 2026}})에서 붙인다.
"""
from __future__ import annotations

import hashlib
import json
import os
import pwd
import socket
import struct
import subprocess
import sys
from pathlib import Path

ROOT = Path(os.environ.get("HEOBRAIN_INDEX_ROOT") or Path.home() / ".local/share/heobrain-ai-agent-index")
SOCKET = Path(os.environ.get("HEOBRAIN_BOOK_SEARCH_SOCKET") or "/run/heobrain-book-search/search.sock")
ALLOWED_USERS = tuple(name for name in os.environ.get("HEOBRAIN_BOOK_ALLOWED_USERS", "ubuntu").split(",") if name)
MAX_REQUEST = 8192
MAX_QUERY = 800
POOL = 20               # rag_index.py query가 허용하는 최대 개수. 종류를 거른 뒤 앞에서부터 자른다.
SEARCH_SECONDS = 50
KINDS = {"book_text": "book", "course_material": "course"}


def book_id(source: str) -> str:
    return hashlib.sha256(source.encode("utf-8")).hexdigest()[:24]


def load_catalog(root: Path = ROOT) -> dict:
    try:
        data = json.loads((root / "book_catalog.json").read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return {}
    return {str(key): value for key, value in data.items() if isinstance(value, dict)} if isinstance(data, dict) else {}


def _int(value, low, high):
    return value if type(value) is int and low <= value <= high else None


def shape(item: dict, catalog: dict) -> dict | None:
    """검색 결과 한 줄을 내보낼 모양으로 바꾼다. 책과 강의 자료가 아니면 버린다."""
    kind = KINDS.get(item.get("kind"))
    source = item.get("source")
    title = str(item.get("source_title") or item.get("title") or "").strip()
    text = str(item.get("text") or "").strip()
    chunk = item.get("content_hash")
    if not kind or not isinstance(source, str) or not source or not title or not text or not isinstance(chunk, str) or len(chunk) != 64:
        return None
    meta = catalog.get(title, {})
    author = meta.get("author") if isinstance(meta.get("author"), str) and meta["author"].strip() else None
    policy = "paraphrase_only" if kind == "course" or item.get("quote_policy") == "paraphrase_only" else "quote_ok"
    return {
        "book_id": book_id(source), "kind": kind, "title": title[:300], "author": author.strip()[:200] if author else None,
        "year": _int(item.get("published_year"), 1900, 2100) or _int(meta.get("year"), 1900, 2100),
        "printed_page": _int(item.get("printed_page"), 1, 100_000), "file_page": _int(item.get("file_page"), 1, 100_000),
        "locator": " ".join(str(item.get("locator") or "").split())[:120], "text": text[:2400], "chunk_sha256": chunk,
        "quote_policy": policy, "ocr_quality": item.get("ocr_quality") if isinstance(item.get("ocr_quality"), str) else None,
        "score": item.get("score") if isinstance(item.get("score"), (int, float)) else None,
    }


def run_search(query: str) -> dict:
    """개인 DB의 기존 검색 명령을 그대로 돌린다(nice 10). 실패하면 RuntimeError."""
    release = (ROOT / "current").resolve()
    python = ROOT / "runtime/venv/bin/python"
    env = {"PATH": "/usr/bin:/bin", "HOME": str(Path.home()), "HF_HUB_OFFLINE": "1", "HF_HUB_DISABLE_TELEMETRY": "1",
           "OMP_NUM_THREADS": "1", "PYTHONDONTWRITEBYTECODE": "1",
           "XDG_RUNTIME_DIR": os.environ.get("XDG_RUNTIME_DIR") or f"/run/user/{os.getuid()}"}
    command = ["nice", "-n", "10", str(python), "-B", str(release / "rag_index.py"), "query", "--db", str(release / "index.sqlite3"),
               "--limit", str(POOL), query]
    result = subprocess.run(command, capture_output=True, text=True, timeout=SEARCH_SECONDS, env=env, check=False)
    if result.returncode:
        raise RuntimeError("search failed")
    return json.loads(result.stdout)


def handle(raw: bytes, search=run_search, catalog_root: Path = ROOT) -> dict:
    try:
        request = json.loads(raw.decode("utf-8"))
        query = " ".join(str(request.get("query") or "").split())[:MAX_QUERY]
        limit = int(request.get("limit", 4))
    except (UnicodeError, ValueError, TypeError, AttributeError):
        return {"status": "error", "message": "요청 형식이 올바르지 않아요"}
    if not query:
        return {"status": "error", "message": "검색어가 비어 있어요"}
    limit = max(1, min(limit, 6))
    try:
        found = search(query)
    except (OSError, RuntimeError, ValueError, subprocess.TimeoutExpired):
        return {"status": "error", "message": "개인 DB 검색이 실패했어요. 잠시 뒤 다시 찾아 주세요"}
    catalog = load_catalog(catalog_root)
    rows = []
    for item in found.get("results") or []:
        row = shape(item, catalog) if isinstance(item, dict) else None
        if row:
            rows.append(row)
        if len(rows) == limit:
            break
    return {"status": "ok", "mode": found.get("effective_mode"), "hint": found.get("hint"), "results": rows}


def _allowed_uids() -> set[int]:
    uids = {os.getuid()}
    for name in ALLOWED_USERS:
        try:
            uids.add(pwd.getpwnam(name).pw_uid)
        except KeyError:
            continue
    return uids


def _peer_uid(conn: socket.socket) -> int:
    creds = conn.getsockopt(socket.SOL_SOCKET, socket.SO_PEERCRED, struct.calcsize("3i"))
    return struct.unpack("3i", creds)[1]


def _read_request(conn: socket.socket) -> bytes:
    data = b""
    while len(data) <= MAX_REQUEST:
        chunk = conn.recv(4096)
        if not chunk:
            break
        data += chunk
        if b"\n" in data:
            break
    return data.split(b"\n", 1)[0]


def serve() -> int:
    SOCKET.parent.mkdir(parents=True, exist_ok=True)
    if SOCKET.exists():
        SOCKET.unlink()
    allowed = _allowed_uids()
    with socket.socket(socket.AF_UNIX, socket.SOCK_STREAM) as server:
        server.bind(str(SOCKET))
        os.chmod(SOCKET, 0o660)
        server.listen(8)
        while True:
            conn, _ = server.accept()
            with conn:
                conn.settimeout(10)
                try:
                    if _peer_uid(conn) not in allowed:
                        conn.sendall(b'{"status":"error","message":"forbidden"}\n')
                        continue
                    raw = _read_request(conn)
                    conn.settimeout(SEARCH_SECONDS + 10)
                    reply = handle(raw) if len(raw) <= MAX_REQUEST else {"status": "error", "message": "요청이 너무 커요"}
                    conn.sendall((json.dumps(reply, ensure_ascii=False) + "\n").encode("utf-8"))
                except (OSError, socket.timeout):
                    continue


if __name__ == "__main__":
    sys.exit(serve())
