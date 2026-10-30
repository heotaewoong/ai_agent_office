"""Opt-in OpenAI narration for approved scenes. No defaults, retries, or fallback.

Pricing verified 2026-10-30: https://developers.openai.com/api/docs/pricing
  gpt-4o-mini-tts · text input $0.60 / 1M tokens · audio output $12.00 / 1M tokens (no $/minute listed).
Protocol: https://developers.openai.com/api/reference/resources/audio/subresources/speech/methods/create
  POST /v1/audio/speech returns raw audio bytes (input ≤ 4,096 chars, instructions ≤ 4,096 chars).
  response_format "pcm" = 24 kHz, 16-bit signed little-endian samples without a header
  (https://developers.openai.com/api/docs/guides/text-to-speech); this module wraps them in a mono WAV.
  The docs recommend the `marin` or `cedar` voice for best quality. The docs also announce that
  gpt-4o-mini-tts shuts down on 2027-01-06; the price validity below forces a re-check well before that.

The response carries no token usage, so each successful call is settled from a deterministic estimate:
UTF-8 bytes of input+instructions as a token upper bound, plus the measured audio length × an assumed
audio-token rate (OpenAI does not publish tokens per second for this model). The receipt and cost row are
labelled `provider_usage_estimate_pending_invoice`; the invoice remains the source of truth.
The operator supplies OPENAI_API_KEY through the runtime environment only; the key is never stored.
"""
from __future__ import annotations

from datetime import datetime, timezone
import json
import math
import os
from pathlib import Path
import re
import shutil
import wave

import requests

from .speech_provider import _hash, _json, _lock
from .store import Store, WorkflowError, digest

PRICE_SOURCE = "https://developers.openai.com/api/docs/pricing"
PRICE_CHECKED = "2026-10-30"
PRICE_VALID_UNTIL = "2026-11-06T00:00:00+00:00"
ENDPOINT = "https://api.openai.com/v1/audio/speech"
FX_KRW = 2000
MODEL = "gpt-4o-mini-tts"
VOICE = "marin"
SAMPLE_RATE = 24000
MAX_SECONDS = 60
MAX_INPUT_BYTES = 3000
JOB_CAP_KRW = 1000
# Assumption, not an official figure: a generous audio-token rate so the estimate errs high.
AUDIO_TOKENS_PER_SECOND = 50
INSTRUCTIONS = ("표준 한국어 내레이션입니다. 차분하고 또렷한 목소리로 자연스러운 속도로 읽으세요. "
                "외래어와 약어는 한국어식으로 자연스럽게 발음하고, 과장된 연기나 감정 표현은 하지 마세요.")
PRICING = {"text_input_usd_million": 0.60, "audio_output_usd_million": 12.00,
           "audio_tokens_per_second_assumption": AUDIO_TOKENS_PER_SECOND,
           "fx_krw": FX_KRW, "source": PRICE_SOURCE, "checked": PRICE_CHECKED}
BILLING_NOTE = ("응답에 사용량이 없어 입력 UTF-8 바이트(토큰 상한)와 실제 음성 길이×가정 토큰율(초당 50)×공식 단가×2,000원 "
                "예약 환산으로 정산한 추정 원가; 청구서 대사 전")


def estimate_krw(input_bytes, seconds):
    audio_tokens = math.ceil(seconds * AUDIO_TOKENS_PER_SECOND)
    usd = (input_bytes * PRICING["text_input_usd_million"] + audio_tokens * PRICING["audio_output_usd_million"]) / 1_000_000
    return audio_tokens, usd * FX_KRW


