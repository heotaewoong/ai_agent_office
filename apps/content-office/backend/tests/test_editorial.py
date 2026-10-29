from office.providers import cache_key
from office.editorial import review_until_ready, deterministic_checks


def test_model_cache_covers_actual_system_schema_and_options():
    base = dict(provider="gemini", model="model", messages=[{"role": "system", "content": "rubric-v1"}, {"role": "user", "content": "article"}], schema={"type": "object"}, options={"max_tokens": 100})
    original = cache_key(**base)
    assert cache_key(**{**base, "messages": [{"role": "system", "content": "rubric-v2"}]}) != original
    assert cache_key(**{**base, "schema": {"type": "array"}}) != original
    assert cache_key(**{**base, "options": {"max_tokens": 200}}) != original


class ReviewingProvider:
    def __init__(self, always_block=False):
        self.calls = []
        self.always_block = always_block

    def generate(self, role, messages, schema, options=None):
        self.calls.append((role, messages))
        if role == "refine":
            return {"title": "수정 원고", "body": "수정된 본문", "video": {"scenes": []}}
        return {"role": role, "score": 60 if self.always_block else 90, "passed": not self.always_block, "critical_issues": ["근거 오류"] if self.always_block else [], "minor_issues": [], "summary": "검토"}


def test_critique_and_eval_never_receive_each_others_answers():
    provider = ReviewingProvider()
    packet = {"title": "원고", "body": "본문", "evidence": [{"claim": "사실"}]}
    result = review_until_ready(packet, provider)
    assert result["quality"]["status"] == "passed"
    assert [x[0] for x in provider.calls] == ["critique", "eval", "korean"]
    assert provider.calls[0][1][-1]["content"] == provider.calls[1][1][-1]["content"] == provider.calls[2][1][-1]["content"]
    assert "근거 오류" not in provider.calls[1][1][-1]["content"]
    assert "주어" in provider.calls[2][1][0]["content"] and "조사" in provider.calls[2][1][0]["content"]


def test_refine_is_limited_to_two_and_critical_errors_block():
    provider = ReviewingProvider(always_block=True)
    result = review_until_ready({"title": "원고", "body": "본문", "evidence": []}, provider)
    roles = [role for role, _ in provider.calls]
    assert roles.count("refine") == 2
    assert roles.count("critique") == 3
    assert roles.count("eval") == 3
    assert result["quality"]["critical"] is True
    assert result["quality"]["status"] == "blocked"


def test_foreign_language_intrusion_blocks_even_with_high_model_scores():
    packet = {"title": "광고", "body": "8 месяцев(8개월) 누적 광고주" * 100, "evidence": [], "video": {"scenes": []}}
    assert any("언어" in issue for issue in deterministic_checks(packet)["issues"])


def test_fact_specific_metric_label_guard_applies_to_narration_and_caption():
    packet = {"title": "반복 신뢰성", "body": "근거 있는 설명 [TB3] " * 100, "evidence": [{"id": "TB3", "url": "https://example.com/experiment", "claim": "20회 중 한번 이상 성공 비율은 87.97%", "checks": [{"prohibited_pattern": "반복.{0,20}87[.,]97", "message": "반복 신뢰성과 20회 중 한번 이상 성공을 혼동"}]}], "video": {"scenes": [{"narration": "반복 성공률이 87.97퍼센트입니다", "caption": "반복 성공률"}]}}
    assert any("혼동" in issue for issue in deterministic_checks(packet)["issues"])


def test_old_evidence_collection_cannot_replace_new_operator_source(tmp_path, monkeypatch):
    import pytest
    from office.store import Store, WorkflowError
    from office.editorial import prepare_source
    from office import evidence
    store = Store(tmp_path)
    article = {'id': 'source-race', 'title': '원문 수정 시험', 'url': 'https://example.com/news', 'evidence': []}
    store.save_articles([article])
    job = store.create_job(article)
    first = store.register_source_input(job['id'], '첫번째 공개 원문입니다. ' * 30, expected_hash=None)
    latest = {}
    def collect_old(*args):
        latest.update(store.register_source_input(job['id'], '새로 교체한 공개 원문입니다. ' * 30, expected_hash=first['source_hash']))
        return {'evidence': [{'id': 'E1', 'url': 'https://example.com/news', 'claim': '이전 원문의 주장'}], 'limitations': [], 'hook': '이전 질문', 'source_kind': 'http_article_body', 'retrieved_at': '2026-10-26T04:00:00+09:00', 'source_sha256': 'a'*64}
    monkeypatch.setattr(evidence, 'collect_article_evidence', collect_old)
    class NoGeneration:
        def generate(self, *args, **kwargs):
            raise AssertionError('수정된 원문을 옛 조사로 덮고 생성하면 안 됩니다')
    with pytest.raises(WorkflowError, match='버전|변경'):
        prepare_source(store, job['id'], provider=NoGeneration())
    assert store.job(job['id'])['source_hash'] == latest['source_hash']
    assert store.job(job['id'])['article']['operator_source_text'].startswith('새로 교체한')
    assert store.article('source-race').get('operator_source_text') is None
    assert store.article('source-race')['evidence'] == []


