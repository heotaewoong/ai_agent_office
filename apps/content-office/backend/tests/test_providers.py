import requests
import pytest
from office.providers import Provider
from office.store import Store, WorkflowError


class Response:
    status_code = 200
    def __init__(self, text):
        self.text = text
    def json(self):
        return {"usageMetadata": {"promptTokenCount": 10, "candidatesTokenCount": 3}, "candidates": [{"content": {"parts": [{"text": self.text}]}}]}


SCHEMA = {"type": "object", "properties": {"passed": {"type": "boolean"}}, "required": ["passed"], "additionalProperties": False}


def test_schema_invalid_model_result_is_not_cached_as_success(tmp_path, monkeypatch):
    monkeypatch.setenv("GEMINI_API_KEY", "test-only-placeholder")
    store = Store(tmp_path)
    provider = Provider(store, transport=lambda *a, **kw: Response('{"passed":"false"}'))
    with pytest.raises(WorkflowError, match="형식|schema"):
        provider.generate("eval", [{"role": "user", "content": "test"}], SCHEMA)
    with store.connection() as db:
        assert db.execute("SELECT COUNT(*) FROM cache").fetchone()[0] == 0
    assert store.budget()["spent_krw"] > 0


def test_schema_valid_cache_reuse_does_not_reserve_or_spend_again(tmp_path, monkeypatch):
    monkeypatch.setenv("GEMINI_API_KEY", "test-only-placeholder")
    store = Store(tmp_path)
    provider = Provider(store, transport=lambda *a, **kw: Response('{"passed":true}'))
    first = provider.generate("eval", [{"role": "user", "content": "test"}], SCHEMA)
    budget = store.budget()
    second = provider.generate("eval", [{"role": "user", "content": "test"}], SCHEMA)
    assert first == second == {"passed": True}
    assert store.budget() == budget


def test_lost_response_preserves_reservation_and_never_marks_success(tmp_path, monkeypatch):
    monkeypatch.setenv("GEMINI_API_KEY", "test-only-placeholder")
    store = Store(tmp_path)
    def lost(*args, **kwargs):
        raise requests.ConnectionError("transport broke")
    provider = Provider(store, transport=lost)
    with pytest.raises(WorkflowError, match="予約|예약"):
        provider.generate("gen", [{"role": "user", "content": "test"}], SCHEMA)
    assert store.budget()["reserved_krw"] > 0
    assert store.budget()["spent_krw"] == 0


def test_verified_price_expiry_blocks_new_paid_calls(tmp_path, monkeypatch):
    monkeypatch.setenv("GEMINI_API_KEY", "test-only-placeholder")
    store = Store(tmp_path)
    provider = Provider(store, transport=lambda *a, **kw: Response('{"passed":true}'))
    store.set_setting("price_valid_until", "2026-01-01T00:00:00+00:00")
    with pytest.raises(WorkflowError, match="단가|요금"):
        provider.generate("eval", [{"role": "user", "content": "test"}], SCHEMA)
    assert store.budget()["spent_krw"] == 0


def test_missing_output_usage_does_not_release_open_reservation(tmp_path, monkeypatch):
    monkeypatch.setenv("GEMINI_API_KEY", "test-only-placeholder")
    store = Store(tmp_path)
    class MissingUsage(Response):
        def json(self):
            data = super().json()
            del data["usageMetadata"]["candidatesTokenCount"]
            return data
    provider = Provider(store, transport=lambda *a, **kw: MissingUsage('{"passed":true}'))
    with pytest.raises(WorkflowError, match="使用|사용량|예약"):
        provider.generate("eval", [{"role": "user", "content": "test"}], SCHEMA)
    assert store.budget()["reserved_krw"] > 0


@pytest.mark.parametrize('field,value', [('promptTokenCount', 3.5), ('candidatesTokenCount', True), ('candidatesTokenCount', '3'), ('thoughtsTokenCount', -1)])
def test_invalid_usage_counter_types_keep_reservation(tmp_path, monkeypatch, field, value):
    monkeypatch.setenv('GEMINI_API_KEY', 'test-only-placeholder')
    store = Store(tmp_path)
    class InvalidCounter(Response):
        def json(self):
            data = super().json()
            data['usageMetadata'][field] = value
            return data
    provider = Provider(store, transport=lambda *a, **kw: InvalidCounter('{"passed":true}'))
    with pytest.raises(WorkflowError, match='사용량|예약'):
        provider.generate('eval', [{'role': 'user', 'content': 'test'}], SCHEMA)
    assert store.budget()['reserved_krw'] > 0
    assert store.budget()['spent_krw'] == 0