class OpenAISpeechProvider:
    def __init__(self, store: Store, *, job_id, allow_paid=False, voice=VOICE, transport=None):
        self.store, self.job_id, self.allow_paid = store, job_id, allow_paid
        self.transport = transport or requests.post
        if not isinstance(voice, str) or not re.fullmatch(r"[a-z][a-z0-9_-]{0,39}", voice):
            raise WorkflowError("음성 이름이 유효하지 않습니다")
        # Approval+enqueue needs metadata first; tts() still authorizes before any side effect.
        source = store.job(job_id)
        if not source.get("source_hash") or not isinstance(source.get("source_packet"), dict):
            raise WorkflowError("음성 제작 설정을 확인하려면 현재 원고가 필요합니다")
        self.source_hash = source["source_hash"]
        narrations = [scene.get("narration") for scene in source["source_packet"].get("video", {}).get("scenes", [])]
        self.request_limit = len(dict.fromkeys(narrations))
        profile = {"provider": "openai-speech", "model": MODEL, "voice": voice, "instructions": INSTRUCTIONS,
                   "response_format": "pcm", "sample_rate": SAMPLE_RATE, "channels": 1, "language": "ko-KR",
                   "job_id": job_id, "source_hash": self.source_hash, "job_cap_krw": JOB_CAP_KRW,
                   "budget_scope_id": "voice-job-budget-" + digest(job_id)[:32],
                   "pricing": {**PRICING, "valid_until": PRICE_VALID_UNTIL}, "contract": "openai-speech-opt-in-v1"}
        self._config_json = json.dumps(profile, ensure_ascii=False, sort_keys=True)
        self.assets = store.root / "openai-speech-assets"

    @property
    def config(self):
        return json.loads(self._config_json)

    @property
    def cache_key(self):
        return "openai-speech:" + digest(self.config)

    @property
    def asset_cache_key(self):
        """Synthesis bytes depend on these options, not approval or billing scope."""
        request = {key: self.config[key] for key in ("provider", "model", "voice", "instructions", "response_format", "sample_rate", "channels")}
        return "openai-speech-asset:" + digest(request)

    def _authorized(self, text=None):
        if self.allow_paid is not True:
            raise WorkflowError("유료 음성은 명시적으로 선택한 경우에만 호출합니다")
        job = self.store.require_source_approval(self.job_id)
        if job.get("selections", {}).get("video") is not True:
            raise WorkflowError("영상 제작 선택과 승인이 있어야 유료 음성을 호출할 수 있습니다")
        if job["source_hash"] != self.source_hash:
            raise WorkflowError("원고 버전이 변경되어 음성 승인이 무효입니다")
        allowed = [s.get("narration") for s in job["source_packet"].get("video", {}).get("scenes", [])]
        if text is not None and text not in allowed:
            raise WorkflowError("승인된 원고의 음성 대본만 합성할 수 있습니다")
        return job

    def _path(self, path):
        path = Path(path).resolve()
        if not path.is_relative_to(self.store.root.resolve()) or path.suffix.lower() != ".wav":
            raise WorkflowError("음성 경로는 앱 상태 폴더 안의 WAV 파일이어야 합니다")
        return path

    def _reserve(self, key, payload, maximum):
        self._authorized()
        if not os.environ.get("OPENAI_API_KEY"):
            raise WorkflowError("OPENAI_API_KEY가 설정되지 않았습니다. 실행 환경 파일에 운영자의 키를 넣은 뒤 다시 요청하세요")
        current = datetime.now(timezone.utc)
        if current >= datetime.fromisoformat(PRICE_VALID_UNTIL):
            raise WorkflowError("OpenAI 음성 단가 유효기간이 지나 재확인이 필요합니다")
        window = self.store.setting("work_window", {})
        if window.get("authorized_end") and current >= datetime.fromisoformat(window["authorized_end"]):
            raise WorkflowError("허용된 작업 시간이 끝나 유료 호출을 보류합니다")
        committed, calls = 0, 0
        with self.store.connection() as db:
            for row in db.execute("SELECT state,reserved_krw,actual_krw,data FROM costs"):
                data = json.loads(row["data"])
                if data.get("cache_key") == key and row["state"] in ("reserved", "unknown"):
                    raise WorkflowError("같은 음성 요청이 진행 중이거나 결과 불명입니다. 비용 예약을 먼저 확인하세요")
                # Gemini and OpenAI narration for one job share the same voice cap.
                if data.get("job_id") != self.job_id or data.get("request_kind") not in ("openai_tts", "tts", "asr"):
                    continue
                if data.get("reservation_overrun") or data.get("usage", {}).get("request_contract_exceeded"):
                    raise WorkflowError("이 업무에서 음성 사용량 초과가 발생했습니다. 비용 대사 전 추가 호출을 차단합니다")
                committed += row["actual_krw"] if row["state"] == "settled" else row["reserved_krw"]
                if data.get("request_kind") == "openai_tts" and data.get("source_hash") == self.source_hash:
                    calls += 1
        if committed + math.ceil(maximum) > JOB_CAP_KRW:
            raise WorkflowError("음성 업무당 1,000원 한도를 초과하여 요청을 보류합니다")
        if calls >= self.request_limit:
            raise WorkflowError("승인된 장면 수만큼만 음성을 합성할 수 있습니다. 호출 횟수 한도에 도달했습니다")
        return self.store.reserve_cost("speech_openai_tts", maximum, {
            "budget_scope_id": self.config["budget_scope_id"], "request_kind": "openai_tts", "cache_key": key,
            "job_id": self.job_id, "source_hash": self.source_hash, "payload_hash": digest(payload),
            "model": MODEL, "price_source": PRICE_SOURCE, "price_checked": PRICE_CHECKED,
            "fx_reservation_krw": FX_KRW, "invoice_reconciled": False,
        })

    def _post(self, key, payload, maximum):
        reservation = self._reserve(key, payload, maximum)
        self.store.event("speech_request_started", {"kind": "openai_tts", "reservation_id": reservation["id"], "model": MODEL, "scope": self.config["budget_scope_id"]}, self.job_id)
        try:
            response = self.transport(ENDPOINT, headers={"Authorization": "Bearer " + os.environ["OPENAI_API_KEY"], "Content-Type": "application/json"},
                                      json=payload, timeout=(10, 150))
        except requests.RequestException:
            self.store.unknown_cost(reservation["id"], "openai_speech_network_result_unknown")
            raise WorkflowError("음성 요청 결과가 불명입니다. 예약을 유지하고 자동 재호출하지 않습니다") from None
        if response.status_code != 200:
            # 4xx means the request was rejected without synthesis, so it is not billed; other statuses stay unknown.
            if 400 <= response.status_code < 500:
                self.store.settle_cost(reservation["id"], 0, {"http_status": response.status_code, "accepted": False})
                raise WorkflowError(f"OpenAI 음성 제공자가 HTTP {response.status_code}를 반환했습니다. 자동 재시도·대체 호출 없이 확인이 필요합니다")
            self.store.unknown_cost(reservation["id"], f"openai_speech_http_{response.status_code}")
            raise WorkflowError(f"OpenAI 음성 제공자 HTTP {response.status_code}; 비용 예약을 유지하며 자동 대체 호출하지 않습니다")
        return reservation, response

    def tts(self, text, out_path):
        self._authorized(text)
        out_path = self._path(out_path)
        if len(text.encode("utf-8")) > MAX_INPUT_BYTES:
            raise WorkflowError("장면 대본이 너무 깁니다. 3,000바이트 이하로 줄이세요")
        config = self.config
        payload = {"model": MODEL, "voice": config["voice"], "input": text, "instructions": config["instructions"], "response_format": config["response_format"]}
        input_bytes = len(text.encode("utf-8")) + len(config["instructions"].encode("utf-8"))
        maximum = estimate_krw(input_bytes, MAX_SECONDS)[1]
        key = "openai-speech:" + digest({"payload": payload, "source_hash": self.source_hash, "job_id": self.job_id})
        name = key.split(":", 1)[1]
        self.assets.mkdir(parents=True, exist_ok=True)
        with _lock(self.assets / (config["budget_scope_id"] + ".lock")):
            audio_path, receipt_path = self.assets / (name + ".wav"), self.assets / (name + ".json")
            receipt = json.loads(receipt_path.read_text(encoding="utf-8")) if receipt_path.is_file() else None
            if receipt:
                if receipt.get("status") != "complete":
                    raise WorkflowError("받은 음성이 검토 필요 또는 불명 상태입니다. 비용 정산과 자산을 먼저 확인하세요")
                if not audio_path.is_file() or _hash(audio_path) != receipt.get("sha256"):
                    raise WorkflowError("저장된 음성이 변경되어 자동 재합성을 보류합니다")
                self._authorized(text); out_path.parent.mkdir(parents=True, exist_ok=True); shutil.copyfile(audio_path, out_path)
                return receipt["voice_metadata"]
            reservation, response = self._post(key, payload, maximum)
            raw = response.content if isinstance(response.content, (bytes, bytearray)) else b""
            receipt = {"status": "received", "request_hash": key, "source_hash": self.source_hash, "reservation_id": reservation["id"],
                       "request_id": (getattr(response, "headers", None) or {}).get("x-request-id"), "config": config, "bytes": len(raw)}
            readable = bool(raw) and len(raw) % 2 == 0
            if readable:
                partial = audio_path.with_suffix(".partial.wav")
                with wave.open(str(partial), "wb") as audio:
                    audio.setnchannels(1); audio.setsampwidth(2); audio.setframerate(SAMPLE_RATE); audio.writeframes(raw)
                os.replace(partial, audio_path)
                receipt["sha256"] = _hash(audio_path)
            else:
                receipt["asset_error"] = "audio_unreadable"
            _json(receipt_path, receipt)  # Asset receipt exists before settlement.
            seconds = len(raw) / 2 / SAMPLE_RATE if readable else None
            audio_tokens, actual = estimate_krw(input_bytes, seconds) if readable else (None, reservation["reserved_krw"])
            exceeded = actual > reservation["reserved_krw"]
            usage = {"estimated": True, "cost_status": "provider_usage_estimate_pending_invoice",
                     "estimate_basis": "measured_audio_seconds" if readable else "reservation_upper_bound_audio_unreadable",
                     "input_token_bound_utf8_bytes": input_bytes, "audio_seconds": seconds, "audio_output_tokens_estimate": audio_tokens,
                     "estimated_krw": actual, "request_contract_exceeded": exceeded, "billing_note": BILLING_NOTE}
            self.store.settle_cost(reservation["id"], actual, usage)
            receipt.update(usage=usage, estimated_krw=actual, cost_estimated=True)
            if exceeded:
                receipt["status"] = "usage_overrun"; _json(receipt_path, receipt)
                raise WorkflowError("음성이 60초 상한을 넘어 예약을 초과했습니다. 추정 원가를 기록했고 추가 호출을 중단합니다")
            try:
                if not readable: raise ValueError("unreadable")
                if not 0 < seconds <= MAX_SECONDS: raise ValueError("duration")
                if not any(raw[:SAMPLE_RATE * 2 * 10]): raise ValueError("silent")
            except ValueError:
                receipt["status"] = "asset_needs_review"; _json(receipt_path, receipt)
                raise WorkflowError("받은 음성이 비어 있거나 무음·60초 초과·PCM 형식 오류여서 검토가 필요합니다. 비용은 추정 정산했습니다") from None
            metadata = {"voice": config["voice"], "provider": "openai", "model": MODEL, "disclosure": "OpenAI 한국어 AI 합성 음성"}
            receipt.update(status="complete", duration=seconds, voice_metadata=metadata); _json(receipt_path, receipt)
            self._authorized(text); out_path.parent.mkdir(parents=True, exist_ok=True); shutil.copyfile(audio_path, out_path)
            return metadata


def make_openai_voice_renderer(store, *, job_id, allow_paid=False, voice=VOICE, transport=None):
    provider = OpenAISpeechProvider(store, job_id=job_id, allow_paid=allow_paid, voice=voice, transport=transport)

    def render(text, out_path):
        return provider.tts(text, out_path)
    render.cache_key = provider.cache_key
    render.asset_cache_key = provider.asset_cache_key
    render.speech_provider = provider
    return render
