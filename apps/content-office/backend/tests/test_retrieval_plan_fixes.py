"""2026-11-26 검색 골든셋 시험0에서 나온 조사 계획 문제를 고친 것을 지킨다."""
from office.external_research import build_queries, guess_area, library_verdict, research_plan


def test_english_names_with_korean_particles_and_tool_names_are_ai_topics():
    for title in ("긴 답변 대신 짧은 판단만, Decisions API는 어디에 쓰나", "AI로 만든 유튜브 영상, 수익 창출 되나요",
                  "NotebookLM으로 강의 자료 요약하기", "Perplexity로 출처 있는 시장조사", "Make 요금제 개편, 바뀌는 것"):
        assert guess_area(title) == "B", title


def test_study_words_and_life_words_do_not_steal_other_areas():
    assert guess_area("뽀모도로 25분이 정말 맞을까") == "C"
    assert guess_area("공부할 때 이 소리 틀었더니") == "C"
    assert guess_area("한 주를 30분에 정리하는 주간 회고 루틴") == "D"
    assert guess_area("노트북 수리비 61만 원, 나흘의 기록") == "E"
    assert guess_area("make a plan for the week") != "B"


def test_sync_is_not_translated_as_motivation():
    english = build_queries("옵시디언 PC 안드로이드 동기화 방법")["english"]
    assert "sync" in english and "motivation" not in english
    assert "pomodoro" in build_queries("뽀모도로 25분이 정말 맞을까")["english"]


def test_number_and_policy_claims_ask_for_facts():
    assert research_plan("습관 만들기 66일은 사실일까", kind="W3")["fact"]["need"] == "required"
    assert research_plan("AI 이미지, 상업적으로 써도 될까", kind="W3")["fact"]["need"] == "required"


def test_missing_tool_name_lowers_the_library_verdict_one_step():
    assert library_verdict(3, 0.70)["verdict"] == "correct"
    assert library_verdict(3, 0.70, names_missing=True)["verdict"] == "ambiguous"
    assert library_verdict(3, 0.55, names_missing=True)["verdict"] == "incorrect"
    assert library_verdict(3, 0.40, names_missing=True)["verdict"] == "incorrect"