def test_refinement_gets_editorial_scenes_and_reviews_one_canonical_campaign_cta():
    import json
    from office.offers import campaign_packet
    from tests.test_offer import coupon_offer
    offer = coupon_offer()
    original = {"title": "합성 원고", "body": "합성 본문", "video": {"title": "합성 영상", "description": "시험", "scenes": [{"narration": "본문 설명", "caption": "본문"}]}}
    seen = []
    class Refiner:
        def generate(self, role, messages, schema, options=None):
            context = json.loads(messages[-1]["content"])
            scenes = context["packet"].get("video", {}).get("scenes", [])
            if role == "refine":
                assert len(scenes) == 1 and "쿠폰" not in scenes[-1]["narration"]
                return {**original, "video": {**original["video"], "scenes": [{"narration": "수정한 본문 설명", "caption": "수정 본문"}]}}
            seen.append(scenes)
            return {"score": 70, "passed": False, "critical_issues": ["합성 수정 요청"], "minor_issues": [], "summary": "시험"}
    result = review_until_ready(campaign_packet(original, offer), Refiner(), offer=offer)
    assert len(seen) == 9 and all(len(scenes) == 2 for scenes in seen)
    assert all("50퍼센트" in scenes[-1]["narration"] for scenes in seen)
    assert len(result["video"]["scenes"]) == 2



def _reevaluation_fixture(tmp_path, language):
    from office.store import Store
    from office.briefs import build_brief
    store = Store(tmp_path)
    job = store.create_job({"id": "language-fixture", "title": "합성 언어 검증", "url": "https://example.invalid/source", "evidence": [{"id": "E1", "claim": "합성 근거", "url": "https://example.invalid/source"}]})
    packet = {"title": "합성 한국어 원고", "body": "한국어 합성 본문은 재검수로 번역되지 않아요.", "evidence": job["article"]["evidence"], "quality": {"status": "passed", "critical": False}, "video": {"scenes": []}}
    if language is not None:
        packet["audience"] = build_brief("ai-agent", {"language": language})
    return store, store.save_source(job["id"], packet)


def test_reevaluation_cannot_relabel_korean_source_as_english_before_any_work(tmp_path, monkeypatch):
    import pytest
    from office import editorial
    from office.store import WorkflowError
    store, job = _reevaluation_fixture(tmp_path, "ko")
    store.set_brief(job["id"], {**job["brief"], "language": "en"}, "fixture-operator")
    before, events = store.job(job["id"]), store.events(job["id"])
    def forbidden(*args, **kwargs):
        pytest.fail("Language mismatch must be blocked before state, evidence or provider work")
    monkeypatch.setattr(editorial, "Provider", forbidden)
    monkeypatch.setattr(editorial, "load_brand", forbidden)
    monkeypatch.setattr("office.evidence.collect_article_evidence", forbidden)
    with pytest.raises(WorkflowError, match="새 원고"):
        editorial.prepare_source(store, job["id"], evaluate_only=True)
    assert store.job(job["id"]) == before and store.events(job["id"]) == events
    assert store.job(job["id"])["source_packet"]["audience"]["language"] == "ko"


def test_reevaluation_of_legacy_unknown_language_requires_new_source(tmp_path, monkeypatch):
    import pytest
    from office import editorial
    from office.store import WorkflowError
    store, job = _reevaluation_fixture(tmp_path, None)
    before, events = store.job(job["id"]), store.events(job["id"])
    def forbidden(*args, **kwargs):
        pytest.fail("Unknown source language must never be promoted by metadata alone")
    monkeypatch.setattr(editorial, "Provider", forbidden)
    monkeypatch.setattr(editorial, "load_brand", forbidden)
    with pytest.raises(WorkflowError, match="미확인"):
        editorial.prepare_source(store, job["id"], evaluate_only=True)
    assert store.job(job["id"]) == before and store.events(job["id"]) == events


def test_same_language_reader_change_can_be_reevaluated_without_translation(tmp_path, monkeypatch):
    from office import editorial
    store, job = _reevaluation_fixture(tmp_path, "ko")
    store.set_brief(job["id"], {**job["brief"], "reader": "합성 시험의 새 독자"}, "fixture-operator")
    # These stubs isolate the language/brief handoff, not model or content-quality validation.
    monkeypatch.setattr(editorial, "deterministic_checks", lambda packet: {"passed": True, "issues": []})
    monkeypatch.setattr(editorial, "run_gates", lambda *args: {"status": "pass"})
    provider = ReviewingProvider()
    result = editorial.prepare_source(store, job["id"], provider=provider, evaluate_only=True)
    assert [role for role, _ in provider.calls] == ["critique", "eval", "korean"]
    assert result["source_packet"]["body"] == job["source_packet"]["body"]
    assert result["source_packet"]["audience"]["reader"] == "합성 시험의 새 독자"
    assert result["source_packet"]["audience"]["language"] == "ko"
