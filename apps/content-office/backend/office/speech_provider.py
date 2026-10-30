"""Opt-in Gemini speech experiment. No defaults, retries, fallback, or news mutation.

Pricing verified 2026-10-26: https://ai.google.dev/gemini-api/docs/pricing
Protocol: https://ai.google.dev/gemini-api/docs/speech-generation
"""
from __future__ import annotations

import base64
from contextlib import contextmanager
from datetime import datetime, timezone
import hashlib
import json
import os
from pathlib import Path
import re
import shutil
import wave

import requests

from .store import Store, WorkflowError, digest

PRICE_SOURCE = "https://ai.google.dev/gemini-api/docs/pricing"
PRICE_VALID_UNTIL = "2026-11-02T00:00:00+00:00"
FX_KRW = 2000
EXPERIMENT_LIMIT_KRW = 1000
TTS_MODEL = "gemini-3.8-flash-tts"
ASR_MODEL = "gemini-3.5-flash-lite"
TTS_MAX_OUTPUT = 2048
ASR_MAX_OUTPUT = 1024
ASR_PROMPT = "한국어 음성에서 실제 들리는 말만 그대로 받아 적으세요. 문장을 고치거나 추가하지 마세요. 들리지 않는 부분은 [불명확]으로 표시하고 전사문만 출력하세요."
DEFAULT_STYLE = "표준 한국어로 차분하고 또렷하게 읽으세요. 외래어와 약어는 자연스럽게 발음하고 과장된 연기는 하지 마세요."


def voice_profile_config(*, voice="Kore", style=DEFAULT_STYLE, synthetic_only=True,
                         job_id=None, source_hash=None, approved_narrations=None):
    """Pure, serializable profile. No environment, Store, network, or settings reads."""
    if type(synthetic_only) is not bool:
        raise WorkflowError("음성 프로필의 제작 모드는 명시적인 boolean이어야 합니다")
    if not isinstance(voice, str) or not re.fullmatch(r"[A-Za-z][A-Za-z0-9_-]{0,79}", voice):
        raise WorkflowError("음성 이름이 유효하지 않습니다")
    if not isinstance(style, str) or len(style.encode("utf-8")) > 2000:
        raise WorkflowError("음성 발음·문체 지시는 2,000 UTF-8 바이트 이하여야 합니다")
    if approved_narrations is not None and any(not isinstance(t, str) or not t.strip() for t in approved_narrations):
        raise WorkflowError("승인 대본은 비어 있지 않은 문자열이어야 합니다")
    unique = tuple(dict.fromkeys(approved_narrations or ()))
    if not synthetic_only:
        if not job_id or not re.fullmatch(r"[0-9a-f]{64}", source_hash or ""):
            raise WorkflowError("프로덕션 음성 프로필에는 업무와 승인 원고 버전이 필요합니다")
        if not approved_narrations or not 3 <= len(approved_narrations) <= 7 or any(not isinstance(t, str) or not t.strip() for t in unique):
            raise WorkflowError("프로덕션 음성은 승인된 3~7개 장면 대본이 필요합니다")
    scope = "voice-job-" + digest({"job_id": job_id, "source_hash": source_hash})[:32] if not synthetic_only else None
    return {"provider": "gemini-interactions", "model": TTS_MODEL, "voice": voice, "style": style,
            "language": "ko-KR", "response_mime_type": "audio/wav", "max_output_tokens": TTS_MAX_OUTPUT,
            "asr_max_output_tokens": ASR_MAX_OUTPUT, "service_tier": "standard", "store_remote": False,
            "asr_model": ASR_MODEL, "asr_prompt": ASR_PROMPT,
            "mode": "synthetic_experiment" if synthetic_only else "approved_production",
            "request_limits": {"tts": 1 if synthetic_only else len(unique), "asr": 2 if synthetic_only else 0},
            "reservations_krw": {"tts": 400, "asr": 100}, "subcap_krw": EXPERIMENT_LIMIT_KRW,
            "scope_id": scope, "job_id": job_id, "source_hash": source_hash,
            "budget_scope_id": ('voice-job-budget-' + digest(job_id)[:32]) if not synthetic_only else None,
            "pricing": {"tts_text_usd_million": .50, "tts_audio_usd_million": 9.0,
                        "asr_input_usd_million": .30, "asr_output_usd_million": 2.50,
                        "fx_krw": FX_KRW, "valid_until": PRICE_VALID_UNTIL,
                        "tts_serving_output_limit": 16384, "source": PRICE_SOURCE, "checked": "2026-10-26"},
            "contract": "speech-opt-in-v2"}


