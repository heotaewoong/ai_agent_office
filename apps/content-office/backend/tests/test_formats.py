import pytest
from office.formats import check_shorts, plan_formats, retention_beats
from office.store import WorkflowError


def test_formats_branch_only_from_approved_source():
    with pytest.raises(WorkflowError, match="승인①"):
        plan_formats("v2", "v1", ["shorts"])
    plans = plan_formats("v1", "v1", ["blog_naver", "shorts"])
    assert [p["format"] for p in plans] == ["blog_naver", "shorts"]
    assert {p["parent_hash"] for p in plans} == {"v1"}
    assert plans[0]["delivery"] == "manual_paste"


def test_unknown_format_is_rejected():
    with pytest.raises(WorkflowError, match="알 수 없는 포맷"):
        plan_formats("v1", "v1", ["tiktok"])


def test_shorts_length_and_hook():
    assert check_shorts([2.5, 30, 40]) == []
    issues = check_shorts([4.0, 100, 100])
    assert any("180초" in i for i in issues) and any("훅" in i for i in issues)


def test_retention_beats():
    assert retention_beats(400) == [60, 180, 360]
    assert retention_beats(150) == [60]
