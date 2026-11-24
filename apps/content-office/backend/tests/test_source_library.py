"""자료 창고: 링크·메모·파일을 문단으로 저장하고, 운영자가 켠 자료만 근거 후보로 쓴다."""
import base64
import fcntl
import io
import json
import os
import re
import sqlite3
import struct
import sys
from contextlib import closing
from types import SimpleNamespace

import pytest
from fastapi.testclient import TestClient

from office.source_library import (
    add_file, add_links, add_memo, delete_item, fill_text, import_inbox, item_detail, library_overview, library_path,
    retry_item, search_library, set_evidence, split_passages, update_item, vector_status,
)
from office.store import Store, WorkflowError

BODY = "".join(f"<p>문단 {n}. 간격을 두고 다시 꺼내 보는 복습은 한 번에 몰아서 하는 공부보다 오래 남습니다.</p>" for n in range(1, 9))
PAGE = f"<html><head><title>간격 복습 안내</title></head><body><nav>메뉴</nav>{BODY}<script>x()</script></body></html>"
PMC = ('<?xml version="1.0"?>\n<!DOCTYPE pmc-articleset PUBLIC "-//NLM//DTD ARTICLE SET 2.0//EN" '
       '"https://dtd.nlm.nih.gov/ncbi/pmc/articleset/nlm-articleset-2.0.dtd">\n<pmc-articleset><article><front>'
       '<article-meta><title-group><article-title>Spacing review</article-title></title-group><abstract><p>'
       + 'Spaced retrieval practice improves long-term retention across many studies. ' * 3 + '</p></abstract>'
       '</article-meta></front><body><p>' + 'Distributed practice outperforms massed practice in classrooms. ' * 4
       + '</p></body></article></pmc-articleset>')


def page(markup=PAGE, kind="text/html; charset=utf-8"):
    calls = []

    def fetch(url, *, maximum):
        calls.append(url)
        return markup.encode("utf-8"), url, kind
    fetch.calls = calls
    return fetch


def routed(pages):
    calls = []

    def fetch(url, *, maximum):
        calls.append(url)
        for prefix, value in pages.items():
            if url.startswith(prefix):
                if isinstance(value, Exception):
                    raise value
                return value[0].encode("utf-8"), url, value[1]
        raise OSError("not found")
    fetch.calls = calls
    return fetch


def test_link_is_read_once_and_saved_as_passages(tmp_path):
    fetch = page()
    [result] = add_links(tmp_path, ["https://example.org/spacing?utm_source=x"], area="C", fetch=fetch)
    item = result["item"]
    assert result["result"] == "added" and item["status"] == "done" and item["title"] == "간격 복습 안내"
    assert item["passages"] >= 1 and item["area_label"] == "학습법과 뇌과학" and item["use_as_evidence"] is False and item["pasted"] is False
    detail = item_detail(tmp_path, item["id"])
    assert "메뉴" not in "".join(detail["passage_texts"]) and "x()" not in "".join(detail["passage_texts"])
    again = add_links(tmp_path, ["https://example.org/spacing"], area="C", fetch=fetch)
    assert again[0]["result"] == "exists" and len(fetch.calls) == 1


def test_unreadable_link_is_kept_with_a_reason_and_can_be_retried(tmp_path):
    [result] = add_links(tmp_path, ["https://example.org/login"], area="B", fetch=page("<title>Just a moment</title><p>잠시만요</p>"))
    item = result["item"]
    assert item["status"] == "needs_check" and "본문 붙여넣기" in item["note"] and item["title"] == "https://example.org/login"
    with pytest.raises(WorkflowError, match="본문이 저장된 자료만"):
        update_item(tmp_path, item["id"], {"use_as_evidence": True})
    assert retry_item(tmp_path, item["id"], fetch=page())["status"] == "done"
    with pytest.raises(WorkflowError, match="확인이 필요한 자료만"):
        retry_item(tmp_path, item["id"], fetch=page())


