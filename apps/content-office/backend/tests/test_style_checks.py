"""Brand voice rules from the owner's voice.md become deterministic checks and prompt text."""
from office.editorial import deterministic_checks, style_issues

GOOD_BODY = "## 먼저 할 일\n\n" + "오픽 IM에서 막힌 분은 이것부터 해요. " * 40 + "\n\n## 왜 그런가\n\n" + "저도 처음엔 이거 몰랐어요. " * 40 + "\n\n## 오늘 해볼 것\n\n퀴즈 세 문제만 풀어 보세요. [E1]"


def packet(body):
    return {"title": "오픽 IM 탈출", "body": body, "evidence": [{"id": "E1", "url": "https://example.com/a", "claim": "근거"}],
            "video": {"title": "오픽", "description": "", "tags": [], "thumbnails": [], "scenes": [{"narration": "세 가지만 기억해요", "caption": "세 가지", "visual": "표"}] * 3}}


def test_clean_text_has_no_style_issues():
    assert style_issues(packet(GOOD_BODY)) == []
    assert deterministic_checks(packet(GOOD_BODY))["passed"] is True


def test_em_dash_and_repeated_thought_phrase_are_flagged():
    body = GOOD_BODY.replace("이것부터 해요.", "이것부터 — 해요.")
    assert any("줄표" in issue for issue in style_issues(packet(body)))
    repeated = GOOD_BODY + "\n\n효과가 있다고 생각합니다. 도움이 된다고 생각합니다. 맞다고 생각합니다."
    assert any("라고 생각합니다" in issue for issue in style_issues(packet(repeated)))


def test_preaching_and_overclaim_phrases_are_flagged_everywhere():
    body = GOOD_BODY + "\n\n포기하지 마세요. 노력하면 됩니다."
    assert any("훈계" in issue for issue in style_issues(packet(body)))
    with_title = packet(GOOD_BODY)
    with_title["video"]["scenes"][0] = {"narration": "3일 완성이에요", "caption": "3일 완성", "visual": "표"}
    issues = style_issues(with_title)
    assert any("과장" in issue and "3일 완성" in issue for issue in issues)


def test_formal_endings_outnumbering_haeyo_is_flagged_but_mixed_is_allowed():
    formal = "## 하나\n\n" + "이렇게 하면 됩니다. " * 60 + "\n\n## 둘\n\n확인했습니다. 정리했습니다.\n\n## 셋\n\n끝입니다. [E1]"
    assert any("해요체" in issue for issue in style_issues(packet(formal)))
    mixed = GOOD_BODY + "\n\n참고로 공식 문서에는 이렇게 적혀 있습니다."
    assert not any("해요체" in issue for issue in style_issues(packet(mixed)))


def test_style_issues_block_deterministic_checks_and_are_listed():
    checks = deterministic_checks(packet(GOOD_BODY + " — 그리고"))
    assert checks["passed"] is False
    assert any("줄표" in issue for issue in checks["issues"])
    assert "문체 규칙" in checks["checks"]


def test_brand_config_carries_voice_rules_and_overclaims():
    from office.brand import load_brand, brand_system_prompt
    brand = load_brand()
    assert "해요체" in brand["voice"] and "줄표" in brand["voice"]
    assert {"무조건 합격", "3일 완성", "뇌과학으로 입증"} <= set(brand["banned"])
    prompt = brand_system_prompt("BASE", brand)
    assert "해요체" in prompt and "뇌과학으로 입증" in prompt
