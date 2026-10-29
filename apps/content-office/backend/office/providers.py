"""Explicit, budgeted provider calls. No paid fallback and no implicit SDK retries.

The text model is one explicit choice (text_selection.PROFILES): a Gemini model or an OpenAI model.
Both paths share the same cache, reservation, settlement and schema checks; nothing switches
providers on its own when one of them fails.
"""
from __future__ import annotations

import json
import os
from datetime import datetime, timezone

import requests
from jsonschema import Draft202012Validator, ValidationError

from .store import Store, WorkflowError, canonical, digest

PRICES = {
    "gemini-3.8-flash": {"input_usd_million": 0.75, "output_usd_million": 3.75},
    "gemini-3.5-flash-lite": {"input_usd_million": 0.30, "output_usd_million": 2.50},
}
PRICE_SOURCE = "https://ai.google.dev/gemini-api/docs/pricing"
OPENAI_PRICES = {
    "gpt-5.5": {"input_usd_million": 5.00, "output_usd_million": 30.00},
    "gpt-5.4": {"input_usd_million": 2.50, "output_usd_million": 15.00},
    "gpt-5.4-mini": {"input_usd_million": 0.75, "output_usd_million": 4.50},
    "gpt-5.4-nano": {"input_usd_million": 0.20, "output_usd_million": 1.25},
}
OPENAI_PRICE_SOURCE = "https://developers.openai.com/api/docs/pricing"
OPENAI_PRICE_CHECKED = "2026-10-30"
FX_RESERVATION_KRW = 2000


def provider_for(model):
    if model in OPENAI_PRICES:
        return "openai"
    if model in PRICES:
        return "gemini"
    return None


def price_for(model):
    return OPENAI_PRICES.get(model) or PRICES.get(model)


def schema_constraints(schema, path=""):
    """Array counts, enums and lengths as sentences. OpenAI's json_schema mode (non-strict) does not
    enforce minItems/maxItems/enum/maxLength, so the model is told them explicitly."""
    lines = []
    if not isinstance(schema, dict):
        return lines
    kind = schema.get("type")
    label = path or "(root)"
    if kind == "array":
        low, high = schema.get("minItems"), schema.get("maxItems")
        if low is not None and high is not None and low == high:
            lines.append(f"{label}: 정확히 {low}개")
        elif low is not None and high is not None:
            lines.append(f"{label}: {low}~{high}개")
        elif low is not None:
            lines.append(f"{label}: {low}개 이상")
        elif high is not None:
            lines.append(f"{label}: {high}개 이하")
        lines.extend(schema_constraints(schema.get("items"), path + "[]"))
    elif kind == "string":
        if schema.get("enum"):
            lines.append(f"{label}: 다음 중 하나 {schema['enum']}")
        elif schema.get("maxLength") is not None:
            lines.append(f"{label}: {schema['maxLength']}자 이하")
    elif kind == "object":
        for name, sub in (schema.get("properties") or {}).items():
            lines.extend(schema_constraints(sub, f"{path}.{name}" if path else name))
    return lines


def cache_key(provider, model, messages, schema, options):
    return digest({"provider": provider, "model": model, "actual_messages": messages, "schema": schema, "actual_options": options, "contract": "heobrain-model-v1"})