def test_network_failure_does_not_raise(tmp_path):
    def broken(url, *, maximum):
        raise OSError("connection reset")
    [result] = add_links(tmp_path, ["https://example.org/a"], area="B", fetch=broken)
    assert result["item"]["status"] == "needs_check" and "OSError" in result["item"]["note"]


def test_only_public_https_links_are_accepted(tmp_path):
    results = add_links(tmp_path, ["http://example.org/a", "ftp://example.org/b"], area="B", fetch=page())
    assert [r["result"] for r in results] == ["rejected", "rejected"]
    with pytest.raises(WorkflowError, match="한 개 이상"):
        add_links(tmp_path, ["  "], area="B", fetch=page())
    with pytest.raises(WorkflowError, match="10개까지"):
        add_links(tmp_path, [f"https://example.org/{n}" for n in range(11)], area="B", fetch=page())
    with pytest.raises(WorkflowError, match="분야"):
        add_links(tmp_path, ["https://example.org/a"], area="source", fetch=page())


def test_pmc_and_pubmed_links_are_read_from_the_institution_xml(tmp_path):
    fetch = routed({"https://eutils.ncbi.nlm.nih.gov/": (PMC, "text/xml")})
    item = add_links(tmp_path, ["https://pmc.ncbi.nlm.nih.gov/articles/PMC11078833/"], area="C", fetch=fetch)[0]["item"]
    assert item["status"] == "done" and item["title"] == "Spacing review"
    assert fetch.calls == ["https://eutils.ncbi.nlm.nih.gov/entrez/eutils/efetch.fcgi?db=pmc&id=11078833&retmode=xml"]
    assert "Distributed practice" in "".join(item_detail(tmp_path, item["id"])["passage_texts"])
    evil = '<?xml version="1.0"?><!DOCTYPE x [<!ENTITY a "aaaa">]><x>&a;</x>'
    blocked = add_links(tmp_path, ["https://pubmed.ncbi.nlm.nih.gov/39288097/"], area="C",
                        fetch=routed({"https://eutils.ncbi.nlm.nih.gov/": (evil, "text/xml")}))[0]["item"]
    assert blocked["status"] == "needs_check" and "형식" in blocked["note"]


def test_arxiv_pdf_links_use_the_html_version_then_the_abstract(tmp_path):
    fetch = routed({"https://arxiv.org/html/": OSError("404"), "https://arxiv.org/abs/": (PAGE, "text/html")})
    item = add_links(tmp_path, ["https://arxiv.org/pdf/2312.10997v5"], area="B", fetch=fetch)[0]["item"]
    assert item["status"] == "done" and item["url"] == "https://arxiv.org/pdf/2312.10997v5"
    assert fetch.calls == ["https://arxiv.org/html/2312.10997v5", "https://arxiv.org/abs/2312.10997v5"]


def test_youtube_links_explain_the_block_keep_the_title_and_accept_pasted_text(tmp_path):
    fetch = routed({"https://www.youtube.com/oembed": ('{"title": "간격 반복 공부법"}', "application/json")})
    item = add_links(tmp_path, ["https://youtu.be/abcdefghijk"], area="C", fetch=fetch)[0]["item"]
    assert item["status"] == "needs_check" and "스크립트 표시" in item["note"] and item["title"] == "간격 반복 공부법"
    assert len(fetch.calls) == 1 and "oembed" in fetch.calls[0]
    text = "영상에서 설명한 간격 반복은 하루, 사흘, 일주일 간격으로 다시 꺼내 보는 방법입니다. " * 3
    with pytest.raises(WorkflowError, match="80자 이상"):
        fill_text(tmp_path, item["id"], "짧은 글")
    filled = fill_text(tmp_path, item["id"], text)
    assert filled["status"] == "done" and filled["pasted"] is True and filled["url"] == "https://youtu.be/abcdefghijk"
    assert filled["title"] == "간격 반복 공부법" and update_item(tmp_path, item["id"], {"use_as_evidence": True})["use_as_evidence"]
    with pytest.raises(WorkflowError, match="확인이 필요한"):
        fill_text(tmp_path, item["id"], text)
    memo = add_memo(tmp_path, "메모", "메모 본문입니다. 직접 겪은 일을 적어 둡니다. " * 5, area="A")
    with pytest.raises(WorkflowError, match="확인이 필요한"):
        fill_text(tmp_path, memo["id"], text)


