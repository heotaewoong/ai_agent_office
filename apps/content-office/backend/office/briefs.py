"""독자 브리프: 사업 축별 프리셋과 작업별 덮어쓰기.

축 A는 시험 합격·편입처럼 불안한 학습자, 축 B는 AI·자동화로 시간을 아끼려는 직장인이다.
축 C는 학습법과 뇌과학, 축 D는 자기계발, 축 E는 일상생활 꿀팁이다. 축이 화면의 큰 분야이고 프리셋이 세부 항목이다.
생성·비평·평가·수정 호출은 모두 같은 브리프를 받는다. 브리프는 사람 승인을 만들지 않는다.
"""
from __future__ import annotations

from .store import WorkflowError

OVERRIDE_FIELDS = ("topic", "reader", "prior_knowledge", "problem", "current_solution", "outcome", "goal", "tone", "language", "cta")
LANGUAGES = ("ko", "en")
DEFAULT_PRESET = "ai-agent"
MAX_FIELD_LENGTH = 500

# 화면의 큰 분야. 프리셋의 axis 값과 같다. evidence는 화면 안내용 문구이며 승인이나 검증을 대신하지 않는다.
AXES = {
    "source": {"label": "내 원문", "evidence": "원문에 있는 내용만 사용"},
    "B": {"label": "AI 활용과 자동화", "evidence": "공식 문서 우선. 버전·가격·약관은 공식 출처에서 다시 확인"},
    "A": {"label": "시험과 자격증", "evidence": "일정·접수·합격 기준은 시행 기관 공고에서 확인"},
    "C": {"label": "학습법과 뇌과학", "evidence": "논문 근거 필수. 연구 대상과 조건을 함께 표기"},
    "D": {"label": "자기계발", "evidence": "경험은 출처를 밝히고 수치 주장에는 근거 필요"},
    "E": {"label": "일상생활 꿀팁", "evidence": "직접 해 본 것과 조사한 것을 구분. 가격·조건은 확인 날짜 표기"},
}

