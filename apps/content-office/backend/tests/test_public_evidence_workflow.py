import hashlib
import json
import sys
from types import SimpleNamespace

import pytest
from fastapi.testclient import TestClient

from office.api import create_app
from office.editorial import prepare_source
from office.packaging import attach_packaging
from office.store import Store, WorkflowError, digest, now
from test_agent_editorial import FullProvider, brief


def evidence_id(url, source_sha256, paragraph, quote_sha256):
    encoded = json.dumps([url, source_sha256, paragraph, quote_sha256], ensure_ascii=False, separators=(",", ":")).encode()
    return hashlib.sha256(encoded).hexdigest()


def reference(number):
    url = f"https://docs.example.org/article-{number}"
    source_sha256 = hashlib.sha256(("article" + str(number)).encode()).hexdigest()
    quote = f"원래 문단 {number}의 고유 인용 원문입니다. 줄 전체를 보존합니다."
    quote_sha256 = hashlib.sha256(quote.encode()).hexdigest()
    return {
        "id": evidence_id(url, source_sha256, number, quote_sha256),
        "url": url,
        "title": f"관련 공개 원문 {number}",
        "paragraph": number,
        "quote": quote,
        "source_sha256": source_sha256,
        "quote_sha256": quote_sha256,
    }


@pytest.fixture
def scope(tmp_path, monkeypatch):
    hits = [reference(3), reference(7), reference(11)]
    calls = []

    def find(query, *, limit):
        calls.append((query, limit))
        return hits

    monkeypatch.setitem(sys.modules, "office.public_evidence", SimpleNamespace(
        find_public_evidence=find, public_evidence_id=evidence_id,
        PublicEvidenceUnavailable=type("PublicEvidenceUnavailable", (RuntimeError,), {}),
    ))
    store = Store(tmp_path)
    client = TestClient(create_app(store), base_url="http://localhost:8510")
    headers = {"Origin": "http://localhost:3110", "X-Office-CSRF": client.get("/api/session").json()["csrf"]}
    idea = client.post("/api/ideas", headers=headers, json={
        "title": "공개 근거를 인용하는 원고",
        "source_url": "https://primary.example.org/article",
        "primary_sources": 1,
    }).json()
    return store, client, headers, idea, hits, calls


def test_search_requires_session_and_keeps_choice_budget_and_approvals(scope):
    store, client, headers, idea, hits, calls = scope
    route = f"/api/ideas/{idea['id']}/public-evidence"
    before = store.budget()
    initial = digest(idea)
    assert client.post(route, json={"expected_hash": initial}).status_code == 403
    assert client.post(route, headers=headers, json={"expected_hash": "0" * 64}).status_code == 409
    assert calls == []
    response = client.post(route, headers=headers, json={"expected_hash": initial})
    assert response.status_code == 200
    saved = response.json()
    assert saved["public_evidence"] == hits and saved["edit_hash"] != initial
    assert saved["state"] == "candidate"
    assert calls == [(idea["title"], 4)] and store.budget() == before
    assert not store.jobs() and not store.tasks()
    with store.connection() as db:
        assert db.execute("SELECT count(*) FROM approvals").fetchone()[0] == 0
    assert client.get("/api/ideas").json()["ideas"][0]["edit_hash"] == saved["edit_hash"]


