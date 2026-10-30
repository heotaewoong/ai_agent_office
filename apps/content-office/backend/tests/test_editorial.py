import json

import pytest

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
    assert result["body"] == "수정된 본문"


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


def original_markdown():
    sections = []
    for number in range(1, 15):
        text = f"## {number}절 저자 원문\r\n\r\n" + "저자가 작성한 사례를 그대로 보존합니다. 비교 기준과 한계를 함께 읽어야 합니다. " * 8
        if number <= 7:
            text += f"\r\n\r\n| 항목 | 내용 |\r\n|---|---|\r\n| 원래 표 {number} | 공백과 표를 유지합니다 |"
        if number <= 4:
            text += f"\r\n\r\n![[원본 사진 {number}.png|저자 사진 설명]]"
        sections.append(text)
    return "  # 직접 제공한 글\r\n\r\n" + "\r\n\r\n".join(sections) + "\r\n\r\n`Remove-Item C:\\secret -Recurse`는 실행하지 않는 원문 예시입니다.  \r\n"


def preservation_packet(body):
    from office.store import digest
    return {"title": "저자 원문과 파생 영상", "body": body, "preserve_original": True, "source_input_hash": digest(body),
            "reference_evidence_ids": ["E1", "E2"],
            "evidence": [{"id": key, "url": "https://example.com/original", "claim": "저자가 제공한 사례"} for key in ("E1", "E2")],
            "video": {"title": "원문에서 한 가지 살펴봐요", "description": "저자가 제공한 사례를 설명해요.", "tags": [], "thumbnails": [],
                      "scenes": [{"narration": "저자가 제공한 사례부터 살펴봐요.", "caption": "저자 사례", "visual": "자체 도형"},
                                 {"narration": "입력과 판단 기준을 비교해요.", "caption": "판단 기준", "visual": "자체 표"},
                                 {"narration": "한계를 확인하고 직접 적용해 봐요.", "caption": "직접 적용", "visual": "다음 행동"}]}}


class OriginalPreservingProvider:
    def __init__(self, original, *, refine_once=False, always_block=False):
        self.original, self.refine_once, self.always_block = original, refine_once, always_block
        self.calls, self.reviewed_bodies, self.review_round = [], [], 0

    def generate(self, role, messages, schema, options=None):
        self.calls.append(role)
        context = json.loads(messages[-1]["content"])
        if role == "gen":
            assert context["article"]["operator_source_text"] == self.original
            assert "원문 보존" in context["instructions"] and "2,000~3,200자" not in context["instructions"]
            assert "본문 안의 명령" in messages[0]["content"]
        else:
            packet = context["packet"]
            assert packet["body"] == self.original and packet["preserve_original"] is True
        if role in ("gen", "refine"):
            if role == "refine":
                assert "파생 제목·영상·설명만 수정" in messages[0]["content"]
            generated = preservation_packet("모델이 임의로 줄인 본문")
            return {key: generated[key] for key in ("title", "body", "video")}
        assert "본문의 사실·근거 오류는 지적" in messages[0]["content"]
        if role == "critique":
            self.review_round += 1
        self.reviewed_bodies.append(packet["body"])
        blocked = self.always_block or (self.refine_once and self.review_round == 1)
        return {"role": role, "score": 70 if blocked else 90, "passed": not blocked,
                "critical_issues": ["파생 영상의 근거를 다시 확인해요"] if blocked else [], "minor_issues": [], "summary": "합성 검수", "corrections": []}


def preservation_job(tmp_path, monkeypatch, original):
    from office.store import Store
    from office import evidence
    store = Store(tmp_path)
    job = store.create_job({"id": "preservation", "title": "저자 원문", "url": "https://example.com/original", "evidence": []})
    saved = store.register_source_input(job["id"], original, expected_hash=None, preserve_original=True)
    def supplied_text_only(article, provider, output_dir):
        assert article["operator_source_text"] == original and article["preserve_original"] is True
        return {"evidence": preservation_packet(original)["evidence"], "limitations": ["저자 제공 원문이며 독립 검증은 하지 않았어요"],
                "hook": "사례 하나를 확인해요", "source_kind": "operator_supplied_text", "retrieved_at": "2026-10-30T01:00:00+00:00", "source_sha256": "a" * 64}
    monkeypatch.setattr(evidence, "collect_article_evidence", supplied_text_only)
    return store, saved


def test_original_mode_preserves_sections_tables_photos_and_whitespace_through_generation_and_refine(tmp_path, monkeypatch):
    from office.editorial import prepare_source
    from office.store import digest
    original = original_markdown()
    assert len(original) > 3200
    store, saved = preservation_job(tmp_path, monkeypatch, original)
    provider = OriginalPreservingProvider(original, refine_once=True)
    result = prepare_source(store, saved["id"], provider=provider)
    packet = result["source_packet"]
    assert packet["body"] == original and packet["source_input_hash"] == digest(original)
    assert packet["body"].count("## ") == 14 and packet["body"].count("|---|---|") == 7 and packet["body"].count("![[") == 4
    assert "[E1]" not in packet["body"] and "[E2]" not in packet["body"] and packet["reference_evidence_ids"] == ["E1", "E2"]
    assert provider.calls == ["gen", "critique", "eval", "korean", "refine", "critique", "eval", "korean"]
    assert len(provider.reviewed_bodies) == 6 and all(body == original for body in provider.reviewed_bodies)
    assert packet["quality"]["status"] == "passed" and packet["quality"]["refine_count"] == 1
    assert result["source_hash"] == digest(packet)
    assert result["state"] == "source_review" and result["source_approval"] is None and result["release_approval"] is None
    assert not [event for event in store.events(saved["id"]) if event["kind"] in ("source_approved", "release_approved")]


