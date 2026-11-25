"""개인 DB(책, 강의 자료) 근거: 다리 소켓, 승인⓪ 선택, 원고 근거, 인용 규칙, 출처 표기."""
import hashlib
import importlib.util
import json
import socket
import threading
from pathlib import Path

import pytest
from fastapi.testclient import TestClient

from office import private_books
from office.api import create_app
from office.editorial import deterministic_checks, prepare_source
from office.exports import reference_lines
from office.packaging import attach_packaging
from office.private_books import (BOOK_SOURCE_KIND, BookEvidenceUnavailable, book_citation, book_evidence_items,
                                  book_quote_issues, checked_book_references, find_book_evidence)
from office.store import Store, WorkflowError, digest, now
from test_agent_editorial import FullProvider, brief

BRIDGE = Path(__file__).resolve().parents[2] / "scripts" / "private_books_bridge.py"
QUOTE = ("검색 증강 생성은 질문과 관련된 문서를 먼저 찾아 모델에 넣어 준다. 그래서 모델이 모르는 최신 자료도 답에 쓸 수 있다. "
         "다만 찾은 조각이 엉뚱하면 답도 엉뚱해진다. 그래서 조각 나누기와 검색 품질을 먼저 재야 한다.")


def bridge_row(**extra):
    row = {"book_id": "a" * 24, "kind": "book", "title": "RAG의 모든 것", "author": "정민제", "year": 2026,
           "printed_page": 93, "file_page": 101, "locator": "pdf:101", "text": QUOTE, "chunk_sha256": "b" * 64,
           "quote_policy": "quote_ok", "ocr_quality": "paddleocr_vl_1.6", "score": 0.81}
    row.update(extra)
    return row


@pytest.fixture
def bridge(tmp_path, monkeypatch):
    """요청을 받아 정해진 답을 돌려주는 가짜 다리 소켓."""
    path = tmp_path / "search.sock"
    replies, seen = [], []
    server = socket.socket(socket.AF_UNIX, socket.SOCK_STREAM)
    server.bind(str(path))
    server.listen(4)

    def loop():
        while True:
            try:
                conn, _ = server.accept()
            except OSError:
                return
            with conn:
                data = b""
                while b"\n" not in data:
                    chunk = conn.recv(4096)
                    if not chunk:
                        break
                    data += chunk
                seen.append(json.loads(data.split(b"\n")[0]))
                conn.sendall((json.dumps(replies[0] if replies else {"status": "ok", "results": []}, ensure_ascii=False) + "\n").encode())

    thread = threading.Thread(target=loop, daemon=True)
    thread.start()
    monkeypatch.setenv("HEOBRAIN_BOOK_SEARCH_SOCKET", str(path))
    yield replies, seen
    server.close()


def test_find_book_evidence_keeps_bibliography_and_forces_paraphrase_for_courses(bridge):
    replies, seen = bridge
    replies.append({"status": "ok", "mode": "hybrid", "results": [
        bridge_row(),
        bridge_row(book_id="c" * 24, kind="course", title="강의 자료_프롬프트 엔지니어링.pdf", author=None, printed_page=None,
                   file_page=None, locator="extracted-text 2", chunk_sha256="d" * 64, quote_policy="quote_ok"),
        bridge_row(book_id="not-hex", chunk_sha256="e" * 64),           # 형식이 이상한 줄은 버린다
    ]})
    rows, mode = find_book_evidence("  RAG 검색 품질을   어떻게 재나 ", limit=4)
    assert seen == [{"query": "RAG 검색 품질을 어떻게 재나", "limit": 4}] and mode == "hybrid"
    assert [row["kind"] for row in rows] == ["book", "course"]
    assert rows[0]["quote_policy"] == "quote_ok" and rows[1]["quote_policy"] == "paraphrase_only"
    assert rows[0]["quote_sha256"] == hashlib.sha256(QUOTE.encode()).hexdigest()
    assert checked_book_references(rows) == rows
    assert "drive.google.com" not in json.dumps(rows)


