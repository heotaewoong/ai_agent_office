"""Explicit, budgeted provider calls. No paid fallback and no implicit SDK retries."""
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
FX_RESERVATION_KRW = 2000


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
        if self.model not in PRICES:
            raise WorkflowError("모델의 검증된 단가가 없어 호출을 보류합니다")
        key = cache_key("gemini", self.model, messages, schema, options)
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
        api_key = os.environ.get("GEMINI_API_KEY")
        if not api_key:
            raise WorkflowError("기존 Gemini 연결이 없습니다. 자격 설정 후 다시 요청하세요")
        system = "\n\n".join(m["content"] for m in messages if m["role"] == "system")
        contents = [{"role": "model" if m["role"] == "assistant" else "user", "parts": [{"text": m["content"]}]} for m in messages if m["role"] != "system"]
        payload = {"systemInstruction": {"parts": [{"text": system}]}, "contents": contents, "generationConfig": {"responseMimeType": "application/json", "responseJsonSchema": schema, "temperature": options["temperature"], "maxOutputTokens": options["max_tokens"]}}
        price = PRICES[self.model]
        # UTF-8 byte length is a conservative token bound for these text-only inputs.
        input_bound = len(canonical(payload).encode("utf-8"))
        maximum = ((input_bound * price["input_usd_million"] + options["max_tokens"] * price["output_usd_million"]) / 1_000_000 * FX_RESERVATION_KRW) * 1.2
        reservation = self.store.reserve_cost("model", maximum, {"role": role, "model": self.model, "cache_key": key, "input_byte_bound": input_bound, "max_output_tokens": options["max_tokens"], "price": price, "price_source": PRICE_SOURCE, "price_checked": "2026-10-26", "fx_reservation_krw": FX_RESERVATION_KRW})
        self.store.event("model_started", {"role": role, "model": self.model, "reservation_id": reservation["id"], "input_hash": digest(messages), "schema_hash": digest(schema), "reserved_krw": reservation["reserved_krw"]})
        try:
            response = self.transport(f"https://generativelanguage.googleapis.com/v1beta/models/{self.model}:generateContent", headers={"x-goog-api-key": api_key, "Content-Type": "application/json"}, json=payload, timeout=(10, 150))
        except requests.RequestException:
            self.store.unknown_cost(reservation["id"], "network_result_unknown")
            raise WorkflowError("모델 응답을 확인하지 못했습니다. 비용 예약을 유지하며 자동 재호출하지 않습니다") from None
        if response.status_code >= 400:
            # 제공자가 명시적으로 '처리하지 않았다'고 알린 503 UNAVAILABLE(수요 폭주)은 과금이 없으므로 예약을 0원으로 정산한다.
            # 그 밖의 5xx는 처리 여부를 알 수 없어 예약을 유지한다.
            rejected = 400 <= response.status_code < 500 or (response.status_code == 503 and self._error_status(response) == "UNAVAILABLE")
            if rejected:
                self.store.settle_cost(reservation["id"], 0, {"http_status": response.status_code, "accepted": False})
            else:
                self.store.unknown_cost(reservation["id"], "provider_server_error")
            uncertainty = "" if rejected else " 비용 예약을 유지합니다."
            raise WorkflowError(f"모델 제공자가 HTTP {response.status_code}를 반환했습니다.{uncertainty} 자동 재시도 없이 확인이 필요합니다")
        try:
            data = response.json()
            if not isinstance(data, dict) or not isinstance(data.get('usageMetadata'), dict):
                raise ValueError('Invalid usage object')
            usage = data['usageMetadata']
            counters = [usage['promptTokenCount'], usage['candidatesTokenCount'], usage.get('thoughtsTokenCount', 0)]
            if any(type(value) is not int or value < 0 for value in counters):
                raise ValueError("Invalid token counters")
            input_tokens = counters[0]
            output_tokens = counters[1] + counters[2]
            actual = (input_tokens * price["input_usd_million"] + output_tokens * price["output_usd_million"]) / 1_000_000 * FX_RESERVATION_KRW
            self.store.settle_cost(reservation["id"], actual, {**usage, "provider_response_id": data.get("responseId"), "billing_note": "사용량×공식 단가×예약 환산 가정. 계정 청구서 대사 전 추정 원가"})
        except (ValueError, KeyError, TypeError):
            self.store.unknown_cost(reservation["id"], "usage_missing")
            raise WorkflowError("모델 사용량을 확인하지 못해 비용 예약을 유지합니다") from None
        try:
            candidate = data["candidates"][0]
            text = "".join(part.get("text", "") for part in candidate["content"]["parts"] if not part.get("thought"))
            result = json.loads(text)
            if not isinstance(result, dict):
                raise ValueError("Object required")
            Draft202012Validator(schema).validate(result)
        except ValidationError:
            raise WorkflowError("모델 결과 형식이 요청한 schema와 다릅니다. 성공으로 저장하지 않습니다") from None
        except (ValueError, KeyError, TypeError, IndexError):
            raise WorkflowError("모델 결과 형식이 올바르지 않습니다. 성공으로 처리하지 않습니다") from None
        self.store.cache_put(key, result)
        self.store.event("model_completed", {"role": role, "model": self.model, "key": key, "input_tokens": input_tokens, "output_tokens": output_tokens, "estimated_krw": round(actual, 3)})
        return result
