"""Opt-in images through the operator's Codex subscription (ChatGPT sign-in). No API key, no per-image charge.

Each image is one `codex exec` turn in a read-only sandbox. The PNG is taken from Codex's own
generated_images/<thread_id> folder, so Codex never needs write access. Runs count against the
operator's plan limits (shared with development work), hence a daily cap. No retries and no
fallback to the paid Images API: a failure fails that output only.
Protocol: https://learn.chatgpt.com/docs/non-interactive-mode
"""
from __future__ import annotations

from datetime import datetime, timedelta, timezone
import json
import os
from pathlib import Path
import re
import shutil
import struct
import subprocess
import tempfile

from .image_provider import MAX_IMAGE_BYTES, PROMPT_VERSION, STYLE, ImageProvider
from .speech_provider import _hash, _json, _lock
from .store import WorkflowError, digest, now

PROFILE_ID = "codex-subscription"
MODEL = "codex-imagegen"
DAILY_CAP = 20
TIMEOUT_SECONDS = 300
KST = timezone(timedelta(hours=9))
PNG_SIGNATURE = b"\x89PNG\r\n\x1a\n"


def codex_binary():
    explicit = os.environ.get("CONTENT_OFFICE_CODEX_BIN")
    if explicit:
        return shutil.which(explicit)
    found = shutil.which("codex")
    if found:
        return found
    for candidate in (Path.home() / ".local/node/bin/codex", Path.home() / ".npm-global/bin/codex"):
        if candidate.is_file() and os.access(candidate, os.X_OK):
            return str(candidate)
    return None


def codex_home():
    return Path(os.environ.get("CODEX_HOME") or Path.home() / ".codex")


def codex_status():
    """Readiness without reading credentials: the CLI is on PATH and a ChatGPT login file exists."""
    return {"configured": bool(codex_binary()) and (codex_home() / "auth.json").is_file(), "daily_cap_images": DAILY_CAP}


def today():
    return datetime.now(KST).date().isoformat()


def used_today(store):
    usage = store.setting("codex_image_usage", {})
    return usage.get("count", 0) if usage.get("date") == today() else 0


def codex_prompt(image_prompt, size):
    width, height = size.split("x")
    return (f"이미지 생성 도구로 이미지 1장만 만든다. 크기는 가로 {width}px, 세로 {height}px에 맞춘다. "
            "파일 저장·명령 실행·다른 작업은 하지 않고, 끝나면 '완료'라고만 답한다.\n\n" + image_prompt)


def png_size(raw):
    if not raw.startswith(PNG_SIGNATURE) or len(raw) < 24 or len(raw) > MAX_IMAGE_BYTES:
        raise WorkflowError("Codex가 만든 파일이 PNG가 아니거나 너무 큽니다")
    return struct.unpack(">II", raw[16:24])


def run_codex(prompt):
    """One `codex exec` turn; returns (png bytes, thread_id). Raises WorkflowError and never retries."""
    binary = codex_binary()
    if not binary:
        raise WorkflowError("codex 명령을 찾지 못했습니다. 앱을 실행하는 계정에 Codex CLI를 설치하세요")
    home = codex_home()
    # Bill the ChatGPT plan only: an API key in the environment would switch Codex to paid API usage.
    env = {key: value for key, value in os.environ.items() if key not in ("OPENAI_API_KEY", "CODEX_API_KEY")}
    env["CODEX_HOME"] = str(home)
    env["PATH"] = str(Path(binary).parent) + os.pathsep + env.get("PATH", "")
    with tempfile.TemporaryDirectory(prefix="codex-image-") as work:
        try:
            completed = subprocess.run(
                [binary, "exec", "--ignore-user-config", "--disable", "shell_tool", "--disable", "unified_exec", "-c", 'forced_login_method="chatgpt"', "--skip-git-repo-check", "--sandbox", "read-only", "--json",
                 "-c", 'model_reasoning_effort="low"', "-C", work, prompt],
                stdin=subprocess.DEVNULL, capture_output=True, text=True, encoding="utf-8", errors="replace",
                timeout=TIMEOUT_SECONDS, env=env)
        except subprocess.TimeoutExpired:
            raise WorkflowError(f"Codex 이미지 생성이 {TIMEOUT_SECONDS}초 안에 끝나지 않았습니다. 자동 재시도하지 않습니다") from None
    thread_id = None
    for line in completed.stdout.splitlines():
        try:
            event = json.loads(line)
        except ValueError:
            continue
        if isinstance(event, dict) and event.get("type") == "thread.started":
            thread_id = event.get("thread_id")
            break
    if completed.returncode != 0 or not isinstance(thread_id, str) or not re.fullmatch(r"[0-9a-f-]{36}", thread_id):
        raise WorkflowError(f"Codex 실행이 실패했습니다(종료 코드 {completed.returncode}). 앱 계정의 codex 로그인 상태를 확인하세요")
    folder = home / "generated_images" / thread_id
    images = sorted(folder.glob("*.png")) if folder.is_dir() else []
    if len(images) != 1:
        raise WorkflowError(f"Codex가 이미지를 {len(images)}장 만들었습니다. 1장일 때만 사용합니다")
    raw = images[0].read_bytes()
    shutil.rmtree(folder, ignore_errors=True)  # The app keeps its own copy; Codex's copy would only fill the disk.
    return raw, thread_id


