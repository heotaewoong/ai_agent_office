"""브랜드 두뇌: 모든 생성 단계가 같은 목소리·표기·금지 주장·발음 사전을 불러온다(Jasper IQ·WRITER Voice Profile 패턴)."""
from __future__ import annotations

import json
import re
from pathlib import Path

from .store import WorkflowError, digest

DEFAULT_DIR = Path(__file__).resolve().parents[1] / "config" / "brand"


def _json(path, default):
    if not path.is_file():
        return default
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except json.JSONDecodeError:
        raise WorkflowError(f"브랜드 설정 파일을 읽을 수 없습니다: {path.name}") from None


def load_brand(directory=DEFAULT_DIR):
    directory = Path(directory)
    voice_path = directory / "voice.md"
    glossary = _json(directory / "glossary.json", {})
    if not isinstance(glossary, dict):
        raise WorkflowError("glossary.json은 {\"terms\": {...}, \"pronunciation\": {...}} 형태의 객체여야 합니다")
    for key in ("terms", "pronunciation"):
        if not isinstance(glossary.get(key, {}), dict):
            raise WorkflowError(f"glossary.json의 {key}는 {{\"표기\": \"값\"}} 형태의 객체여야 합니다")
    banned = _json(directory / "banned_claims.json", [])
    if not isinstance(banned, list) or not all(isinstance(claim, str) for claim in banned):
        raise WorkflowError("banned_claims.json은 문자열 목록([\"금지 주장\", ...])이어야 합니다")
    brand = {
        "voice": voice_path.read_text(encoding="utf-8").strip() if voice_path.is_file() else "",
        "terms": glossary.get("terms", {}),
        "pronunciation": glossary.get("pronunciation", {}),
        "banned": banned,
    }
    return {**brand, "hash": digest(brand)}


def brand_system_prompt(base, brand):
    if not (brand["voice"] or brand["terms"] or brand["banned"]):
        return base
    terms = "\n".join(f"- {written}: {fixed}" for written, fixed in brand["terms"].items())
    banned = "\n".join(f"- {claim}" for claim in brand["banned"])
    return f"{base}\n\n[브랜드 목소리 {brand['hash'][:12]}]\n{brand['voice']}\n\n[표기 고정]\n{terms}\n\n[쓰지 않는 주장]\n{banned}"


def banned_claim_hits(text, brand):
    return [claim for claim in brand["banned"] if re.search(re.escape(claim), text or "", flags=re.IGNORECASE)]


def tts_text(text, brand):
    for written, spoken in sorted(brand["pronunciation"].items(), key=lambda kv: -len(kv[0])):
        text = re.sub(rf"(?<![0-9A-Za-z]){re.escape(written)}(?![0-9A-Za-z])", spoken, text)
    return text
