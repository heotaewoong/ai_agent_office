"""원고 검수 하네스 v2_harness (설계: 2026-11-25 HeoBrain RAG 정렬 검수 계획, Stage 0~4).

legacy 검수(같은 모델 3명이 최대 3라운드, 80점 기준)를 바꾸는 실행기. 기본값은 legacy이고
설정 editorial_engine=v2_harness(또는 환경 변수 HEOBRAIN_EDITORIAL_ENGINE)일 때만 쓴다.

한 라운드의 순서:
1. Validate(0원): 기존 코드 검사 + 글 유형별 규칙(harness_rules). 무결성 문제(https/서지 없는 근거, 원문 해시 변경,
   범위 밖 글)는 모델이 고칠 수 없으므로 그 자리에서 멈춘다.
2. 규칙 위반이 있고 마지막 라운드가 아니면 유료 판정을 부르지 않고 바로 고친다(판정 호출 0회).
3. Judge: 생성 모델과 다른 모델 1회. 6축 통과/실패와 근거 없는 문장, 국어 교정만 받는다(점수 없음).
4. Refine: 밖에서 온 신호(규칙 위반, 실패한 축의 이유, 근거 없는 문장, 국어 교정)만 넘긴다. 자기 비평은 하지 않는다.
5. 단조 보호: 고친 판에서 통과하던 규칙이나 축이 하나라도 실패로 바뀌면 직전 판으로 되돌리고 멈춘다.

사람 승인 ⓪①②③은 만들거나 대신하지 않는다. 모든 모델 호출은 기존 Provider(비용 장부, 작업 시간, 단가 검사)와
LangGraph 체크포인트(editorial_call_intents: 결과가 불명확한 호출은 다시 부르지 않음)를 그대로 지난다.
"""
from __future__ import annotations

import copy
import hashlib
import os
import time
from pathlib import Path

from .store import WorkflowError, canonical, digest

HARNESS_VERSION = "v2-harness-2026-11-25"
ENGINES = ("legacy", "v2_harness")
BINARY_AXES = ("accuracy", "groundedness", "completeness", "safety_policy", "abstention_scope", "reader_value_korean")
AXIS_LABELS = {"accuracy": "정확성", "groundedness": "근거 연결", "completeness": "완결성", "safety_policy": "안전과 정책",
               "abstention_scope": "범위 지키기", "reader_value_korean": "독자 가치와 한국어"}
_RUBRIC_PATH = Path(__file__).with_name("harness_rubric.md")
_AXIS = {"type": "object", "properties": {"passed": {"type": "boolean"}, "reason": {"type": "string"}},
         "required": ["passed", "reason"], "additionalProperties": False}
JUDGE_SCHEMA = {"type": "object", "properties": {
    "axes": {"type": "object", "properties": {axis: _AXIS for axis in BINARY_AXES}, "required": list(BINARY_AXES),
             "additionalProperties": False},
    "ungrounded_sentences": {"type": "array", "maxItems": 20, "items": {"type": "string"}},
    "korean_corrections": {"type": "array", "maxItems": 30, "items": {"type": "object", "properties": {
        "field": {"type": "string"}, "original": {"type": "string"}, "revised": {"type": "string"}, "reason": {"type": "string"}},
        "required": ["field", "original", "revised", "reason"], "additionalProperties": False}},
    "content_checks": {"type": "object", "properties": {
        "source_sufficient": {"type": "boolean"}, "topic_matches": {"type": "boolean"}, "reason": {"type": "string"},
        "channel_topics": {"type": "array", "maxItems": 5, "items": {"type": "object", "properties": {
            "channel": {"type": "string"}, "topic_matches": {"type": "boolean"}, "reason": {"type": "string"}},
            "required": ["channel", "topic_matches", "reason"], "additionalProperties": False}}},
        "required": ["source_sufficient", "topic_matches", "reason", "channel_topics"], "additionalProperties": False},
}, "required": ["axes", "ungrounded_sentences", "korean_corrections", "content_checks"], "additionalProperties": False}


def load_rubric() -> tuple[str, str]:
    text = _RUBRIC_PATH.read_text(encoding="utf-8")
    return text, hashlib.sha256(text.encode("utf-8")).hexdigest()


