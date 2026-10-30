"""승인 원고의 발췌를 채널별 검토 파일로 만든다. 외부 임시저장·게시를 실행하지 않는다."""
from __future__ import annotations

import hashlib
import json
from pathlib import Path
import re

from .channels import CHANNELS
from .channel_adaptation import CHANNEL_COPY, adaptation_issues, social_text
from .exports import offer_line, plain_text, write_text
from .store import WorkflowError


# 앱 내부의 보수적 검토 예산이다. 계정별 플랫폼 한도·URL 가중치 검증을 대신하지 않는다.
SOCIAL_TARGETS = {
    "x_main": ("x-main.txt", 140, 1),
    "threads_main": ("threads-main.txt", 500, 1),
    "linkedin_personal": ("linkedin-personal.txt", 3000, 2),
    "instagram_main": ("instagram-main-caption.txt", 2200, 1),
    "instagram_english": ("instagram-english-caption.txt", 2200, 1),
}


def write_channel_handoffs(packet: dict, folder: Path, offer: dict | None = None,
                           *, source_hash: str | None = None, language: str | None = None,
                           channels: list[dict] | None = None) -> list[Path]:
    from .offers import require_offer_ready

    if not isinstance(source_hash, str) or not re.fullmatch(r"[a-f0-9]{64}", source_hash):
        raise WorkflowError("채널 검토 파일에는 승인 원고의 내용 해시가 필요합니다")
    title, body = packet.get("title"), packet.get("body")
    if not isinstance(title, str) or not title.strip() or not isinstance(body, str) or not body.strip():
        raise WorkflowError("채널 검토 파일로 나눌 승인 원고가 없습니다")
    require_offer_ready(offer)
    paragraphs = [plain_text(part) for part in re.split(r"\n\s*\n", body.strip())
                  if part.strip() and not re.fullmatch(r"\s*#{1,6}\s+[^\n]+\s*", part)]
    if not paragraphs:
        raise WorkflowError("채널 검토 파일로 발췌할 승인 본문 문단이 없습니다")
    registry = {row["key"]: row for row in (channels if channels is not None else list(CHANNELS.values()))
                if isinstance(row, dict) and row.get("key") in SOCIAL_TARGETS}
    references = list(dict.fromkeys(e["url"] for e in packet.get("evidence", [])
                                   if isinstance(e, dict) and isinstance(e.get("url"), str)
                                   and re.match(r"^https?://[^\s]+$", e["url"])))
    footer = offer_line(offer)
    adapted = isinstance(packet.get('channel_posts'), dict)
    copy_issues = adaptation_issues(packet, footer)
    paths, entries = [], []
    for key, (filename, budget, count) in SOCIAL_TARGETS.items():
        channel = registry.get(key) or CHANNELS[key]
        matched_copy = adapted and key in CHANNEL_COPY and isinstance(packet['channel_posts'].get(key), str)
        text = social_text(packet, key, footer) if matched_copy else "\n\n".join([plain_text(title), *paragraphs[:count], *([footer] if footer else []), *references]).strip() + "\n"
        issues = [issue for issue in copy_issues if key in issue or not any(k in issue for k in CHANNEL_COPY)]
        if adapted and not matched_copy:
            issues.append("이 언어·매체의 요약본은 생성하지 않았습니다. 원문 발췌를 그대로 게시하지 마세요")
        if matched_copy:
            budget = CHANNEL_COPY[key][0]
        if len(text.rstrip()) > budget:
            issues.append("앱의 보수적 글자 수 기준을 넘었습니다. 조건·근거를 유지한 채 직접 편집하세요")
        if not language or language != channel.get("locale"):
            issues.append("원고와 채널 언어가 다르거나 언어가 미확인입니다. 자동 번역하지 않았습니다")
        if key not in registry or not channel.get("public_url"):
            issues.append("대상 채널 주소를 확인해야 합니다")
        if channel.get("platform") == "instagram":
            issues.append("캡션 초안만 준비했습니다. 승인한 카드·영상은 별도로 선택·검토해야 합니다")
        path = write_text(folder, filename, text)
        paths.append(path)
        entries.append({"channel_key": key, "platform": channel["platform"], "locale": channel.get("locale"),
                        "public_url": channel.get("public_url"), "file": filename,
                        "sha256": hashlib.sha256(path.read_bytes()).hexdigest(), "characters": len(text.rstrip()),
                        "review_budget_characters": budget, "state": "needs_review" if issues else "draft_ready",
                        "copy_mode": "channel_adapted" if matched_copy else "legacy_excerpt",
                        "issues": issues, "source_hash": source_hash,
                        "requires_release_approval": True, "external_draft_created": False, "external_published": False})
    manifest = {"source_hash": source_hash, "kind": "manual-channel-handoff", "channels": entries,
                "external_draft_created": False, "external_published": False,
                "notes": ["상세 블로그 본문과 매체별 SNS 요약본을 분리했습니다. 구버전의 문단 발췌는 copy_mode로 구분합니다" if adapted else "승인 본문의 문단을 그대로 발췌했습니다. 새 주장·경험·자동 번역을 만들지 않았습니다",
                          "문단 발췌로 빠진 한계·조건과 문맥을 사람이 확인하고 출고 승인② 뒤 직접 전달하세요",
                          "앱 글자 수 기준 통과는 플랫폼 유효성·게시 권한·외부 임시저장 완료를 뜻하지 않습니다"]}
    paths.append(write_text(folder, "channel-handoff.json", json.dumps(manifest, ensure_ascii=False, indent=2) + "\n"))
    return paths