def test_approval_pins_only_checked_references_and_real_editorial_receives_them(scope, monkeypatch):
    store, client, headers, idea, hits, _ = scope
    root = f"/api/ideas/{idea['id']}"
    saved = client.post(root + "/public-evidence", headers=headers, json={"expected_hash": digest(idea)}).json()
    keys = [hits[0]["id"], hits[2]["id"]]
    assert client.post(root + "/select", headers=headers, json={"expected_hash": digest(idea), "public_evidence_ids": keys}).status_code == 409
    assert client.post(root + "/select", headers=headers, json={"expected_hash": saved["edit_hash"], "public_evidence_ids": ["0" * 64]}).status_code == 409
    assert client.post(root + "/select", headers=headers, json={"expected_hash": saved["edit_hash"], "public_evidence_ids": [keys[0], keys[0]]}).status_code == 409
    assert store.jobs() == []
    choose = client.post(root + "/select", headers=headers, json={"expected_hash": saved["edit_hash"], "public_evidence_ids": keys})
    assert choose.status_code == 200
    job = choose.json()["job"]
    selected = [hits[0], hits[2]]
    assert job["article"]["approved_public_evidence"] == selected
    assert job["article"]["approved_public_evidence_hash"] == digest(selected)
    assert job["article"]["url"] == idea["source_url"] and not job["source_approval"] and not job["release_approval"]
    attach_packaging(store, job["id"], brief(), "local-operator")
    before_budget = store.budget()
    primary = {"id": "E1", "claim": "기존 대표 원문의 주장입니다.", "url": idea["source_url"], "numbers": [],
               "source_paragraph": 1, "source_quote": "기존 대표 원문의 정확한 인용입니다.", "scope": "원문 서술"}
    primary_calls = []

    def collect(article, provider, directory):
        primary_calls.append(article["url"])
        return {"evidence": [primary], "limitations": [], "hook": "", "source_kind": "http_article_body",
                "source_sha256": "1" * 64, "retrieved_at": now(), "content_status": "substantive_body"}

    monkeypatch.setattr("office.evidence.collect_article_evidence", collect)

    class FixtureProvider(FullProvider):
        def _packet(self):
            packet = super()._packet()
            packet["body"] += "\n공개 원문을 교차 확인했어요. [E2][E3]"
            return packet

    provider = FixtureProvider("AI 도구 비교")
    result = prepare_source(store, job["id"], provider=provider)
    gen = json.loads(provider.users[provider.roles.index("gen")])
    stored_packet = result["source_packet"]
    assert gen["evidence"] == stored_packet["evidence"] == store.job(job["id"])["article"]["evidence"]
    assert gen["evidence"][0] == primary
    assert [(e["url"], e["source_paragraph"], e["source_quote"], e["source_sha256"], e["quote_sha256"]) for e in gen["evidence"][1:]] == [
        (hit["url"], hit["paragraph"], hit["quote"], hit["source_sha256"], hit["quote_sha256"]) for hit in selected
    ]
    assert hits[1]["quote"] not in provider.users[provider.roles.index("gen")]
    assert "[E2][E3]" in stored_packet["body"] and primary_calls == [idea["source_url"]]
    assert store.budget() == before_budget
    assert not result["source_approval"] and not result["release_approval"]
    assert stored_packet["approved_public_evidence_hash"] == digest(selected)
    assert primary_calls == [idea["source_url"]]
    edited = client.put(f"/api/jobs/{job['id']}/source", headers=headers, json={
        "version": result["source_hash"], "packet": {
            "title": "편집 후 원고 제목", "body": stored_packet["body"], "approved_public_evidence_hash": "0" * 64,
            "evidence": [{"url": hits[1]["url"], "source_quote": hits[1]["quote"]}],
        },
    })
    assert edited.status_code == 200, edited.text
    assert edited.json()["source_packet"]["approved_public_evidence_hash"] == digest(selected)
    assert edited.json()["source_packet"]["evidence"] == stored_packet["evidence"]
    again = prepare_source(store, job["id"], provider=FixtureProvider("AI 도구 비교"))
    assert again["source_packet"]["evidence"] == stored_packet["evidence"]
    assert primary_calls == [idea["source_url"]]

    omitted_provider = FullProvider("AI 도구 비교")
    omitted_provider.model = "fixture-missing-public-citations"
    omitted = prepare_source(store, job["id"], provider=omitted_provider)
    quality = omitted["source_packet"]["quality"]
    assert quality["status"] == "blocked" and quality["critical"]
    assert "승인⓪에서 고른 공개 근거 E2, E3를 원고에 연결하세요" in quality["deterministic_checks"]["blocking"]
    assert omitted_provider.roles.count("refine") <= provider.roles.count("refine")
    with pytest.raises(WorkflowError, match="승인할 수 없습니다"):
        store.review_source(job["id"], omitted["source_hash"], "approved", "fixture-operator")
    assert not store.job(job["id"])["source_approval"]
    assert store.budget() == before_budget


