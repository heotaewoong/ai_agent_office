"""검수 하네스 v2_harness: 0원 규칙 먼저, 교차 모델 6축 판정, 밖의 신호로만 고치기, 나빠지면 되돌리기."""
import json

import pytest

from office.editorial import prepare_source
from office.harness import (BINARY_AXES, compare_quality_snapshots, resolve_editorial_engine, resolve_judge_model,
                            review_until_ready_v2)
from office.harness_calibration import compute_judge_calibration
from office.harness_rules import extra_rule_issues, pure_prose_length
from office.harness_trace import FAILURE_LAYERS, TraceRecorder, assert_no_remote_tracing, read_traces
from office.store import Store, WorkflowError
from test_agent_editorial import FullProvider, evidence_job

EVIDENCE = [{"id": "E1", "claim": "공식 발표에 따르면 도구는 3가지", "url": "https://example.com/a", "numbers": ["3"], "paragraph": 1, "scope": "발표"}]


def good_body():
    return ("## 질문\n" + "도구 3가지를 실제 화면으로 비교해요 [E1]. " * 20 + "\n## 사례\n" + "입력과 판단 결과를 그대로 보여 줘요. " * 20
            + "\n## 오늘 할 일\n" + "한 가지를 직접 실행해 봐요. " * 22)


def packet(body=None):
    scenes = [{"narration": "세 도구를 비교해요", "caption": f"장면{i}", "visual": "화면"} for i in range(4)]
    return {"title": "AI 도구 비교", "body": body if body is not None else good_body(), "evidence": EVIDENCE,
            "video": {"title": "AI 도구 비교", "description": "", "tags": [], "scenes": scenes, "thumbnails": []}}


def verdict(**failed):
    return {"axes": {axis: {"passed": axis not in failed, "reason": failed.get(axis, "근거와 일치")} for axis in BINARY_AXES},
            "ungrounded_sentences": [], "korean_corrections": [],
            "content_checks": {"source_sufficient": True, "topic_matches": True, "reason": "주제 일치", "channel_topics": []}}


class Stub:
    model = "gemini-3.8-flash"
    judge_model = "gpt-5.4-mini"

    def __init__(self, judges=(), refines=()):
        self.judges, self.refines, self.calls = list(judges), list(refines), []

    def generate(self, role, messages, schema, options=None):
        self.calls.append(role)
        if role == "judge":
            return self.judges.pop(0)
        body = self.refines.pop(0)
        return {"title": "AI 도구 비교", "body": body, "video": packet()["video"]}


def run(stub, start, **kw):
    return review_until_ready_v2(start, stub, gen_model=stub.model, judge_model=stub.judge_model, refine_limit=2, **kw)


def test_engine_and_judge_model_are_explicit(monkeypatch, tmp_path):
    monkeypatch.delenv("HEOBRAIN_EDITORIAL_ENGINE", raising=False)
    store = Store(tmp_path)
    assert resolve_editorial_engine(store) == "legacy"
    monkeypatch.setenv("HEOBRAIN_EDITORIAL_ENGINE", "v2_harness")
    assert resolve_editorial_engine(store) == "v2_harness"
    monkeypatch.setenv("HEOBRAIN_EDITORIAL_ENGINE", "fast")
    with pytest.raises(WorkflowError):
        resolve_editorial_engine(store)
    monkeypatch.delenv("HEOBRAIN_JUDGE_MODEL", raising=False)
    with pytest.raises(WorkflowError, match="판정 모델"):
        resolve_judge_model(store, "gemini-3.8-flash")
    monkeypatch.setenv("HEOBRAIN_JUDGE_MODEL", "gemini-3.8-flash")
    with pytest.raises(WorkflowError, match="같아요"):
        resolve_judge_model(store, "gemini-3.8-flash")