def test_memo_and_file_are_saved_and_duplicates_are_not_stored_twice(tmp_path):
    text = "편입 시험 한 달 전 모의고사 점수가 낮았지만, 틀린 문제만 사흘 간격으로 다시 풀면서 점수를 올렸습니다. " * 3
    memo = add_memo(tmp_path, "편입 복습 경험", text, area="A")
    assert memo["status"] == "done" and memo["mine"] is True and memo["kind"] == "memo"
    copy = add_memo(tmp_path, "같은 내용", text, area="A")
    assert copy["status"] == "duplicate" and "편입 복습 경험" in copy["note"]
    encoded = base64.b64encode(("n8n으로 블로그 초안을 만들 때는 채널마다 따로 생성합니다. " * 6).encode("utf-8")).decode("ascii")
    file = add_file(tmp_path, "자동화 메모.md", encoded, area="B")
    assert file["status"] == "done" and file["file_name"] == "자동화 메모.md"
    with pytest.raises(WorkflowError, match="txt, md, docx, pdf"):
        add_file(tmp_path, "run.exe", encoded, area="B")
    with pytest.raises(WorkflowError, match="다시 올려"):
        add_file(tmp_path, "a.txt", "!!!", area="B")
    with pytest.raises(WorkflowError, match="제목과 내용"):
        add_memo(tmp_path, "", "x", area="A")


def test_evidence_switch_area_and_delete(tmp_path):
    item = add_links(tmp_path, ["https://example.org/spacing"], area="C", fetch=page())[0]["item"]
    updated = update_item(tmp_path, item["id"], {"use_as_evidence": True, "area": "D", "title": " 새 제목 "})
    assert updated["use_as_evidence"] is True and updated["area"] == "D" and updated["title"] == "새 제목"
    overview = library_overview(tmp_path)
    assert overview["stats"] == {"items": 1, "ready": 1, "passages": updated["passages"], "evidence": 1, "needs_check": 0}
    assert [a["items"] for a in overview["areas"] if a["id"] == "D"] == [1]
    for changes in ({}, {"status": "done"}, {"use_as_evidence": "yes"}, {"area": "Z"}, {"title": ""}):
        with pytest.raises(WorkflowError):
            update_item(tmp_path, item["id"], changes)
    assert delete_item(tmp_path, item["id"]) == {"deleted": item["id"]}
    assert library_overview(tmp_path)["items"] == []
    with pytest.raises(WorkflowError, match="찾을 수 없습니다"):
        item_detail(tmp_path, item["id"])


def test_bulk_evidence_switch_skips_unready_items(tmp_path):
    ready = add_memo(tmp_path, "경험", "직접 해 본 공부 방법을 정리한 메모입니다. " * 5, area="D")
    broken = add_links(tmp_path, ["https://example.org/x"], area="B", fetch=page("<title>Just a moment</title>"))[0]["item"]
    assert set_evidence(tmp_path, [ready["id"], broken["id"], "missing"], True) == {"changed": 1, "skipped": 2}
    assert set_evidence(tmp_path, [ready["id"], broken["id"]], False) == {"changed": 2, "skipped": 0}
    for ids, value in (([], True), (["a"], "yes"), ("abc", True), ([1], True)):
        with pytest.raises(WorkflowError):
            set_evidence(tmp_path, ids, value)


def test_search_ranks_matching_passages_and_filters_by_area_and_evidence(tmp_path):
    study = add_links(tmp_path, ["https://example.org/spacing"], area="C", fetch=page())[0]["item"]
    add_memo(tmp_path, "자동화 메모", "n8n 워크플로는 사람의 판단과 반복 작업을 나눕니다. " * 5, area="B")
    hits = search_library(tmp_path, "간격 복습")
    assert hits and hits[0]["item_id"] == study["id"] and "복습" in hits[0]["matched"] and hits[0]["paragraph"] >= 1
    assert search_library(tmp_path, "간격 복습", area="B") == []
    assert search_library(tmp_path, "간격 복습", evidence_only=True) == []
    update_item(tmp_path, study["id"], {"use_as_evidence": True})
    assert search_library(tmp_path, "간격 복습", evidence_only=True)[0]["use_as_evidence"] is True
    assert search_library(tmp_path, "!!") == [] and search_library(tmp_path, "없는낱말") == []
    with pytest.raises(WorkflowError, match="분야"):
        search_library(tmp_path, "복습", area="Z")


