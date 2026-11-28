"""단서 문장 2차(2026-11-28): 11-27 단어 목록이 놓친 면책, 단서 문장을 잡고, 고치기 뒤에도 남으면 통과시키지 않아요."""
from office.claim_checks import caveat_issues, caveat_report
from office.editorial import BASE, deterministic_checks, idea_instructions
from office.harness_rules import unresolved_must_fix
from test_harness import Stub, good_body, packet, run, verdict

# 사용자가 2026-11-28에 짚은 원고(OG-D003, 11-03 작업)의 단서 문장 네 개. 11-27 검사는 0개를 찾았어요.
REPORTED = [
    "다만 이건 고정된 버전의 computer-use 배포를 전제로 한 주장이라, 일반 운영환경에 그대로 넓혀 읽으면 안 돼요. [E1][E2]",
    "하지만 성과를 보장하는 것은 아니에요. [E4][E5]",
    "이 수치는 저자 실험 범위 안에서만 읽어야 해요.",
    "외부 환경에서 같은 결과가 난다고 말할 수는 없어요. [E4][E5]",
]


def body_with(*paragraphs, headings=("질문", "핵심", "숫자", "오늘 할 일")):
    parts = []
    for heading, paragraph in zip(headings, paragraphs):
        parts.append(f"## {heading}\n{paragraph}")
    return "\n\n".join(parts)


def test_reported_disclaimers_are_all_caught():
    for sentence in REPORTED:
        found = caveat_report("## 하나\n저자들은 경로마다 같은 판단을 하자고 제안해요. " + sentence)
        assert len(found["boilerplate"]) == 1, sentence


def test_reported_draft_shape_goes_to_refine():
    body = body_with("에이전트는 여러 경로로 움직여요. " + REPORTED[0], "경로보다 효과를 먼저 묶어요 [E2].",
                     "저자 보고 결과는 구체적이에요. " + REPORTED[1] + " " + REPORTED[2] + " " + REPORTED[3],
                     "입력 경로와 저장 지점을 적어 보세요.", headings=("질문", "핵심", "숫자는 저자 실험 범위로만 읽어야 해요", "오늘 할 일"))
    issues = caveat_issues(body)
    assert any("면책 문장이에요(4개)" in issue for issue in issues)
    assert any("4개예요(글 전체 2개까지)" in issue for issue in issues)
    assert any("소제목이 글 중간에" in issue for issue in issues)


def test_useful_limits_and_reported_findings_are_not_disclaimers():
    useful = ("## 사례\n실험은 시뮬레이션 안에서만 했고, 추정 물성치는 실제 로봇에 맞춰 보정하지 않았어요 [E1].\n"
              "## 근거\n이번 근거는 21일이라는 기간을 그대로 받아들이기 어렵다고 말해요 [E2].\n"
              "## 사례 둘\n지금 성적만으로 결과를 단정할 수는 없다는 점을 보여 주는 사례예요.\n"
              "## 오늘 할 일\n하지만 오늘 한 문제를 다시 풀면 차이를 직접 볼 수 있어요.")
    found = caveat_report(useful)
    assert found["boilerplate"] == [] and found["caveat_headings"] == []
    assert caveat_issues(useful) == []


def test_one_limit_at_the_end_under_a_limit_heading_is_fine():
    body = good_body() + "\n## 알아 둘 한계\n실험은 고정된 버전 한 가지에서만 했어요. 내 도구에 쓰려면 경로 목록부터 적어 보세요 [E1]."
    assert caveat_issues(body) == []


def test_more_than_two_contrast_openers_are_flagged():
    body = "## 하나\n" + " ".join(f"하지만 {n}번째 설명이에요." for n in range(1, 4))
    assert any("'다만', '하지만'으로 시작하는 문장이 3개" in issue for issue in caveat_issues(body))
    assert not any("시작하는 문장" in issue for issue in caveat_issues("## 하나\n하지만 하나예요. 다만 둘이에요."))


def test_deterministic_checks_send_caveats_to_refine_but_not_for_preserved_originals():
    disclaimer = "\n## 숫자\n" + REPORTED[1]
    flagged = deterministic_checks({**packet(good_body() + disclaimer)})
    assert any("면책 문장" in issue for issue in flagged["issues"])
    preserved = deterministic_checks({**packet(good_body() + disclaimer), "preserve_original": True})
    assert not any("면책 문장" in issue for issue in preserved["issues"])


def test_leftover_disclaimer_keeps_the_draft_out_of_passed_even_when_the_judge_passes():
    stubborn = good_body() + "\n## 숫자\n" + REPORTED[1]
    stub = Stub(judges=[verdict(), verdict()], refines=[stubborn, stubborn])
    result = run(stub, packet(stubborn), w_type="W3", checks_fn=deterministic_checks)
    quality = result["quality"]
    assert quality["advisories"]["model_reviews_passed"] is True
    assert quality["status"] == "needs_review" and quality["critical"] is False
    assert any("면책 문장" in item for item in quality["review_pending"])
    assert "면책, 단서 문장이 남아" in quality["advisories"]["note"]


def test_refine_that_removes_the_disclaimer_passes():
    stub = Stub(judges=[verdict()], refines=[good_body()])
    result = run(stub, packet(good_body() + "\n## 숫자\n" + REPORTED[1]), w_type="W3", checks_fn=deterministic_checks)
    assert stub.calls == ["refine", "judge"]
    assert result["quality"]["status"] == "passed" and result["quality"]["review_pending"] == []


def test_unresolved_must_fix_only_reports_caveat_rules():
    validation = {"issues": ["주소와 근거 표시를 뺀 본문이 300자예요", "한계, 단서 문장이 독자에게 쓸모없는 면책 문장이에요(1개): 'x'"]}
    assert unresolved_must_fix(validation) == [validation["issues"][1]]


def test_writer_prompts_ask_for_one_limit_without_disclaimers():
    assert "면책 문장은 쓰지 않는다" in BASE and "글 전체에서 2개까지" in BASE and "한계만 다루는 소제목을 글 중간에" in BASE
    text = idea_instructions("W3")
    assert "한계는 글 전체에서 1~2문장만" in text and "원문이 밝힌 한계가 있으면 여기서 한 문장" not in text
