import pytest
from office.packaging import attach_packaging, require_packaging, validate_packaging
from office.store import Store, WorkflowError


def brief(**changes):
    base = {
        "titles": ["Claude 팀으로 블로그 자동화", "AI 팀이 블로그를 쓰는 법", "블로그 자동화 3단계"],
        "thumbnails": [{"text": "AI 팀 블로그", "visual": "작업 화면"}, {"text": "3단계", "visual": "표"}, {"text": "직접 해봄", "visual": "결과 화면"}],
        "hook": "블로그 자동화를 Claude 팀으로 나눠 맡긴 결과부터 보여 드립니다",
        "logline": "한 명이 에이전트 팀으로 블로그 한 편을 끝내는 과정",
        "reasons": ["검색 수요가 있음", "실제 작업 화면으로 증명 가능"],
    }
    return {**base, **changes}


def test_complete_packaging_passes():
    assert validate_packaging(brief()) == {"passed": True, "issues": []}


def test_hook_must_carry_title_promise():
    report = validate_packaging(brief(hook="오늘은 날씨 이야기를 합니다"))
    assert "훅이 제목의 약속을 이어받지 않습니다" in report["issues"]


def test_thumbnail_text_limit():
    long = brief(thumbnails=[{"text": "아주아주아주긴썸네일문구입니다", "visual": "x"}] * 3)
    assert any("썸네일 1안" in issue for issue in validate_packaging(long)["issues"])


def test_idea_job_requires_packaging_before_drafting(tmp_path):
    store = Store(tmp_path)
    job = store.create_job({"id": "idea-1", "title": "기획", "url": "https://example.com", "origin": "idea"})
    with pytest.raises(WorkflowError, match="패키징"):
        require_packaging(store.job(job["id"]))
    attach_packaging(store, job["id"], brief(), "local-operator")
    require_packaging(store.job(job["id"]))


def test_rss_job_keeps_existing_flow(tmp_path):
    store = Store(tmp_path)
    job = store.create_job({"id": "rss-1", "title": "뉴스", "url": "https://example.com"})
    require_packaging(store.job(job["id"]))


def test_korean_particles_do_not_break_hook_promise():
    report = validate_packaging(brief(chosen_title="AI 팀이 블로그를 쓰는 법", hook="블로그 글을 팀에게 맡긴 결과부터 봅니다"))
    assert "훅이 제목의 약속을 이어받지 않습니다" not in report["issues"]
    assert validate_packaging(brief(chosen_title="AI 팀이 블로그를 쓰는 법", hook="오늘은 날씨 이야기를 합니다"))["issues"] == ["훅이 제목의 약속을 이어받지 않습니다"]


def test_blank_titles_and_thumbnail_text_are_rejected():
    report = validate_packaging(brief(titles=["", " ", "제목"], thumbnails=[{"text": " ", "visual": "a"}, {"text": "b", "visual": "b"}, {"text": "c", "visual": "c"}]))
    assert not report["passed"]
    assert "제목 1안이 비어 있습니다" in report["issues"] and "제목 2안이 비어 있습니다" in report["issues"]
    assert "썸네일 1안 글자가 비어 있습니다" in report["issues"]


def test_existing_body_uses_fixed_title_without_reselecting_packaging():
    require_packaging({'article': {'origin': 'idea'}, 'source_packet': {'title': '이미 확정', 'body': '이미 작성한 원고'}, 'packaging': None})
