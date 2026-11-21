"""Dispatch evidence must not turn an uncertain paid call into a safe replay."""
from datetime import datetime, timedelta, timezone
import json
import socket
import subprocess

import pytest
import requests

from office.providers import Provider
from office.store import CostScopeExceeded, Store, WorkflowError

SCHEMA = {"type": "object", "properties": {"passed": {"type": "boolean"}}, "required": ["passed"], "additionalProperties": False}
MESSAGES = [{"role": "user", "content": "synthetic dispatch-boundary test"}]


def forbidden(*args, **kwargs):
    raise AssertionError("External I/O is forbidden in dispatch tests")


@pytest.fixture(autouse=True)
def isolated_dispatch(monkeypatch):
    monkeypatch.setattr(socket.socket, "connect", forbidden)
    monkeypatch.setattr(socket.socket, "connect_ex", forbidden)
    monkeypatch.setattr(requests.sessions.Session, "request", forbidden)
    monkeypatch.setattr(subprocess, "run", forbidden)
    monkeypatch.setenv("GEMINI_API_KEY", "test-only-placeholder")
    monkeypatch.setenv("OPENAI_API_KEY", "test-only-placeholder")


@pytest.fixture
def store(tmp_path):
    result = Store(tmp_path)
    result.set_setting("price_valid_until", (datetime.now(timezone.utc) + timedelta(days=1)).isoformat())
    return result


class Response:
    def __init__(self, data=None, status=200):
        self.status_code = status
        self.data = data if data is not None else {
            "usageMetadata": {"promptTokenCount": 10, "candidatesTokenCount": 3},
            "candidates": [{"content": {"parts": [{"text": '{"passed":true}'}]}}],
        }

    def json(self):
        return self.data


@pytest.mark.parametrize("reason", ["unsupported_model", "expired_price", "expired_window", "missing_gemini_key", "missing_openai_key"])
def test_explicit_preflight_rejection_proves_no_dispatch(store, monkeypatch, reason):
    model = "gemini-3.8-flash"
    if reason == "unsupported_model":
        model = "unpriced-test-model"
    elif reason == "expired_price":
        store.set_setting("price_valid_until", "2020-01-01T00:00:00+00:00")
    elif reason == "expired_window":
        store.set_setting("work_window", {"authorized_end": "2020-01-01T00:00:00+00:00"})
    elif reason == "missing_gemini_key":
        monkeypatch.delenv("GEMINI_API_KEY")
    else:
        model = "gpt-5.4-mini"
        monkeypatch.delenv("OPENAI_API_KEY")
    before = store.budget()
    with pytest.raises(WorkflowError) as caught:
        Provider(store, model=model, transport=forbidden).generate("gen", MESSAGES, SCHEMA)
    assert getattr(caught.value, "provider_not_dispatched", False) is True
    assert store.budget() == before


@pytest.mark.parametrize("boundary", ["global", "job", "scope"])
def test_budget_rejection_preserves_costs_and_original_exception_contract(store, boundary):
    job_id = store.create_job({"id": "dispatch-test-job", "title": "Synthetic budget"})["id"]
    scope = None
    if boundary == "global":
        store.set_setting("budget_cap", 0)
    elif boundary == "job":
        current = store.get_job_budget(job_id)
        store.set_job_budget(job_id, 1000, "test", expected_hash=current["hash"])
        store.reserve_cost("other-call", 1000, {"job_id": job_id})
    else:
        scope = {"id": "dispatch-test-scope", "cap_krw": 1}
    before = store.budget()
    provider = Provider(store, model="gemini-3.8-flash", transport=forbidden, job_id=job_id, cost_scope=scope)
    with pytest.raises(CostScopeExceeded if boundary == "scope" else WorkflowError) as caught:
        provider.generate("gen", MESSAGES, SCHEMA)
    assert getattr(caught.value, "provider_not_dispatched", False) is True
    assert provider.cost_scope_exhausted is (boundary == "scope")
    assert store.budget() == before


@pytest.mark.parametrize("pending_state", ["reserved", "unknown"])
def test_current_not_sent_never_releases_an_earlier_uncertain_reservation(store, pending_state):
    def lost(*args, **kwargs):
        raise requests.Timeout("synthetic lost response")
    provider = Provider(store, model="gemini-3.8-flash", transport=lost)
    with pytest.raises(WorkflowError) as original:
        provider.generate("gen", MESSAGES, SCHEMA)
    assert getattr(original.value, "provider_not_dispatched", False) is False
    with store.connection() as db:
        db.execute("UPDATE costs SET state=?", (pending_state,))
        before = [tuple(row) for row in db.execute("SELECT * FROM costs")]
    provider.transport = forbidden
    with pytest.raises(WorkflowError) as retry:
        provider.generate("gen", MESSAGES, SCHEMA)
    assert getattr(retry.value, "provider_not_dispatched", False) is True
    with store.connection() as db:
        assert [tuple(row) for row in db.execute("SELECT * FROM costs")] == before


