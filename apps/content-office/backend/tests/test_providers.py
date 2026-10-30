import json

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


def test_job_budget_blocks_model_before_transport_and_preserves_other_job_costs(tmp_path, monkeypatch):
    monkeypatch.setenv("GEMINI_API_KEY", "test-only-placeholder")
    store = Store(tmp_path)
    job_id = store.create_job({"id": "capped-provider", "title": "예산 시험"})["id"]
    current = store.get_job_budget(job_id)
    store.set_job_budget(job_id, 1000, "op", expected_hash=current["hash"])
    store.reserve_cost("speech_tts", 1000, {"job_id": job_id})
    calls = []
    provider = Provider(store, job_id=job_id, transport=lambda *a, **kw: calls.append(kw))
    with pytest.raises(WorkflowError, match="업무의 합산 예산"):
        provider.generate("eval", [{"role": "user", "content": "test"}], SCHEMA)
    assert calls == []
    assert store.get_job_budget(job_id)["reserved_krw"] == 1000


def test_job_attributed_model_cache_reuse_is_free_even_after_job_budget_is_full(tmp_path, monkeypatch):
    monkeypatch.setenv("GEMINI_API_KEY", "test-only-placeholder")
    store = Store(tmp_path)
    job_id = store.create_job({"id": "cached-provider", "title": "예산 시험"})["id"]
    current = store.get_job_budget(job_id)
    store.set_job_budget(job_id, 1000, "op", expected_hash=current["hash"])
    calls = []

    def transport(*args, **kwargs):
        calls.append(kwargs)
        return Response('{"passed":true}')

    provider = Provider(store, job_id=job_id, transport=transport)
    messages = [{"role": "user", "content": "cached test"}]
    result = provider.generate("eval", messages, SCHEMA)
    budget = store.get_job_budget(job_id)
    assert budget["spent_krw"] > 0 and len(calls) == 1
    with store.connection() as db:
        costs = [json.loads(row[0]) for row in db.execute("SELECT data FROM costs")]
    assert len(costs) == 1 and costs[0]["job_id"] == job_id
    store.reserve_cost("speech_tts", budget["remaining_krw"], {"job_id": job_id})
    full = store.get_job_budget(job_id)
    assert provider.generate("eval", messages, SCHEMA) == result
    assert store.get_job_budget(job_id) == full and len(calls) == 1
    assert {event["kind"] for event in store.events(job_id)} >= {"model_started", "model_completed", "model_cache_hit"}


def test_run_scope_checks_maximum_before_transport_but_reuses_cache_for_free(tmp_path, monkeypatch):
    from office.store import CostScopeExceeded
    monkeypatch.setenv("GEMINI_API_KEY", "test-only-placeholder")
    store = Store(tmp_path)
    calls = []

    def transport(*args, **kwargs):
        calls.append(kwargs)
        return Response('{"passed":true}')

    scope = {"id": "provider-run", "cap_krw": 1000}
    provider = Provider(store, transport=transport, cost_scope=scope)
    messages = [{"role": "user", "content": "cached scoped test"}]
    result = provider.generate("eval", messages, SCHEMA)
    remaining = store.cost_scope_budget(scope)["remaining_krw"]
    store.reserve_cost("synthetic-pending", remaining, {}, scope=scope)
    with pytest.raises(CostScopeExceeded):
        provider.generate("eval", [{"role": "user", "content": "different request"}], SCHEMA)
    assert len(calls) == 1 and provider.cost_scope_exhausted is True
    before = store.cost_scope_budget(scope)
    assert provider.generate("eval", messages, SCHEMA) == result
    assert store.cost_scope_budget(scope) == before and len(calls) == 1


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


class ErrorResponse:
    def __init__(self, status_code, body):
        self.status_code = status_code
        self._body = body

    def json(self):
        return self._body


