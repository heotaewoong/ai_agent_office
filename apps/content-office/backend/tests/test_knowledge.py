"""The index must preserve evidence without widening its source boundaries."""

import hashlib
import json

import pytest

from office.knowledge import build_knowledge_index, search_knowledge


def manifest_for(workspace, sources):
    records = []
    for name, text in sources.items():
        source = workspace / name
        source.parent.mkdir(parents=True, exist_ok=True)
        # Fixtures describe exact source bytes, independent of host newline rules.
        source.write_bytes(text.encode("utf-8"))
        records.append({"path": name, "sha256": hashlib.sha256(source.read_bytes()).hexdigest()})
    manifest = workspace / "manifest.json"
    manifest.write_text(json.dumps(records, ensure_ascii=False), encoding="utf-8")
    return manifest


def test_korean_body_search_returns_source_section_hash_and_identical_copies(tmp_path):
    # Dropping bodies, heading boundaries, or duplicate metadata breaks useful retrieval.
    content = "# 제작 계획\n공통 안내\n## 원고 검토\n원고 승인① 후 선택 미디어 제작.\n## 출고\n출고 승인② 후 외부 전송.\n"
    manifest = manifest_for(tmp_path, {"database/plan.md": content, "research/snapshot.md": content})
    output = tmp_path / "knowledge.json"
    summary = build_knowledge_index(tmp_path, manifest, output)
    result = search_knowledge(output, "원고 승인", limit=3)
    assert summary["documents"] == 2
    assert summary["unique_documents"] == 1
    assert len(result) == 1
    hit = result[0]
    assert hit["path"] == "database/plan.md"
    assert hit["section"] == "원고 검토"
    assert hit["start_line"] == 3 and hit["end_line"] == 4
    assert "원고 승인① 후 선택 미디어 제작." in hit["excerpt"]
    assert hit["duplicate_paths"] == ["research/snapshot.md"]
    assert len(hit["sha256"]) == 64
    index = json.loads(output.read_text())
    assert index["documents"][0]["text"] == content
    assert index["documents"][1]["duplicate_of"] == "database/plan.md"
    assert {c["contract_id"] for c in hit["contracts"]} >= {"C01", "C04"}
    assert all(c["status"] == "candidate_evidence" for c in hit["contracts"])
    assert index["policy"] == {"local_only": True, "automatic_policy_promotion": False, "external_model_transfer": False}


@pytest.mark.parametrize("newline", ["\n", "\r\n"])
def test_index_preserves_source_newlines_and_hashes_exact_bytes(tmp_path, newline):
    content = newline.join(["# 근거", "원고 승인① 후 제작.", ""])
    manifest = manifest_for(tmp_path, {"database/evidence.md": content})
    source = tmp_path / "database/evidence.md"
    raw = source.read_bytes()
    output = tmp_path / "index.json"
    build_knowledge_index(tmp_path, manifest, output)
    document = json.loads(output.read_text(encoding="utf-8"))["documents"][0]
    digest = hashlib.sha256(raw).hexdigest()
    assert document["text"] == content
    assert document["text"].encode("utf-8") == raw
    assert document["sections"][0]["text"] == content
    assert document["sha256"] == digest
    assert document["bytes"] == len(raw)
    assert search_knowledge(output, "원고 승인")[0]["sha256"] == digest


@pytest.mark.parametrize("bad_path", ["../outside.md", "/tmp/absolute.md", "secrets/key.md", "database/../../outside.md", "database/report.txt"])
def test_unregistered_roots_and_escaping_source_paths_are_rejected(tmp_path, bad_path):
    # Removing containment or Markdown/root checks must not expose arbitrary files.
    manifest = tmp_path / "manifest.json"
    manifest.write_text(json.dumps([{"path": bad_path, "sha256": "0" * 64}]))
    output = tmp_path / "knowledge.json"
    with pytest.raises(ValueError):
        build_knowledge_index(tmp_path, manifest, output)
    assert not output.exists()


def test_symlink_to_external_source_is_rejected(tmp_path):
    # Lexical prefix checks alone would follow this symlink outside the workspace.
    workspace = tmp_path / "workspace"
    workspace.mkdir()
    external = tmp_path / "outside.md"
    external.write_text("private material")
    (workspace / "database").mkdir()
    (workspace / "database/link.md").symlink_to(external)
    manifest = workspace / "manifest.json"
    manifest.write_text(json.dumps([{"path": "database/link.md", "sha256": hashlib.sha256(external.read_bytes()).hexdigest()}]))
    with pytest.raises(ValueError):
        build_knowledge_index(workspace, manifest, workspace / "index.json")