def test_split_passages_joins_short_and_cuts_long_paragraphs():
    assert split_passages(["가" * 10, "", "나" * 10], limit=50) == ["가" * 10 + "\n" + "나" * 10]
    parts = split_passages(["문장입니다. " * 300], limit=200)
    assert len(parts) > 5 and all(len(part) <= 300 for part in parts)


def add_vector(root, item_id, seq, score, start=0, end=None):
    from office.public_evidence import LIBRARY_MODEL
    from test_public_evidence import vector_blob
    with closing(sqlite3.connect(library_path(root))) as db, db:
        text = db.execute("SELECT text FROM passages WHERE item_id=? AND seq=?", (item_id, seq)).fetchone()[0]
        db.execute("INSERT OR REPLACE INTO passage_vectors VALUES (?,?,?,?,?,?,?)",
                   (item_id, seq, 0, start, len(text) if end is None else end, LIBRARY_MODEL, vector_blob(score)))
    return text


def test_vector_status_counts_only_checked_link_passages(tmp_path):
    link = add_links(tmp_path, ["https://example.org/spacing"], area="C", fetch=page())[0]["item"]
    memo = add_memo(tmp_path, "경험", "직접 해 본 공부 방법을 정리한 메모입니다. " * 5, area="D")
    assert library_overview(tmp_path)["vectors"] == {"passages": 0, "ready": 0, "pending": 0, "available": False}
    set_evidence(tmp_path, [link["id"], memo["id"]], True)
    assert vector_status(tmp_path) == {"passages": link["passages"], "ready": 0, "pending": link["passages"], "available": False}
    add_vector(tmp_path, link["id"], 1, .9)
    assert vector_status(tmp_path)["ready"] == 1
    delete_item(tmp_path, link["id"])
    with closing(sqlite3.connect(library_path(tmp_path))) as db:
        assert db.execute("SELECT COUNT(*) FROM passage_vectors").fetchone()[0] == 0


def test_checked_link_passages_join_the_public_evidence_search(tmp_path, monkeypatch):
    from office import public_evidence
    from office.ideas import _checked_public_references
    from test_public_evidence import build_index
    build_index(tmp_path, monkeypatch, [("https://docs.example.org/indexed", 2, "색인 문단", .5)])
    monkeypatch.setattr(public_evidence, "_query_vector", lambda *_, **__: [1.0] + [0.0] * 383)
    strong = add_links(tmp_path, ["https://example.org/spacing"], area="C", fetch=page())[0]["item"]
    weak = add_links(tmp_path, ["https://example.org/weak"], area="C", fetch=page(PAGE.replace("복습은", "반복은")))[0]["item"]
    off = add_links(tmp_path, ["https://example.org/off"], area="C", fetch=page(PAGE.replace("복습은", "연습은")))[0]["item"]
    set_evidence(tmp_path, [strong["id"], weak["id"]], True)
    text = add_vector(tmp_path, strong["id"], 1, .9, 0, 80)
    add_vector(tmp_path, weak["id"], 1, public_evidence._LIBRARY_MIN_SIMILARITY - .05)
    add_vector(tmp_path, off["id"], 1, .99)
    results = public_evidence.find_public_evidence("간격 복습", limit=4)
    assert [r["url"] for r in results] == ["https://example.org/spacing", "https://docs.example.org/indexed"]
    assert results[0]["paragraph"] == 1 and results[0]["quote"] == text[:80].strip() and results[0]["title"] == "간격 복습 안내"
    assert _checked_public_references(results) == results
    assert public_evidence.find_library_evidence("간격 복습", root=tmp_path, limit=4)[0]["url"] == "https://example.org/spacing"
    assert public_evidence.find_library_evidence("간격 복습", root=tmp_path, exclude_urls=("https://example.org/spacing",)) == []
    assert public_evidence.find_library_evidence("간격 복습", root=tmp_path / "other", limit=4) == []
    add_vector(tmp_path, weak["id"], 1, .99, 0, 20)
    assert public_evidence.find_library_evidence("간격 복습", root=tmp_path, limit=4)[0]["url"] == "https://example.org/spacing"


