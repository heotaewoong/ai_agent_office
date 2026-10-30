"""Opt-in Runway image-to-video clips. Every scene by default (scenes marked `clip: generated` first, then the
rest in order), so no scene is left as a near-frozen still; an operator setting may lower it to 1.
Variable-length models (Grok Lite: 1-15 s, confirmed 2026-10-30 from Runway's own validation error) get a clip as
long as the scene's voice, so the footage never loops or jumps.

Pricing verified 2026-10-28 (gen4) and 2026-10-30 (grok_imagine_1_5_lite: 3 credits/s at 720p + 1 credit
per image start frame): https://docs.dev.runwayml.com/guides/pricing/ (1 credit = $0.01)
Grok params (runwayml/sdk-python image_to_video_create_params.py): model, promptImage (first frame),
ratio auto_480p|auto_720p|auto_1080p (aspect follows the frame, w/h 0.4-2.5), optional duration/promptText.
Spending guards: per-job KRW cap, per-KST-day paid clip cap (default 3), credit preflight via
GET /v1/organization (creditBalance) before the first paid clip, and a scene-input cache key so the
same clip is never paid for twice.
Protocol: https://docs.dev.runwayml.com/api/ (POST /v1/image_to_video, GET /v1/tasks/{id})
The operator supplies RUNWAYML_API_SECRET through the runtime environment only. Task output
URLs expire within 24-48 hours, so the clip bytes are stored locally with a receipt.
"""
from __future__ import annotations

import base64
from datetime import datetime, timedelta, timezone
import json
import math
import os
from pathlib import Path
import re
import shutil
import time

import requests

from .speech_provider import _hash, _json, _lock
from .store import Store, WorkflowError, digest

PRICE_SOURCE = "https://docs.dev.runwayml.com/guides/pricing/"
PRICE_CHECKED = "2026-10-28"
PRICE_VALID_UNTIL = "2026-11-04T00:00:00+00:00"
FX_KRW = 2000
CREDIT_USD = 0.01
API_BASE = "https://api.dev.runwayml.com/v1"
API_VERSION = "2024-11-06"
MODELS = {"grok_imagine_1_5_lite": {"credits_per_second": 3, "start_frame_credits": 1, "ratio": "auto_720p",
                                    "name": "Runway Grok Imagine 1.5 Lite", "price_checked": "2026-10-30", "max_seconds": 15},
          "gen4_turbo": {"credits_per_second": 5, "start_frame_credits": 0, "ratio": "720:1280", "name": "Runway Gen-4 Turbo", "price_checked": "2026-10-28"},
          "gen4.5": {"credits_per_second": 12, "start_frame_credits": 0, "ratio": "720:1280", "name": "Runway Gen-4.5", "price_checked": "2026-10-28"}}
RATIO = "720:1280"
KST = timezone(timedelta(hours=9))
MAX_CLIPS_PER_JOB = 12  # = the most scenes a short may have, i.e. every scene
DEFAULT_CLIPS_PER_VIDEO = MAX_CLIPS_PER_JOB
DEFAULT_DAILY_PAID_CLIPS = 15
MAX_DAILY_PAID_CLIPS = 36
DURATION = 5
MAX_SHORT_SECONDS = 60
JOB_CAP_KRW = 5000
MAX_PROMPT_IMAGE_BYTES = 5_000_000
MAX_CLIP_BYTES = 60_000_000
DEFAULT_MAX_POLLS = 90
POLL_SECONDS = 5
STYLE = ("Subtle realistic handheld documentary camera motion on this photograph, slow and smooth, keep every object, "
         "the composition and the colors, no new objects, no new people, no text or letters or logos.")


class KnownUsageOverrun(WorkflowError):
    def __init__(self, usage, actual):
        super().__init__("영상 제공자 사용량이 예약 상한을 초과했습니다. 실제 비용과 초과액을 기록했고 추가 호출을 중단합니다")
        self.usage, self.actual = usage, actual


def generated_scene_indexes(scenes, limit=None):
    """Scenes marked `clip: generated` first, then the others in order (the hook first); at most `limit`, sorted."""
    valid = [index for index, scene in enumerate(scenes) if isinstance(scene, dict)]
    marked = [index for index in valid if scenes[index].get("clip") == "generated"]
    chosen = marked + [index for index in valid if index not in marked]
    return sorted(chosen if limit is None else chosen[:limit])


