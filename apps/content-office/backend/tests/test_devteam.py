import json

import pytest
from fastapi.testclient import TestClient

from office.api import create_app
from office.devteam import dev_status, set_switch
from office.store import Store


@pytest.fixture
def context(tmp_path):
    store = Store(tmp_path)
    client = TestClient(create_app(store), base_url="http://localhost:8510")
    token = client.get("/api/session").json()["csrf"]
    return store, client, {"Origin": "http://localhost:3110", "X-Office-CSRF": token}


def write(path, value):
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(value), encoding="utf-8")


def test_fresh_install_is_off_and_watcher_not_installed(tmp_path):
    status = dev_status(tmp_path)
    assert status["enabled"] is False and status["watcher_installed"] is False and status["deployments"] == []


def test_status_reads_watcher_build_and_recent_deployments(tmp_path):
    runtime = tmp_path / "runtime"
    write(runtime / "build-info.json", {"commit": "a" * 40, "deployed_at": "2026-10-30T05:00:00+00:00", "tests": {"ci": {"source": "github-actions"}}})
    write(runtime / "auto-deploy.json", {"checked_at": "t", "decision": "waiting_ci", "reason": "진행 중", "origin": "b" * 40, "deployed": "a" * 40, "ci": {"state": "pending", "url": "https://github.com/o/r/runs/1"}, "history": [{"at": "t", "origin": "b" * 40, "decision": "waiting_ci", "reason": "진행 중"}]})
    write(runtime / "deployments" / "20261030T050000Z-1" / "deployment.json", {"status": "deployed", "target": "a" * 40, "ci": {"source": "github-actions"}})
    write(runtime / "deployments" / "20261030T040000Z-2" / "deployment.json", {"status": "checks_failed", "target": "c" * 40})
    status = dev_status(tmp_path)
    assert status["running"] == {"commit": "a" * 10, "deployed_at": "2026-10-30T05:00:00+00:00", "ci_verified": True}
    assert status["watcher"]["label"] == "GitHub 검증 기다림" and status["watcher"]["ci"]["state"] == "pending"
    assert [d["status"] for d in status["deployments"]] == ["deployed", "checks_failed"]
    assert status["deployments"][0]["ci_verified"] is True and status["deployments"][1]["label"] == "빌드 실패"


def test_switch_api_requires_operator_session_and_records_event(context):
    store, client, headers = context
    assert client.post("/api/dev/auto-deploy", json={"enabled": True}, headers={"Origin": "http://localhost:3110"}).status_code == 403
    assert client.post("/api/dev/auto-deploy", json={"enabled": True, "extra": 1}, headers=headers).status_code == 422
    response = client.post("/api/dev/auto-deploy", json={"enabled": True}, headers=headers)
    assert response.status_code == 200 and response.json()["enabled"] is True
    assert client.get("/api/dev").json()["enabled"] is True
    assert any(e["kind"] == "auto_deploy_switch" for e in store.events(limit=5))
    client.post("/api/dev/auto-deploy", json={"enabled": False}, headers=headers)
    assert dev_status(store.root)["enabled"] is False


def test_space_projection_carries_dev_team_state(context):
    store, client, _ = context
    set_switch(store.root, True)
    dev = client.get("/api/space").json()["dev"]
    assert dev["version"] == 1 and dev["enabled"] is True
