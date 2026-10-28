"""Opt-in OpenAI background images for approved scenes. No defaults, retries, or fallback.

Pricing verified 2026-10-28: https://developers.openai.com/api/docs/pricing
Protocol: https://developers.openai.com/api/docs/api-reference/images/create
The operator supplies OPENAI_API_KEY through the runtime environment only; the key is never
stored in the state folder, receipts, exports, or the repository.
"""
from __future__ import annotations

import base64
from datetime import datetime, timezone
import json
import os
from pathlib import Path
import re
import shutil

import requests

from .speech_provider import _hash, _json, _lock
from .store import Store, WorkflowError, digest

PRICE_SOURCE = "https://developers.openai.com/api/docs/pricing"
PRICE_CHECKED = "2026-10-28"
PRICE_VALID_UNTIL = "2026-11-04T00:00:00+00:00"
FX_KRW = 2000
MODEL = "gpt-image-2.5-flare"
SIZE = "1024x1536"
QUALITY = "medium"
OUTPUT_FORMAT = "png"
RESERVATION_KRW = 200
JOB_CAP_KRW = 2000
MAX_IMAGE_BYTES = 12_000_000
PRICING = {"text_input_usd_million": 5.0, "image_input_usd_million": 8.0, "image_output_usd_million": 30.0,
           "fx_krw": FX_KRW, "valid_until": PRICE_VALID_UNTIL, "source": PRICE_SOURCE, "checked": PRICE_CHECKED}
STYLE = ("세로 숏폼 영상의 배경 일러스트. 어두운 남색 계열의 차분한 추상 배경, 부드러운 빛과 단순한 도형. "
         "사진처럼 과장하거나 인물 얼굴을 그리지 않음. 글자·문자·숫자·로고·워터마크를 절대 넣지 않음 (no text). "
         "화면 중앙과 하단은 자막을 얹을 수 있도록 단순하게 비워 둠.")


class KnownUsageOverrun(WorkflowError):
    def __init__(self, usage, actual):
        super().__init__("이미지 제공자 사용량이 예약 상한을 초과했습니다. 실제 비용과 초과액을 기록했고 추가 호출을 중단합니다")
        self.usage, self.actual = usage, actual


def scene_prompt(scene):
    caption = str(scene.get("caption", "")).strip()
    visual = str(scene.get("visual", "")).strip()
    parts = [STYLE, "주제: " + caption]
    if visual:
        parts.append("시각 요소: " + visual)
    return "\n".join(parts)[:4000]


def image_profile_config(*, job_id, source_hash, scene_count):
    """Pure, serializable request profile bound to one approved source version."""
    if not job_id or not re.fullmatch(r"[0-9a-f]{64}", source_hash or ""):
        raise WorkflowError("배경 이미지 프로필에는 업무와 승인 원고 버전이 필요합니다")
    if not 1 <= scene_count <= 12:
        raise WorkflowError("배경 이미지는 승인된 1~12개 장면에만 생성합니다")
    return {"provider": "openai-images", "model": MODEL, "size": SIZE, "quality": QUALITY,
            "output_format": OUTPUT_FORMAT, "moderation": "auto", "n": 1,
            "job_id": job_id, "source_hash": source_hash, "scene_count": scene_count,
            "reservation_krw": RESERVATION_KRW, "job_cap_krw": JOB_CAP_KRW,
            "budget_scope_id": "image-job-budget-" + digest(job_id)[:32],
            "pricing": dict(PRICING), "contract": "openai-image-opt-in-v1"}