def clip_limits(store):
    raw = store.setting("clip_limits", {}) or {}
    per_video, daily = raw.get("max_clips_per_video"), raw.get("daily_paid_clips")
    return {"max_clips_per_video": per_video if type(per_video) is int and 1 <= per_video <= MAX_CLIPS_PER_JOB else DEFAULT_CLIPS_PER_VIDEO,
            "daily_paid_clips": daily if type(daily) is int and 0 <= daily <= MAX_DAILY_PAID_CLIPS else DEFAULT_DAILY_PAID_CLIPS,
            "hard_max_clips_per_video": MAX_CLIPS_PER_JOB, "hard_max_daily_paid_clips": MAX_DAILY_PAID_CLIPS}


def kst_today():
    return datetime.now(KST).date()


def paid_clips_today(store):
    """Every Runway clip reservation created today (KST), whatever its outcome, across all jobs."""
    today = kst_today()
    count = 0
    with store.connection() as db:
        for row in db.execute("SELECT created_at FROM costs WHERE kind='clip'"):
            try:
                if datetime.fromisoformat(row["created_at"]).astimezone(KST).date() == today:
                    count += 1
            except (TypeError, ValueError):
                count += 1  # Unreadable timestamps count against the cap.
    return count


BALANCE_CACHE_SECONDS = 300


def runway_credit_balance(store, *, session=None, force=False):
    """creditBalance from GET /v1/organization (free), cached ~5 minutes in the store. None when unreadable."""
    if not os.environ.get("RUNWAYML_API_SECRET"):
        return None
    cached = store.setting("runway_credit_cache", {}) or {}
    current = datetime.now(timezone.utc)
    try:
        fresh = (current - datetime.fromisoformat(cached["checked_at"])).total_seconds() < BALANCE_CACHE_SECONDS
    except (KeyError, TypeError, ValueError):
        fresh = False
    if fresh and not force:
        return cached.get("balance")
    balance = None
    try:
        response = (session or requests).get(API_BASE + "/organization", timeout=(5, 10), headers={
            "Authorization": "Bearer " + os.environ["RUNWAYML_API_SECRET"], "X-Runway-Version": API_VERSION})
        value = response.json().get("creditBalance") if response.status_code == 200 else None
        balance = value if type(value) in (int, float) and value >= 0 else None
    except (requests.RequestException, ValueError, TypeError, AttributeError):
        balance = None
    store.set_setting("runway_credit_cache", {"checked_at": current.isoformat(), "balance": balance})
    return balance


def clip_seconds(model, scene_seconds=None):
    """Requested clip length: the scene's voice length rounded up (never shorter, so no loop) for variable-length
    models, clamped to what the model accepts; fixed-length models and unknown scene lengths get DURATION."""
    maximum = MODELS[model].get("max_seconds")
    if not maximum or scene_seconds is None:
        return DURATION
    return max(1, min(maximum, math.ceil(float(scene_seconds) + 0.05)))


def credits_for(model, seconds=DURATION):
    spec = MODELS[model]
    return spec["credits_per_second"] * seconds + spec["start_frame_credits"]


def credits_per_clip(model):
    return credits_for(model, DURATION)


def max_credits(model, clips):
    """Upper bound before production, when voice lengths are still unknown: each clip at most the model maximum and
    all clips together at most the 60 s short (+ rounding up per clip)."""
    maximum = MODELS[model].get("max_seconds")
    if not maximum:
        return clips * credits_per_clip(model)
    seconds = min(clips * maximum, MAX_SHORT_SECONDS + clips)
    return MODELS[model]["credits_per_second"] * seconds + clips * MODELS[model]["start_frame_credits"]


def clip_prompt(scene):
    motion = str(scene.get("motion", "")).strip()
    caption = str(scene.get("caption", "")).strip()
    text = STYLE + " Scene: " + caption
    if motion:
        text += ". Motion: " + motion
    return text[:1000]