def test_503_unavailable_is_settled_as_unbilled_and_retryable(tmp_path, monkeypatch):
    monkeypatch.setenv("GEMINI_API_KEY", "test-only-placeholder")
    store = Store(tmp_path)
    busy = ErrorResponse(503, {"error": {"code": 503, "status": "UNAVAILABLE", "message": "high demand"}})
    provider = Provider(store, transport=lambda *a, **kw: busy)
    with pytest.raises(WorkflowError, match="503") as info:
        provider.generate("card_ko", [{"role": "user", "content": "a"}], SCHEMA)
    assert "예약을 유지" not in str(info.value)
    assert store.budget()["reserved_krw"] == 0 and store.budget()["spent_krw"] == 0
    # 같은 호출을 다시 시도할 수 있다(결과 불명으로 막히지 않는다)
    with pytest.raises(WorkflowError, match="503"):
        provider.generate("card_ko", [{"role": "user", "content": "a"}], SCHEMA)


def test_other_5xx_keeps_reservation_unknown(tmp_path, monkeypatch):
    monkeypatch.setenv("GEMINI_API_KEY", "test-only-placeholder")
    store = Store(tmp_path)
    provider = Provider(store, transport=lambda *a, **kw: ErrorResponse(500, {"error": {"status": "INTERNAL"}}))
    with pytest.raises(WorkflowError, match="예약을 유지"):
        provider.generate("card_ko", [{"role": "user", "content": "b"}], SCHEMA)
    assert store.budget()["reserved_krw"] > 0


class OpenAIResponse:
    status_code = 200

    def __init__(self, text, usage=None):
        self.text = text
        self.usage = usage or {"prompt_tokens": 100, "completion_tokens": 50, "completion_tokens_details": {"reasoning_tokens": 20}}

    def json(self):
        return {"id": "chatcmpl-test", "choices": [{"message": {"content": self.text}, "finish_reason": "stop"}], "usage": self.usage}


def test_openai_model_uses_chat_completions_with_schema_and_settles_real_usage(tmp_path, monkeypatch):
    monkeypatch.setenv("OPENAI_API_KEY", "test-only-placeholder")
    monkeypatch.delenv("GEMINI_API_KEY", raising=False)
    store = Store(tmp_path)
    calls = []

    def transport(url, **kwargs):
        calls.append((url, kwargs))
        return OpenAIResponse('{"passed":true}')
    provider = Provider(store, model="gpt-5.4-mini", transport=transport)
    result = provider.generate("gen", [{"role": "system", "content": "SYS"}, {"role": "user", "content": "hi"}], SCHEMA)
    assert result == {"passed": True}
    url, kwargs = calls[0]
    assert url == "https://api.openai.com/v1/chat/completions"
    assert kwargs["headers"]["Authorization"] == "Bearer test-only-placeholder"
    body = kwargs["json"]
    assert body["model"] == "gpt-5.4-mini" and body["messages"][0] == {"role": "system", "content": "SYS"}
    assert body["response_format"]["type"] == "json_schema" and body["response_format"]["json_schema"]["schema"] == SCHEMA
    assert body["max_completion_tokens"] == 8192 and "temperature" not in body and body["reasoning_effort"] == "low"
    expected = (100 * 0.75 + 50 * 4.5) / 1_000_000 * 2000
    assert store.budget()["spent_krw"] > 0 and store.budget()["reserved_krw"] == 0
    done = next(e for e in store.events(limit=5) if e["kind"] == "model_completed")
    assert done["data"]["model"] == "gpt-5.4-mini" and done["data"]["provider"] == "openai" and done["data"]["output_tokens"] == 50
    assert abs(done["data"]["estimated_krw"] - expected) < 0.01
    provider.generate("gen", [{"role": "system", "content": "SYS"}, {"role": "user", "content": "hi"}], SCHEMA)
    assert len(calls) == 1


def test_openai_model_requires_openai_key_not_gemini(tmp_path, monkeypatch):
    monkeypatch.setenv("GEMINI_API_KEY", "test-only-placeholder")
    monkeypatch.delenv("OPENAI_API_KEY", raising=False)
    provider = Provider(Store(tmp_path), model="gpt-5.5", transport=lambda *a, **kw: OpenAIResponse('{"passed":true}'))
    with pytest.raises(WorkflowError, match="OpenAI"):
        provider.generate("gen", [{"role": "user", "content": "hi"}], SCHEMA)


