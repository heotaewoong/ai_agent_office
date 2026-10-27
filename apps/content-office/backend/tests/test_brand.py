import json
from office.brand import banned_claim_hits, brand_system_prompt, load_brand, tts_text


def write_brand(folder, voice="친절하고 구체적으로 설명한다"):
    folder.mkdir(exist_ok=True)
    (folder / "voice.md").write_text(voice, encoding="utf-8")
    (folder / "glossary.json").write_text(json.dumps({"terms": {"클로드": "Claude"}, "pronunciation": {"API": "에이피아이"}}), encoding="utf-8")
    (folder / "banned_claims.json").write_text(json.dumps(["수익 보장"]), encoding="utf-8")
    return load_brand(folder)


def test_empty_brand_keeps_base_prompt(tmp_path):
    assert brand_system_prompt("BASE", load_brand(tmp_path / "none")) == "BASE"


def test_voice_change_changes_prompt_and_hash(tmp_path):
    one = write_brand(tmp_path / "a")
    two = write_brand(tmp_path / "b", voice="짧고 단호하게 말한다")
    assert one["hash"] != two["hash"]
    assert brand_system_prompt("BASE", one) != brand_system_prompt("BASE", two)


def test_banned_claims_and_pronunciation(tmp_path):
    brand = write_brand(tmp_path / "c")
    assert banned_claim_hits("이 방법은 수익 보장!", brand) == ["수익 보장"]
    assert tts_text("API와 APIs", brand) == "에이피아이와 APIs"
