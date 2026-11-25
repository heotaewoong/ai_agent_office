"""근거 결과의 쪽과 소제목, 그리고 사람이 누르는 Tavily 1회 검색."""
import json
import os
import sqlite3
from contextlib import closing

import pytest
from fastapi.testclient import TestClient

from office import external_research, public_evidence
from office.api import create_app
from office.editorial import _with_approved_public_references
from office.ideas import _checked_public_references
from office.source_library import add_links, library_path, set_evidence
from office.store import Store, WorkflowError
from test_public_evidence import build_index
from test_source_library import add_vector, page


def test_library_evidence_carries_pdf_page_and_heading_without_changing_its_id(tmp_path, monkeypatch):
    build_index(tmp_path, monkeypatch, [])
    monkeypatch.setattr(public_evidence, "_query_vector", lambda *_, **__: [1.0] + [0.0] * 383)
    item = add_links(tmp_path, ["https://example.org/spacing"], area="C", fetch=page())[0]["item"]
    set_evidence(tmp_path, [item["id"]], True)
    add_vector(tmp_path, item["id"], 1, .9)
    [before] = public_evidence.find_library_evidence("간격 복습", root=tmp_path, limit=4)
    with closing(sqlite3.connect(library_path(tmp_path))) as db, db:
        db.execute("UPDATE passages SET locator='p.12', heading='2장 > 간격 복습' WHERE item_id=? AND seq=1", (item["id"],))
    [after] = public_evidence.find_library_evidence("간격 복습", root=tmp_path, limit=4)
    assert after["id"] == before["id"] and after["locator"] == "p.12" and after["heading"] == "2장 > 간격 복습"
    assert _checked_public_references([after]) == [after]
    [evidence] = _with_approved_public_references([], [after])
    assert evidence["source_locator"] == "p.12" and evidence["source_heading"] == "2장 > 간격 복습"
    with pytest.raises(WorkflowError, match="쪽이나 소제목"):
        _checked_public_references([{**after, "locator": "p.12\n다른 줄"}])


class Response:
    def __init__(self, status, payload):
        self.status_code, self._payload = status, payload

    def json(self):
        return self._payload

    def raise_for_status(self):
        if self.status_code >= 400:
            raise external_research.requests.HTTPError(str(self.status_code))


@pytest.fixture
def key(tmp_path, monkeypatch):
    monkeypatch.delenv("TAVILY_API_KEY", raising=False)
    path = tmp_path / "tavily.key"
    monkeypatch.setenv("TAVILY_KEY_FILE", str(path))
    return path


def test_tavily_without_key_does_not_call_and_says_so(tmp_path, key):
    def post(*args, **kwargs):
        pytest.fail("키가 없으면 부르지 않는다")
    result = external_research.run_tavily(tmp_path, "간격 복습 효과", post=post)
    assert result["searched"] is False and result["tavily"]["has_key"] is False and "키가 아직 없어요" in result["notes"][0]


def test_tavily_key_file_must_be_private(tmp_path, key):
    key.write_text("tvly-" + "a" * 32)
    os.chmod(key, 0o644)
    assert external_research.tavily_key() is None
    os.chmod(key, 0o600)
    assert external_research.tavily_key() == "tvly-" + "a" * 32