def test_platform_ideas_fill_free_evidence_slots_from_the_library(tmp_path, monkeypatch):
    from office import ideas, public_evidence
    from test_public_evidence_workflow import reference
    seen = []
    monkeypatch.setattr(public_evidence, "find_library_evidence",
                        lambda title, *, root, exclude_urls, limit: seen.append((title, root, exclude_urls, limit)) or [reference(9), reference(3)])
    store = Store(tmp_path)
    merged, claims = ideas._with_library_references(store, "기획", [reference(3)], [{"label": "공식", "evidence_ids": [reference(3)["id"]]}])
    assert [item["url"] for item in merged] == [reference(3)["url"], reference(9)["url"]]
    assert claims[-1] == {"label": "자료 창고에서 근거로 고른 문단", "evidence_ids": [reference(9)["id"]]}
    assert seen == [("기획", store.root, (reference(3)["url"],), ideas.PUBLIC_EVIDENCE_LIMIT - 1)]


def runtime(tmp_path, monkeypatch):
    from office import public_evidence
    monkeypatch.setenv("OFFICE_STATE_DIR", str(tmp_path))
    for key in ("HEOBRAIN_PUBLIC_RAG_DB", "HEOBRAIN_PUBLIC_RAG_PYTHON", "HEOBRAIN_PUBLIC_RAG_MODEL_CACHE"):
        monkeypatch.delenv(key, raising=False)
    (tmp_path / "public-rag/runtime/bin").mkdir(parents=True)
    (tmp_path / "public-rag/runtime/bin/python").write_text("")
    (tmp_path / "public-rag/model-cache").mkdir()
    monkeypatch.setattr(public_evidence, "_last_spawn", [0.0])
    return public_evidence


def test_vector_worker_starts_only_for_the_live_state_folder(tmp_path, monkeypatch):
    public_evidence = runtime(tmp_path, monkeypatch)
    calls = []
    monkeypatch.setattr(public_evidence.subprocess, "Popen", lambda command, **options: calls.append((command, options)))
    assert public_evidence.start_library_vectors(tmp_path) is False
    add_memo(tmp_path, "경험", "직접 해 본 공부 방법을 정리한 메모입니다. " * 5, area="D")
    assert public_evidence.library_worker_available(tmp_path) and not public_evidence.library_worker_available(tmp_path / "copy")
    assert public_evidence.start_library_vectors(tmp_path / "copy") is False
    assert public_evidence.start_library_vectors(tmp_path) is True
    assert public_evidence.start_library_vectors(tmp_path) is False
    [(command, options)] = calls
    assert command[1:5] == ["-I", "-B", os.path.realpath(public_evidence.__file__), "--library"]
    assert command[-1] == str(library_path(tmp_path)) and command[-2].endswith("query.lock")
    assert options["start_new_session"] is True and options["env"]["HF_HUB_OFFLINE"] == "1"


def library_model(tmp_path, monkeypatch, public_evidence):
    cache = tmp_path / "cache"
    model_dir = cache / public_evidence._LIBRARY_MODEL_DIR / public_evidence._LIBRARY_MODEL_REVISION
    model_dir.mkdir(parents=True)
    monkeypatch.setattr(public_evidence, "_LIBRARY_MODEL_FILES", {"model.onnx": 1, "tokenizer.json": 1})
    for name in public_evidence._LIBRARY_MODEL_FILES:
        (model_dir / name).write_text("x")
    monkeypatch.setattr(public_evidence, "_mem_available_kib", lambda: 4 * 1024 * 1024)
    return cache, model_dir