class KnownUsageOverrun(WorkflowError):
    def __init__(self, usage, actual):
        super().__init__("제공자 사용량이 요청 또는 예약 상한을 초과했습니다. 실제 비용과 초과액을 기록했고 추가 호출을 중단합니다")
        self.usage, self.actual = usage, actual


def _hash(path):
    return hashlib.sha256(path.read_bytes()).hexdigest()


def _json(path, value):
    partial = path.with_name(path.name + ".partial")
    partial.write_text(json.dumps(value, ensure_ascii=False, indent=2), encoding="utf-8")
    os.replace(partial, path)


@contextmanager
def _lock(path):
    """One experiment per process at a time; kernel releases this on process exit."""
    fd = os.open(path, os.O_CREAT | os.O_RDWR, 0o600)
    try:
        if os.name == "nt":
            import msvcrt
            if not os.fstat(fd).st_size: os.write(fd, b"0")
            os.lseek(fd, 0, os.SEEK_SET)
            msvcrt.locking(fd, msvcrt.LK_NBLCK, 1)
        else:
            import fcntl
            fcntl.flock(fd, fcntl.LOCK_EX | fcntl.LOCK_NB)
        yield
    except (BlockingIOError, PermissionError):
        raise WorkflowError("같은 음성 실험이 진행 중입니다") from None
    finally:
        os.close(fd)


