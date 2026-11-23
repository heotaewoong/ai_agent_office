"""자료 창고: 링크·메모·파일을 문단으로 저장하고, 운영자가 켠 자료만 근거 후보로 표시한다."""
import base64

import pytest
from fastapi.testclient import TestClient

from office.source_library import (
    add_file, add_links, add_memo, delete_item, item_detail, library_overview, retry_item, search_library,
    split_passages, update_item,
)
from office.store import Store, WorkflowError

BODY = "".join(f"<p>문단 {n}. 간격을 두고 다시 꺼내 보는 복습은 한 번에 몰아서 하는 공부보다 오래 남습니다.</p>" for n in range(1, 9))
PAGE = f"<html><head><title>간격 복습 안내</title></head><body><nav>메뉴</nav>{BODY}<script>x()</script></body></html>"


def page(markup=PAGE, kind="text/html; charset=utf-8"):
    calls = []

    def fetch(url, *, maximum):
        calls.append(url)
        return markup.encode("utf-8"), url, kind
    fetch.calls = calls
    return fetch


def test_link_is_read_once_and_saved_as_passages(tmp_path):
    fetch = page()
    [result] = add_links(tmp_path, ["https://example.org/spacing?utm_source=x"], area="C", fetch=fetch)
    item = result["item"]
    assert result["result"] == "added" and item["status"] == "done" and item["title"] == "간격 복습 안내"
    assert item["passages"] >= 1 and item["area_label"] == "학습법과 뇌과학" and item["use_as_evidence"] is False
    detail = item_detail(tmp_path, item["id"])
    assert "메뉴" not in "".join(detail["passage_texts"]) and "x()" not in "".join(detail["passage_texts"])
    again = add_links(tmp_path, ["https://example.org/spacing"], area="C", fetch=fetch)
    assert again[0]["result"] == "exists" and len(fetch.calls) == 1


def test_unreadable_link_is_kept_with_a_reason_and_can_be_retried(tmp_path):
    [result] = add_links(tmp_path, ["https://example.org/login"], area="B", fetch=page("<title>Just a moment</title><p>잠시만요</p>"))
    item = result["item"]
    assert item["status"] == "needs_check" and "본문을 읽지 못했습니다" in item["note"]
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
    assert api.post("/api/source-library/memos", json={"title": "x", "text": "y", "area": "Z"}).status_code == 409
    assert api.post("/api/source-library/links", json={"urls": ["http://example.org/a"], "area": "B"}).json()["results"][0]["result"] == "rejected"
    assert api.delete(f"/api/source-library/items/{item['id']}").json()["stats"]["items"] == 0
    assert api.get(f"/api/source-library/items/{item['id']}").status_code == 409


def test_api_rejects_writes_without_the_session_token(tmp_path):
    from office.api import create_app
    api = TestClient(create_app(Store(tmp_path)), base_url="http://localhost:8510")
    api.get("/api/session")
    response = api.post("/api/source-library/memos", json={"title": "a", "text": "b" * 100, "area": "A"}, headers={"Origin": "http://localhost:3110"})
    assert response.status_code in (401, 403)