class Provider:
    def __init__(self, store: Store, model=None, transport=None):
        self.store = store
        self.model = model or store.setting("model") or os.environ.get("OFFICE_MODEL", "gemini-3.8-flash")
        self.transport = transport or requests.post

    @staticmethod
    def _error_status(response):
        try:
            data = response.json()
            return data["error"]["status"] if isinstance(data, dict) else None
        except (ValueError, KeyError, TypeError):
            return None

    def generate(self, role, messages, schema, options=None):
        options = {"max_tokens": 8192, "temperature": 0.5, **(options or {})}
        provider = provider_for(self.model)
        if provider is None:
            raise WorkflowError("모델의 검증된 단가가 없어 호출을 보류합니다")
        key = cache_key(provider, self.model, messages, schema, options)
        cached = self.store.cache_get(key)
        if cached is not None:
            try:
                Draft202012Validator(schema).validate(cached)
            except ValidationError:
                raise WorkflowError("저장된 모델 결과 형식이 schema와 달라 검토가 필요합니다") from None
            self.store.event("model_cache_hit", {"role": role, "model": self.model, "key": key})
            return cached
        price_until = self.store.setting("price_valid_until", "2026-11-02T00:00:00+09:00")
        if datetime.now(timezone.utc) >= datetime.fromisoformat(price_until):
            raise WorkflowError("검증한 요금 단가의 유효기간이 지났습니다. 단가를 재확인하세요")
        window = self.store.setting("work_window", {})
        if window.get("authorized_end") and datetime.now(timezone.utc) >= datetime.fromisoformat(window["authorized_end"]):
            raise WorkflowError("허용된 작업 시간이 종료되어 새 유료 호출을 보류합니다")
        if provider == "openai":
            api_key = os.environ.get("OPENAI_API_KEY")
            if not api_key:
                raise WorkflowError("OpenAI 연결이 없습니다. OPENAI_API_KEY를 설정하거나 제작 설정에서 글 모델을 바꾸세요")
            url, headers, payload = self._openai_request(api_key, messages, schema, options)
            price, price_source, price_checked = OPENAI_PRICES[self.model], OPENAI_PRICE_SOURCE, OPENAI_PRICE_CHECKED
        else:
            api_key = os.environ.get("GEMINI_API_KEY")
            if not api_key:
                raise WorkflowError("기존 Gemini 연결이 없습니다. 자격 설정 후 다시 요청하세요")
            url, headers, payload = self._gemini_request(api_key, messages, schema, options)
            price, price_source, price_checked = PRICES[self.model], PRICE_SOURCE, "2026-10-26"
        # UTF-8 byte length is a conservative token bound for these text-only inputs.
        input_bound = len(canonical(payload).encode("utf-8"))
        maximum = ((input_bound * price["input_usd_million"] + options["max_tokens"] * price["output_usd_million"]) / 1_000_000 * FX_RESERVATION_KRW) * 1.2
        reservation = self.store.reserve_cost("model", maximum, {"role": role, "model": self.model, "provider": provider, "cache_key": key, "input_byte_bound": input_bound, "max_output_tokens": options["max_tokens"], "price": price, "price_source": price_source, "price_checked": price_checked, "fx_reservation_krw": FX_RESERVATION_KRW})
        self.store.event("model_started", {"role": role, "model": self.model, "provider": provider, "reservation_id": reservation["id"], "input_hash": digest(messages), "schema_hash": digest(schema), "reserved_krw": reservation["reserved_krw"]})
        try:
            response = self.transport(url, headers=headers, json=payload, timeout=(10, 150))
        except requests.RequestException:
            self.store.unknown_cost(reservation["id"], "network_result_unknown")
            raise WorkflowError("모델 응답을 확인하지 못했습니다. 비용 예약을 유지하며 자동 재호출하지 않습니다") from None
        if response.status_code >= 400:
            # 4xx와 Gemini의 명시적 503 UNAVAILABLE(수요 폭주)은 '처리하지 않았다'는 뜻이라 과금이 없으므로 예약을 0원으로 정산한다.
            # 그 밖의 5xx는 처리 여부를 알 수 없어 예약을 유지한다.
            rejected = 400 <= response.status_code < 500 or (provider == "gemini" and response.status_code == 503 and self._error_status(response) == "UNAVAILABLE")
            if rejected:
                self.store.settle_cost(reservation["id"], 0, {"http_status": response.status_code, "accepted": False})
            else:
                self.store.unknown_cost(reservation["id"], "provider_server_error")
            uncertainty = "" if rejected else " 비용 예약을 유지합니다."
            raise WorkflowError(f"모델 제공자가 HTTP {response.status_code}를 반환했습니다.{uncertainty} 자동 재시도 없이 확인이 필요합니다")
        try:
            data = response.json()
            if provider == "openai":
                input_tokens, output_tokens, usage, response_id = self._openai_usage(data)
            else:
                input_tokens, output_tokens, usage, response_id = self._gemini_usage(data)
            actual = (input_tokens * price["input_usd_million"] + output_tokens * price["output_usd_million"]) / 1_000_000 * FX_RESERVATION_KRW
            self.store.settle_cost(reservation["id"], actual, {**usage, "provider_response_id": response_id, "billing_note": "사용량×공식 단가×예약 환산 가정. 계정 청구서 대사 전 추정 원가"})
        except (ValueError, KeyError, TypeError):
            self.store.unknown_cost(reservation["id"], "usage_missing")
            raise WorkflowError("모델 사용량을 확인하지 못해 비용 예약을 유지합니다") from None
        try:
            text = self._openai_text(data) if provider == "openai" else self._gemini_text(data)
            result = json.loads(text)
            if not isinstance(result, dict):
                raise ValueError("Object required")
            Draft202012Validator(schema).validate(result)
        except ValidationError:
            raise WorkflowError("모델 결과 형식이 요청한 schema와 다릅니다. 성공으로 저장하지 않습니다") from None
        except (ValueError, KeyError, TypeError, IndexError):
            raise WorkflowError("모델 결과 형식이 올바르지 않습니다. 성공으로 처리하지 않습니다") from None
        self.store.cache_put(key, result)
        self.store.event("model_completed", {"role": role, "model": self.model, "provider": provider, "key": key, "input_tokens": input_tokens, "output_tokens": output_tokens, "estimated_krw": round(actual, 3)})
        return result

    # --- Gemini -------------------------------------------------------------------------------
    def _gemini_request(self, api_key, messages, schema, options):
        system = "\n\n".join(m["content"] for m in messages if m["role"] == "system")
        contents = [{"role": "model" if m["role"] == "assistant" else "user", "parts": [{"text": m["content"]}]} for m in messages if m["role"] != "system"]
        payload = {"systemInstruction": {"parts": [{"text": system}]}, "contents": contents, "generationConfig": {"responseMimeType": "application/json", "responseJsonSchema": schema, "temperature": options["temperature"], "maxOutputTokens": options["max_tokens"]}}
        return (f"https://generativelanguage.googleapis.com/v1beta/models/{self.model}:generateContent",
                {"x-goog-api-key": api_key, "Content-Type": "application/json"}, payload)

    @staticmethod
    def _gemini_usage(data):
        if not isinstance(data, dict) or not isinstance(data.get("usageMetadata"), dict):
            raise ValueError("Invalid usage object")
        usage = data["usageMetadata"]
        counters = [usage["promptTokenCount"], usage["candidatesTokenCount"], usage.get("thoughtsTokenCount", 0)]
        if any(type(value) is not int or value < 0 for value in counters):
            raise ValueError("Invalid token counters")
        return counters[0], counters[1] + counters[2], usage, data.get("responseId")

    @staticmethod
    def _gemini_text(data):
        candidate = data["candidates"][0]
        return "".join(part.get("text", "") for part in candidate["content"]["parts"] if not part.get("thought"))

    # --- OpenAI -------------------------------------------------------------------------------
    def _openai_request(self, api_key, messages, schema, options):
        # gpt-5 family: temperature is fixed by the API, output limit is max_completion_tokens,
        # and reasoning effort stays low so Korean drafting is fast and the reasoning tokens stay small.
        chat = [{"role": m["role"], "content": m["content"]} for m in messages]
        constraints = schema_constraints(schema)
        if constraints:
            # Keep the operator's own system prompt first; insert the schema facts before the first non-system message.
            first_user = next((i for i, m in enumerate(chat) if m["role"] != "system"), len(chat))
            chat.insert(first_user, {"role": "system", "content": "출력 JSON 형식 제약(반드시 지킬 것):" + chr(10) + "- " + (chr(10) + "- ").join(constraints)})
        payload = {"model": self.model,
                   "messages": chat,
                   "response_format": {"type": "json_schema", "json_schema": {"name": "office_result", "schema": schema}},
                   "max_completion_tokens": options["max_tokens"],
                   "reasoning_effort": options.get("reasoning_effort", "low")}
        return ("https://api.openai.com/v1/chat/completions",
                {"Authorization": f"Bearer {api_key}", "Content-Type": "application/json"}, payload)

    @staticmethod
    def _openai_usage(data):
        if not isinstance(data, dict) or not isinstance(data.get("usage"), dict):
            raise ValueError("Invalid usage object")
        usage = data["usage"]
        counters = [usage["prompt_tokens"], usage["completion_tokens"]]
        if any(type(value) is not int or value < 0 for value in counters):
            raise ValueError("Invalid token counters")
        # completion_tokens already includes reasoning tokens for the gpt-5 family.
        return counters[0], counters[1], usage, data.get("id")

    @staticmethod
    def _openai_text(data):
        message = data["choices"][0]["message"]
        if message.get("refusal"):
            raise ValueError("Refusal")
        return message["content"]