def test_bridge_errors_become_unavailable(bridge, monkeypatch, tmp_path):
    replies, _ = bridge
    replies.append({"status": "error", "message": "개인 DB 검색이 실패했어요"})
    with pytest.raises(BookEvidenceUnavailable, match="실패"):
        find_book_evidence("질문")
    monkeypatch.setenv("HEOBRAIN_BOOK_SEARCH_SOCKET", str(tmp_path / "missing.sock"))
    with pytest.raises(BookEvidenceUnavailable, match="설치"):
        find_book_evidence("질문")


def test_checked_references_reject_tampered_quote_and_quoting_courses(bridge):
    replies, _ = bridge
    replies.append({"status": "ok", "mode": "text", "results": [bridge_row()]})
    rows, _ = find_book_evidence("질문")
    with pytest.raises(WorkflowError, match="판본"):
        checked_book_references([{**rows[0], "quote": rows[0]["quote"] + " 덧붙인 문장"}])
    with pytest.raises(WorkflowError):
        checked_book_references([{**rows[0], "kind": "course"}])


def test_citation_and_quote_rules():
    book = {"kind": "book", "title": "RAG의 모든 것", "author": "정민제", "printed_page": 93, "file_page": 101}
    assert book_citation(book) == "『RAG의 모든 것』, 정민제, 93쪽"
    assert book_citation({**book, "author": None, "printed_page": None}) == "『RAG의 모든 것』, PDF 101쪽(파일 기준)"
    assert book_citation({"kind": "course", "title": "교안.pdf"}) == "강의 자료 「교안.pdf」"
    source = {"id": "1" * 64, "book_id": "a" * 24, "kind": "book", "title": "RAG의 모든 것", "author": None, "year": None,
              "printed_page": 93, "file_page": None, "locator": "", "quote": QUOTE, "chunk_sha256": "b" * 64,
              "quote_sha256": "", "quote_policy": "quote_ok"}
    evidence = book_evidence_items([{"id": "E1", "url": "https://example.org"}], [source])
    item = evidence[1]
    assert item["id"] == "E2" and item["url"] == "book://" + "a" * 24 and item["source_kind"] == BOOK_SOURCE_KIND
    sentences = [part.strip() for part in QUOTE.split(". ")]
    two = f"{sentences[0]}. {sentences[1]}. 나머지는 내 말로 풀어 썼어요."
    three = two + f" {sentences[2]}."
    assert book_quote_issues(evidence, [two]) == ["[E2] 『RAG의 모든 것』의 저자를 확인해 출처에 적어 주세요"]
    assert any("3문장" in issue for issue in book_quote_issues(evidence, [three]))
    paraphrase = [{**item, "quote_policy": "paraphrase_only", "author": "정민제"}]
    assert any("풀어 쓰기만" in issue for issue in book_quote_issues(paraphrase, [sentences[0] + "."]))
    assert book_quote_issues(paraphrase, ["검색해서 넣은 문서가 틀리면 답도 틀린다는 점을 먼저 확인해요."]) == []


def test_reference_lines_show_bibliography_without_private_location():
    packet = {"evidence": [
        {"id": "E1", "claim": "보도자료 발췌", "url": "https://example.go.kr/a.pdf", "source_locator": "p.12"},
        {"id": "E2", "url": "book://" + "a" * 24, "source_kind": BOOK_SOURCE_KIND, "book_kind": "book",
         "book_title": "RAG의 모든 것", "printed_page": 93, "source_quote": QUOTE, "citation": "『RAG의 모든 것』, 정민제, 93쪽"},
    ]}
    assert reference_lines(packet) == ["[E1] 보도자료 발췌 (PDF 12쪽)\nhttps://example.go.kr/a.pdf", "[E2] 『RAG의 모든 것』, 정민제, 93쪽"]


def test_book_evidence_is_traceable_without_https_but_needs_a_page():
    item = {"id": "E1", "url": "book://" + "a" * 24, "source_kind": BOOK_SOURCE_KIND, "book_kind": "book",
            "book_title": "RAG의 모든 것", "printed_page": 93, "source_quote": QUOTE, "author": "정민제"}
    body = "## 하나\n본문 [E1]\n## 둘\n설명\n## 셋\n정리"
    passed = deterministic_checks({"title": "t", "body": body, "evidence": [item], "video": {"scenes": []}})
    assert "검토 가능한 HTTPS 원출처가 필요합니다" not in passed["blocking"]
    failed = deterministic_checks({"title": "t", "body": body, "evidence": [{**item, "printed_page": None}], "video": {"scenes": []}})
    assert "검토 가능한 HTTPS 원출처가 필요합니다" in failed["blocking"]


