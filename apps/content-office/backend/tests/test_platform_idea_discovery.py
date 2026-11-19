from datetime import datetime, timezone
from types import SimpleNamespace
import sys

from fastapi.testclient import TestClient

from office.api import create_app
from office.store import Store, digest
from office.benchmarks import DEFAULT as BENCHMARK_DEFAULT
from test_public_evidence_workflow import reference


def test_platform_save_resolves_observation_and_researches_before_approval(tmp_path, monkeypatch):
    store = Store(tmp_path)
    stamped = datetime.now(timezone.utc).isoformat()
    item_url = "https://www.instagram.com/example/p/QWERTy12345/"
    title = "AI agent workflow with MoneyPrinterTurbo"
    store.set_setting("benchmark_snapshot", {"registry_hash": digest(BENCHMARK_DEFAULT), "items": [
        {"id": "platform-example", "title": title, "platform": "instagram", "url": item_url,
         "summary": "MoneyPrinterTurbo project demo", "source_id": "every-ai-instagram",
         "checked_at": stamped, "published_at": stamped, "metrics": {
             "likes": {"value": 9, "availability": "observed", "precision": "exact"}}},
    ]})
    monkeypatch.setenv("HEOBRAIN_PLATFORM_NEWS_SOURCES_DB", str(tmp_path / "missing.db"))
    evidence = reference(3)
    calls = []
    def discover(query, *, seed_urls, context, limit):
        calls.append((query, tuple(seed_urls), context, limit))
        if len(calls) == 1:
            return {"status": "unavailable", "references": [], "claims": []}
        return {"status": "ready", "references": [evidence],
                "claims": [{"label": "확인할 주요 기능", "evidence_ids": [evidence["id"]]}]}
    monkeypatch.setitem(sys.modules, "office.public_discovery", SimpleNamespace(discover_public_evidence=discover))
    client = TestClient(create_app(store), base_url="http://localhost:8510")
    headers = {"Origin": "http://localhost:3110", "X-Office-CSRF": client.get("/api/session").json()["csrf"]}
    board = client.get("/api/platform-news").json()
    route = "/api/platform-news/ideas"
    payload = {"platform": "instagram", "url": item_url, "expected_hash": board.get("snapshot_hash", "0" * 64)}
    assert client.post(route, json=payload).status_code == 403
    assert client.post(route, headers=headers, json={**payload, "expected_hash": "f" * 64}).status_code == 409
    assert client.post(route, headers=headers, json={**payload, "url": "https://www.instagram.com/p/Unlisted/"}).status_code == 409
    assert not calls and not store.ideas()

    budget = store.budget()
    busy = client.post(route, headers=headers, json=payload).json()["idea"]
    assert busy["state"] == "candidate" and busy["public_discovery"]["status"] == "unavailable"
    assert "public_discovery" not in store.ideas()[0]
    response = client.post(route, headers=headers, json=payload)
    assert response.status_code == 200, response.text
    saved = response.json()["idea"]
    assert saved["state"] == "candidate" and saved["primary_sources"] == 0
    assert saved["platform_origin"]["url"] == item_url
    assert saved["public_evidence"] == [evidence]
    assert saved["public_discovery"]["claims"] == [{"label": "확인할 주요 기능", "evidence_ids": [evidence["id"]]}]
    assert saved["public_discovery"]["paid_calls"] == 0
    assert saved["id"] == busy["id"]
    assert calls == [(title, (item_url,), "MoneyPrinterTurbo project demo", 4)] * 2
    assert client.post(route, headers=headers, json=payload).json()["idea"] == saved
    assert len(calls) == 2 and len(store.ideas()) == 1
    assert not store.jobs() and not store.tasks() and store.budget() == budget
    with store.connection() as db:
        assert db.execute("SELECT count(*) FROM approvals").fetchone()[0] == 0
        assert db.execute("SELECT count(*) FROM costs").fetchone()[0] == 0
    idea_route = "/api/ideas/" + saved["id"]
    approve = {"expected_hash": saved["edit_hash"], "public_evidence_ids": [evidence["id"]]}
    assert client.post(idea_route + "/select", headers=headers, json=approve).status_code == 409
    response = client.put(idea_route + "/sources", headers=headers, json={
        "expected_hash": saved["edit_hash"], "source_urls": [evidence["url"]], "operator_verified": True,
    })
    assert response.status_code == 200, response.text
    reviewed = response.json()
    assert "public_discovery" not in reviewed and "public_evidence" not in reviewed
    assert client.post(idea_route + "/select", headers=headers, json=approve).status_code == 409
    refreshed = client.post(idea_route + "/public-evidence", headers=headers,
                            json={"expected_hash": reviewed["edit_hash"]}).json()
    approved = client.post(idea_route + "/select", headers=headers, json={
        "expected_hash": refreshed["edit_hash"], "public_evidence_ids": [evidence["id"]],
    })
    assert approved.status_code == 200, approved.text
    assert approved.json()["job"]["article"]["approved_public_evidence"] == [evidence]
    prior = store.ideas()[0]
    assert client.post(route, headers=headers, json=payload).json()["idea"]["state"] == "selected"
    assert store.ideas()[0] == prior and len(calls) == 3 and not store.tasks() and store.budget() == budget