def test_library_worker_embeds_each_pending_passage_once_with_the_library_model(tmp_path, monkeypatch):
    from office import public_evidence
    cache, model_dir = library_model(tmp_path, monkeypatch, public_evidence)
    item = add_links(tmp_path, ["https://example.org/spacing"], area="C", fetch=page())[0]["item"]
    memo = add_memo(tmp_path, "경험", "직접 해 본 공부 방법을 정리한 메모입니다. " * 5, area="D")
    set_evidence(tmp_path, [item["id"], memo["id"]], True)
    with closing(sqlite3.connect(library_path(tmp_path))) as db, db:  # 예전 모델이 문단 하나를 두 구간으로 나눠 둔 흔적
        db.executemany("INSERT INTO passage_vectors VALUES (?,?,?,?,?,?,?)",
                       [(item["id"], 1, part, 0, 10, "old-model", b"x") for part in (0, 1)])
    embedded = []
    monkeypatch.setattr(public_evidence, "_library_embedder",
                        lambda path: (lambda text: embedded.append((path, text)) or [3.0] + [0.0] * 383))
    lock = tmp_path / "query.lock"
    assert vector_status(tmp_path)["ready"] == 0
    assert public_evidence._run_library_worker(cache, lock, library_path(tmp_path)) == 0
    status = vector_status(tmp_path)
    assert status["pending"] == 0 and status["ready"] == item["passages"] == len(embedded)
    with closing(sqlite3.connect(library_path(tmp_path))) as db:
        rows = db.execute("SELECT v.seq, v.part, v.start_char, v.end_char, v.model, v.vector, p.text FROM passage_vectors v "
                          "JOIN passages p ON p.item_id=v.item_id AND p.seq=v.seq ORDER BY v.seq, v.part").fetchall()
    assert [(seq, part, start) for seq, part, start, *_ in rows] == [(n, 0, 0) for n in range(1, item["passages"] + 1)]
    assert all(end == len(text) and model == public_evidence.LIBRARY_MODEL and struct.unpack("<384f", blob)[0] == 1.0
               for _, _, _, end, model, blob, text in rows)
    first = rows[0][-1]
    wanted = f"간격 복습 안내 | {first}" if public_evidence._LIBRARY_TITLE_IN_PASSAGE else first
    assert embedded[0] == (model_dir, public_evidence._LIBRARY_PASSAGE_PREFIX + wanted)
    count = len(embedded)
    assert public_evidence._run_library_worker(cache, lock, library_path(tmp_path)) == 0 and len(embedded) == count
    holder = os.open(lock, os.O_RDWR)
    fcntl.flock(holder, fcntl.LOCK_EX | fcntl.LOCK_NB)
    try:
        assert public_evidence._run_library_worker(cache, lock, library_path(tmp_path)) == public_evidence._BUSY_STATUS
    finally:
        os.close(holder)


def test_library_workers_refuse_low_memory_and_a_model_that_is_not_the_pinned_one(tmp_path, monkeypatch, capsys):
    from office import public_evidence
    cache, model_dir = library_model(tmp_path, monkeypatch, public_evidence)
    monkeypatch.setattr(public_evidence.os, "O_NOFOLLOW", 0, raising=False)
    monkeypatch.setattr(public_evidence, "_library_embedder", lambda path: (lambda text: [0.0, 2.0] + [0.0] * 382))
    lock = tmp_path / "query.lock"

    def ask(text="간격 복습"):
        monkeypatch.setattr(sys, "stdin", SimpleNamespace(buffer=io.BytesIO(text.encode("utf-8"))))
        return public_evidence._run_worker(cache, lock, library=True)

    monkeypatch.setattr(public_evidence, "_mem_available_kib", lambda: public_evidence._MIN_LIBRARY_WORKER_AVAILABLE_KIB - 1)
    assert ask() == public_evidence._LOW_MEMORY_STATUS
    assert public_evidence._run_library_worker(cache, lock, library_path(tmp_path)) == public_evidence._LOW_MEMORY_STATUS
    monkeypatch.setattr(public_evidence, "_mem_available_kib", lambda: 4 * 1024 * 1024)
    (model_dir / "model.onnx").write_text("다른 파일")  # 크기가 고정한 판과 다르면 쓰지 않는다
    assert ask() == public_evidence._CACHE_MISSING_STATUS
    assert public_evidence._run_library_worker(cache, lock, library_path(tmp_path)) == public_evidence._CACHE_MISSING_STATUS
    assert capsys.readouterr().out == ""
    (model_dir / "model.onnx").write_text("x")
    assert ask() == 0 and json.loads(capsys.readouterr().out) == [0.0, 2.0] + [0.0] * 382  # 성공하면 잠금을 쥔 채 끝난다