def test_tampered_or_replaced_evidence_cannot_be_approved(scope):
    store, client, headers, idea, hits, _ = scope
    root = f"/api/ideas/{idea['id']}"
    saved = client.post(root + "/public-evidence", headers=headers, json={"expected_hash": digest(idea)}).json()
    actual = store.ideas()[0]
    actual["public_evidence"][0]["quote"] += " 손상"
    with store.connection(transaction=True) as db:
        db.execute("UPDATE ideas SET data=? WHERE id=?", (json.dumps(actual), idea["id"]))
    result = client.post(root + "/select", headers=headers, json={
        "expected_hash": digest(actual), "public_evidence_ids": [hits[0]["id"]],
    })
    assert result.status_code == 409 and not store.jobs()
    replaced = client.put(root + "/sources", headers=headers, json={
        "expected_hash": digest(actual), "operator_verified": True, "source_urls": ["https://docs.example.org/other"],
    }).json()
    assert not replaced.get("public_evidence") and replaced["edit_hash"] != saved["edit_hash"]
    result = client.post(root + "/select", headers=headers, json={
        "expected_hash": replaced["edit_hash"], "public_evidence_ids": [hits[0]["id"]],
    })
    assert result.status_code == 409 and not store.jobs()


def test_suggestions_never_satisfy_primary_source_gate_or_choose_for_operator(scope):
    store, client, headers, idea, hits, _ = scope
    no_primary = client.post("/api/ideas", headers=headers, json={"title": "대표 출처가 아직 없는 기획"}).json()
    root = f"/api/ideas/{no_primary['id']}"
    found = client.post(root + "/public-evidence", headers=headers, json={"expected_hash": digest(no_primary)}).json()
    result = client.post(root + "/select", headers=headers, json={
        "expected_hash": found["edit_hash"], "public_evidence_ids": [hits[0]["id"]],
    })
    assert result.status_code == 409 and not store.jobs()
    root = f"/api/ideas/{idea['id']}"
    found = client.post(root + "/public-evidence", headers=headers, json={"expected_hash": digest(idea)}).json()
    result = client.post(root + "/select", headers=headers, json={"expected_hash": found["edit_hash"]})
    assert result.status_code == 200
    assert "approved_public_evidence" not in result.json()["job"]["article"]
def test_selected_platform_idea_approves_evidence_on_existing_job_only(scope):
    store, client, headers, idea, hits, _ = scope
    root = f"/api/ideas/{idea['id']}"
    chosen = client.post(root + "/select", headers=headers, json={"expected_hash": digest(idea)}).json()
    old_job = chosen["job"]
    old_events = store.events()
    budget = store.budget()
    route = root + "/public-evidence"
    listed = client.get("/api/ideas").json()["ideas"][0]
    assert listed["public_evidence_reviewable"] is True
    found = client.post(route, headers=headers, json={"expected_hash": listed["edit_hash"]}).json()
    assert found["state"] == "selected" and found["public_evidence"] == hits
    keys = [hits[1]["id"]]
    request = {"expected_hash": found["edit_hash"], "public_evidence_ids": keys}
    assert client.post(route + "/approve", json=request).status_code == 403
    assert client.post(route + "/approve", headers=headers, json={**request, "public_evidence_ids": []}).status_code == 409
    assert client.post(route + "/approve", headers=headers, json={**request, "expected_hash": listed["edit_hash"]}).status_code == 409
    approved = client.post(route + "/approve", headers=headers, json=request)
    assert approved.status_code == 200, approved.text
    result = approved.json()
    assert result["idea"]["selected_at"] == chosen["idea"]["selected_at"]
    assert result["idea"]["approved_public_evidence_ids"] == keys
    job = store.job(old_job["id"])
    assert job["article"]["approved_public_evidence"] == [hits[1]]
    evidence_hash = job["article"]["approved_public_evidence_hash"]
    assert result["job"]["id"] == old_job["id"] and len(store.jobs()) == 1
    assert {k: v for k, v in job.items() if k not in ("article", "updated_at")} == {k: v for k, v in old_job.items() if k not in ("article", "updated_at")}
    assert all(event in store.events() for event in old_events)

    preview = f"/api/jobs/{old_job['id']}/drafts/evidence-preview"
    draft_request = {"title": "근거 인용 검토 원고", "body": "공개 문서의 핵심 사실을 설명합니다 [E1].", "expected_evidence_hash": evidence_hash}
    assert client.post(preview, headers=headers, json={**draft_request, "body": "인용 없음"}).status_code == 409
    assert client.post(preview, headers=headers, json={**draft_request, "expected_evidence_hash": "0" * 64}).status_code == 409
    draft_response = client.post(preview, headers=headers, json=draft_request)
    assert draft_response.status_code == 200, draft_response.text
    draft = draft_response.json()
    assert draft["status"] == "unapproved_draft"
    assert draft["evidence"][0]["source_quote"] == hits[1]["quote"]
    html = client.get(f"/api/jobs/{old_job['id']}/drafts/{draft['id']}/preview").text
    body, heading, sources = html.partition("출처와 확인 범위")
    assert heading and "공개 문서의 핵심 사실을 설명합니다 [E1]." in body
    assert f'<a href="{hits[1]["url"]}"' in sources
    assert client.post(preview, headers=headers, json=draft_request).json()["id"] == draft["id"]
    assert store.job(old_job["id"]) == job and len(store.drafts(old_job["id"])) == 1
    assert store.budget() == budget and not store.tasks()
    with store.connection() as db:
        assert db.execute("SELECT count(*) FROM approvals").fetchone()[0] == 0
        assert db.execute("SELECT count(*) FROM costs").fetchone()[0] == 0

    store.enqueue("draft", {"job_id": old_job["id"]}, key="fixture-queued")
    assert client.get("/api/ideas").json()["ideas"][0]["public_evidence_reviewable"] is False
    current = result["idea"]["edit_hash"]
    assert client.post(route, headers=headers, json={"expected_hash": current}).status_code == 409
    assert client.post(route + "/approve", headers=headers, json={**request, "expected_hash": current}).status_code == 409