def test_remote_tracing_is_blocked_and_private_runs_keep_no_payload(monkeypatch, tmp_path):
    monkeypatch.setenv("LANGSMITH_TRACING", "true")
    with pytest.raises(WorkflowError):
        assert_no_remote_tracing()
    monkeypatch.delenv("LANGSMITH_TRACING")
    recorder = TraceRecorder(tmp_path, "run-1", w_type="W3", contains_private=True)
    recorder.record(step="judge:0", layer="eval_judge", input_obj={"book": "책 원문 문단"}, output_obj={"ok": True}, calls=1,
                    summary={"quote": "책 원문 문단"})
    [row] = read_traces(tmp_path)
    assert row["layer"] in FAILURE_LAYERS and row["payload"] is None and row["private_redacted"] is True
    assert "책 원문" not in json.dumps(row, ensure_ascii=False)
    with pytest.raises(ValueError):
        recorder.record(step="x", layer="unknown")


def test_snapshot_comparison_rolls_back_on_any_regression():
    before = {"rule_scores": {"length": True, "style": False}, "axes": {"accuracy": True, "groundedness": False}}
    after = {"rule_scores": {"length": True, "style": True}, "axes": {"accuracy": False, "groundedness": True}}
    result = compare_quality_snapshots(before, after)
    assert result["deteriorated"] is True and result["regressed_axes"] == ["accuracy"] and result["action"] == "rollback_to_previous"
    assert compare_quality_snapshots(before, {**after, "axes": {"accuracy": True, "groundedness": True}})["deteriorated"] is False


def test_layer1_rules_by_post_type():
    assert pure_prose_length("## 제목\n[링크](https://a.com) 본문 [E1] https://b.com") == len("제목 링크 본문")
    short = extra_rule_issues({"body": "## 하나\n짧아요 https://a.com https://a.com\n이 글은 정보 제공 목적입니다.", "evidence": []}, w_type="W1")
    assert short["prose_length"] and short["duplicate_url"] and short["disclaimer"] and short["comparison_table"]
    table = good_body() + "\n| 도구 | 가격 |\n|---|---|\n| A | 무료 |"
    assert not extra_rule_issues({"body": table, "evidence": []}, w_type="W1")["comparison_table"]
    example = [{"id": "E2", "claim": "기획 승인⓪에서 선택한 사례·참고 자료 발췌", "url": "https://blog.example.com"}]
    numbers = extra_rule_issues({"body": good_body() + "\n사용자가 30% 늘었어요 [E2].", "evidence": example}, w_type="W3")
    assert numbers["example_numbers"]
    assert extra_rule_issues({"body": good_body(), "evidence": []}, w_type="W5")["w_scope"]
    books = [{"id": "E3", "source_kind": "approved_book_evidence", "url": "book://" + "a" * 24}]
    assert extra_rule_issues({"body": good_body(), "evidence": books}, w_type="W4")["w_scope"]


def test_rule_failure_skips_the_paid_judge_and_refines_first(tmp_path):
    stub = Stub(judges=[verdict()], refines=[good_body()])
    trace = TraceRecorder(tmp_path, "run-2", w_type="W3")
    result = run(stub, packet("## 하나\n너무 짧은 본문이에요 [E1]."), w_type="W3", trace=trace)
    assert stub.calls == ["refine", "judge"]
    harness = result["quality"]["harness"]
    assert harness["judge_calls"] == 1 and harness["judge_skipped_rounds"] == 1 and harness["rolled_back"] is False
    assert result["quality"]["status"] == "passed" and result["quality"]["reviews"][0]["role"] == "judge"
    assert [row["layer"] for row in read_traces(tmp_path)] == ["validate", "refine", "validate", "eval_judge"]


def test_refine_that_breaks_a_passing_axis_is_rolled_back(tmp_path):
    first = good_body()
    stub = Stub(judges=[verdict(groundedness="E1이 받치지 않는 문장"), verdict(accuracy="숫자가 바뀜")], refines=[good_body() + "\n더 쓴 문단이에요 [E1]."])
    result = run(stub, packet(first))
    assert stub.calls == ["judge", "refine", "judge"]
    quality = result["quality"]
    assert quality["harness"]["rolled_back"] is True and quality["harness"]["deterioration"]["regressed_axes"] == ["accuracy"]
    assert result["body"] == first and quality["reviews"][0]["axes"]["groundedness"] is False
    assert "근거 연결" in quality["reviews"][0]["critical_issues"][0]