def resolve_editorial_engine(store=None) -> str:
    """사람이 고른 실행기. 설정 → 환경 변수 → legacy. 모르는 값은 legacy로 두지 않고 막는다."""
    value = (store.setting("editorial_engine") if store is not None else None) or os.environ.get("HEOBRAIN_EDITORIAL_ENGINE") or "legacy"
    if value not in ENGINES:
        raise WorkflowError(f"원고 검수 실행기는 {', '.join(ENGINES)} 중 하나여야 합니다")
    return value


def resolve_judge_model(store, gen_model: str | None) -> str:
    judge = (store.setting("judge_model") if store is not None else None) or os.environ.get("HEOBRAIN_JUDGE_MODEL")
    if not judge:
        raise WorkflowError("v2 검수에는 판정 모델(judge_model)이 필요합니다. 생성 모델과 다른 모델을 정해 주세요")
    if judge == gen_model:
        raise WorkflowError("판정 모델이 생성 모델과 같아요. 교차 판정을 위해 다른 모델을 정해 주세요")
    return judge


def _family(model: str | None) -> str:
    model = str(model or "")
    return "gemini" if model.startswith("gemini") else "openai" if model.startswith(("gpt", "codex")) else model


class RoutingProvider:
    """판정(role=judge)은 판정 모델로, 나머지(gen, refine)는 생성 모델로 보낸다. 다른 속성은 생성 쪽을 따른다."""

    def __init__(self, writer, judge):
        self.writer, self.judge = writer, judge
        self.model, self.judge_model = getattr(writer, "model", None), getattr(judge, "model", None)

    def generate(self, role, messages, schema, options=None):
        return (self.judge if role == "judge" else self.writer).generate(role, messages, schema, options)

    def __getattr__(self, name):
        return getattr(self.writer, name)


def run_binary_judge(packet, provider, *, w_type, gen_model, judge_model, brief, extra_prompt="") -> dict:
    """교차 모델 6축 판정 1회. 판정 모델이 생성 모델과 같으면 부르지 않는다."""
    from .editorial import BASE, content_context
    if not judge_model or judge_model == gen_model:
        raise WorkflowError("판정 모델이 생성 모델과 같아요. 교차 판정을 위해 다른 모델을 정해 주세요")
    rubric, _ = load_rubric()
    system = (BASE + "\n너는 생성 모델과 다른 판정자다. 다음 기준표로만 판정한다.\n" + rubric +
              "\ncontent_checks에는 source_sufficient(실제 본문 근거 확보), topic_matches(제목, 본문, 결론, SNS, 영상이 원문 주제를 설명), "
              "reason, channel_topics(channel_posts의 각 키를 한 번씩)를 반환한다." + extra_prompt)
    payload = canonical({"packet": content_context(packet), "audience": brief, "w_type": w_type})
    result = provider.generate("judge", [{"role": "system", "content": system}, {"role": "user", "content": payload}],
                               JUDGE_SCHEMA, {"max_tokens": 4096, "temperature": 0.1})
    axes = result.get("axes") if isinstance(result, dict) else None
    if not isinstance(axes, dict) or any(not isinstance((axes.get(axis) or {}).get("passed"), bool) for axis in BINARY_AXES):
        raise WorkflowError("판정 모델의 6축 결과 형식이 올바르지 않습니다")
    passed = {axis: axes[axis]["passed"] for axis in BINARY_AXES}
    return {"axes": passed, "reasons": {axis: str(axes[axis].get("reason", ""))[:400] for axis in BINARY_AXES},
            "ungrounded_sentences": [str(item)[:400] for item in result.get("ungrounded_sentences") or []][:20],
            "korean_corrections": list(result.get("korean_corrections") or [])[:30],
            "content_checks": result.get("content_checks") or {}, "passed": all(passed.values())}