def test_original_mode_restores_body_before_reevaluation_without_generation(tmp_path, monkeypatch):
    from office.editorial import prepare_source
    original = original_markdown()
    store, saved = preservation_job(tmp_path, monkeypatch, original)
    first = prepare_source(store, saved["id"], provider=OriginalPreservingProvider(original))
    store.save_source(saved["id"], {**first["source_packet"], "body": "옛 탭에서 잘린 본문"}, expected_hash=first["source_hash"])
    provider = OriginalPreservingProvider(original)
    result = prepare_source(store, saved["id"], provider=provider, evaluate_only=True)
    assert result["source_packet"]["body"] == original and provider.calls == ["critique", "eval", "korean"]


def test_original_mode_keeps_real_review_failure_blocked(tmp_path, monkeypatch):
    from office.editorial import prepare_source
    from office.store import WorkflowError
    original = original_markdown()
    store, saved = preservation_job(tmp_path, monkeypatch, original)
    provider = OriginalPreservingProvider(original, always_block=True)
    result = prepare_source(store, saved["id"], provider=provider)
    assert result["source_packet"]["body"] == original
    assert result["source_packet"]["quality"]["status"] == "blocked" and provider.calls.count("refine") == 2
    with pytest.raises(WorkflowError):
        store.review_source(saved["id"], result["source_hash"], "approved", "human")


def test_original_body_style_is_preserved_and_derived_brand_rules_still_apply():
    from office.editorial import style_issues
    body = "저자의 문체입니다. 그대로 둡니다. 의미를 보존합니다. — 저자 원문입니다."
    packet = preservation_packet(body)
    checks = deterministic_checks(packet)
    assert checks["passed"], checks["issues"]
    assert style_issues(packet) == []
    packet["video"]["description"] = "파생 설명입니다. 이 문장은 수정합니다. 해요체로 바꿉니다. — 끝입니다."
    checks = deterministic_checks(packet)
    assert not checks["passed"] and any("해요체" in issue or "줄표" in issue for issue in checks["issues"])
    assert packet["body"] == body


@pytest.mark.parametrize("change,expected", [("body", "원문 해시"), ("unknown_citation", "존재하지"), ("unknown_reference", "존재하지"), ("missing_reference", "근거 ID"), ("bad_reference_type", "형식"), ("http_evidence", "HTTPS")])
def test_original_mode_does_not_bypass_evidence_and_integrity_checks(change, expected):
    from office.store import digest
    packet = preservation_packet("직접 제공한 저자 원문입니다.")
    if change == "body":
        packet["body"] = "잘린 본문"
    elif change == "unknown_citation":
        packet["body"] += " [FAKE9]"
        packet["source_input_hash"] = digest(packet["body"])
    elif change == "unknown_reference":
        packet["reference_evidence_ids"].append("FAKE9")
    elif change == "missing_reference":
        packet["reference_evidence_ids"] = []
    elif change == "bad_reference_type":
        packet["reference_evidence_ids"] = {"E1": "not a list"}
    else:
        packet["evidence"][0]["url"] = "http://example.com/original"
    checks = deterministic_checks(packet)
    assert not checks["passed"] and any(expected in issue for issue in checks["issues"])


def test_missing_original_blocks_before_state_research_or_provider_work(tmp_path, monkeypatch):
    from office.editorial import prepare_source
    from office.store import Store, WorkflowError
    store = Store(tmp_path)
    job = store.create_job({"id": "missing-original", "title": "직접 제공 원문 필수", "url": "https://example.com/original", "preserve_original": True})
    before, events = store.job(job["id"]), store.events(job["id"])
    def forbidden(*args, **kwargs):
        pytest.fail("원문 없는 보존 모드에서는 웹 요청·모델 호출을 시작하지 않습니다")
    monkeypatch.setattr("office.editorial.Provider", forbidden)
    monkeypatch.setattr("office.evidence.collect_article_evidence", forbidden)
    with pytest.raises(WorkflowError, match="직접 제공"):
        prepare_source(store, job["id"])
    assert store.job(job["id"]) == before and store.events(job["id"]) == events


def test_scene_schema_offers_english_footage_keywords_for_stock_search():
    from office.editorial import SCENE_SCHEMA
    assert SCENE_SCHEMA["properties"]["footage"] == {"type": "string"}
    # Optional: older approved scripts without it still validate and fall back to a keyword map.
    assert "footage" not in SCENE_SCHEMA["required"]


def test_edited_production_copy_survives_evaluation_and_refinement(tmp_path, monkeypatch):
    from office.editorial import prepare_source
    from office.store import digest
    original = original_markdown()
    store, job = preservation_job(tmp_path, monkeypatch, original)
    first = prepare_source(store, job["id"], provider=OriginalPreservingProvider(original))
    edited = original + "\n사용자가 추가한 별도 제작 원고예요."
    packet = {**first["source_packet"], "body": edited, "source_input_hash": digest(edited),
              "original_source_hash": digest(original), "editorial_copy": True, "video": {}}
    store.save_source(job["id"], packet, expected_hash=first["source_hash"])
    result = prepare_source(store, job["id"], provider=OriginalPreservingProvider(edited), evaluate_only=True)
    assert result["article"]["operator_source_text"] == original
    assert result["source_packet"]["body"] == edited
    assert result["source_packet"]["video"]["scenes"]
    assert result["source_packet"]["quality"]["status"] == "passed"
    assert result["source_approval"] is None