def load_bridge():
    spec = importlib.util.spec_from_file_location("private_books_bridge", BRIDGE)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def test_bridge_returns_only_books_and_courses_without_source_urls(tmp_path):
    bridge = load_bridge()
    (tmp_path / "book_catalog.json").write_text(json.dumps({"RAG의 모든 것": {"author": "정민제", "year": 2026}}), encoding="utf-8")
    found = {"effective_mode": "hybrid", "results": [
        {"kind": "career_reference", "source": "https://drive.google.com/file/d/x/view", "source_title": "이력서", "text": "개인 경력",
         "content_hash": "f" * 64},
        {"kind": "book_text", "source": "https://drive.google.com/file/d/book/view", "source_title": "RAG의 모든 것", "text": QUOTE,
         "content_hash": "b" * 64, "printed_page": 93, "file_page": 101, "locator": "pdf:101", "quote_policy": "paraphrase_only",
         "published_year": None, "score": 0.8},
        {"kind": "course_material", "source": "https://drive.google.com/file/d/course/view", "source_title": "교안.pdf",
         "text": "강의 설명", "content_hash": "c" * 64},
    ]}
    reply = bridge.handle(json.dumps({"query": "검색 품질", "limit": 4}).encode(), search=lambda query: found, catalog_root=tmp_path)
    assert reply["status"] == "ok" and reply["mode"] == "hybrid"
    assert [row["kind"] for row in reply["results"]] == ["book", "course"]
    book = reply["results"][0]
    assert book["author"] == "정민제" and book["year"] == 2026 and book["quote_policy"] == "paraphrase_only"
    assert book["book_id"] == hashlib.sha256(b"https://drive.google.com/file/d/book/view").hexdigest()[:24]
    assert "drive.google.com" not in json.dumps(reply) and "이력서" not in json.dumps(reply, ensure_ascii=False)
    assert bridge.handle(b"not json")["status"] == "error"
    assert bridge.handle(json.dumps({"query": "  "}).encode())["status"] == "error"

    def broken(query):
        raise RuntimeError("search failed")
    assert bridge.handle(json.dumps({"query": "질문"}).encode(), search=broken, catalog_root=tmp_path)["status"] == "error"


@pytest.fixture
def scope(tmp_path, monkeypatch, bridge):
    replies, seen = bridge
    replies.append({"status": "ok", "mode": "hybrid", "results": [
        bridge_row(),
        bridge_row(book_id="c" * 24, title="처음 만나는 에이전트", author=None, printed_page=None, file_page=44,
                   chunk_sha256="d" * 64, quote_policy="paraphrase_only", text="에이전트는 도구를 고르고 결과를 보고 다음 행동을 정한다."),
    ]})
    store = Store(tmp_path / "state")
    client = TestClient(create_app(store), base_url="http://localhost:8510")
    headers = {"Origin": "http://localhost:3110", "X-Office-CSRF": client.get("/api/session").json()["csrf"]}
    idea = client.post("/api/ideas", headers=headers, json={
        "title": "RAG 검색 품질을 먼저 재야 하는 이유", "source_url": "https://primary.example.org/article", "primary_sources": 1,
    }).json()
    return store, client, headers, idea, seen