@pytest.mark.parametrize("title,official_title,official_quote", [
    ("오픽 IM2에서 막힌 분을 위한 첫 7일", "OPIc 공식 등급", "OPIc IM2는 한국에서 제공되는 Intermediate Mid 세부 등급입니다."),
    ("편입 영어 단어 복습과 50% 쿠폰 캠페인", "2027학년도 일반편입 안내", "일반편입 원서접수의 해당 연도 일정과 편입 영어 전형 안내입니다."),
])
def test_noisy_saved_candidates_are_hidden_and_cannot_be_approved(scope, title, official_title, official_quote):
    store, client, headers, old, _, _ = scope
    idea = client.post("/api/ideas", headers=headers, json={
        "title": title, "source_url": "https://primary.example.org/notice", "primary_sources": 1,
    }).json()

    def hit(number, heading, quote):
        value = reference(number)
        value.update(title=heading, quote=quote, quote_sha256=hashlib.sha256(quote.encode()).hexdigest())
        value["id"] = evidence_id(value["url"], value["source_sha256"], number, value["quote_sha256"])
        return value

    wrong = [
        hit(4, "Agentic AI and SETI", "Radio telescopes identify extraterrestrial signals."),
        hit(5, official_title, "[28], [42], [43], [47], [72] Language Modeling WikiText-103 [147] [5], [29], [64], [71] StrategyQA [148]"),
        hit(6, official_title, "공공질서 및 미풍양속에 위반되는 내용을 유포하거나 링크시키는 경우 영리를 목적으로 하는 광고"),
    ]
    right = hit(7, official_title, official_quote)
    idea["public_evidence"] = [*wrong, right]
    with store.connection(transaction=True) as db:
        db.execute("UPDATE ideas SET data=? WHERE id=?", (json.dumps(idea), idea["id"]))
    visible = next(card for card in client.get("/api/ideas").json()["ideas"] if card["id"] == idea["id"])
    assert visible["public_evidence"] == [right]
    assert visible["edit_hash"] == digest(idea)
    path = f"/api/ideas/{idea['id']}/select"
    for ref in wrong:
        assert client.post(path, headers=headers, json={"expected_hash": visible["edit_hash"], "public_evidence_ids": [ref["id"]]}).status_code == 409
    assert client.post(path, headers=headers, json={"expected_hash": visible["edit_hash"], "public_evidence_ids": [right["id"]]}).status_code == 200