def test_openai_4xx_is_settled_unbilled_and_5xx_keeps_reservation(tmp_path, monkeypatch):
    monkeypatch.setenv("OPENAI_API_KEY", "test-only-placeholder")
    store = Store(tmp_path)
    provider = Provider(store, model="gpt-5.4-mini", transport=lambda *a, **kw: ErrorResponse(429, {"error": {"type": "rate_limit_error", "message": "slow down"}}))
    with pytest.raises(WorkflowError, match="429"):
        provider.generate("gen", [{"role": "user", "content": "a"}], SCHEMA)
    assert store.budget()["reserved_krw"] == 0 and store.budget()["spent_krw"] == 0
    provider = Provider(store, model="gpt-5.4-mini", transport=lambda *a, **kw: ErrorResponse(502, {"error": {"type": "server_error"}}))
    with pytest.raises(WorkflowError, match="예약을 유지"):
        provider.generate("gen", [{"role": "user", "content": "b"}], SCHEMA)
    assert store.budget()["reserved_krw"] > 0


def test_openai_usage_missing_keeps_reservation(tmp_path, monkeypatch):
    monkeypatch.setenv("OPENAI_API_KEY", "test-only-placeholder")
    store = Store(tmp_path)
    provider = Provider(store, model="gpt-5.4-mini", transport=lambda *a, **kw: OpenAIResponse('{"passed":true}', usage={"prompt_tokens": "x"}))
    with pytest.raises(WorkflowError, match="사용량"):
        provider.generate("gen", [{"role": "user", "content": "c"}], SCHEMA)
    assert store.budget()["reserved_krw"] > 0


def test_openai_request_spells_out_array_counts_and_enums_the_json_schema_mode_ignores(tmp_path, monkeypatch):
    from office.providers import schema_constraints
    monkeypatch.setenv("OPENAI_API_KEY", "test-only-placeholder")
    schema = {"type": "object", "properties": {"title": {"type": "string", "maxLength": 45}, "video": {"type": "object", "properties": {"thumbnails": {"type": "array", "minItems": 5, "maxItems": 5, "items": {"type": "object"}}, "scenes": {"type": "array", "minItems": 3, "items": {"type": "object"}}, "kind": {"type": "string", "enum": ["long", "short"]}}}, "corrections": {"type": "array", "maxItems": 40, "items": {"type": "string"}}}, "required": ["title"]}
    lines = schema_constraints(schema)
    assert any("video.thumbnails" in l and "정확히 5개" in l for l in lines)
    assert any("video.scenes" in l and "3개 이상" in l for l in lines)
    assert any("corrections" in l and "40개 이하" in l for l in lines)
    assert any("video.kind" in l and "long" in l and "short" in l for l in lines)
    assert any("title" in l and "45자 이하" in l for l in lines)
    calls = []

    def transport(url, **kwargs):
        calls.append(kwargs["json"])
        return OpenAIResponse('{"title":"t"}')
    Provider(Store(tmp_path), model="gpt-5.4-mini", transport=transport).generate("gen", [{"role": "system", "content": "SYS"}, {"role": "user", "content": "hi"}], schema)
    systems = [m["content"] for m in calls[0]["messages"] if m["role"] == "system"]
    assert systems[0] == "SYS" and any("정확히 5개" in s and "thumbnails" in s for s in systems)
    assert calls[0]["messages"][-1]["role"] == "user"


def test_openai_truncated_output_says_so(tmp_path, monkeypatch):
    monkeypatch.setenv("OPENAI_API_KEY", "test-only-placeholder")

    class Cut(OpenAIResponse):
        def json(self):
            data = super().json()
            data["choices"][0]["finish_reason"] = "length"
            return data
    store = Store(tmp_path)
    with pytest.raises(WorkflowError, match="길이 제한"):
        Provider(store, model="gpt-5.4-mini", transport=lambda *a, **kw: Cut('{"passed":tr')).generate("gen", [{"role": "user", "content": "x"}], SCHEMA)
    assert store.budget()["spent_krw"] > 0 and store.budget()["reserved_krw"] == 0
