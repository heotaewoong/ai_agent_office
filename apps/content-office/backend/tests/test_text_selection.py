"""Text (원고) model profile: Gemini or OpenAI, chosen explicitly; never auto-fallback."""
import pytest

from office.store import Store, WorkflowError


def test_default_profile_is_gemini_and_summary_reports_key_presence(tmp_path, monkeypatch):
    from office.text_selection import profile_summary, PROFILES
    monkeypatch.delenv("GEMINI_API_KEY", raising=False)
    monkeypatch.setenv("OPENAI_API_KEY", "x")
    store = Store(tmp_path)
    assert {"gemini-3.8-flash", "gemini-3.5-flash-lite", "gpt-5.4-mini", "gpt-5.5"} <= set(PROFILES)
    summary = profile_summary(store)
    assert summary["id"] == "gemini-3.8-flash" and summary["provider"] == "gemini" and summary["configured"] is False
    assert summary["paid"] is True and summary["automatic_fallback"] is False and summary["model"] == "gemini-3.8-flash"
    assert "GEMINI_API_KEY" in summary["key_source"]


def test_selecting_openai_profile_changes_the_model_the_provider_uses(tmp_path, monkeypatch):
    from office.text_selection import select_profile, profile_summary
    from office.providers import Provider
    monkeypatch.setenv("OPENAI_API_KEY", "x")
    store = Store(tmp_path)
    summary = select_profile(store, "gpt-5.4-mini", actor="local-operator-ui")
    assert summary["id"] == "gpt-5.4-mini" and summary["provider"] == "openai" and summary["configured"] is True
    assert "OPENAI_API_KEY" in summary["key_source"] and summary["price_usd_per_million"] == {"input": 0.75, "output": 4.5}
    assert store.setting("model") == "gpt-5.4-mini"
    assert Provider(store).model == "gpt-5.4-mini"
    assert any(e["kind"] == "text_profile_selected" and e["data"]["id"] == "gpt-5.4-mini" and e["data"]["paid_call_made"] is False for e in store.events(limit=3))
    assert profile_summary(store)["id"] == "gpt-5.4-mini"
    with pytest.raises(WorkflowError, match="프로필"):
        select_profile(store, "gpt-3", actor="local-operator-ui")
    with pytest.raises(WorkflowError):
        select_profile(store, "gpt-5.5", actor=" ")


def test_api_exposes_text_profile_and_accepts_choice(tmp_path, monkeypatch):
    from fastapi.testclient import TestClient
    from office.api import create_app
    monkeypatch.setenv("OPENAI_API_KEY", "x")
    store = Store(tmp_path)
    client = TestClient(create_app(store), base_url="http://localhost:8510")
    headers = {"Origin": "http://localhost:3110", "X-Office-CSRF": client.get("/api/session").json()["csrf"]}
    dashboard = client.get("/api/dashboard").json()
    assert dashboard["provider"]["text"]["id"] == "gemini-3.8-flash"
    chosen = client.post("/api/settings/profiles", json={"kind": "text", "profile": "gpt-5.4-mini"}, headers=headers)
    assert chosen.status_code == 200 and chosen.json()["text"]["id"] == "gpt-5.4-mini"
    assert client.get("/api/dashboard").json()["provider"]["model"] == "gpt-5.4-mini"
    assert client.post("/api/settings/profiles", json={"kind": "text", "profile": "nope"}, headers=headers).status_code in (409, 422)
