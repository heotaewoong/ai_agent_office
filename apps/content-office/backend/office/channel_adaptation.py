"""One detailed source, separately reviewed social copies. Never approves or publishes."""
import re
import unicodedata
from urllib.parse import unquote, urlsplit, urlunsplit
from .store import WorkflowError

VERSION = "channel-copy-2-topic"
CHANNEL_COPY = {
    "threads_main": (500, "질문 하나 → 핵심 답·설정·주의점. 한 게시물로 완결"),
    "linkedin_personal": (3000, "원문 사건·핵심 답 → 구체적인 과정 → 해당 사건의 의미와 한계"),
    "instagram_main": (2200, "원문 주제의 핵심 → 알아둘 사실·과정 → 해당 주제의 확인 사항"),
    "x_main": (280, "핵심 결론 하나와 중요한 조건. 긴 설명은 원문 링크로 연결"),
    "instagram_english": (2200, "원문 주제의 핵심 → 사실·과정 → 해당 주제의 확인 사항. 영어 독자를 위한 en-US 본문"),
}
COPY_LOCALES = {key: 'en' if key == 'instagram_english' else 'ko' for key in CHANNEL_COPY}
# X는 글자를 가중치로 센다(CONNECT AI LAB connect-ai-marketer의 xcount와 같은 규칙, 공개 twitter-text v3 설정):
# 라틴 문자 등은 1, 한글, 한자, 이모지는 2, 주소는 길이와 관계없이 23. 한도는 280이다(2026-11-27 사용자 결정).
X_LIMIT = 280
X_URL_WEIGHT = 23
_X_LIGHT = ((0x0000, 0x10FF), (0x2000, 0x200D), (0x2010, 0x201F), (0x2032, 0x2037))
_URL = re.compile(r"https?://\S+")
NARRATION_RANGE = (180, 280)  # 영상 내레이션 합계(공백 포함). 프롬프트와 검사가 이 값 하나를 같이 쓴다


def x_length(text):
    urls = _URL.findall(text or "")
    rest = _URL.sub("", text or "")
    return sum(1 if any(a <= ord(ch) <= b for a, b in _X_LIGHT) else 2 for ch in rest) + X_URL_WEIGHT * len(urls)


def x_korean_budget(packet, footer=""):
    """x_main 본문(링크, 캠페인 문구 제외)에 한글로 쓸 수 있는 글자 수."""
    extra = x_length("\n\n".join(part for part in (footer, source_link(packet)) if part)) + (4 if footer or source_link(packet) else 0)
    return max(20, (X_LIMIT - extra) // 2)


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
    targets = {'threads_main': 250, 'linkedin_personal': 600, 'instagram_main': 450, 'instagram_english': 450}

    def target(key, limit):
        if key == 'x_main':
            return f"한글 {x_korean_budget(packet)}자 이하(X는 한글 1자를 2자로, 링크를 23자로 세요)"
        return f"본문 목표 {min(targets[key], max(40, limit - len(link) - 120))}자 이하"
    limits = "; ".join(f"{key}: {target(key, limit)}, {style}"
                       for key, (limit, style) in CHANNEL_COPY.items() if COPY_LOCALES[key] == language)
    return ("블로그와 SNS·숏폼을 분리한다. 네이버·티스토리는 body의 상세 원문과 모든 설정·표·이미지·문제해결·한계를 보존한다. "
            "channel_posts에는 각 채널에 맞게 새로 편집한 요약 본문을 작성한다. 원문의 첫 문단을 반복 발췌하거나 상세 블로그를 SNS 요약으로 덮어쓰지 않는다. "
            "개인 경험·효과·비교 우위·필수 선택 이유를 지어내지 않고 원문에 있는 조건과 한계를 보존한다. "
            "원문 주제를 채널마다 유지한다. 원문과 무관한 업무 적용·회의 녹취·일반 자동화 교훈으로 결론을 바꾸지 않는다. 예시라고 표시해도 주제 이탈은 허용되지 않는다. "
            "같은 요약을 모든 매체에 복사하지 않는다. 한국어 원고는 한국어 채널만 작성하고 자동 영문 번역은 하지 않는다. "
            "검수 과정·원고/출고 승인 상태·내부 편집 메모는 quality에만 남기고 SNS 본문과 영상 설명란에 노출하지 않는다. 독자에게 필요한 실제 사용 조건과 한계만 게시 문구에 쓴다. "
            "출처 URL과 캠페인 문구는 서버가 덧붙이므로 channel_posts 본문에는 URL을 쓰지 않는다. "
            + limits + f". 영상은 원문 사건의 질문 → 구체적인 사실·과정 → 해당 사건의 의미와 한계로 4~6장면, 내레이션 합계 {NARRATION_RANGE[0]}~{NARRATION_RANGE[1]}자. "
            "구체적이고 검색 가능한 블로그 제목과 간결한 영상 제목을 별도로 쓴다.")


def adaptation_issues(packet, footer=""):
    # Older saved drafts remain readable; only the new explicit contract requires every adapted copy.
    if "channel_posts" not in packet and "channel_policy_version" not in packet:
        return []
    copies = packet.get("channel_posts")
    if not isinstance(copies, dict):
        return ["매체별 SNS 요약본 형식이 올바르지 않습니다"]
    issues = []
    def comparison_text(value):
        return re.sub(r"\s+", "", unicodedata.normalize("NFKC", value))
    language = (packet.get('audience') or {}).get('language', 'ko')
    for key, (limit, _) in CHANNEL_COPY.items():
        if COPY_LOCALES[key] != language:
            continue
        value = copies.get(key)
        if not isinstance(value, str) or not value.strip():
            issues.append(f"{key} 매체별 요약본이 필요합니다")
        elif key == "x_main" and x_length(social_text(packet, key, footer).rstrip()) > X_LIMIT:
            issues.append(f"x_main이 X 가중 글자 수 {x_length(social_text(packet, key, footer).rstrip())}/{X_LIMIT}를 넘습니다(한글 2, 링크 23). 한글 {x_korean_budget(packet, footer)}자 안으로 줄이세요")
        elif len(social_text(packet, key, footer).rstrip()) > limit:
            issues.append(f"{key} 요약본과 원문 링크·캠페인 문구가 {limit}자를 넘습니다")
        elif comparison_text(value) == comparison_text(packet.get("body", "")):
            issues.append(f"{key}에는 상세 블로그 전체가 아닌 매체별 요약본이 필요합니다")
        if isinstance(value, str) and value.strip():
            if _URL.search(value):
                issues.append(f"{key} 본문에 주소가 있습니다. 출처 주소는 서버가 덧붙이니 본문에서 빼세요")
            if key == "threads_main" and "?" not in value.strip().split("\n")[0]:
                issues.append("threads_main은 첫 줄을 질문 하나로 시작해야 합니다")
    scenes = [scene for scene in ((packet.get("video") or {}).get("scenes") or []) if isinstance(scene, dict)]
    if scenes:
        spoken = len(" ".join(str(scene.get("narration") or "").strip() for scene in scenes).strip())
        lo, hi = NARRATION_RANGE
        if not lo <= spoken <= hi:
            issues.append(f"영상 내레이션 합계가 {spoken}자예요. {lo}~{hi}자로 맞추세요")
    normalized = [comparison_text(value) for value in copies.values() if isinstance(value, str)]
    if len(normalized) != len(set(normalized)):
        issues.append("SNS 요약본은 동일 문구 복사 대신 매체별 구성이 필요합니다")
    return issues