def test_library_question_uses_the_library_worker_and_never_another_model(tmp_path, monkeypatch):
    public_evidence = runtime(tmp_path, monkeypatch)
    commands = []

    def worker(command, **options):
        commands.append(command)
        return SimpleNamespace(returncode=0, stdout=json.dumps([1.0] + [0.0] * 383))

    monkeypatch.setattr(public_evidence.subprocess, "run", worker)
    item = add_links(tmp_path, ["https://example.org/spacing"], area="C", fetch=page())[0]["item"]
    set_evidence(tmp_path, [item["id"]], True)
    text = add_vector(tmp_path, item["id"], 1, .9)
    [found] = public_evidence.find_library_evidence("간격 복습", root=tmp_path, limit=4)
    assert found["quote"] == text.strip() and found["paragraph"] == 1
    assert [command[4] for command in commands] == ["--library-query"]
    monkeypatch.setattr(public_evidence.subprocess, "run", lambda command, **options: SimpleNamespace(returncode=public_evidence._CACHE_MISSING_STATUS, stdout=""))
    with pytest.raises(public_evidence.PublicEvidenceUnavailable):
        public_evidence.find_library_evidence("간격 복습", root=tmp_path, limit=4)


def test_import_inbox_maps_groups_and_skips_duplicates(tmp_path):
    rows = [
        {"id": "a" * 20, "kind": "link", "grp": "뇌과학과 마인드셋", "title": "Spacing review", "url": "https://pmc.ncbi.nlm.nih.gov/articles/PMC1/",
         "status": "done", "chunks": ["첫 문단 " * 40, "둘째 문단 " * 40], "created_at": 1795400000.0},
        {"id": "b" * 20, "kind": "link", "grp": "AI와 자동화", "title": "Hermes", "url": "https://hermes.example.org/docs",
         "status": "done", "chunks": ["Hermes 문단 " * 40]},
        {"id": "c" * 20, "kind": "memo", "grp": "내 경험과 아이디어", "title": "편입 경험", "url": None, "status": "done",
         "chunks": ["편입 경험 " * 30], "body": "편입 경험 " * 30},
        {"id": "d" * 20, "kind": "link", "grp": "AI와 자동화", "title": "막힌 글", "url": "https://x.example.org", "status": "needs_check", "chunks": []},
        {"id": "bad id", "kind": "link", "chunks": ["x"]},
    ]
    assert [r["result"] for r in import_inbox(tmp_path, rows)] == ["imported", "imported", "imported", "skipped", "rejected"]
    items = {item["title"]: item for item in library_overview(tmp_path)["items"]}
    assert items["Spacing review"]["area"] == "C" and items["Spacing review"]["origin"] == "import" and items["Spacing review"]["passages"] == 2
    assert items["Spacing review"]["origin_ref"] == "a" * 20 and items["Spacing review"]["created_at"].startswith("2026-11")
    assert items["Hermes"]["area"] == "B" and items["편입 경험"]["mine"] is True and items["편입 경험"]["area"] == "D"
    assert not any(item["use_as_evidence"] for item in items.values())
    assert item_detail(tmp_path, items["Spacing review"]["id"])["passage_texts"] == rows[0]["chunks"]
    assert [r["result"] for r in import_inbox(tmp_path, rows[:3])] == ["exists"] * 3
    with pytest.raises(WorkflowError):
        import_inbox(tmp_path, {"id": "a"})