def test_refine_receives_only_external_signals():
    captured = []

    class Capture(Stub):
        def generate(self, role, messages, schema, options=None):
            if role == "refine":
                captured.append(json.loads(messages[1]["content"]))
            return super().generate(role, messages, schema, options)
    stub = Capture(judges=[verdict(completeness="비교축이 빠짐"), verdict()], refines=[good_body()])
    run(stub, packet())
    feedback = captured[0]["external_feedback"]
    assert feedback["failed_axes"] == {"완결성": "비교축이 빠짐"} and "feedback" not in captured[0]


def test_same_model_judge_and_integrity_problems_never_call_a_model():
    stub = Stub()
    with pytest.raises(WorkflowError, match="같아요"):
        review_until_ready_v2(packet(), stub, gen_model="gpt-5.4-mini", judge_model="gpt-5.4-mini")
    from office.editorial import deterministic_checks
    broken = {**packet(), "evidence": [{"id": "E1", "claim": "주소 없는 근거", "url": "", "numbers": []}]}
    result = run(stub, broken, checks_fn=deterministic_checks)
    assert stub.calls == [] and result["quality"]["status"] == "blocked" and result["quality"]["harness"]["judge_calls"] == 0


def test_prepare_source_uses_one_cross_model_judge_instead_of_three_reviewers(tmp_path, monkeypatch):
    monkeypatch.delenv("HEOBRAIN_EDITORIAL_ENGINE", raising=False)
    store = Store(tmp_path)
    store.set_setting("editorial_engine", "v2_harness")
    job = evidence_job(store)

    class Routed(FullProvider):
        model = "gemini-3.8-flash"
        judge_model = "gpt-5.4-mini"

        def generate(self, role, messages, schema, options=None):
            if role == "judge":
                self.roles.append(role)
                return verdict()
            return super().generate(role, messages, schema, options)
    provider = Routed("AI 도구 비교")
    result = prepare_source(store, job["id"], provider=provider)
    assert "critique" not in provider.roles and "eval" not in provider.roles and "korean" not in provider.roles
    assert provider.roles.count("judge") >= 1 and provider.roles[0] == "gen"
    quality = result["source_packet"]["quality"]
    assert quality["harness"]["engine"] == "v2_harness" and quality["harness"]["judge_model"] == "gpt-5.4-mini"
    assert quality["status"] == "passed" and not result["source_approval"]


def test_judge_calibration_reports_tpr_tnr():
    pairs = [{"human": True, "judge": True}] * 17 + [{"human": True, "judge": False}] + [{"human": False, "judge": False}] * 10 + [{"human": False, "judge": True}] * 2
    result = compute_judge_calibration(pairs, min_tpr=0.85, min_tnr=0.85)
    assert result["total"] == 30 and result["tpr"] == round(17 / 18, 4) and result["tnr"] == round(10 / 12, 4)
    assert result["calibrated"] is False and "TNR" in result["note"]
    with pytest.raises(ValueError):
        compute_judge_calibration(pairs[:10])


def test_engine_comparison_needs_paid_acknowledgement_and_counts_calls(tmp_path):
    from office.editorial_compare import compare_editorial_engines
    from test_agent_editorial import FullProvider
    with pytest.raises(WorkflowError, match="acknowledge_paid"):
        compare_editorial_engines(packet(), legacy_provider=FullProvider("AI 도구 비교"), harness_provider=Stub())
    legacy = FullProvider("AI 도구 비교")
    report = compare_editorial_engines(packet(), legacy_provider=legacy, harness_provider=Stub(judges=[verdict()]),
                                       acknowledge_paid=True, root=tmp_path)
    assert report["legacy"]["roles"] == ["critique", "eval", "korean"] and report["v2_harness"]["roles"] == ["judge"]
    assert report["calls_saved"] == 2 and (tmp_path / "evals" / "reports").is_dir()


def test_judge_uses_its_own_prompt_and_writes_the_reason_before_the_verdict():
    from office.editorial import BASE
    from office.harness import JUDGE_SYSTEM
    seen = []

    class Capture(Stub):
        def generate(self, role, messages, schema, options=None):
            if role == "judge":
                seen.append((messages[0]["content"], schema))
            return super().generate(role, messages, schema, options)
    run(Capture(judges=[verdict()]), packet())
    system, schema = seen[0]
    assert system.startswith(JUDGE_SYSTEM) and "심사자" in system and BASE[:40] not in system
    assert "[기준표]" in system and "[글쓰기 기준: 판정에만 참고한다" in system
    axis = schema["properties"]["axes"]["properties"]["accuracy"]
    assert list(axis["properties"]) == ["reason", "passed"] and axis["required"] == ["reason", "passed"]