class ImageProvider:
    def __init__(self, store: Store, *, job_id, allow_paid=False, transport=None):
        self.store, self.job_id, self.allow_paid = store, job_id, allow_paid
        self.transport = transport or requests.post
        source = store.require_source_approval(job_id)
        self.source_hash = source["source_hash"]
        scenes = source["source_packet"].get("video", {}).get("scenes", [])
        self._config_json = json.dumps(image_profile_config(job_id=job_id, source_hash=self.source_hash, scene_count=len(scenes)), ensure_ascii=False, sort_keys=True)
        self.assets = store.root / "image-assets"

    @property
    def config(self):
        return json.loads(self._config_json)

    @property
    def cache_key(self):
        return "openai-image:" + digest(self.config)

    @property
    def asset_cache_key(self):
        request = {key: self.config[key] for key in ("provider", "model", "size", "quality", "output_format", "moderation", "n")}
        request["prompt_style"] = STYLE
        return "openai-image-asset:" + digest(request)

    def _authorized(self, scene_index=None):
        if self.allow_paid is not True:
            raise WorkflowError("유료 이미지 생성은 명시적으로 선택한 경우에만 호출합니다")
        job = self.store.require_source_approval(self.job_id)
        selections = job.get("selections", {})
        if not (selections.get("video") is True or selections.get("cards") is True):
            raise WorkflowError("영상 또는 카드 제작 선택과 승인이 있어야 배경 이미지를 생성할 수 있습니다")
        if job["source_hash"] != self.source_hash:
            raise WorkflowError("원고 버전이 변경되어 배경 이미지 승인이 무효입니다")
        scenes = job["source_packet"].get("video", {}).get("scenes", [])
        if scene_index is not None and not (isinstance(scene_index, int) and 0 <= scene_index < len(scenes)):
            raise WorkflowError("승인된 장면 번호만 배경 이미지를 생성할 수 있습니다")
        return scenes

    def _path(self, path):
        path = Path(path).resolve()
        if not path.is_relative_to(self.store.root.resolve()) or path.suffix.lower() != ".png":
            raise WorkflowError("배경 이미지 경로는 앱 상태 폴더 안의 PNG 파일이어야 합니다")
        return path

    def _reserve(self, key, payload):
        if not os.environ.get("OPENAI_API_KEY"):
            raise WorkflowError("OPENAI_API_KEY가 설정되지 않았습니다. 실행 환경 파일에 운영자의 키를 넣은 뒤 다시 요청하세요")
        current = datetime.now(timezone.utc)
        if current >= datetime.fromisoformat(self.config["pricing"]["valid_until"]):
            raise WorkflowError("이미지 단가 유효기간이 지나 재확인이 필요합니다")
        window = self.store.setting("work_window", {})
        if window.get("authorized_end") and current >= datetime.fromisoformat(window["authorized_end"]):
            raise WorkflowError("허용된 작업 시간이 끝나 유료 호출을 보류합니다")
        committed = 0
        with self.store.connection() as db:
            for row in db.execute("SELECT state,reserved_krw,actual_krw,data FROM costs"):
                data = json.loads(row["data"])
                if data.get("cache_key") == key and row["state"] in ("reserved", "unknown"):
                    raise WorkflowError("같은 이미지 요청이 진행 중이거나 결과 불명입니다. 비용 예약을 먼저 확인하세요")
                if data.get("job_id") != self.job_id or data.get("request_kind") != "image":
                    continue
                if data.get("reservation_overrun") or data.get("usage", {}).get("request_contract_exceeded"):
                    raise WorkflowError("이 업무에서 이미지 제공자 사용량 초과가 발생했습니다. 비용 대사 전 추가 호출을 차단합니다")
                committed += row["actual_krw"] if row["state"] == "settled" else row["reserved_krw"]
        if committed + self.config["reservation_krw"] > self.config["job_cap_krw"]:
            raise WorkflowError("배경 이미지 업무당 2,000원 한도를 초과하여 요청을 보류합니다")
        return self.store.reserve_cost("image", self.config["reservation_krw"], {
            "budget_scope_id": self.config["budget_scope_id"], "request_kind": "image", "cache_key": key,
            "job_id": self.job_id, "source_hash": self.source_hash, "payload_hash": digest(payload),
            "model": payload["model"], "price_source": self.config["pricing"]["source"], "price_checked": self.config["pricing"]["checked"],
            "fx_reservation_krw": self.config["pricing"]["fx_krw"], "invoice_reconciled": False,
        })

    def _post(self, key, payload):
        reservation = self._reserve(key, payload)
        self.store.event("image_request_started", {"reservation_id": reservation["id"], "model": payload["model"], "scope": self.config["budget_scope_id"]}, self.job_id)
        try:
            response = self.transport("https://api.openai.com/v1/images/generations",
                                      headers={"Authorization": "Bearer " + os.environ["OPENAI_API_KEY"], "Content-Type": "application/json"},
                                      json=payload, timeout=(10, 180))
        except requests.RequestException:
            self.store.unknown_cost(reservation["id"], "image_network_result_unknown")
            raise WorkflowError("이미지 요청 결과가 불명입니다. 예약을 유지하고 자동 재호출하지 않습니다") from None
        if response.status_code != 200:
            self.store.unknown_cost(reservation["id"], f"image_http_{response.status_code}")
            raise WorkflowError(f"이미지 제공자 HTTP {response.status_code}; 비용 예약을 유지하며 자동 대체 호출하지 않습니다")
        try:
            data = response.json()
        except (ValueError, TypeError):
            self.store.unknown_cost(reservation["id"], "image_response_unreadable")
            raise WorkflowError("이미지 응답을 읽지 못해 비용 예약을 유지합니다") from None
        return reservation, data

    def _settle(self, reservation, data):
        try:
            usage = data["usage"]
            details = usage.get("input_tokens_details") or {}
            text_in = details.get("text_tokens", usage["input_tokens"])
            image_in = details.get("image_tokens", 0)
            output = usage["output_tokens"]
            if any(type(n) is not int or n < 0 for n in (text_in, image_in, output)):
                raise ValueError("usage counters")
            price = self.config["pricing"]
            actual = (text_in * price["text_input_usd_million"] + image_in * price["image_input_usd_million"]
                      + output * price["image_output_usd_million"]) / 1_000_000 * price["fx_krw"]
        except (KeyError, ValueError, TypeError):
            self.store.unknown_cost(reservation["id"], "image_usage_missing_or_out_of_bounds")
            raise WorkflowError("이미지 사용량을 확인하지 못해 예약을 유지합니다. 받은 자산은 보존했습니다") from None
        exceeded = actual > reservation["reserved_krw"]
        self.store.settle_cost(reservation["id"], actual, {**usage, "request_contract_exceeded": exceeded,
                                                            "billing_note": "공식 사용량×공식 단가×2,000원 예약 환산; 청구서 대사 전 추정 원가"})
        if exceeded:
            raise KnownUsageOverrun(usage, actual)
        return usage, actual

    def background(self, scene_index, out_path):
        scenes = self._authorized(scene_index)
        out_path = self._path(out_path)
        prompt = scene_prompt(scenes[scene_index])
        payload = {"model": self.config["model"], "prompt": prompt, "n": self.config["n"], "size": self.config["size"],
                   "quality": self.config["quality"], "output_format": self.config["output_format"], "moderation": self.config["moderation"]}
        key = "image:" + digest({"payload": payload, "source_hash": self.source_hash, "job_id": self.job_id})
        self.assets.mkdir(parents=True, exist_ok=True)
        with _lock(self.assets / (self.config["budget_scope_id"] + ".lock")):
            image_path, receipt_path = self.assets / (key[6:] + ".png"), self.assets / (key[6:] + ".json")
            receipt = json.loads(receipt_path.read_text(encoding="utf-8")) if receipt_path.is_file() else None
            if receipt:
                if receipt.get("status") != "complete":
                    raise WorkflowError("받은 이미지 또는 사용량이 불명 상태입니다. 비용 예약과 자산을 먼저 확인하세요")
                if not image_path.is_file() or _hash(image_path) != receipt.get("sha256"):
                    raise WorkflowError("저장된 배경 이미지가 변경되어 자동 재생성을 보류합니다")
                self._authorized(scene_index); out_path.parent.mkdir(parents=True, exist_ok=True); shutil.copyfile(image_path, out_path)
                return receipt["image_metadata"]
            reservation, data = self._post(key, payload)
            receipt = {"status": "received", "request_hash": key, "source_hash": self.source_hash, "scene_index": scene_index,
                       "reservation_id": reservation["id"], "created": data.get("created"), "config": self.config, "prompt": prompt}
            items = data.get("data") if isinstance(data.get("data"), list) else []
            if items and isinstance(items[-1], dict) and items[-1].get("b64_json"):
                try:
                    raw = base64.b64decode(items[-1]["b64_json"], validate=True)
                    if not raw.startswith(b"\x89PNG\r\n\x1a\n") or len(raw) > MAX_IMAGE_BYTES:
                        raise ValueError("png")
                    partial = image_path.with_suffix(".partial.png"); partial.write_bytes(raw); os.replace(partial, image_path)
                    receipt.update(sha256=_hash(image_path), bytes=len(raw))
                except (KeyError, ValueError, TypeError):
                    receipt["asset_error"] = "image_unreadable"
            _json(receipt_path, receipt)  # Asset receipt exists even if usage parsing fails below.
            try:
                usage, actual = self._settle(reservation, data)
            except KnownUsageOverrun as error:
                receipt.update(status="usage_overrun", usage=error.usage, estimated_krw=error.actual)
                _json(receipt_path, receipt)
                raise
            receipt.update(usage=usage, estimated_krw=actual)
            if not image_path.is_file() or receipt.get("asset_error"):
                receipt["status"] = "asset_needs_review"; _json(receipt_path, receipt)
                raise WorkflowError("받은 배경 이미지가 비어 있거나 PNG 형식이 아니어서 검토가 필요합니다")
            metadata = {"provider": "openai", "model": self.config["model"], "size": self.config["size"], "quality": self.config["quality"],
                        "sha256": receipt["sha256"], "disclosure": "OpenAI 생성 배경 이미지"}
            receipt.update(status="complete", image_metadata=metadata); _json(receipt_path, receipt)
            self._authorized(scene_index); out_path.parent.mkdir(parents=True, exist_ok=True); shutil.copyfile(image_path, out_path)
            return metadata


def make_openai_background_renderer(store, *, job_id, allow_paid=False, transport=None):
    provider = ImageProvider(store, job_id=job_id, allow_paid=allow_paid, transport=transport)

    def render(scene_index, out_path):
        return provider.background(scene_index, out_path)
    render.cache_key = provider.cache_key
    render.asset_cache_key = provider.asset_cache_key
    render.image_provider = provider
    return render
