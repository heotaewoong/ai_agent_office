"""One detailed source, separately reviewed social copies. Never approves or publishes."""
import re
from urllib.parse import unquote, urlsplit, urlunsplit
from .store import WorkflowError

VERSION = "channel-copy-1"
CHANNEL_COPY = {
    "threads_main": (500, "질문 하나 → 핵심 답·설정·주의점. 한 게시물로 완결"),
    "linkedin_personal": (3000, "문제 상황 → 선택 기준 → 해결 과정 → 업무에 적용할 교훈"),
    "instagram_main": (2200, "첫 줄의 실용적인 이점 → 짧은 단계 → 저장해 둘 점검 항목"),
    "x_main": (280, "핵심 결론 하나와 중요한 조건. 긴 설명은 원문 링크로 연결"),
    "instagram_english": (2200, "실용적인 이점 → 짧은 단계 → 점검 항목. 영어 독자를 위한 en-US 본문"),
}
COPY_LOCALES = {key: 'en' if key == 'instagram_english' else 'ko' for key in CHANNEL_COPY}


def copy_schema(language='ko'):
    keys = [key for key in CHANNEL_COPY if COPY_LOCALES[key] == language]
    return {"type": "object", "properties": {
        key: {"type": "string", "minLength": 1, "maxLength": CHANNEL_COPY[key][0]} for key in keys
    }, "required": keys, "additionalProperties": False}


COPY_SCHEMA = copy_schema()


def title_overrides(value):
    if value is None:
        return {}
    if (not isinstance(value, dict) or set(value) - {'blog', 'shorts'}
            or any(not isinstance(text, str) or not text.strip() or len(text) > 200 for text in value.values())):
        raise WorkflowError('선택한 매체별 제목은 blog·shorts의 1~200자 문자열이어야 합니다')
    return dict(value)


def source_link(packet):
    value = packet.get("source_article_url", "")
    if not isinstance(value, str) or not value.startswith("https://") or re.search(r"\s", value):
        return ""
    try:
        parts = urlsplit(value)
        if not parts.hostname or parts.username or parts.password or parts.port not in (None, 443):
            return ""
    except ValueError:
        return ""
    # Show percent-encoded UTF-8 Korean readably, without decoding reserved ASCII URL syntax.
    path = parts.path if re.search(r"%[0-7][0-9a-f]", parts.path, re.I) else unquote(parts.path)
    return urlunsplit((parts.scheme, parts.netloc, path, parts.query, ""))


def social_text(packet, key, footer=""):
    text = packet["channel_posts"][key].strip()
    link = source_link(packet)
    return "\n\n".join([text, *([footer] if footer and footer not in text else []),
                         *([link] if link and link not in text else [])]) + "\n"


def adaptation_prompt(packet=None):
    packet = packet or {}
    link = source_link(packet)
    language = (packet.get('audience') or {}).get('language', 'ko')
    targets = {'threads_main': 250, 'linkedin_personal': 600, 'instagram_main': 450, 'instagram_english': 450, 'x_main': 70}
    limits = "; ".join(f"{key}: 본문 목표 {min(targets[key], max(40, limit - len(link) - 120))}자 이하, {style}"
                       for key, (limit, style) in CHANNEL_COPY.items() if COPY_LOCALES[key] == language)
    return ("블로그와 SNS·숏폼을 분리한다. 네이버·티스토리는 body의 상세 원문과 모든 설정·표·이미지·문제해결·한계를 보존한다. "
            "channel_posts에는 각 채널에 맞게 새로 편집한 요약 본문을 작성한다. 원문의 첫 문단을 반복 발췌하거나 상세 블로그를 SNS 요약으로 덮어쓰지 않는다. "
            "개인 경험·효과·비교 우위·필수 선택 이유를 지어내지 않고 원문에 있는 조건과 한계를 보존한다. "
            "같은 요약을 모든 매체에 복사하지 않는다. 한국어 원고는 한국어 채널만 작성하고 자동 영문 번역은 하지 않는다. "
            "검수 과정·원고/출고 승인 상태·내부 편집 메모는 quality에만 남기고 SNS 본문과 영상 설명란에 노출하지 않는다. 독자에게 필요한 실제 사용 조건과 한계만 게시 문구에 쓴다. "
            "출처 URL과 캠페인 문구는 서버가 덧붙이므로 channel_posts 본문에는 URL을 쓰지 않는다. "
            + limits + ". 영상은 선택 이유 → 핵심 방법 → 대표 문제해결 하나로 4~6장면, 내레이션 합계 180~280자. "
            "구체적이고 검색 가능한 블로그 제목과 간결한 영상 제목을 별도로 쓴다.")


def adaptation_issues(packet, footer=""):
    # Older saved drafts remain readable; only the new explicit contract requires every adapted copy.
    if "channel_posts" not in packet and "channel_policy_version" not in packet:
        return []
    copies = packet.get("channel_posts")
    if not isinstance(copies, dict):
        return ["매체별 SNS 요약본 형식이 올바르지 않습니다"]
    issues = []
    language = (packet.get('audience') or {}).get('language', 'ko')
    for key, (limit, _) in CHANNEL_COPY.items():
        if COPY_LOCALES[key] != language:
            continue
        value = copies.get(key)
        if not isinstance(value, str) or not value.strip():
            issues.append(f"{key} 매체별 요약본이 필요합니다")
        elif len(social_text(packet, key, footer).rstrip()) > limit:
            issues.append(f"{key} 요약본과 원문 링크·캠페인 문구가 {limit}자를 넘습니다")
        elif value.strip() == packet.get("body", "").strip():
            issues.append(f"{key}에는 상세 블로그 전체가 아닌 매체별 요약본이 필요합니다")
    normalized = [re.sub(r"\s+", "", value) for value in copies.values() if isinstance(value, str)]
    if len(normalized) != len(set(normalized)):
        issues.append("SNS 요약본은 동일 문구 복사 대신 매체별 구성이 필요합니다")
    return issues
