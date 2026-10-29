"""승인한 원고(①) 하나에서 포맷별 제작 계획을 독립 분기한다. 블로그 게시는 영상·뉴스레터의 선행 조건이 아니다."""
from __future__ import annotations

from .store import WorkflowError

SHORTS_MAX_SECONDS = 180  # 2024-10-15부터 Shorts 최대 3분
SHORTS_HOOK_SECONDS = 3
LONG_BEATS = (60, 180, 360)  # 첫 1분 약속 이행, 3분·6분 재몰입 지점
FORMATS = {
    "blog_tistory": {"delivery": "manual_or_api", "checks": ["제목·메타·대체 텍스트 사실 확인", "AI 활용 고지 문구"]},
    "blog_naver": {"delivery": "manual_paste", "checks": ["직접 경험·실제 화면 포함", "비슷한 글 반복 금지"]},
    "youtube_long": {"delivery": "manual_upload", "checks": ["썸네일 3안 1280×720 이상", "첫 1분에 제목 약속 이행"]},
    "shorts": {"delivery": "manual_upload", "checks": ["3초 안 훅", "180초 이하", "마지막 문장이 첫 장면으로 이어짐"]},
    "newsletter": {"delivery": "approval_3", "checks": ["발송 직전 최신 동의", "회차 키"]},
    # 아래 소셜 포맷은 수동 전달 전용이다. 제작 파이프라인(media/exports)은 이 키를 모르며 plan_formats 분기에만 쓴다.
    "x_post": {"delivery": "manual_paste", "checks": ["짧은 글 초안은 승인② 뒤 사람이 붙여넣기", "계정 주소는 오너 확인 후 등록"]},
    "threads_post": {"delivery": "manual_paste", "checks": ["즉시 발행 옵션이 승인②를 우회하지 않음", "짧은 글 초안만"]},
    "linkedin_post": {"delivery": "manual_paste", "checks": ["방법·사례 중심", "개인 프로필이며 조직 페이지가 아님"]},
    "instagram_card": {"delivery": "manual_upload", "checks": ["카드·릴 검토 묶음", "공식 게시 API 조건 확인 전 수동"]},
}


def plan_formats(source_hash, approved_hash, selected):
    if not approved_hash or source_hash != approved_hash:
        raise WorkflowError("승인①한 원고와 현재 원고가 다릅니다. 다시 승인한 뒤 분기합니다")
    unknown = [name for name in selected if name not in FORMATS]
    if unknown:
        raise WorkflowError("알 수 없는 포맷: " + ", ".join(unknown))
    return [{"format": name, "parent_hash": source_hash, **FORMATS[name], "checks": list(FORMATS[name]["checks"])} for name in selected]


def check_shorts(durations):
    issues, total = [], sum(durations)
    if total > SHORTS_MAX_SECONDS:
        issues.append(f"쇼츠 길이 {total:.0f}초가 {SHORTS_MAX_SECONDS}초를 넘습니다")
    if durations and durations[0] > SHORTS_HOOK_SECONDS:
        issues.append(f"첫 장면이 {durations[0]:.1f}초라 훅이 {SHORTS_HOOK_SECONDS}초 안에 끝나지 않습니다")
    return issues


def retention_beats(total_seconds):
    return [beat for beat in LONG_BEATS if beat < total_seconds]
