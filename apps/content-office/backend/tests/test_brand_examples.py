import json

from office.brand import DEFAULT_DIR, brand_system_prompt, load_brand


def write_brand(folder):
    folder.mkdir(parents=True, exist_ok=True)
    (folder / "voice.md").write_text("짧은 해요체로 말해요", encoding="utf-8")
    (folder / "glossary.json").write_text(json.dumps({"terms": {}, "pronunciation": {}}), encoding="utf-8")
    (folder / "banned_claims.json").write_text(json.dumps(["수익 보장"]), encoding="utf-8")
    return folder


def write_example(folder, name, title, body):
    examples = folder / "examples"
    examples.mkdir(exist_ok=True)
    (examples / f"{name}.md").write_text(f"---\ntitle: {title}\nsource_url: https://onethingflow.tistory.com/entry/{name}\nfetched_at: 2026-10-29\n---\n{body}\n", encoding="utf-8")


def test_brand_without_examples_has_empty_list_and_no_section(tmp_path):
    brand = load_brand(write_brand(tmp_path / "b"))
    assert brand["examples"] == []
    assert "문체 예시" not in brand_system_prompt("BASE", brand)


def test_examples_are_loaded_truncated_and_prompted(tmp_path):
    folder = write_brand(tmp_path / "b")
    write_example(folder, "a-one", "첫 글", "가" * 2000)
    write_example(folder, "b-two", "둘째 글", "둘째 본문이에요")
    write_example(folder, "c-three", "셋째 글", "셋째 본문이에요")
    (folder / "examples" / "README.md").write_text("# 형식 설명", encoding="utf-8")
    brand = load_brand(folder)
    assert [e["title"] for e in brand["examples"]] == ["첫 글", "둘째 글", "셋째 글"]
    assert brand["examples"][0]["source_url"] == "https://onethingflow.tistory.com/entry/a-one"
    assert len(brand["examples"][0]["text"]) == 1500
    prompt = brand_system_prompt("BASE", brand)
    assert "[문체 예시]" in prompt and "첫 글" in prompt and "둘째 본문이에요" in prompt and "셋째" not in prompt
    without = load_brand(write_brand(tmp_path / "c"))
    assert without["hash"] != brand["hash"]


def test_example_without_front_matter_uses_file_name(tmp_path):
    folder = write_brand(tmp_path / "b")
    (folder / "examples").mkdir()
    (folder / "examples" / "plain-post.md").write_text("본문만 있어요", encoding="utf-8")
    brand = load_brand(folder)
    assert brand["examples"] == [{"title": "plain-post", "source_url": "", "text": "본문만 있어요"}]


def test_shipped_examples_if_present_are_owner_posts():
    brand = load_brand(DEFAULT_DIR)
    for example in brand["examples"]:
        assert example["source_url"].startswith(("https://onethingflow.tistory.com", "https://blog.naver.com/oneflowwhy"))
        assert example["title"] and example["text"]
    assert len(brand["examples"]) <= 2