def test_last_refine_is_kept_for_the_judge_so_its_feedback_can_be_fixed():
    captured = []

    class Capture(Stub):
        def generate(self, role, messages, schema, options=None):
            if role == "refine":
                captured.append(json.loads(messages[1]["content"])["external_feedback"])
            return super().generate(role, messages, schema, options)
    stub = Capture(judges=[verdict(completeness="비교축이 빠짐"), verdict()], refines=["## 하나\n아직 짧은 본문이에요 [E1].", good_body()])
    result = run(stub, packet("## 하나\n너무 짧은 본문이에요 [E1]."), w_type="W3")
    assert stub.calls == ["refine", "judge", "refine", "judge"]
    assert captured[0]["failed_axes"] == {} and captured[0]["rule_issues"]
    assert captured[1]["failed_axes"] == {"완결성": "비교축이 빠짐"} and captured[1]["rule_issues"]
    harness = result["quality"]["harness"]
    assert harness["judge_calls"] == 2 and harness["judge_skipped_rounds"] == 1 and harness["refine_calls"] == 2
    assert result["quality"]["advisories"]["model_reviews_passed"] is True and harness["rolled_back"] is False


def test_exhausted_refines_below_accuracy_stay_in_review_pending():
    # 고치기를 다 써도 정확성이 기준에 못 미치면, 가장 나은 판은 남기되 통과로 올리지 않고 검토 대기로 둔다.
    stub = Stub(judges=[verdict(accuracy="숫자가 원문과 다름") for _ in range(3)], refines=[good_body(), good_body()])
    result = run(stub, packet(), w_type="W3")
    assert stub.calls == ["judge", "refine", "judge", "refine", "judge"]
    quality = result["quality"]
    assert quality["refine_count"] == 2 and quality["harness"]["rolled_back"] is False
    assert quality["status"] == "needs_review" and quality["critical"] is False
    assert quality["advisories"]["model_reviews_passed"] is False
    assert quality["review_pending"] == ["정확성: 숫자가 원문과 다름"]
    assert "정확성" in quality["reviews"][0]["critical_issues"][0]


def test_review_pending_draft_cannot_be_approved(tmp_path):
    store = Store(tmp_path)
    job = evidence_job(store)
    pending = {**packet(), "quality": {"status": "needs_review", "critical": False}}
    store.update_job(job["id"], state="source_review", source_packet=pending, source_hash="h1")
    with pytest.raises(WorkflowError, match="미완료 검수"):
        store.review_source(job["id"], "h1", "approved", "tester")


def test_remote_tracing_only_for_checked_in_public_samples(monkeypatch):
    from office.public_sample import load_public_sample, require_public_sample, run_public_probe
    monkeypatch.delenv("LANGSMITH_API_KEY", raising=False)
    monkeypatch.setenv("LANGSMITH_TRACING", "true")
    sample = load_public_sample()
    with pytest.raises(WorkflowError):
        assert_no_remote_tracing()
    assert_no_remote_tracing(public_sample=sample)
    changed = json.loads(json.dumps(sample))
    changed["packet"]["body"] += " 개인 원고 문장"
    with pytest.raises(WorkflowError, match="다릅니다"):
        assert_no_remote_tracing(public_sample=changed)
    book = json.loads(json.dumps(sample))
    book["packet"]["evidence"][0]["source_kind"] = "approved_book_evidence"
    with pytest.raises(WorkflowError):
        require_public_sample(book)
    with pytest.raises(WorkflowError, match="LANGSMITH_API_KEY"):
        run_public_probe(send=True)
    monkeypatch.delenv("LANGSMITH_TRACING")
    summary = run_public_probe(send=False)
    assert summary["sent"] is False and summary["calls"][-1] == "judge" and summary["status"] in ("passed", "needs_review")