def compare_quality_snapshots(previous: dict, current: dict) -> dict:
    """통과하던 규칙이나 축이 실패로 바뀌었는지 본다. 하나라도 있으면 직전 판으로 되돌린다."""
    def regressions(key):
        before, after = previous.get(key) or {}, current.get(key) or {}
        return sorted(name for name, ok in before.items() if ok is True and after.get(name) is False)

    def improvements(key):
        before, after = previous.get(key) or {}, current.get(key) or {}
        return sorted(name for name, ok in after.items() if ok is True and before.get(name) is False)

    rules, axes = regressions("rule_scores"), regressions("axes")
    deteriorated = bool(rules or axes)
    return {"deteriorated": deteriorated, "regressed_rules": rules, "regressed_axes": axes,
            "improved": improvements("rule_scores") + improvements("axes"),
            "action": "rollback_to_previous" if deteriorated else "keep"}


def _judge_review(judge: dict) -> dict:
    failed = [axis for axis in BINARY_AXES if not judge["axes"][axis]]
    passed_count = len(BINARY_AXES) - len(failed)
    return {"role": "judge", "score": round(100 * passed_count / len(BINARY_AXES)), "passed": judge["passed"],
            "critical_issues": [f"{AXIS_LABELS[axis]}: {judge['reasons'][axis]}" for axis in failed],
            "minor_issues": judge["ungrounded_sentences"],
            "summary": f"6축 중 {passed_count}축 통과" + (f"(실패: {', '.join(AXIS_LABELS[a] for a in failed)})" if failed else ""),
            "axes": judge["axes"], "content_checks": judge["content_checks"]}