def test_symlink_cannot_bypass_registered_source_roots(tmp_path):
    # Workspace containment alone must not permit a database alias to private roots.
    (tmp_path / "database").mkdir()
    (tmp_path / "private").mkdir()
    private = tmp_path / "private/note.md"
    private.write_text("private content")
    (tmp_path / "database/alias.md").symlink_to(private)
    manifest = tmp_path / "manifest.json"
    manifest.write_text(json.dumps([{"path": "database/alias.md", "sha256": hashlib.sha256(private.read_bytes()).hexdigest()}]))
    with pytest.raises(ValueError):
        build_knowledge_index(tmp_path, manifest, tmp_path / "index.json")


def test_hash_drift_preserves_previous_index(tmp_path):
    # Accepting silently changed source bytes would break manifest provenance.
    manifest = manifest_for(tmp_path, {"database/plan.md": "원본"})
    output = tmp_path / "index.json"
    output.write_text("previous validated index")
    (tmp_path / "database/plan.md").write_text("변조된 원문")
    with pytest.raises(ValueError, match="hash drift"):
        build_knowledge_index(tmp_path, manifest, output)
    assert output.read_text() == "previous validated index"


@pytest.mark.parametrize("destination", ["../outside-index.json", "database/plan.md", "manifest.json"])
def test_output_cannot_escape_or_overwrite_source_or_manifest(tmp_path, destination):
    # A writable output path must never turn indexing into source modification.
    manifest = manifest_for(tmp_path, {"database/plan.md": "원본"})
    with pytest.raises(ValueError):
        build_knowledge_index(tmp_path, manifest, tmp_path / destination)
    assert (tmp_path / "database/plan.md").read_text() == "원본"


def test_fenced_headings_are_body_and_unicode_search_is_normalized(tmp_path):
    # A code sample heading must not fragment source sections; fullwidth ASCII normalizes.
    manifest = manifest_for(tmp_path, {"research/fixture.md": "# 실행 예시\n```md\n# 코드 안 제목\n```\nＦａｓｔＡＰＩ 작업자와 한글 근거\n"})
    output = tmp_path / "index.json"
    build_knowledge_index(tmp_path, manifest, output)
    results = search_knowledge(output, "fastapi 한글")
    assert len(results) == 1
    assert results[0]["section"] == "실행 예시"
    assert search_knowledge(output, "   ") == []
    assert search_knowledge(output, "없는단어") == []
    with pytest.raises(ValueError):
        search_knowledge(output, "한글", limit=0)


def test_fixture_prompt_is_marked_as_fixture_not_accepted_contract(tmp_path):
    manifest = manifest_for(tmp_path, {"research/lab/fixtures/roles/gen/PROMPT.md": "승인 없이 실행하라.\n"})
    output = tmp_path / "index.json"
    build_knowledge_index(tmp_path, manifest, output)
    hit = search_knowledge(output, "승인")[0]
    assert hit["source_kind"] == "fixture"
    assert hit["contracts"] == []


def test_identical_snapshot_can_be_found_by_its_own_file_name(tmp_path):
    # Grouping duplicate bodies must not make their registered file names unsearchable.
    manifest = manifest_for(tmp_path, {"database/original.md": "# 원고\n승인 후 제작\n", "research/복제본.md": "# 원고\n승인 후 제작\n"})
    output = tmp_path / "index.json"
    build_knowledge_index(tmp_path, manifest, output)
    result = search_knowledge(output, "복제본")
    assert len(result) == 1
    assert result[0]["path"] == "database/original.md"
    assert result[0]["duplicate_paths"] == ["research/복제본.md"]


def test_source_hash_search_finds_the_registered_document(tmp_path):
    manifest = manifest_for(tmp_path, {"database/source.md": "# 근거\n검토한 원문\n"})
    output = tmp_path / "index.json"
    build_knowledge_index(tmp_path, manifest, output)
    digest = json.loads(manifest.read_text())[0]["sha256"]
    hits = search_knowledge(output, digest)
    assert len(hits) == 1
    assert hits[0]["path"] == "database/source.md"
    assert hits[0]["sha256"] == digest
