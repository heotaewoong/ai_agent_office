import pytest

from office.output_specs import output_issues

def test_blog_contract_and_legacy():
    assert output_issues({'body':'old'}) == []
    good={'body':'가'*1500,'titles':['가','나','다'],'hashtags':['#가','#나','#다','#라','#마']}
    assert output_issues(good)==[]
    assert output_issues({**good,'body':'짧음'})
    assert output_issues({**good,'hashtags':['#가']*5})


@pytest.mark.parametrize("length,valid", [(1349, False), (1350, True), (1650, True), (1651, False)])
def test_summary_body_length_policy_is_unchanged(length, valid):
    packet = {"body": "가" * length, "titles": ["가", "나", "다"], "hashtags": ["#가", "#나", "#다", "#라", "#마"]}
    assert (not output_issues(packet)) is valid


@pytest.mark.parametrize("derived", [{}, {"titles": ["가", "나", "다"]}, {"hashtags": ["#가", "#나", "#다", "#라", "#마"]},
                                     {"titles": ["가", "나", "다"], "hashtags": ["#가", "#나", "#다", "#라", "#마"]}])
def test_preserved_original_ignores_compact_length_and_allows_optional_derived_fields(derived):
    packet = {"body": "원" * 11352, "preserve_original": True, **derived}
    assert output_issues(packet) == [] and len(packet["body"]) == 11352


@pytest.mark.parametrize("derived", [{"titles": ["중복"] * 3}, {"titles": None}, {"hashtags": None}, {"hashtags": ["#가"] * 5},
                                     {"hashtags": ["가", "#나", "#다", "#라", "#마"]}, {"hashtags": ["#가 나", "#나", "#다", "#라", "#마"]}])
def test_preserved_original_still_validates_provided_derived_fields(derived):
    issues = output_issues({"body": "원" * 11352, "preserve_original": True, **derived})
    assert issues and all("1,500" not in issue for issue in issues)


def test_generation_and_refine_keep_long_original_with_new_titles_and_hashtags(tmp_path, monkeypatch):
    from office.editorial import prepare_source
    from office.store import digest
    from tests.test_editorial import original_markdown, preservation_job, OriginalPreservingProvider
    original = original_markdown()
    store, saved = preservation_job(tmp_path, monkeypatch, original)
    class DerivedProvider(OriginalPreservingProvider):
        def generate(self, role, *args, **kwargs):
            result = super().generate(role, *args, **kwargs)
            if role in ("gen", "refine"):
                result.update(titles=["저자 사례를 확인하는 법", "원문에서 기준을 찾는 법", "원문을 적용하는 순서"],
                              hashtags=["#원문", "#사례", "#판단", "#한계", "#적용"])
            return result
    provider = DerivedProvider(original, refine_once=True)
    result = prepare_source(store, saved["id"], provider=provider)
    packet = result["source_packet"]
    assert packet["body"] == original and packet["source_input_hash"] == digest(original)
    assert len(packet["titles"]) == 3 and len(packet["hashtags"]) == 5
    assert packet["quality"]["status"] == "passed" and provider.calls.count("refine") == 1
    assert packet["quality"]["deterministic_checks"]["passed"] is True
    assert result["source_approval"] is None and result["release_approval"] is None