def client(tmp_path):
    from office.api import create_app
    api = TestClient(create_app(Store(tmp_path)), base_url="http://localhost:8510")
    api.headers.update({"Origin": "http://localhost:3110", "X-Office-CSRF": api.get("/api/session").json()["csrf"]})
    return api


def test_api_saves_searches_and_marks_evidence(tmp_path):
    api = client(tmp_path)
    assert api.get("/api/source-library").json()["stats"]["items"] == 0
    text = "오픽 시험은 질문을 듣고 바로 답해야 해서, 답변 틀을 미리 세 개 정해 두고 연습했습니다. " * 3
    created = api.post("/api/source-library/memos", json={"title": "오픽 준비 경험", "text": text, "area": "A", "origin": "idea", "origin_ref": "idea-1"})
    assert created.status_code == 201 and created.json()["stats"]["ready"] == 1
    item = created.json()["item"]
    assert item["origin"] == "idea" and item["origin_ref"] == "idea-1"
    patched = api.patch(f"/api/source-library/items/{item['id']}", json={"use_as_evidence": True})
    assert patched.status_code == 200 and patched.json()["stats"]["evidence"] == 1
    found = api.get("/api/source-library/search", params={"q": "오픽 답변", "evidence_only": "true"}).json()
    assert found["results"][0]["item_id"] == item["id"]
    assert api.get(f"/api/source-library/items/{item['id']}").json()["passage_texts"]
    assert api.patch(f"/api/source-library/items/{item['id']}", json={"status": "done"}).status_code == 422
    assert api.patch(f"/api/source-library/items/{item['id']}", json={"use_as_evidence": "yes"}).status_code == 422
    assert api.post("/api/source-library/memos", json={"title": "x", "text": "y", "area": "Z"}).status_code == 409
    assert api.post("/api/source-library/links", json={"urls": ["http://example.org/a"], "area": "B"}).json()["results"][0]["result"] == "rejected"
    assert api.delete(f"/api/source-library/items/{item['id']}").json()["stats"]["items"] == 0
    assert api.get(f"/api/source-library/items/{item['id']}").status_code == 409


def test_api_paste_and_bulk_evidence_start_the_vector_worker(tmp_path, monkeypatch):
    from office import public_evidence
    started = []
    monkeypatch.setattr(public_evidence, "start_library_vectors", lambda root: started.append(root) or False)
    api = client(tmp_path)
    memo = api.post("/api/source-library/memos", json={"title": "경험", "text": "직접 해 본 공부 방법을 정리한 메모입니다. " * 5, "area": "D"}).json()["item"]
    broken = add_links(tmp_path, ["https://example.org/login"], area="B", fetch=page("<title>Just a moment</title>"))[0]["item"]
    filled = api.post(f"/api/source-library/items/{broken['id']}/text", json={"text": "붙여 넣은 로그인 글 본문입니다. " * 10, "title": "로그인 글"})
    assert filled.status_code == 200 and filled.json()["item"]["pasted"] is True and filled.json()["item"]["title"] == "로그인 글"
    assert api.post(f"/api/source-library/items/{memo['id']}/text", json={"text": "x" * 100}).status_code == 409
    bulk = api.post("/api/source-library/evidence", json={"ids": [memo["id"], broken["id"]], "use_as_evidence": True})
    assert bulk.status_code == 200 and bulk.json()["changed"] == 2 and bulk.json()["stats"]["evidence"] == 2
    assert len(started) == 1
    assert api.post("/api/source-library/evidence", json={"ids": [memo["id"]], "use_as_evidence": "yes"}).status_code == 422
    assert api.post("/api/source-library/evidence", json={"ids": [], "use_as_evidence": True}).status_code == 422


def test_api_rejects_writes_without_the_session_token(tmp_path):
    from office.api import create_app
    api = TestClient(create_app(Store(tmp_path)), base_url="http://localhost:8510")
    api.get("/api/session")
    response = api.post("/api/source-library/memos", json={"title": "a", "text": "b" * 100, "area": "A"}, headers={"Origin": "http://localhost:3110"})
    assert response.status_code in (401, 403)