class CodexImageProvider(ImageProvider):
    """Same approval, version and asset rules as the API provider; only generation and accounting differ."""

    def __init__(self, store, *, job_id, runner=None):
        from .content_api_mode import require_subscription_allowed
        require_subscription_allowed(store)
        super().__init__(store, job_id=job_id, allow_paid=True)  # Selecting this profile is the explicit opt-in.
        self.runner = runner or run_codex
        config = {**json.loads(self._config_json), "provider": PROFILE_ID, "model": MODEL, "quality": "auto",
                  "reservation_krw": 0, "job_cap_krw": 0, "daily_cap_images": DAILY_CAP, "contract": "codex-image-opt-in-v1"}
        config.pop("pricing", None)
        self._config_json = json.dumps(config, ensure_ascii=False, sort_keys=True)

    @property
    def cache_key(self):
        return "codex-image:" + digest(self.config)

    @property
    def asset_cache_key(self):
        return "codex-image-asset:" + digest({"provider": PROFILE_ID, "model": MODEL, "size": self.config["size"], "prompt_style": STYLE, "prompt_version": PROMPT_VERSION})

    def _generate(self, key, payload, prompt, out_path, receipt_extra, reauthorize, request_kind, cap, size, disclosure):
        from .content_api_mode import require_subscription_allowed
        require_subscription_allowed(self.store)
        self.assets.mkdir(parents=True, exist_ok=True)
        with _lock(self.assets / (self.config["budget_scope_id"] + ".lock")):
            image_path, receipt_path = self.assets / (key[6:] + ".png"), self.assets / (key[6:] + ".json")
            receipt = json.loads(receipt_path.read_text(encoding="utf-8")) if receipt_path.is_file() else None
            if receipt and receipt.get("status") == "complete":
                if not image_path.is_file() or _hash(image_path) != receipt.get("sha256"):
                    raise WorkflowError("저장된 배경 이미지가 변경되어 자동 재생성을 보류합니다")
                reauthorize(); out_path.parent.mkdir(parents=True, exist_ok=True); shutil.copyfile(image_path, out_path)
                return receipt["image_metadata"]
            day, count = today(), used_today(self.store)
            if count >= DAILY_CAP:
                raise WorkflowError(f"Codex 구독 이미지는 하루 {DAILY_CAP}장까지입니다. 내일 다시 요청하거나 프로필을 바꾸세요")
            self.store.set_setting("codex_image_usage", {"date": day, "count": count + 1})  # Attempts count, not only successes.
            receipt = {"status": "started", "provider": PROFILE_ID, "request_hash": key, "source_hash": self.source_hash, **receipt_extra,
                       "request_kind": request_kind, "started_at": now(), "config": self.config, "prompt": prompt}
            _json(receipt_path, receipt)
            self.store.event("codex_image_started", {"request_kind": request_kind, "used_today": count + 1, "daily_cap": DAILY_CAP}, self.job_id)
            try:
                raw, thread_id = self.runner(codex_prompt(prompt, size))
                width, height = png_size(raw)
            except WorkflowError as error:
                receipt.update(status="failed", error=str(error)); _json(receipt_path, receipt)
                raise
            partial = image_path.with_suffix(".partial.png"); partial.write_bytes(raw); os.replace(partial, image_path)
            metadata = {"provider": PROFILE_ID, "model": MODEL, "size": f"{width}x{height}", "requested_size": size,
                        "sha256": _hash(image_path), "disclosure": disclosure.replace("OpenAI", "Codex(ChatGPT 구독)")}
            receipt.update(status="complete", thread_id=thread_id, bytes=len(raw), sha256=metadata["sha256"], image_metadata=metadata)
            _json(receipt_path, receipt)
            reauthorize(); out_path.parent.mkdir(parents=True, exist_ok=True); shutil.copyfile(image_path, out_path)
            return metadata


def make_codex_background_renderer(store, *, job_id, runner=None):
    provider = CodexImageProvider(store, job_id=job_id, runner=runner)

    def render(scene_index, out_path):
        return provider.background(scene_index, out_path)
    render.cache_key = provider.cache_key
    render.asset_cache_key = provider.asset_cache_key
    render.image_provider = provider
    return render


def make_codex_card_image_renderer(store, *, job_id, runner=None):
    provider = CodexImageProvider(store, job_id=job_id, runner=runner)

    def render(card_index, slide, out_path):
        return provider.card_image(card_index, slide, out_path)
    render.image_provider = provider
    return render