def test_book_search_select_and_editorial_use_only_checked_book(scope, monkeypatch):
    store, client, headers, idea, seen = scope
    root = f"/api/ideas/{idea['id']}"
    assert client.post(root + "/book-evidence", json={"expected_hash": digest(idea)}).status_code == 403
    saved = client.post(root + "/book-evidence", headers=headers, json={"expected_hash": digest(idea)})
    assert saved.status_code == 200, saved.text
    card = saved.json()
    assert seen[-1]["query"] == idea["title"] and card["book_discovery"]["status"] == "ready" and card["book_discovery"]["paid_calls"] == 0
    books = card["book_evidence"]
    assert len(books) == 2 and not store.jobs()
    assert client.post(root + "/select", headers=headers, json={"expected_hash": card["edit_hash"], "book_evidence_ids": ["0" * 64]}).status_code == 409
    chosen = client.post(root + "/select", headers=headers, json={"expected_hash": card["edit_hash"], "book_evidence_ids": [books[0]["id"]]})
    assert chosen.status_code == 200, chosen.text
    job = chosen.json()["job"]
    assert job["article"]["approved_book_evidence"] == [books[0]]
    assert job["article"]["approved_book_evidence_hash"] == digest([books[0]])
    attach_packaging(store, job["id"], brief(), "local-operator")
    primary = {"id": "E1", "claim": "대표 원문의 주장입니다.", "url": idea["source_url"], "numbers": [],
               "source_paragraph": 1, "source_quote": "대표 원문의 정확한 인용입니다.", "scope": "원문 서술"}

    def collect(article, provider, directory):
        return {"evidence": [primary], "limitations": [], "hook": "", "source_kind": "http_article_body",
                "source_sha256": "1" * 64, "retrieved_at": now(), "content_status": "substantive_body"}

    monkeypatch.setattr("office.evidence.collect_article_evidence", collect)

    class BookProvider(FullProvider):
        def _packet(self):
            packet = super()._packet()
            packet["body"] += "\n책에서 말하는 검색 품질 점검을 내 말로 풀었어요. [E2]"
            return packet

    provider = BookProvider("AI 도구 비교")
    before = store.budget()
    result = prepare_source(store, job["id"], provider=provider)
    gen = json.loads(provider.users[provider.roles.index("gen")])
    book = gen["evidence"][1]
    assert book["id"] == "E2" and book["url"] == "book://" + "a" * 24 and book["citation"] == "『RAG의 모든 것』, 정민제, 93쪽"
    assert book["source_quote"] == QUOTE and "drive.google.com" not in json.dumps(gen)
    assert "에이전트는 도구를 고르고" not in provider.users[provider.roles.index("gen")]   # 고르지 않은 책 문단은 안 넘어간다
    assert "책 근거 항목" in gen["instructions"]
    packet = result["source_packet"]
    assert packet["approved_book_evidence_hash"] == digest([books[0]]) and "[E2]" in packet["body"]
    assert "검토 가능한 HTTPS 원출처가 필요합니다" not in deterministic_checks(packet)["blocking"]
    assert "[E2] 『RAG의 모든 것』, 정민제, 93쪽" in reference_lines(packet)
    assert store.budget() == before and not result["source_approval"]


def test_reapproval_can_swap_to_books_only_before_any_manuscript(scope):
    store, client, headers, idea, _ = scope
    root = f"/api/ideas/{idea['id']}"
    card = client.post(root + "/book-evidence", headers=headers, json={"expected_hash": digest(idea)}).json()
    job = client.post(root + "/select", headers=headers, json={"expected_hash": card["edit_hash"]}).json()["job"]
    assert "approved_book_evidence" not in job["article"]
    listed = next(item for item in client.get("/api/ideas").json()["ideas"] if item["id"] == idea["id"])
    assert listed["public_evidence_reviewable"] is True
    again = client.post(root + "/public-evidence/approve", headers=headers,
                        json={"expected_hash": listed["edit_hash"], "book_evidence_ids": [listed["book_evidence"][1]["id"]]})
    assert again.status_code == 200, again.text
    article = store.job(job["id"])["article"]
    assert article["approved_book_evidence"] == [listed["book_evidence"][1]] and "approved_public_evidence" not in article
    empty = client.post(root + "/public-evidence/approve", headers=headers, json={"expected_hash": again.json()["idea"]["edit_hash"]})
    assert empty.status_code == 409


def test_unavailable_bridge_is_a_plain_message(scope, monkeypatch, tmp_path):
    store, client, headers, idea, _ = scope
    monkeypatch.setenv("HEOBRAIN_BOOK_SEARCH_SOCKET", str(tmp_path / "missing.sock"))
    response = client.post(f"/api/ideas/{idea['id']}/book-evidence", headers=headers, json={"expected_hash": digest(idea)})
    assert response.status_code == 409 and "설치" in response.json()["detail"]
    assert not store.jobs()
