import test from "node:test";
import assert from "node:assert/strict";
import { briefOverridesFromForm, axisLabel, briefSummary, presetLabel } from "../lib/briefs.ts";

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
