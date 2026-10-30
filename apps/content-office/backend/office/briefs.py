"""독자 브리프: 사업 축별 프리셋과 작업별 덮어쓰기.

축 A는 시험 합격·편입처럼 불안한 학습자, 축 B는 AI·자동화로 시간을 아끼려는 직장인이다.
생성·비평·평가·수정 호출은 모두 같은 브리프를 받는다. 브리프는 사람 승인을 만들지 않는다.
"""
from __future__ import annotations

from .store import WorkflowError

OVERRIDE_FIELDS = ("topic", "reader", "prior_knowledge", "problem", "current_solution", "outcome", "goal", "tone", "language", "cta")
LANGUAGES = ("ko", "en")
DEFAULT_PRESET = "ai-agent"
MAX_FIELD_LENGTH = 500

PRESETS = {
    "ai-agent": {
        "axis": "B",
        "label": "AI·에이전트 실무",
        "topic": "AI / AI Agent",
        "reader": "AI를 업무와 콘텐츠 제작에 활용하려는 한국어 입문·실무 독자",
        "prior_knowledge": "챗봇 사용 경험. 논문 통계·API 전문 지식은 가정하지 않음",
        "problem": "AI 뉴스를 읽어도 내 업무에 적용할 작은 사례와 판단 기준이 남지 않음",
        "outcome": "완결된 사례의 입력·판단·다음 행동을 설명하고 자기 업무 하나에 적용할 질문을 적을 수 있음",
        "tone": "구체적이고 자연스러운 설명. 독자에게 줄 답을 먼저 쓰고, 관련 한계를 필요한 위치에 짧게 남김. 자극적 단정·가짜 경험·매출 보장 금지",
        "language": "ko",
        "cta": "무료 AI 업무 적용 점검표 받기",
    },
    "exam-opic": {
        "axis": "A",
        "label": "오픽(OPIc) 등급 올리기",
        "topic": "오픽 말하기 시험 준비",
        "reader": "오픽 IM 등급에서 IH·AL로 올리려는 취업 준비생과 직장인",
        "prior_knowledge": "오픽을 한 번 이상 응시했고 기본 문법과 생활 어휘는 알지만, 질문을 들으면 문장을 길게 잇지 못함",
        "problem": "단어와 표현은 외웠는데 막상 말이 막히고, 무엇부터 고쳐야 등급이 오르는지 판단하지 못함",
        "outcome": "자기 답변에서 막히는 지점 하나를 찾고, 다음 7일 동안 매일 할 연습 한 가지를 정할 수 있음",
        "tone": "해요체로 차분하게 설명해요. 시험 불안을 키우지 않고 오늘 할 수 있는 연습 하나를 먼저 보여 줘요. 훈계·등급 보장·단기 합격 과장 금지",
        "language": "ko",
        "cta": "무료 오픽 7일 연습표 받기",
    },
    "exam-info-processing": {
        "axis": "A",
        "label": "정보처리기사 합격",
        "topic": "정보처리기사 필기·실기 준비",
        "reader": "비전공이거나 실무 경험이 짧은 정보처리기사 수험생",
        "prior_knowledge": "기본 컴퓨터 용어는 알지만 SQL·네트워크·소프트웨어 공학 용어를 체계적으로 배운 적은 없음",
        "problem": "기출을 풀어도 같은 유형에서 반복해서 틀리고, 암기 범위가 넓어 남은 기간에 어디에 시간을 써야 할지 모름",
        "outcome": "자주 틀리는 유형 하나의 풀이 기준을 설명하고, 시험 D-30 복습 순서를 적을 수 있음",
        "tone": "해요체로 또박또박 설명해요. 용어는 처음 나올 때 한 줄로 풀이하고, 훈계 없이 오늘 풀 문제를 제시해요. 합격률·합격 보장 과장 금지",
        "language": "ko",
        "cta": "무료 D-30 복습 플래너 받기",
    },
    "transfer-admission": {
        "axis": "A",
        "label": "대학 편입 준비",
        "topic": "대학 편입 영어·전형 준비",
        "reader": "편입을 처음 준비하는 2~3학년 재학생과 휴학생",
        "prior_knowledge": "수능 영어 수준의 독해 경험. 편입 전형 구조와 대학별 모집 요강을 읽는 법은 모름",
        "problem": "요강과 합격 수기는 많은데 내 상황에서 무엇을 먼저 정해야 하는지 판단 기준이 없음",
        "outcome": "지원 가능한 전형 유형을 구분하고, 이번 달 안에 확인할 요강 항목과 공부 순서를 정할 수 있음",
        "tone": "해요체로 담담하게 설명해요. 불안을 자극하지 않고 확인할 공식 요강 항목을 짚어요. 특정 대학 합격 보장·경쟁률 과장 금지",
        "language": "ko",
        "cta": "무료 편입 준비 점검표 받기",
    },
    "productivity-automation": {
        "axis": "B",
        "label": "생산성·업무 자동화",
        "topic": "반복 업무 자동화와 AI 도구 활용",
        "reader": "AI와 자동화 도구로 매주 반복되는 정리·보고 시간을 줄이려는 직장인",
        "prior_knowledge": "엑셀·구글 시트·챗봇 사용 경험. 코드 작성이나 API 연결 경험은 가정하지 않음",
        "problem": "자동화 도구 소개는 많이 봤지만 내 업무 중 무엇을 어떤 도구로 바꿀지 정하지 못하고 시도하다 멈춤",
        "outcome": "반복 업무 하나를 골라 입력·판단·결과 흐름으로 쪼개고, 이번 주에 자동화할 첫 단계를 정할 수 있음",
        "tone": "해요체로 실제 화면 흐름을 구체적으로 설명해요. 도구 이름보다 판단 기준을 먼저 보여 줘요. 절약 시간 수치·수익 보장 과장 금지",
        "language": "ko",
        "cta": "무료 반복 업무 점검표 받기",
    },
}


