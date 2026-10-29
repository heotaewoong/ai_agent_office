import test from "node:test";
import assert from "node:assert/strict";
import { briefFormFromBrief, briefOverridesFromForm, axisLabel, briefSummary, presetLabel } from "../lib/briefs.ts";

test("덮어쓰기는 빈 문자열을 빼고 공백을 다듬는다", () => {
  const r = briefOverridesFromForm({ brief_reader: " 독자 ", brief_problem: "", brief_outcome: "결과", brief_cta: "   ", brief_language: "", brief_topic: "주제", brief_prior_knowledge: "", brief_tone: "" });
  assert.ok("overrides" in r);
  assert.deepEqual(r.overrides, { reader: "독자", outcome: "결과", topic: "주제" });
  const none = briefOverridesFromForm({});
  assert.ok("overrides" in none && Object.keys(none.overrides).length === 0);
});

test("언어는 ko·en만 받는다", () => {
  const ko = briefOverridesFromForm({ brief_language: "ko" });
  assert.ok("overrides" in ko && ko.overrides.language === "ko");
  const bad = briefOverridesFromForm({ brief_language: "jp" });
  assert.ok("error" in bad && bad.error.includes("언어"));
});

test("기존 브리프의 CTA만 고쳐도 독자·문제·숨은 설정을 보존한다", () => {
  const brief = { preset: "transfer-admission", axis: "A" as const, label: "편입", reader: "직장인 편입생", problem: "주말 공부 시간 부족", outcome: "4주 학습 계획", cta: "기존 자료", topic: "편입 영어", prior_knowledge: "수능 독해", tone: "차분한 해요체", language: "ko" as const };
  const form = briefFormFromBrief(brief);
  assert.equal(form.brief_preset, brief.preset);
  const result = briefOverridesFromForm({ ...form, brief_cta: "새 자료" });
  assert.ok("overrides" in result);
  assert.deepEqual(result.overrides, { reader: brief.reader, problem: brief.problem, outcome: brief.outcome, cta: "새 자료", topic: brief.topic, prior_knowledge: brief.prior_knowledge, tone: brief.tone, language: "ko" });
  assert.equal(brief.cta, "기존 자료");
});

test("아직 브리프가 없으면 프리셋의 기본값을 쓰도록 빈 폼을 만든다", () => {
  const form = briefFormFromBrief(undefined);
  assert.equal(form.brief_preset, "");
  assert.deepEqual(briefOverridesFromForm(form), { overrides: {} });
});

test("축 이름과 프리셋 이름", () => {
  assert.equal(axisLabel("A"), "시험·편입");
  assert.equal(axisLabel("B"), "AI·자동화");
  assert.equal(axisLabel("Z"), "Z");
  const presets = [{ id: "ai-agent", axis: "B" as const, label: "AI 에이전트 입문", topic: "", reader: "", prior_knowledge: "", problem: "", outcome: "", tone: "", language: "ko" as const, cta: "" }];
  assert.equal(presetLabel(presets, "ai-agent"), "AI 에이전트 입문");
  assert.equal(presetLabel(presets, "missing"), "missing");
});

test("브리프 요약은 독자·문제·CTA·언어를 한 줄씩 낸다", () => {
  const rows = briefSummary({ preset: "ai-agent", axis: "B", label: "AI 에이전트 입문", topic: "", reader: "직장인", prior_knowledge: "", problem: "반복 업무", outcome: "", tone: "", language: "en", cta: "뉴스레터" });
  assert.deepEqual(rows, [["프리셋", "AI 에이전트 입문 · AI·자동화"], ["독자", "직장인"], ["문제", "반복 업무"], ["CTA", "뉴스레터"], ["언어", "영어"]]);
  assert.deepEqual(briefSummary(undefined), []);
});