def test_tavily_sorts_official_and_idea_results_and_counts_one_call(tmp_path, key):
    key.write_text("tvly-" + "b" * 32)
    os.chmod(key, 0o600)
    calls = []

    def post(url, *, json, headers, timeout):
        calls.append((url, json, headers["Authorization"]))
        return Response(200, {"results": [
            {"title": "간격 복습 효과 메타분석", "url": "https://pubmed.ncbi.nlm.nih.gov/123/", "content": "간격 복습 효과 연구"},
            {"title": "간격 복습 효과 후기", "url": "https://someblog.example.com/post", "content": "간격 복습 효과를 써 봤어요"},
            {"title": "간격 복습 블로그", "url": "https://docs.example.dev/guide", "content": "개발 문서처럼 보이는 주소"},
            {"title": "주소가 이상한 결과", "url": "http://plain.example.com/x", "content": "https가 아님"},
        ]})
    result = external_research.run_tavily(tmp_path, "간격 복습 효과", post=post)
    assert len(calls) == 1 and calls[0][0] == external_research.TAVILY_URL
    assert calls[0][1]["query"] == "간격 복습 효과 공식" and calls[0][1]["search_depth"] == "basic" and calls[0][2].startswith("Bearer tvly-")
    lanes = {row["url"]: (row["lane"], row["idea_only"]) for row in result["candidates"]}
    assert lanes == {"https://pubmed.ncbi.nlm.nih.gov/123/": ("fact", False), "https://someblog.example.com/post": ("example", True),
                     "https://docs.example.dev/guide": ("fact", False)}
    assert result["tavily"]["calls"] == 1 and result["searched"] is True
    assert "tvly-" not in json.dumps(result)


def test_tavily_stops_at_the_monthly_cap_and_never_retries(tmp_path, key, monkeypatch):
    key.write_text("tvly-" + "c" * 32)
    os.chmod(key, 0o600)
    calls = []

    def fails(*args, **kwargs):
        calls.append(1)
        raise external_research.requests.ConnectionError("down")
    result = external_research.run_tavily(tmp_path, "간격 복습 효과", post=fails)
    assert calls == [1] and result["searched"] is False and "다시 부르지 않아요" in result["notes"][0]
    assert external_research.tavily_usage(tmp_path)["calls"] == 1
    rejected = external_research.run_tavily(tmp_path, "간격 복습 효과", post=lambda *a, **k: Response(401, {}))
    assert "키를 다시 확인" in rejected["notes"][0]
    monkeypatch.setattr(external_research, "TAVILY_MONTHLY_CAP", 2)
    capped = external_research.run_tavily(tmp_path, "간격 복습 효과", post=lambda *a, **k: pytest.fail("한도를 넘기면 부르지 않는다"))
    assert capped["searched"] is False and "다 써서" in capped["notes"][0]


def test_tavily_api_reports_usage_without_the_key(tmp_path, key):
    key.write_text("tvly-" + "d" * 32)
    os.chmod(key, 0o600)
    store = Store(tmp_path)
    client = TestClient(create_app(store), base_url="http://localhost:8510")
    usage = client.get("/api/source-library/research/tavily").json()
    assert usage["has_key"] is True and usage["calls"] == 0 and "tvly" not in json.dumps(usage)


def test_tavily_treats_the_product_site_as_official_and_drops_robots_blocked_hosts(tmp_path, key):
    key.write_text("tvly-" + "e" * 32)
    os.chmod(key, 0o600)

    def post(url, *, json, headers, timeout):
        return Response(200, {"results": [
            {"title": "Obsidian Sync 문제 해결", "url": "https://obsidian.md/help/sync/troubleshoot", "content": "동기화 문제"},
            {"title": "옵시디언 동기화 후기", "url": "https://m.blog.naver.com/someone/1", "content": "후기"},
            {"title": "Obsidian 영상", "url": "https://www.youtube.com/watch?v=1", "content": "영상"},
            {"title": "옵시디언 동기화 방법", "url": "https://goldenrabbit.co.kr/obsidian", "content": "출판사 블로그"},
        ]})
    result = external_research.run_tavily(tmp_path, "옵시디언 Up to Date인데 휴대폰 동기화가 안 될 때", post=post)
    lanes = {row["url"]: row["lane"] for row in result["candidates"]}
    assert lanes == {"https://obsidian.md/help/sync/troubleshoot": "fact", "https://www.youtube.com/watch?v=1": "example",
                     "https://goldenrabbit.co.kr/obsidian": "example"}
    assert any("robots.txt" in note for note in result["notes"])
    assert external_research._site_name("docs.anthropic.com") == "anthropic" and external_research._site_name("goldenrabbit.co.kr") == "goldenrabbit"