def build_brief(preset, overrides=None):
    """프리셋에 덮어쓰기를 적용한 브리프를 돌려준다. 빈 문자열은 프리셋 값을 유지한다."""
    if not isinstance(preset, str) or preset not in PRESETS:
        raise WorkflowError(f"알 수 없는 독자 프리셋입니다: {preset!r}. 사용 가능: {', '.join(PRESETS)}")
    base = PRESETS[preset]
    brief = {"preset": preset, "axis": base["axis"], "label": base["label"], **{field: base.get(field, '') for field in OVERRIDE_FIELDS}}
    if overrides is None:
        overrides = {}
    if not isinstance(overrides, dict):
        raise WorkflowError("브리프 덮어쓰기는 필드 이름과 문자열 값의 객체여야 합니다")
    for field, value in overrides.items():
        if field not in OVERRIDE_FIELDS:
            raise WorkflowError(f"브리프에 없는 필드입니다: {field!r}. 사용 가능: {', '.join(OVERRIDE_FIELDS)}")
        if not isinstance(value, str):
            raise WorkflowError(f"브리프 필드 {field!r}는 문자열이어야 합니다")
        text = value.strip()
        if len(text) > MAX_FIELD_LENGTH:
            raise WorkflowError(f"브리프 필드 {field!r}는 {MAX_FIELD_LENGTH}자 이하여야 합니다")
        if text:
            brief[field] = text
    if brief["language"] not in LANGUAGES:
        raise WorkflowError(f"지원하지 않는 언어입니다: {brief['language']!r}. 사용 가능: {', '.join(LANGUAGES)}")
    return brief


def normalise_brief(brief):
    """저장된 브리프 객체(또는 None)를 검증해 정규화한다. None이면 기본 프리셋."""
    if brief is None:
        return build_brief(DEFAULT_PRESET)
    if not isinstance(brief, dict):
        raise WorkflowError("브리프는 preset 키를 가진 객체여야 합니다")
    return build_brief(brief.get("preset"), {field: brief[field] for field in OVERRIDE_FIELDS if field in brief})


def brief_for_job(job):
    return normalise_brief((job or {}).get("brief"))


def presets_payload():
    return {"default": DEFAULT_PRESET, "languages": list(LANGUAGES), "fields": list(OVERRIDE_FIELDS), "presets": [{"id": key, **preset} for key, preset in PRESETS.items()]}