def review_until_ready_v2(packet, provider, *, event=None, checks_fn=None, system=None, packaging=None, brief=None, offer=None,
                          original_markdown=None, refine_limit=2, topic_prompt="", w_type=None, gen_model=None, judge_model=None,
                          trace=None, writer_checks="off"):
    from .briefs import DEFAULT_PRESET, build_brief
    from .channel_adaptation import adaptation_prompt, copy_schema, title_overrides
    from .editorial import (BASE, DRAFT_SCHEMA, FORMAT_CONTRACT, ORIGINAL_MODE_PROMPT, SUMMARY_BODY_PROMPT, content_context,
                            format_targets, normalize_citations, packet_texts, style_issues)
    from .harness_rules import validate_packet
    from .harness_trace import assert_no_remote_tracing
    from .korean import check_texts
    from .offers import campaign_packet
    from .output_specs import output_issues
    from .writing_style import KOREAN_WRITING_PROMPT, POLICY_ID

    assert_no_remote_tracing()
    from .writer_checks import MODES as WRITER_MODES
    if writer_checks not in WRITER_MODES:
        raise WorkflowError(f"글쓰기 0원 검사 모드는 {', '.join(WRITER_MODES)} 중 하나여야 합니다")
    if original_markdown is not None and (not isinstance(original_markdown, str) or not original_markdown.strip()):
        raise WorkflowError("원문 보존 모드에는 직접 제공한 Markdown 본문이 필요합니다")
    gen_model = gen_model or getattr(provider, "model", None)
    judge_model = judge_model or getattr(provider, "judge_model", None)
    if not judge_model or judge_model == gen_model:
        raise WorkflowError("판정 모델이 생성 모델과 같아요. 교차 판정을 위해 다른 모델을 정해 주세요")
    _, rubric_sha = load_rubric()
    packet = copy.deepcopy(packet)
    selected_titles = title_overrides(packet.get("channel_titles"))
    preserve_prompt = (ORIGINAL_MODE_PROMPT if original_markdown is not None else "") + topic_prompt
    if "channel_posts" in packet:
        preserve_prompt += adaptation_prompt(packet) + "모든 channel_posts의 주장, 조건, 문체와 매체 적합성도 판정하라."
    brief = brief if brief is not None else (packet.get("audience") or build_brief(DEFAULT_PRESET))
    writing_prompt = KOREAN_WRITING_PROMPT if brief.get("language", "ko") == "ko" else ""
    draft_schema = copy.deepcopy(DRAFT_SCHEMA)
    draft_schema["properties"]["channel_posts"] = copy_schema(brief.get("language", "ko"))

    def prepare(current):
        if selected_titles:
            current["channel_titles"] = selected_titles
            if "blog" in selected_titles:
                current["title"] = selected_titles["blog"]
            if "shorts" in selected_titles:
                current.setdefault("video", {})["title"] = selected_titles["shorts"]
        if original_markdown is not None:
            current.update(body=original_markdown, preserve_original=True, source_input_hash=digest(original_markdown),
                           reference_evidence_ids=[item["id"] for item in current.get("evidence", []) if item.get("id")])
        current = campaign_packet(current, offer)
        if original_markdown is None and isinstance(current.get("body"), str):
            current["body"] = normalize_citations(current["body"], {e["id"] for e in current.get("evidence", []) if isinstance(e, dict) and e.get("id")})
        return current

    def record(**kwargs):
        if trace is not None:
            trace.record(**kwargs)

    history, best, outcome = [], None, {"rolled_back": False, "deterioration": None}
    allowed_sentences = []  # 직전 판정에서 근거 없다고 짚은 문장. 고치며 빠져도 사실을 잃은 것으로 세지 않는다
    judge_calls = skipped = refines = 0
    for round_no in range(refine_limit + 1):
        packet = prepare(packet)
        started = time.monotonic()
        base = checks_fn(packet) if checks_fn else {"passed": True, "issues": output_issues(packet), "warnings": output_issues(packet), "blocking": []}
        korean_rules = check_texts(packet_texts(packet))
        writer = None if writer_checks == "off" else {"mode": writer_checks, "allowed_sentences": allowed_sentences,
                                                      "previous_body": best["packet"].get("body") if best else None}
        validation = validate_packet(packet, base_checks=base, w_type=w_type, style=style_issues(packet), korean=korean_rules,
                                     writer=writer)
        record(step=f"validate:{round_no}", layer="validate", input_obj=content_context(packet), output_obj=validation["rule_scores"],
               elapsed_ms=(time.monotonic() - started) * 1000, status="ok" if validation["passed"] else "failed",
               summary={"issues": len(validation["issues"]), "blocking": len(validation["blocking"])})
        last = round_no == refine_limit
        judge = None
        if validation["blocking"]:
            pass  # 무결성 문제는 모델이 고칠 수 없다. 판정과 수정을 부르지 않고 멈춘다.
        elif validation["issues"] and not last:
            skipped += 1  # 0원 규칙에서 걸렸으니 유료 판정 없이 바로 고친다.
        else:
            if event:
                event("editorial_role", {"role": "judge", "round": round_no, "packet_hash": digest(content_context(packet))})
            started = time.monotonic()
            judge = run_binary_judge(packet, provider, w_type=w_type, gen_model=gen_model, judge_model=judge_model, brief=brief,
                                     extra_prompt=writing_prompt + preserve_prompt)
            judge_calls += 1
            record(step=f"judge:{round_no}", layer="eval_judge", input_obj=content_context(packet), output_obj=judge["axes"],
                   elapsed_ms=(time.monotonic() - started) * 1000, calls=1, status="ok" if judge["passed"] else "failed",
                   summary={"failed_axes": [axis for axis in BINARY_AXES if not judge["axes"][axis]]})
        snapshot = {"rule_scores": validation["rule_scores"], "axes": judge["axes"] if judge else None}
        if best is not None:
            compared = compare_quality_snapshots(best["snapshot"], snapshot)
            if compared["deteriorated"]:
                record(step=f"rollback:{round_no}", layer="refine", input_obj=snapshot, output_obj=best["snapshot"], status="rolled_back",
                       failure_reason=", ".join(compared["regressed_rules"] + compared["regressed_axes"]))
                history.append({"round": round_no, "source_content_hash": digest(content_context(packet)), "rule_scores": snapshot["rule_scores"],
                                "axes": snapshot["axes"], "comparison": compared, "kept": False})
                outcome = {"rolled_back": True, "deterioration": compared}
                packet, validation, judge, korean_rules = best["packet"], best["validation"], best["judge"], best["korean"]
                break
        best = {"packet": copy.deepcopy(packet), "snapshot": snapshot, "validation": validation, "judge": judge, "korean": korean_rules}
        history.append({"round": round_no, "source_content_hash": digest(content_context(packet)), "rule_scores": snapshot["rule_scores"],
                        "axes": snapshot["axes"], "judge_skipped": judge is None and not validation["blocking"], "kept": True})
        if validation["blocking"] or last or (validation["passed"] and judge is not None and judge["passed"]):
            break
        if event:
            event("editorial_role", {"role": "refine", "round": round_no + 1})
        feedback = {"rule_issues": validation["issues"],
                    "failed_axes": {AXIS_LABELS[axis]: judge["reasons"][axis] for axis in BINARY_AXES if judge and not judge["axes"][axis]},
                    "ungrounded_sentences": judge["ungrounded_sentences"] if judge else [],
                    "korean_corrections": judge["korean_corrections"] if judge else []}
        allowed_sentences = list(feedback["ungrounded_sentences"])
        refine_packet = campaign_packet(packet, None) if offer else packet
        context = {"packet": content_context(refine_packet), "external_feedback": feedback, "audience": brief, "w_type": w_type}
        if original_markdown is None:
            context["format_targets"] = format_targets(packet)
        if packaging is not None:
            context["packaging"] = packaging
        body_instruction = ("파생 제목, 영상, 설명만 수정하고 body는 빈 문자열로 반환하라. 서버가 저자 원문을 그대로 보존한다." + preserve_prompt
                            if original_markdown is not None else
                            "external_feedback에 적힌 문제만 고친다. 이미 통과한 소제목, 근거 연결, 사실, 숫자는 그대로 둔다. "
                            "korean_corrections는 뜻과 근거 ID를 유지하며 반영한다. body는 1,500자±10%의 전체 원고이며 titles 3안과 hashtags 5개를 함께 고친다. "
                            "format_targets의 현재 수치를 목표 범위로 맞춘다. " + FORMAT_CONTRACT + SUMMARY_BODY_PROMPT)
        started = time.monotonic()
        refined = provider.generate("refine", [{"role": "system", "content": (system or BASE) + "밖에서 받은 지적만 해결하고 근거와 숫자를 임의로 바꾸지 말라." + writing_prompt + body_instruction},
                                               {"role": "user", "content": canonical(context)}], draft_schema, {"max_tokens": 8192, "temperature": 0.4})
        refines += 1
        record(step=f"refine:{round_no + 1}", layer="refine", input_obj=context, output_obj=refined, elapsed_ms=(time.monotonic() - started) * 1000, calls=1)
        for key in ("title", "body", "video", "titles", "hashtags", "channel_posts"):
            if key in refined:
                packet[key] = original_markdown if key == "body" and original_markdown is not None else refined[key]

    blocking = list(validation["blocking"])
    reviews = [_judge_review(judge)] if judge else []
    korean_ok = not korean_rules and (judge is None or judge["axes"]["reader_value_korean"])
    packet["quality"] = {
        "status": "blocked" if blocking else "passed", "critical": bool(blocking),
        "advisories": {"model_reviews_passed": bool(judge and judge["passed"]),
                       "review_issues": reviews[0]["critical_issues"] if reviews else [],
                       "rule_warnings": list(validation["warnings"]) if not blocking else [],
                       "note": "승인을 막지 않는 확인 의견입니다. 사실과 숫자 지적은 승인 전에 원고에서 확인하세요"},
        "reviews": reviews, "history": history, "refine_count": refines, "rubric_version": f"{HARNESS_VERSION}:{rubric_sha[:12]}",
        "deterministic_checks": {key: validation[key] for key in ("passed", "issues", "blocking", "warnings")},
        "korean": {"writing_policy": POLICY_ID if writing_prompt else None, "passed": korean_ok, "score": None,
                   "corrections": judge["korean_corrections"] if judge else [], "rule_issues": korean_rules,
                   "note": "국어 규칙은 코드로, 문장 교정은 판정 모델이 제안한 것이며 사람 검토를 대신하지 않습니다"},
        "harness": {"engine": "v2_harness", "version": HARNESS_VERSION, "w_type": w_type, "gen_model": gen_model, "judge_model": judge_model,
                    "same_family_judge": _family(gen_model) == _family(judge_model), "axes": judge["axes"] if judge else None,
                    "rule_scores": validation["rule_scores"], "judge_calls": judge_calls, "judge_skipped_rounds": skipped,
                    "refine_calls": refines, **outcome,
                    **({"writer_checks": {"mode": writer_checks, **(validation.get("writer_checks") or {})}}
                       if writer_checks != "off" else {})},
        "note": "모델 판정 결과이며 사람 승인이나 독립 사실성 증명이 아닙니다",
    }
    return packet
