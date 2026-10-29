import hashlib
import json

import pytest

from office.channel_handoff import write_channel_handoffs
from office.channels import CHANNELS
from office.store import WorkflowError


SOURCE_HASH = "a" * 64


def packet():
    return {"title": "구문부터 연습해요", "body": "## 공부 순서\n\n오늘은 문장의 주어를 찾아요.\n\n합격을 보장하는 방법은 아닙니다.",
            "evidence": [{"url": "https://example.invalid/guide"}, {"url": "https://example.invalid/guide"}]}


def read_manifest(paths):
    return json.loads(next(p for p in paths if p.name == "channel-handoff.json").read_text(encoding="utf-8"))


def test_handoffs_preserve_source_language_and_manual_delivery_boundary(tmp_path):
    paths = write_channel_handoffs(packet(), tmp_path, source_hash=SOURCE_HASH, language="ko")
    assert len(paths) == 6 and all(p.parent == tmp_path for p in paths)
    manifest = read_manifest(paths)
    assert manifest["source_hash"] == SOURCE_HASH
    assert manifest["external_published"] is manifest["external_draft_created"] is False
    entries = {row["channel_key"]: row for row in manifest["channels"]}
    assert entries["threads_main"]["state"] == "draft_ready"
    assert entries["linkedin_personal"]["state"] == "draft_ready"
    assert "합격을 보장하는 방법은 아닙니다." in (tmp_path / "linkedin-personal.txt").read_text(encoding="utf-8")
    assert entries["instagram_main"]["state"] == "needs_review"
    assert entries["instagram_english"]["state"] == "needs_review"
    assert any("언어" in issue for issue in entries["instagram_english"]["issues"])
    assert any("주소" in issue for issue in entries["x_main"]["issues"])
    for row in entries.values():
        content = (tmp_path / row["file"]).read_text(encoding="utf-8")
        assert content.count("https://example.invalid/guide") == 1
        assert "오늘은 문장의 주어를 찾아요." in content
        assert row["sha256"] == hashlib.sha256((tmp_path / row["file"]).read_bytes()).hexdigest()
        assert row["requires_release_approval"] is True
        assert row["external_draft_created"] is row["external_published"] is False
        assert row["source_hash"] == SOURCE_HASH


def test_long_paragraphs_are_not_silently_cut_and_are_marked_for_review(tmp_path):
    approved = {"title": "실제 조건", "body": "가" * 3100 + " 조건이 있어요.", "evidence": []}
    rows = read_manifest(write_channel_handoffs(approved, tmp_path, source_hash=SOURCE_HASH, language="ko"))["channels"]
    assert all(row["state"] == "needs_review" for row in rows)
    assert all(any("글자 수" in issue for issue in row["issues"]) for row in rows)
    assert all("조건이 있어요." in (tmp_path / row["file"]).read_text(encoding="utf-8") for row in rows)


def test_unknown_language_and_missing_channel_configuration_are_not_ready(tmp_path):
    rows = read_manifest(write_channel_handoffs(packet(), tmp_path, source_hash=SOURCE_HASH, channels=[]))["channels"]
    assert all(row["state"] == "needs_review" for row in rows)
    assert all(any("언어" in issue for issue in row["issues"]) for row in rows)
    assert all(any("주소" in issue for issue in row["issues"]) for row in rows)


def test_runtime_channel_urls_override_defaults_and_only_allowlisted_metadata_is_exported(tmp_path):
    channels = [{**CHANNELS["threads_main"], "public_url": "https://www.threads.com/@approved", "credentials_configured": True,
                 "refresh_token": "DO_NOT_EXPORT", "external_account_id": "PRIVATE_ACCOUNT"}]
    rows = read_manifest(write_channel_handoffs(packet(), tmp_path, source_hash=SOURCE_HASH, language="ko", channels=channels))["channels"]
    row = next(row for row in rows if row["channel_key"] == "threads_main")
    assert row["public_url"] == "https://www.threads.com/@approved" and row["state"] == "draft_ready"
    raw = (tmp_path / "channel-handoff.json").read_text(encoding="utf-8")
    assert "DO_NOT_EXPORT" not in raw and "PRIVATE_ACCOUNT" not in raw and "credentials_configured" not in raw


@pytest.mark.parametrize("source_hash", [None, "", "../unsafe", "a" * 63])
def test_handoff_rejects_unbound_source_before_creating_files(tmp_path, source_hash):
    with pytest.raises(WorkflowError, match="해시"):
        write_channel_handoffs(packet(), tmp_path, source_hash=source_hash, language="ko")
    assert not list(tmp_path.iterdir())


@pytest.mark.parametrize("body", ["", "## 제목뿐인 본문"])
def test_empty_excerpt_is_not_a_ready_draft(tmp_path, body):
    with pytest.raises(WorkflowError):
        write_channel_handoffs({**packet(), "body": body}, tmp_path, source_hash=SOURCE_HASH, language="ko")
    assert not list(tmp_path.iterdir())


def test_same_inputs_generate_identical_files(tmp_path):
    first = write_channel_handoffs(packet(), tmp_path, source_hash=SOURCE_HASH, language="ko")
    before = {path.name: path.read_bytes() for path in first}
    after = write_channel_handoffs(packet(), tmp_path, source_hash=SOURCE_HASH, language="ko")
    assert before == {path.name: path.read_bytes() for path in after}