def clip_profile_config(*, job_id, source_hash, scenes, model, limit=DEFAULT_CLIPS_PER_VIDEO):
    if model not in MODELS:
        raise WorkflowError("등록되지 않은 Runway 모델입니다")
    if not job_id or not re.fullmatch(r"[0-9a-f]{64}", source_hash or ""):
        raise WorkflowError("생성 영상 프로필에는 업무와 승인 원고 버전이 필요합니다")
    if type(limit) is not int or not 1 <= limit <= MAX_CLIPS_PER_JOB:
        raise WorkflowError(f"생성 영상은 한 영상에 1~{MAX_CLIPS_PER_JOB}개 장면까지만 허용합니다")
    generated = generated_scene_indexes(scenes, limit)
    credits = credits_per_clip(model)
    return {"provider": "runway", "model": model, "model_name": MODELS[model]["name"], "ratio": MODELS[model]["ratio"],
            "duration": "scene-length" if MODELS[model].get("max_seconds") else DURATION, "max_seconds": MODELS[model].get("max_seconds"),
            "credits_per_clip": credits, "reservation_krw": int(credits * CREDIT_USD * FX_KRW), "job_cap_krw": JOB_CAP_KRW,
            "clips_per_video_limit": limit, "generated_scenes": generated, "job_id": job_id, "source_hash": source_hash,
            "budget_scope_id": "clip-job-budget-" + digest(job_id)[:32],
            "pricing": {"credit_usd": CREDIT_USD, "fx_krw": FX_KRW, "valid_until": PRICE_VALID_UNTIL, "source": PRICE_SOURCE, "checked": PRICE_CHECKED},
            "contract": "runway-clip-opt-in-v1"}


