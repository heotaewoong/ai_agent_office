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