"""Shared, stdlib-only payload contract for web and native-owned Slack intake.

Install this exact file beside the native intake helper; never import web-owned code
from the native runtime. Preserve the prefix byte for byte for existing body hashes.
"""
BOARD = "heobrain-office"
TENANT = "heobrain-world"
BODY_PREFIX = (
    "3D 오피스에서 사용자가 요청한 내부 업무입니다. 필요한 기존 역할에게만 인계하고 검토 후 "
    "이 카드에 실제 결과와 남은 사람 행동을 보고하세요. 외부 게시·발송·결제·실거래·권한 확대·"
    "새 예약·서비스 재시작·유료 호출은 별도 사람 승인 없이 실행하지 마세요. 승인⓪①②③과 "
    "기존 예산을 유지하세요. 최대 역할 4개·인계 깊이 3·전체 카드 5개로 제한하고 넘으면 사람에게 보고하세요. "
    "고정된 코디네이터 스킬의 담당 작업·독립 검토·루미 최종 카드 절차를 따르세요.\n\n"
    "사용자에게 돌려줄 완료 요약에는 내부 파일 경로·비밀·인증값을 넣지 마세요. 상세 근거는 기존 보드에 보존하세요.\n\n"
)


def task_payload(request_id, text):
    return {"title": "3D 비서 요청 · " + request_id[:8], "body": BODY_PREFIX + text,
            "assignee": "lumi", "tenant": TENANT, "idempotency_key": "office-world:" + request_id,
            "max_runtime_seconds": 300, "goal_mode": False, "skills": ["heobrain-office-coordinator"]}