def test_cached_success_stays_free_when_price_time_and_budget_close(store):
    provider = Provider(store, model="gemini-3.8-flash", transport=lambda *a, **k: Response())
    assert provider.generate("gen", MESSAGES, SCHEMA) == {"passed": True}
    store.set_setting("price_valid_until", "2020-01-01T00:00:00+00:00")
    store.set_setting("work_window", {"authorized_end": "2020-01-01T00:00:00+00:00"})
    store.set_setting("budget_cap", 0)
    before = store.budget()
    provider.transport = forbidden
    assert provider.generate("gen", MESSAGES, SCHEMA) == {"passed": True}
    assert store.budget() == before


def test_invalid_existing_cache_is_not_a_new_dispatch(store):
    provider = Provider(store, model="gemini-3.8-flash", transport=lambda *a, **k: Response())
    provider.generate("gen", MESSAGES, SCHEMA)
    with store.connection() as db:
        db.execute("UPDATE cache SET data=?", (json.dumps({"passed": "invalid"}),))
    before = store.budget()
    provider.transport = forbidden
    with pytest.raises(WorkflowError) as caught:
        provider.generate("gen", MESSAGES, SCHEMA)
    assert getattr(caught.value, "provider_not_dispatched", False) is True
    assert store.budget() == before


@pytest.mark.parametrize("failure, expected_state", [
    ("timeout", "unknown"), ("server", "unknown"), ("usage", "unknown"),
    ("schema", "settled"), ("json", "settled"), ("rejected", "settled"),
])
def test_errors_after_transport_never_claim_request_was_not_sent(store, failure, expected_state):
    def transport(*args, **kwargs):
        if failure == "timeout":
            raise requests.Timeout("synthetic timeout")
        if failure == "server":
            return Response(status=500)
        if failure == "rejected":
            return Response(status=400)
        if failure == "usage":
            return Response(data={})
        result = Response()
        result.data["candidates"][0]["content"]["parts"][0]["text"] = '{"passed":"invalid"}' if failure == "schema" else '{'
        return result
    with pytest.raises(WorkflowError) as caught:
        Provider(store, model="gemini-3.8-flash", transport=transport).generate("gen", MESSAGES, SCHEMA)
    assert getattr(caught.value, "provider_not_dispatched", False) is False
    with store.connection() as db:
        assert [row[0] for row in db.execute("SELECT state FROM costs")] == [expected_state]
        assert db.execute("SELECT COUNT(*) FROM cache").fetchone()[0] == 0


def test_reservation_then_event_failure_is_conservatively_unmarked(store, monkeypatch):
    def broken_event(*args, **kwargs):
        raise WorkflowError("synthetic journal failure")
    monkeypatch.setattr(store, "event", broken_event)
    with pytest.raises(WorkflowError) as caught:
        Provider(store, model="gemini-3.8-flash", transport=forbidden).generate("gen", MESSAGES, SCHEMA)
    assert getattr(caught.value, "provider_not_dispatched", False) is False
    assert store.budget()["reserved_krw"] > 0


def test_subscription_policy_rejection_is_marked_before_adapter_execution(store):
    store.set_setting("content_api_only", True)
    with pytest.raises(WorkflowError) as caught:
        Provider(store, model="codex-subscription-text").generate("gen", MESSAGES, SCHEMA)
    assert getattr(caught.value, "provider_not_dispatched", False) is True
    assert store.budget()["reserved_krw"] == 0


def test_subscription_adapter_failure_is_not_assumed_to_be_pre_dispatch(store, monkeypatch):
    from office import codex_text_provider
    failure = WorkflowError("synthetic subscription outcome unknown")
    def unknown(*args, **kwargs):
        raise failure
    monkeypatch.setattr(codex_text_provider, "generate", unknown)
    with pytest.raises(WorkflowError) as caught:
        Provider(store, model="codex-subscription-text").generate("gen", MESSAGES, SCHEMA)
    assert caught.value is failure
    assert getattr(caught.value, "provider_not_dispatched", False) is False