PRESETS = {
    "source-faithful": {
        "axis": "source", "label": "내 원문 중심 · 주제 추정 없음",
        "topic": "사용자가 제공한 원문의 주제", "reader": "이 원문의 주제와 경험에 관심 있는 독자",
        "prior_knowledge": "원문에 명시된 범위를 넘어 배경지식을 가정하지 않음",
        "problem": "원문의 경험·주장·자료를 이해하고 필요한 조건을 확인하고 싶음",
        "outcome": "원문에서 확인할 수 있는 내용과 미확인 조건을 구분할 수 있음",
        "tone": "원문의 주제·경험·수치·상품 및 할인 조건을 보존한다. 다른 주제의 사례나 광고 효과를 만들어 넣지 않는다. 파생 문구는 자연스러운 해요체로 쓴다.",
        "language": "ko", "cta": "원문에 있는 다음 행동과 조건 확인",
    },
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
    "learning-memory": {
        "axis": "C",
        "label": "공부법과 기억",
        "topic": "기억에 남는 공부법",
        "reader": "공부 시간을 늘려도 성과가 안 나서 방법을 바꾸고 싶은 대학생과 직장인",
        "prior_knowledge": "밑줄 긋기와 반복 읽기 위주로 공부해 왔고 인출 연습·간격 반복 같은 용어는 처음 들음",
        "problem": "오래 앉아 있어도 며칠 지나면 잊어버리고, 어떤 공부법이 실제로 효과가 있는지 가릴 기준이 없음",
        "outcome": "지금 쓰는 공부법 하나를 근거가 확인된 방법으로 바꾸고 이번 주 복습 일정을 적을 수 있음",
        "tone": "해요체로 차분하게 설명해요. 효과는 논문·메타분석에서 확인한 범위만 말하고 연구 대상과 조건을 함께 밝혀요. 근거 없는 효과 단정·'무조건' 표현·성적 보장 금지",
        "language": "ko",
        "cta": "",
    },
    "learning-focus": {
        "axis": "C",
        "label": "집중력",
        "topic": "공부와 업무 집중력",
        "reader": "공부나 업무 중에 자꾸 흐름이 끊겨서 집중 시간을 늘리고 싶은 대학생과 직장인",
        "prior_knowledge": "스마트폰 알림과 멀티태스킹이 방해된다는 건 알지만 주의력 연구 용어는 모름",
        "problem": "집중하려고 마음먹어도 금방 딴짓을 하게 되고, 환경과 습관 중 무엇부터 바꿔야 할지 모름",
        "outcome": "집중을 끊는 원인 하나를 찾고 내일 한 번 시도할 환경 변화 한 가지를 정할 수 있음",
        "tone": "해요체로 구체적인 상황을 들어 설명해요. 연구에서 확인한 내용과 일반적인 조언을 구분해서 써요. 의지력 탓하기·집중력 향상 수치 보장·근거 없는 뇌과학 표현 금지",
        "language": "ko",
        "cta": "",
    },
    "learning-habit": {
        "axis": "C",
        "label": "습관과 동기",
        "topic": "습관 만들기와 동기 유지",
        "reader": "공부나 운동을 꾸준히 하려다 번번이 며칠 만에 그만두는 대학생과 직장인",
        "prior_knowledge": "작심삼일 경험이 여러 번 있고 습관 형성 연구는 접해 본 적 없음",
        "problem": "의지가 약해서 못 한다고 생각하고, 얼마나 반복해야 습관이 되는지와 끊겼을 때 어떻게 이어 갈지 모름",
        "outcome": "만들고 싶은 습관 하나를 시간과 장소가 정해진 작은 행동으로 바꿔 적을 수 있음",
        "tone": "해요체로 담담하게 설명해요. 습관 형성 기간처럼 사람마다 차이가 큰 수치는 범위와 출처를 함께 밝혀요. 자책 유도·'21일이면 된다' 같은 근거 없는 단정·성공 보장 금지",
        "language": "ko",
        "cta": "",
    },
    "learning-sleep-exercise": {
        "axis": "C",
        "label": "수면과 운동",
        "topic": "학습 컨디션을 위한 수면과 운동",
        "reader": "시험이나 업무 때문에 잠과 운동을 줄이고 있는 대학생과 직장인",
        "prior_knowledge": "잠이 부족하면 안 좋다는 건 알지만 수면과 기억, 운동과 인지의 관계를 다룬 연구는 모름",
        "problem": "시간이 없어서 잠과 운동부터 줄이는데, 그게 공부 효율에 얼마나 손해인지 판단할 근거가 없음",
        "outcome": "이번 주 일정에서 지킬 수면 또는 운동 기준 한 가지를 정할 수 있음",
        "tone": "해요체로 차분하게 설명해요. 논문에서 확인한 내용만 말하고 동물 실험·소규모 연구는 그 한계를 밝혀요. 진단·치료 조언을 하지 않고 건강 문제가 있으면 전문가 상담을 안내해요. 효과 과장·공포 유도 금지",
        "language": "ko",
        "cta": "",
    },
    "growth-mindset": {
        "axis": "D",
        "label": "마인드셋",
        "topic": "실패와 불안을 다루는 마음가짐",
        "reader": "시험·취업·일에서 결과가 안 나와 위축된 대학생과 직장인",
        "prior_knowledge": "자기계발 영상과 글을 많이 봤지만 실제 행동으로 이어진 경험은 적음",
        "problem": "남과 비교하며 조급해지고, 좋은 말을 들어도 내 상황에 적용할 구체적인 방법이 남지 않음",
        "outcome": "지금 상황에서 통제할 수 있는 것 하나를 골라 이번 주에 할 행동으로 적을 수 있음",
        "tone": "해요체로 담담하게 써요. 실제 경험은 누구의 경험인지 밝히고 수치 주장에는 출처를 붙여요. 훈계·성공 보장·가짜 경험·근거 없는 심리학 용어 금지",
        "language": "ko",
        "cta": "",
    },
    "growth-time": {
        "axis": "D",
        "label": "시간 관리",
        "topic": "하루 시간 관리와 우선순위",
        "reader": "할 일은 많은데 하루가 어떻게 지나갔는지 모르겠는 대학생과 직장인",
        "prior_knowledge": "할 일 목록이나 플래너를 써 봤지만 오래 유지하지 못함",
        "problem": "계획은 세우는데 지키지 못하고, 무엇을 먼저 해야 할지 매번 다시 고민함",
        "outcome": "내일 할 일 중 가장 중요한 한 가지와 그 일을 할 시간대를 정할 수 있음",
        "tone": "해요체로 실제 하루 흐름을 예로 들어 설명해요. 도구 이름보다 판단 기준을 먼저 보여 줘요. 절약 시간 수치 과장·특정 방법만 정답이라는 단정 금지",
        "language": "ko",
        "cta": "",
    },
    "growth-career": {
        "axis": "D",
        "label": "취업과 면접",
        "topic": "취업 준비와 면접 대비",
        "reader": "첫 취업이나 이직을 준비하는 대학생과 주니어 직장인",
        "prior_knowledge": "자기소개서를 써 봤고 면접 경험이 적거나 없음",
        "problem": "예상 질문 목록은 많은데 내 경험을 어떻게 답으로 풀어야 할지 모르고, 면접에서 말이 길어지거나 막힘",
        "outcome": "내 경험 하나를 상황·행동·결과 순서로 1분 안에 말할 수 있게 정리할 수 있음",
        "tone": "해요체로 구체적인 답변 예시를 보여 줘요. 실제 경험은 누구의 경험인지 밝혀요. 합격 보장·특정 회사 내부 기준 단정·가짜 합격 후기 금지",
        "language": "ko",
        "cta": "",
    },
    "tips-life": {
        "axis": "E",
        "label": "생활 정보",
        "topic": "일상에서 바로 쓰는 생활 정보",
        "reader": "생활 속 번거로운 일을 더 쉽게 처리하고 싶은 대학생과 직장인",
        "prior_knowledge": "관련 정보를 검색해 본 적은 있지만 정리된 순서로 따라 해 본 적은 없음",
        "problem": "방법은 여러 개 나오는데 내 상황에 맞는 것을 고르기 어렵고 따라 하다 중간에 막힘",
        "outcome": "오늘 바로 해 볼 수 있는 방법 한 가지와 주의할 점을 알 수 있음",
        "tone": "해요체로 순서대로 짧게 설명해요. 직접 해 본 내용과 조사한 내용을 구분해요. 가격·조건·제도는 확인한 날짜와 출처를 밝히고 효과 과장·광고성 단정 금지",
        "language": "ko",
        "cta": "",
    },
    "tips-tools": {
        "axis": "E",
        "label": "도구 추천",
        "topic": "공부와 업무에 쓰는 도구 고르기",
        "reader": "앱이나 도구를 바꿔 보고 싶지만 무엇을 골라야 할지 모르는 대학생과 직장인",
        "prior_knowledge": "유명한 도구 이름은 들어 봤지만 직접 비교해 본 적은 없음",
        "problem": "추천 글마다 말이 달라서 내 용도에 맞는 도구를 고르는 기준이 없음",
        "outcome": "내 용도에 맞는 도구를 고르는 기준 두 가지를 알고 후보 하나를 정해 써 볼 수 있음",
        "tone": "해요체로 실제 사용 화면과 상황을 들어 설명해요. 직접 써 본 것과 조사한 것을 구분해요. 가격·요금제·기능은 확인한 날짜와 공식 출처를 밝히고 협찬처럼 보이는 단정·무조건 추천 금지",
        "language": "ko",
        "cta": "",
    },
}