class SpeechProvider:
    def __init__(self, store: Store, *, job_id, experiment_id=None, allow_paid=False, voice="Kore", style=DEFAULT_STYLE, transport=None, synthetic_only=True, source_store=None):
        self.store, self.job_id = store, job_id
        self.source_store = source_store or store
        self.allow_paid, self.synthetic_only = allow_paid, synthetic_only
        self.transport = transport or requests.post
        # Metadata is also used before atomic approval; _authorized still guards every synthesis.
        source = self.source_store.job(job_id)
        if not source.get("source_hash") or not isinstance(source.get("source_packet"), dict):
            raise WorkflowError("음성 제작 설정을 확인하려면 현재 원고가 필요합니다")
        self.source_hash = source["source_hash"]
        narrations = [scene.get("narration") for scene in source["source_packet"].get("video", {}).get("scenes", [])]
        profile = voice_profile_config(voice=voice, style=style, synthetic_only=synthetic_only,
                                       job_id=job_id, source_hash=self.source_hash, approved_narrations=narrations)
        if synthetic_only:
            if not isinstance(experiment_id, str) or not re.fullmatch(r"[A-Za-z0-9][A-Za-z0-9_-]{0,70}", experiment_id):
                raise WorkflowError("음성 실험 ID가 유효하지 않습니다")
            profile["scope_id"] = experiment_id
        self.experiment_id = profile["scope_id"]
        self._config_json = json.dumps(profile, ensure_ascii=False, sort_keys=True)
        self.assets = store.root / "speech-assets"

    @property
    def config(self):
        return json.loads(self._config_json)

    @property
    def cache_key(self):
        return "gemini-speech:" + digest(self.config)

    @property
    def asset_cache_key(self):
        """Synthesis bytes depend on these options, not approval or billing scope."""
        profile = self.config
        request = {key: profile[key] for key in ("provider", "model", "voice", "style", "language", "response_mime_type", "max_output_tokens", "service_tier", "store_remote")}
        request["request_format"] = "interactions-user_input-text-speech_metadata-v1"
        return "gemini-speech-asset:" + digest(request)

    def _authorized(self, text=None):
        if self.allow_paid is not True:
            raise WorkflowError("유료 음성은 명시적으로 선택한 경우에만 호출합니다")
        job = self.source_store.require_source_approval(self.job_id)
        if job.get("selections", {}).get("video") is not True:
            raise WorkflowError("영상 제작 선택과 승인이 있어야 유료 음성을 호출할 수 있습니다")
        if job["source_hash"] != self.source_hash:
            raise WorkflowError("원고 버전이 변경되어 음성 승인이 무효입니다")
        packet = job["source_packet"]
        if self.config["mode"] == "synthetic_experiment" and packet.get("synthetic_fixture") is not True:
            raise WorkflowError("이번 음성 실험은 승인된 합성 자료에만 허용됩니다")
        allowed = [s.get("narration") for s in packet.get("video", {}).get("scenes", [])]
        if text is not None and text not in allowed:
            raise WorkflowError("승인된 원고의 음성 대본만 합성할 수 있습니다")
        return job

    def _path(self, path):
        path = Path(path).resolve()
        if not path.is_relative_to(self.store.root.resolve()) or path.suffix.lower() != ".wav":
            raise WorkflowError("음성 실험 경로는 앱 상태 폴더 안의 WAV 파일이어야 합니다")
        return path

    def _reserve(self, kind, maximum, key, payload):
        self._authorized()
        current = datetime.now(timezone.utc)
        if current >= datetime.fromisoformat(self.config["pricing"]["valid_until"]):
            raise WorkflowError("음성 단가 유효기간이 지나 재확인이 필요합니다")
        window = self.store.setting("work_window", {})
        if window.get("authorized_end") and current >= datetime.fromisoformat(window["authorized_end"]):
            raise WorkflowError("허용된 작업 시간이 끝나 유료 호출을 보류합니다")
        if not os.environ.get("GEMINI_API_KEY"):
            raise WorkflowError("기존 Gemini 연결이 없습니다")
        committed, kind_calls = 0, 0
        with self.store.connection() as db:
            for row in db.execute("SELECT state,reserved_krw,actual_krw,data FROM costs"):
                data = json.loads(row["data"])
                if data.get("cache_key") == key and row["state"] in ("reserved", "unknown"):
                    raise WorkflowError("같은 음성 요청이 진행 중이거나 결과 불명입니다. 비용 예약을 먼저 확인하세요")
                same_scope = data.get('experiment_id') == self.experiment_id
                same_job = self.config['mode'] == 'approved_production' and data.get('job_id') == self.job_id and data.get('request_kind') in ('tts', 'asr')
                if not same_scope and not same_job: continue
                if data.get("reservation_overrun") or data.get("usage", {}).get("request_contract_exceeded"):
                    raise WorkflowError("이 음성 범위에서 제공자 사용량 초과가 발생했습니다. 비용 대사 전 추가 호출을 차단합니다")
                committed += row["actual_krw"] if row["state"] == "settled" else row["reserved_krw"]
                if same_scope and data.get("request_kind") == kind: kind_calls += 1
        if committed + maximum > self.config["subcap_krw"]:
            raise WorkflowError("음성 실험 1,000원 한도를 초과하여 요청을 보류합니다")
        if kind_calls >= self.config["request_limits"][kind]:
            raise WorkflowError("이번 합성 음성 비교 실험의 호출 횟수 한도에 도달했습니다")
        # Experiment lock spans the subcap check and this atomic global reservation.
        return self.store.reserve_cost("speech_" + kind, maximum, {
            "experiment_id": self.experiment_id, 'budget_scope_id': self.config.get('budget_scope_id') or self.experiment_id, "request_kind": kind, "cache_key": key,
            "job_id": self.job_id, "source_hash": self.source_hash, "payload_hash": digest(payload),
            "model": payload["model"], "price_source": self.config["pricing"]["source"], "price_checked": self.config["pricing"]["checked"],
            "fx_reservation_krw": self.config["pricing"]["fx_krw"], "invoice_reconciled": False,
        })

    def _post(self, kind, maximum, key, payload):
        reservation = self._reserve(kind, maximum, key, payload)
        self.store.event("speech_request_started", {"kind": kind, "experiment_id": self.experiment_id, "reservation_id": reservation["id"], "model": payload["model"]}, self.job_id)
        try:
            response = self.transport("https://generativelanguage.googleapis.com/v1beta/interactions",
                                      headers={"x-goog-api-key": os.environ["GEMINI_API_KEY"], "Content-Type": "application/json"},
                                      json=payload, timeout=(10, 150))
        except requests.RequestException:
            self.store.unknown_cost(reservation["id"], "speech_network_result_unknown")
            raise WorkflowError("음성 요청 결과가 불명입니다. 예약을 유지하고 자동 재호출하지 않습니다") from None
        if response.status_code != 200:
            self.store.unknown_cost(reservation["id"], f"speech_http_{response.status_code}")
            raise WorkflowError(f"음성 제공자 HTTP {response.status_code}; 비용 예약을 유지하며 자동 대체 호출하지 않습니다")
        try: data = response.json()
        except (ValueError, TypeError):
            self.store.unknown_cost(reservation["id"], "speech_response_unreadable")
            raise WorkflowError("음성 응답을 읽지 못해 비용 예약을 유지합니다") from None
        return reservation, data

    def _settle(self, reservation, data, kind):
        try:
            usage = data["usage"]
            counts = [usage["total_input_tokens"], usage["total_output_tokens"], usage.get("total_thought_tokens", 0)]
            if any(type(n) is not int or n < 0 for n in counts): raise ValueError("usage counters")
            prompt, output, thoughts = counts
            price = self.config["pricing"]
            if kind == "tts":
                exceeded = prompt > 8192 or output > price["tts_serving_output_limit"] or thoughts > 0
                actual = (prompt * price["tts_text_usd_million"] + (output + thoughts) * price["tts_audio_usd_million"]) / 1_000_000 * price["fx_krw"]
            else:
                exceeded = output + thoughts > self.config["asr_max_output_tokens"]
                actual = (prompt * price["asr_input_usd_million"] + (output + thoughts) * price["asr_output_usd_million"]) / 1_000_000 * price["fx_krw"]
        except (KeyError, ValueError, TypeError):
            self.store.unknown_cost(reservation["id"], "speech_usage_missing_or_out_of_bounds")
            raise WorkflowError("음성 사용량을 확인하지 못해 예약을 유지합니다. 받은 자산은 보존했습니다") from None
        self.store.settle_cost(reservation["id"], actual, {**usage, "request_contract_exceeded": bool(exceeded or actual > reservation["reserved_krw"]), "response_id": data.get("id"), "billing_note": "공식 사용량×공식 단가×2,000원 예약 환산; 청구서 대사 전 추정 원가"})
        if exceeded or actual > reservation["reserved_krw"]:
            raise KnownUsageOverrun(usage, actual)
        return usage, actual

    @staticmethod
    def _parts(data, kind):
        return [part for step in data.get("steps", []) if step.get("type") == "model_output" for part in step.get("content", []) if part.get("type") == kind]

    def tts(self, text, out_path):
        self._authorized(text)
        out_path = self._path(out_path)
        if len(text.encode("utf-8")) > 3000:
            raise WorkflowError("이번 시험은 짧은 한국어 대본만 허용합니다")
        payload = {"model": self.config["model"], "store": self.config["store_remote"], "service_tier": self.config["service_tier"],
                   "input": [{"type": "user_input", "content": [{"type": "text", "text": text, "annotations": [{"type": "speech_metadata", "style": self.config["style"]}]}]}],
                   "response_format": {"type": "audio", "mime_type": "audio/wav"},
                   "generation_config": {"max_output_tokens": self.config["max_output_tokens"], "speech_config": [{"voice": self.config["voice"]}]}}
        key = "speech:" + digest({"payload": payload, "source_hash": self.source_hash, "job_id": self.job_id})
        self.assets.mkdir(parents=True, exist_ok=True)
        with _lock(self.assets / ((self.config.get('budget_scope_id') or self.experiment_id) + ".lock")):
            audio_path, receipt_path = self.assets / (key[7:] + ".wav"), self.assets / (key[7:] + ".json")
            receipt = json.loads(receipt_path.read_text(encoding="utf-8")) if receipt_path.is_file() else None
            if receipt:
                if receipt.get("status") != "complete":
                    raise WorkflowError("받은 음성 또는 사용량이 불명 상태입니다. 비용 예약과 자산을 먼저 확인하세요")
                if not audio_path.is_file() or _hash(audio_path) != receipt.get("sha256"):
                    raise WorkflowError("저장된 음성이 변경되어 자동 재합성을 보류합니다")
                self._authorized(text); out_path.parent.mkdir(parents=True, exist_ok=True); shutil.copyfile(audio_path, out_path)
                return receipt["voice_metadata"]
            reservation, data = self._post("tts", self.config["reservations_krw"]["tts"], key, payload)
            receipt = {"status": "received", "request_hash": key, "source_hash": self.source_hash,
                       "reservation_id": reservation["id"], "response_id": data.get("id"), "config": self.config}
            parts = self._parts(data, "audio")
            if parts:
                try:
                    raw = base64.b64decode(parts[-1]["data"], validate=True)
                    partial = audio_path.with_suffix(".partial.wav"); partial.write_bytes(raw); os.replace(partial, audio_path)
                    receipt.update(sha256=_hash(audio_path), bytes=len(raw), mime_type=parts[-1].get("mime_type"))
                except (KeyError, ValueError, TypeError):
                    receipt["asset_error"] = "audio_unreadable"
            _json(receipt_path, receipt)  # Asset receipt exists even if usage parsing fails below.
            try:
                usage, actual = self._settle(reservation, data, "tts")
            except KnownUsageOverrun as error:
                receipt.update(status="usage_overrun", usage=error.usage, estimated_krw=error.actual)
                _json(receipt_path, receipt)
                raise
            receipt.update(usage=usage, estimated_krw=actual)
            try:
                if data.get("status") != "completed" or not audio_path.is_file(): raise ValueError("incomplete")
                with wave.open(str(audio_path), "rb") as audio:
                    duration = audio.getnframes() / audio.getframerate()
                    if audio.getnframes() <= 0 or duration > 60 or audio.getsampwidth() != 2: raise ValueError("wave format")
                    if not any(audio.readframes(min(audio.getnframes(), 240000))): raise ValueError("silent")
            except (ValueError, wave.Error, EOFError):
                receipt["status"] = "asset_needs_review"; _json(receipt_path, receipt)
                raise WorkflowError("받은 음성이 미완료·무음·60초 초과이거나 WAV 형식이 달라 검토가 필요합니다") from None
            metadata = {"voice": self.config["voice"], "provider": "gemini", "model": TTS_MODEL, "disclosure": "Gemini 한국어 합성 음성"}
            receipt.update(status="complete", duration=duration, voice_metadata=metadata); _json(receipt_path, receipt)
            self._authorized(text); out_path.parent.mkdir(parents=True, exist_ok=True); shutil.copyfile(audio_path, out_path)
            return metadata

    def transcribe(self, audio_path):
        self._authorized()
        audio_path = self._path(audio_path)
        with wave.open(str(audio_path), "rb") as audio:
            duration = audio.getnframes() / audio.getframerate()
        if not 0 < duration <= 60 or audio_path.stat().st_size > 8_000_000:
            raise WorkflowError("이번 ASR 시험은 60초 이하의 작은 WAV만 허용합니다")
        payload = {"model": self.config["asr_model"], "store": self.config["store_remote"], "service_tier": self.config["service_tier"],
                   "input": [{"type": "text", "text": self.config["asr_prompt"]}, {"type": "audio", "mime_type": "audio/wav", "data": base64.b64encode(audio_path.read_bytes()).decode()}],
                   "generation_config": {"max_output_tokens": self.config["asr_max_output_tokens"], "thinking_level": "minimal", "thinking_summaries": "none"}}
        key = "speech-asr:" + digest({"payload": payload, "source_hash": self.source_hash, "job_id": self.job_id})
        self.assets.mkdir(parents=True, exist_ok=True)
        with _lock(self.assets / ((self.config.get('budget_scope_id') or self.experiment_id) + ".lock")):
            receipt_path = self.assets / (key[11:] + ".asr.json")
            if receipt_path.is_file():
                prior = json.loads(receipt_path.read_text(encoding="utf-8"))
                if prior.get("status") != "complete":
                    raise WorkflowError("이전 전사 결과 또는 사용량이 불명입니다. 예약·응답을 먼저 확인하세요")
            cached = self.store.cache_get(key)
            if cached is not None: return cached
            reservation, data = self._post("asr", self.config["reservations_krw"]["asr"], key, payload)
            text = "\n".join(p.get("text", "") for p in self._parts(data, "text")).strip()
            receipt = {"response_id": data.get("id"), "reservation_id": reservation["id"], "audio_sha256": _hash(audio_path), "text": text, "model": ASR_MODEL, "status": "received"}
            _json(receipt_path, receipt)
            try:
                usage, actual = self._settle(reservation, data, "asr")
            except KnownUsageOverrun as error:
                receipt.update(status="usage_overrun", usage=error.usage, estimated_krw=error.actual)
                _json(receipt_path, receipt)
                raise
            receipt.update(usage=usage, estimated_krw=actual)
            if data.get("status") != "completed" or not text:
                receipt["status"] = "transcript_needs_review"; _json(receipt_path, receipt)
                raise WorkflowError("전사 결과가 미완료이거나 비어 있습니다. 자동 재호출하지 않습니다")
            receipt["status"] = "complete"; _json(receipt_path, receipt)
            self.store.cache_put(key, receipt)
            return receipt


def make_gemini_voice_renderer(store, *, job_id, experiment_id=None, allow_paid=False, voice="Kore", style=DEFAULT_STYLE, transport=None, synthetic_only=True, source_store=None):
    provider = SpeechProvider(store, job_id=job_id, experiment_id=experiment_id, allow_paid=allow_paid,
                              voice=voice, style=style, transport=transport, synthetic_only=synthetic_only, source_store=source_store)
    def render(text, out_path):
        return provider.tts(text, out_path)
    render.cache_key = provider.cache_key
    render.asset_cache_key = provider.asset_cache_key
    render.speech_provider = provider
    return render