class ClipProvider:
    def __init__(self, store: Store, *, job_id, allow_paid=False, model="gen4_turbo", session=None, sleep=None, max_polls=DEFAULT_MAX_POLLS, limit=None):
        self.store, self.job_id, self.allow_paid = store, job_id, allow_paid
        self.session, self.sleep, self.max_polls = session or requests, sleep or time.sleep, max_polls
        self._credit_checked = False
        source = store.require_source_approval(job_id)
        self.source_hash = source["source_hash"]
        scenes = source["source_packet"].get("video", {}).get("scenes", [])
        limit = clip_limits(store)["max_clips_per_video"] if limit is None else limit
        self._config_json = json.dumps(clip_profile_config(job_id=job_id, source_hash=self.source_hash, scenes=scenes, model=model, limit=limit), ensure_ascii=False, sort_keys=True)
        self.assets = store.root / "clip-assets"

    @property
    def config(self):
        return json.loads(self._config_json)

    @property
    def cache_key(self):
        return "runway-clip:" + digest(self.config)

    @property
    def asset_cache_key(self):
        request = {key: self.config[key] for key in ("provider", "model", "ratio", "duration")}
        request["prompt_style"] = STYLE
        return "runway-clip-asset:" + digest(request)

    def _authorized(self, scene_index=None):
        if self.allow_paid is not True:
            raise WorkflowError("유료 영상 생성은 명시적으로 선택한 경우에만 호출합니다")
        job = self.store.require_source_approval(self.job_id)
        if job.get("selections", {}).get("video") is not True:
            raise WorkflowError("영상 제작 선택과 승인이 있어야 생성 영상을 호출할 수 있습니다")
        if job["source_hash"] != self.source_hash:
            raise WorkflowError("원고 버전이 변경되어 생성 영상 승인이 무효입니다")
        scenes = job["source_packet"].get("video", {}).get("scenes", [])
        if scene_index is not None:
            if not (isinstance(scene_index, int) and 0 <= scene_index < len(scenes)):
                raise WorkflowError("승인된 장면 번호만 생성 영상을 만들 수 있습니다")
            if scene_index not in self.config["generated_scenes"]:
                raise WorkflowError("승인 원고에서 생성 영상으로 지정한 장면만 호출합니다")
        return scenes

    def _inside(self, path, suffix, label):
        path = Path(path).resolve()
        if not path.is_relative_to(self.store.root.resolve()) or path.suffix.lower() != suffix:
            raise WorkflowError(f"{label} 경로는 앱 상태 폴더 안의 {suffix.upper()[1:]} 파일이어야 합니다")
        return path

    def _headers(self):
        return {"Authorization": "Bearer " + os.environ["RUNWAYML_API_SECRET"], "X-Runway-Version": API_VERSION, "Content-Type": "application/json"}

    def _reserve(self, key, payload, reservation_krw):
        if not os.environ.get("RUNWAYML_API_SECRET"):
            raise WorkflowError("RUNWAYML_API_SECRET가 설정되지 않았습니다. 실행 환경 파일에 운영자의 키를 넣은 뒤 다시 요청하세요")
        current = datetime.now(timezone.utc)
        if current >= datetime.fromisoformat(self.config["pricing"]["valid_until"]):
            raise WorkflowError("영상 단가 유효기간이 지나 재확인이 필요합니다")
        window = self.store.setting("work_window", {})
        if window.get("authorized_end") and current >= datetime.fromisoformat(window["authorized_end"]):
            raise WorkflowError("허용된 작업 시간이 끝나 유료 호출을 보류합니다")
        committed = 0
        with self.store.connection() as db:
            for row in db.execute("SELECT state,reserved_krw,actual_krw,data FROM costs"):
                data = json.loads(row["data"])
                if data.get("cache_key") == key and row["state"] in ("reserved", "unknown"):
                    raise WorkflowError("같은 생성 영상 요청이 진행 중이거나 결과 불명입니다. 비용 예약을 먼저 확인하세요")
                if data.get("job_id") != self.job_id or data.get("request_kind") != "clip":
                    continue
                if data.get("reservation_overrun") or data.get("usage", {}).get("request_contract_exceeded"):
                    raise WorkflowError("이 업무에서 영상 제공자 사용량 초과가 발생했습니다. 비용 대사 전 추가 호출을 차단합니다")
                committed += row["actual_krw"] if row["state"] == "settled" else row["reserved_krw"]
        if committed + reservation_krw > self.config["job_cap_krw"]:
            raise WorkflowError(f"생성 영상 업무당 {self.config['job_cap_krw']:,}원 한도를 초과하여 요청을 보류합니다")
        return self.store.reserve_cost("clip", reservation_krw, {
            "budget_scope_id": self.config["budget_scope_id"], "request_kind": "clip", "cache_key": key,
            "job_id": self.job_id, "source_hash": self.source_hash, "payload_hash": digest({**payload, "promptImage": "omitted"}),
            "model": payload["model"], "price_source": self.config["pricing"]["source"], "price_checked": self.config["pricing"]["checked"],
            "fx_reservation_krw": self.config["pricing"]["fx_krw"], "invoice_reconciled": False,
        })

    def _check_daily_cap(self):
        cap, used = clip_limits(self.store)["daily_paid_clips"], paid_clips_today(self.store)
        if used >= cap:
            self.store.event("clip_daily_cap_refused", {"used_today": used, "daily_cap": cap, "paid_call_made": False}, self.job_id)
            raise WorkflowError(f"오늘(한국 시간) 유료 영상 클립 한도 {cap}개를 모두 썼습니다(사용 {used}개). 유료 호출은 하지 않았습니다. "
                                "내일 다시 하거나 운영자가 하루 한도를 조정하세요")

    def _preflight_credits(self, scene_index, credits):
        """Ask Runway for the balance before the first paid clip, so an empty account never yields a failed paid attempt."""
        if self._credit_checked:
            return
        remaining = [index for index in self.config["generated_scenes"] if index >= scene_index]
        needed = credits * max(1, len(remaining))
        try:
            response = self.session.get(API_BASE + "/organization", headers=self._headers(), timeout=(10, 30))
            balance = response.json()["creditBalance"] if response.status_code == 200 else None
            if type(balance) not in (int, float) or balance < 0:
                raise ValueError("creditBalance")
        except (requests.RequestException, ValueError, TypeError, KeyError):
            self.store.event("clip_credit_preflight", {"ok": False, "needed": needed, "reason": "balance_unreadable", "paid_call_made": False}, self.job_id)
            raise WorkflowError("Runway 크레딧 잔액을 확인하지 못해 유료 영상 호출을 보류합니다. 비용은 발생하지 않았습니다") from None
        if balance < needed:
            self.store.event("clip_credit_preflight", {"ok": False, "balance": balance, "needed": needed, "paid_call_made": False}, self.job_id)
            raise WorkflowError(f"Runway 크레딧이 부족합니다(잔액 {balance}, 필요 {needed}). 유료 영상 호출을 하지 않았습니다")
        self.store.event("clip_credit_preflight", {"ok": True, "balance": balance, "needed": needed}, self.job_id)
        self._credit_checked = True

    def _create_task(self, reservation, payload):
        self.store.event("clip_request_started", {"reservation_id": reservation["id"], "model": payload["model"], "scope": self.config["budget_scope_id"]}, self.job_id)
        try:
            response = self.session.post(API_BASE + "/image_to_video", headers=self._headers(), json=payload, timeout=(10, 60))
        except requests.RequestException:
            self.store.unknown_cost(reservation["id"], "clip_network_result_unknown")
            raise WorkflowError("생성 영상 요청 결과가 불명입니다. 예약을 유지하고 자동 재호출하지 않습니다") from None
        if response.status_code != 200:
            self.store.unknown_cost(reservation["id"], f"clip_http_{response.status_code}")
            raise WorkflowError(f"영상 제공자 HTTP {response.status_code}; 비용 예약을 유지하며 자동 대체 호출하지 않습니다")
        try:
            task_id = response.json()["id"]
            if not isinstance(task_id, str) or not task_id:
                raise ValueError("id")
        except (ValueError, TypeError, KeyError):
            self.store.unknown_cost(reservation["id"], "clip_response_unreadable")
            raise WorkflowError("생성 영상 응답을 읽지 못해 비용 예약을 유지합니다") from None
        return task_id

    def _poll(self, task_id):
        last = None
        for attempt in range(self.max_polls):
            if attempt:
                self.sleep(POLL_SECONDS)
            try:
                response = self.session.get(f"{API_BASE}/tasks/{task_id}", headers=self._headers(), timeout=(10, 30))
                if response.status_code != 200:
                    last = {"status": "HTTP_" + str(response.status_code)}
                    continue
                last = response.json()
            except (requests.RequestException, ValueError, TypeError):
                last = {"status": "NETWORK"}
                continue
            if last.get("status") in ("SUCCEEDED", "FAILED", "CANCELLED"):
                return last
        return {"status": "UNRESOLVED", "last": last}

    def _settle(self, reservation, task):
        try:
            credits = task["cost"]["credits"]
            if type(credits) not in (int, float) or credits < 0:
                raise ValueError("credits")
            price = self.config["pricing"]
            actual = credits * price["credit_usd"] * price["fx_krw"]
        except (KeyError, ValueError, TypeError):
            self.store.unknown_cost(reservation["id"], "clip_cost_missing_or_out_of_bounds")
            raise WorkflowError("영상 사용량(크레딧)을 확인하지 못해 예약을 유지합니다") from None
        exceeded = actual > reservation["reserved_krw"]
        usage = {"credits": credits, "status": task.get("status"), "request_contract_exceeded": exceeded,
                 "billing_note": "제공자 크레딧×$0.01×2,000원 예약 환산; 청구서 대사 전 추정 원가"}
        self.store.settle_cost(reservation["id"], actual, usage)
        if exceeded:
            raise KnownUsageOverrun(usage, actual)
        return usage, actual

    def _download(self, url, target):
        try:
            response = self.session.get(url, timeout=(10, 180))
        except requests.RequestException:
            return None
        if response.status_code != 200:
            return None
        raw = response.content
        if not isinstance(raw, (bytes, bytearray)) or len(raw) > MAX_CLIP_BYTES:
            return None
        partial = target.with_suffix(".partial.mp4")
        partial.write_bytes(raw)
        os.replace(partial, target)
        return target

    def clip(self, scene_index, image_path, out_path, seconds=None):
        scenes = self._authorized(scene_index)
        image_path = self._inside(image_path, ".png", "입력 이미지")
        out_path = self._inside(out_path, ".mp4", "생성 영상")
        image_bytes = image_path.read_bytes()
        if len(image_bytes) > MAX_PROMPT_IMAGE_BYTES or not image_bytes.startswith(b"\x89PNG\r\n\x1a\n"):
            raise WorkflowError("입력 이미지는 5MB 이하 PNG여야 합니다")
        prompt = clip_prompt(scenes[scene_index])
        payload = {"model": self.config["model"], "promptImage": "data:image/png;base64," + base64.b64encode(image_bytes).decode(),
                   "promptText": prompt, "ratio": self.config["ratio"], "duration": clip_seconds(self.config["model"], seconds)}
        credits = credits_for(self.config["model"], payload["duration"])
        # Scene inputs only (model, first frame, prompt, ratio, duration): an unchanged scene is never paid for twice,
        # even after the source is re-approved for unrelated edits.
        key = "clip:" + digest({"model": payload["model"], "image_sha256": _hash(image_path), "prompt": prompt, "ratio": payload["ratio"],
                                "duration": payload["duration"]})
        self.assets.mkdir(parents=True, exist_ok=True)
        with _lock(self.assets / (self.config["budget_scope_id"] + ".lock")):
            clip_path, receipt_path = self.assets / (key[5:] + ".mp4"), self.assets / (key[5:] + ".json")
            receipt = json.loads(receipt_path.read_text(encoding="utf-8")) if receipt_path.is_file() else None
            if receipt:
                if receipt.get("status") != "complete":
                    raise WorkflowError("이전 생성 영상 요청이 실패·불명 상태입니다. 영수증의 task_id로 비용·결과를 먼저 대사하세요")
                if not clip_path.is_file() or _hash(clip_path) != receipt.get("sha256"):
                    raise WorkflowError("저장된 생성 영상이 변경되어 자동 재생성을 보류합니다")
                self._authorized(scene_index); out_path.parent.mkdir(parents=True, exist_ok=True); shutil.copyfile(clip_path, out_path)
                return receipt["clip_metadata"]
            if not os.environ.get("RUNWAYML_API_SECRET"):
                raise WorkflowError("RUNWAYML_API_SECRET가 설정되지 않았습니다. 실행 환경 파일에 운영자의 키를 넣은 뒤 다시 요청하세요")
            self._check_daily_cap()
            self._preflight_credits(scene_index, credits)
            reservation = self._reserve(key, payload, int(credits * CREDIT_USD * FX_KRW))
            task_id = self._create_task(reservation, payload)
            receipt = {"status": "submitted", "request_hash": key, "source_hash": self.source_hash, "scene_index": scene_index,
                       "reservation_id": reservation["id"], "task_id": task_id, "config": self.config, "prompt": prompt, "image_sha256": _hash(image_path)}
            _json(receipt_path, receipt)
            task = self._poll(task_id)
            status = task.get("status")
            if status not in ("SUCCEEDED", "FAILED", "CANCELLED"):
                receipt.update(status="unknown", last_status=task.get("last"))
                _json(receipt_path, receipt)
                self.store.unknown_cost(reservation["id"], "clip_task_unresolved")
                raise WorkflowError("생성 영상 결과가 불명입니다. 예약을 유지했고 영수증의 task_id로 나중에 대사합니다. 자동 재제출하지 않습니다")
            try:
                usage, actual = self._settle(reservation, task)
            except KnownUsageOverrun as error:
                receipt.update(status="usage_overrun", usage=error.usage, estimated_krw=error.actual)
                _json(receipt_path, receipt)
                raise
            receipt.update(usage=usage, estimated_krw=actual)
            if status != "SUCCEEDED":
                receipt.update(status="failed", failure=str(task.get("failure", ""))[:300], failure_code=task.get("failureCode"))
                _json(receipt_path, receipt)
                raise WorkflowError("생성 영상 작업이 실패했습니다. 제공자 사유를 영수증에 기록했고 자동 재시도하지 않습니다")
            outputs = task.get("output") if isinstance(task.get("output"), list) else []
            saved = self._download(outputs[0], clip_path) if outputs and isinstance(outputs[0], str) and outputs[0].startswith("https://") else None
            if not saved or not clip_path.read_bytes()[4:8] == b"ftyp":
                receipt["status"] = "asset_needs_review"; _json(receipt_path, receipt)
                raise WorkflowError("생성 영상 파일을 받지 못했거나 MP4 형식이 아니어서 검토가 필요합니다. 비용은 정산했고 task_id로 다시 내려받을 수 있습니다")
            metadata = {"provider": "runway", "model": self.config["model"], "model_name": self.config["model_name"], "duration": payload["duration"],
                        "ratio": self.config["ratio"], "sha256": _hash(clip_path), "disclosure": "Runway 생성 영상 장면"}
            receipt.update(status="complete", sha256=metadata["sha256"], bytes=clip_path.stat().st_size, clip_metadata=metadata); _json(receipt_path, receipt)
            self._authorized(scene_index); out_path.parent.mkdir(parents=True, exist_ok=True); shutil.copyfile(clip_path, out_path)
            return metadata


def make_runway_clip_renderer(store, *, job_id, allow_paid=False, model="gen4_turbo", session=None, sleep=None, max_polls=DEFAULT_MAX_POLLS, limit=None):
    provider = ClipProvider(store, job_id=job_id, allow_paid=allow_paid, model=model, session=session, sleep=sleep, max_polls=max_polls, limit=limit)

    def render(scene_index, image_path, out_path, seconds=None):
        return provider.clip(scene_index, image_path, out_path, seconds=seconds)
    render.accepts_seconds = True
    render.cache_key = provider.cache_key
    render.asset_cache_key = provider.asset_cache_key
    render.clip_provider = provider
    render.generated_scenes = provider.config["generated_scenes"]
    render.paid = True
    return render
