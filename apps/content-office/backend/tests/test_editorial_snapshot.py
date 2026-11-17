"""A final source save must preserve edits made after the last replay guard."""
import copy
import socket
import subprocess

import pytest
import requests

from office import editorial
from office.packaging import attach_packaging
from office.store import Store, WorkflowError
from tests.test_agent_editorial import FullProvider, brief, evidence_job


@pytest.fixture(autouse=True)
def no_external_io(monkeypatch):
    def forbidden(*args, **kwargs):
        raise AssertionError("External I/O is forbidden in snapshot tests")
    monkeypatch.setattr(socket.socket, "connect", forbidden)
    monkeypatch.setattr(socket.socket, "connect_ex", forbidden)
    monkeypatch.setattr(requests.sessions.Session, "request", forbidden)
    monkeypatch.setattr(subprocess, "run", forbidden)


@pytest.mark.parametrize("change", ["packaging", "approval"])
def test_edit_during_final_gates_cannot_be_overwritten_by_source_save(tmp_path, monkeypatch, change):
    store = Store(tmp_path)
    job = evidence_job(store)
    attach_packaging(store, job["id"], brief(), "initial-operator")
    old_packet = FullProvider("AI 도구 비교")._packet()
    old_packet.update(evidence=job["article"]["evidence"], quality={"status": "passed", "critical": False})
    before = store.save_source(job["id"], old_packet)
    gates = editorial.run_gates
    changed = {}

    def concurrent_edit(*args, **kwargs):
        report = gates(*args, **kwargs)
        if change == "packaging":
            updated = brief()
            updated["logline"] = "운영자가 최종 저장 직전에 새로 선택한 기획"
            changed["packaging"] = attach_packaging(store, job["id"], updated, "concurrent-operator")
        else:
            updated = store.review_source(job["id"], before["source_hash"], "approved", "concurrent-operator",
                                          {"blog": True, "video": False, "pdf": False, "cards": False})
            changed["source_approval"] = copy.deepcopy(updated["source_approval"])
            changed["selections"] = copy.deepcopy(updated["selections"])
        return report

    monkeypatch.setattr(editorial, "run_gates", concurrent_edit)
    with pytest.raises(WorkflowError, match="변경|판본|맥락"):
        editorial.prepare_source(store, job["id"], provider=FullProvider("AI 도구 비교"), engine="langgraph")
    current = store.job(job["id"])
    assert current["source_hash"] == before["source_hash"]
    assert current["source_packet"] == before["source_packet"]
    for key, value in changed.items():
        assert current[key] == value
    assert not any(event["kind"] == "source_review_requested" for event in store.events(job["id"]))


def test_worker_stale_editorial_failure_preserves_new_human_approval(tmp_path, monkeypatch):
    from office.worker import run_once
    store = Store(tmp_path)
    job = evidence_job(store)
    old_packet = FullProvider("AI 도구 비교")._packet()
    old_packet.update(evidence=job["article"]["evidence"], quality={"status": "passed", "critical": False})
    before = store.save_source(job["id"], old_packet)
    task = store.enqueue("draft", {"job_id": job["id"], "source_hash": before["source_hash"]}, "snapshot-worker-test")
    monkeypatch.setattr(editorial, "Provider", lambda *args, **kwargs: FullProvider("AI 도구 비교"))
    gates = editorial.run_gates
    changed = {}

    def concurrent_approval(*args, **kwargs):
        report = gates(*args, **kwargs)
        approved = store.review_source(job["id"], before["source_hash"], "approved", "concurrent-operator",
                                       {"blog": True, "video": False, "pdf": False, "cards": False})
        changed["source_approval"] = copy.deepcopy(approved["source_approval"])
        changed["selections"] = copy.deepcopy(approved["selections"])
        return report

    monkeypatch.setattr(editorial, "run_gates", concurrent_approval)
    assert run_once(store, "snapshot-test-worker") is True
    current = store.job(job["id"])
    assert current["state"] == "source_approved"
    assert current["source_hash"] == before["source_hash"]
    assert current["source_packet"] == before["source_packet"]
    assert current["source_approval"] == changed["source_approval"]
    assert current["selections"] == changed["selections"]
    assert current["error"] is None
    result = store.task(task["id"])
    assert result["state"] == "failed"
    assert result["result"]["automatic_retry"] is False


def test_worker_approval_between_start_guard_and_state_transition_is_preserved(tmp_path, monkeypatch):
    from office import editorial_graph
    from office.worker import run_once
    store = Store(tmp_path)
    job = evidence_job(store)
    old_packet = FullProvider("AI 도구 비교")._packet()
    old_packet.update(evidence=job["article"]["evidence"], quality={"status": "passed", "critical": False})
    before = store.save_source(job["id"], old_packet)
    task = store.enqueue("draft", {"job_id": job["id"], "source_hash": before["source_hash"]}, "start-state-race")
    provider = FullProvider("AI 도구 비교")
    monkeypatch.setattr(editorial, "Provider", lambda *args, **kwargs: provider)
    snapshot = editorial_graph.editorial_snapshot
    approved = {}

    def concurrent_approval(*args, **kwargs):
        captured = snapshot(*args, **kwargs)
        # The initial job snapshot is explicit. Inject after the subsequent guard
        # has read its snapshot but before prepare_source changes the job state.
        if kwargs.get("job") is None and not approved:
            current = store.review_source(job["id"], before["source_hash"], "approved", "concurrent-operator",
                                          {"blog": True, "video": False, "pdf": False, "cards": False})
            approved.update(source_approval=copy.deepcopy(current["source_approval"]),
                            selections=copy.deepcopy(current["selections"]))
        return captured

    monkeypatch.setattr(editorial_graph, "editorial_snapshot", concurrent_approval)
    assert run_once(store, "start-race-worker") is True
    current = store.job(job["id"])
    assert approved
    assert current["state"] == "source_approved"
    assert current["source_hash"] == before["source_hash"]
    assert current["source_packet"] == before["source_packet"]
    assert current["source_approval"] == approved["source_approval"]
    assert current["selections"] == approved["selections"]
    assert current["error"] is None
    assert provider.roles == []
    result = store.task(task["id"])
    assert result["state"] == "failed"
    assert result["result"]["automatic_retry"] is False


def test_model_change_during_final_gates_rejects_stale_source_save(tmp_path, monkeypatch):
    store = Store(tmp_path)
    store.set_setting("model", "gpt-5.4-mini")
    job = evidence_job(store)
    old_packet = FullProvider("AI 도구 비교")._packet()
    old_packet.update(evidence=job["article"]["evidence"], quality={"status": "passed", "critical": False})
    before = store.save_source(job["id"], old_packet)
    gates = editorial.run_gates

    def concurrent_model_change(*args, **kwargs):
        report = gates(*args, **kwargs)
        store.set_setting("model", "gpt-5.5")
        return report

    monkeypatch.setattr(editorial, "run_gates", concurrent_model_change)
    with pytest.raises(WorkflowError, match="변경|판본|모델"):
        editorial.prepare_source(store, job["id"], provider=FullProvider("AI 도구 비교"), engine="langgraph")
    current = store.job(job["id"])
    assert store.setting("model") == "gpt-5.5"
    assert current["source_hash"] == before["source_hash"]
    assert current["source_packet"] == before["source_packet"]
    assert not any(event["kind"] == "source_review_requested" for event in store.events(job["id"]))