EXPERIENCE_FIRST_TONE = ("내 경험 중심: 사용자가 준 원문의 경험·주장·수치를 1차 근거로 삼는다. "
                         "원문에 없는 1인칭 경험·사례·수치를 만들어 넣지 않는다. 외부 근거는 원문을 보충할 때만 쓰고 출처를 밝힌다.")


def experience_first_overrides(preset):
    """'내 경험 중심' 스위치: 고른 프리셋은 그대로 두고 말투 칸에 원문 우선 규칙을 덧붙인다."""
    if not isinstance(preset, str) or preset not in PRESETS:
        raise WorkflowError(f"알 수 없는 독자 프리셋입니다: {preset!r}. 사용 가능: {', '.join(PRESETS)}")
    tone = PRESETS[preset]["tone"].strip()
    if EXPERIENCE_FIRST_TONE in tone:
        return {"tone": tone}
    return {"tone": (tone + " " + EXPERIENCE_FIRST_TONE).strip()[:MAX_FIELD_LENGTH]}


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
    return {"default": DEFAULT_PRESET, "languages": list(LANGUAGES), "fields": list(OVERRIDE_FIELDS), "axes": [{"id": key, **axis} for key, axis in AXES.items()], "presets": [{"id": key, **preset} for key, preset in PRESETS.items()]}
