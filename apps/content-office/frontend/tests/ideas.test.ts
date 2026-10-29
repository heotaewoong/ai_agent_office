import test from "node:test";
import assert from "node:assert/strict";
import { ideaInputFromForm, ideaSourcesDraft, changeIdeaSourcesDraft, syncIdeaSourcesDraft, ideaSourcesInput } from "../lib/ideas.ts";
import type { Idea } from "../lib/types.ts";

test("제목과 https 출처가 있으면 숫자 필드를 변환한다", () => {
  const r = ideaInputFromForm({ title: " Claude 팀 ", source_url: "https://ex.com/a", views: "12,000", channel_avg_views: "3000", demand: "70", primary_sources: "2", fit: "0.9", covered_before: false, policy_flags: "ymyl, 실존인물" });
  assert.ok("input" in r);
  assert.equal(r.input.title, "Claude 팀");
  assert.equal(r.input.views, 12000);
  assert.deepEqual(r.input.policy_flags, ["ymyl", "실존인물"]);
});
test("출처가 https가 아니면 오류를 돌려준다", () => {
  const r = ideaInputFromForm({ title: "x", source_url: "http://ex.com", demand: "0", primary_sources: "0", fit: "0", covered_before: false, policy_flags: "" });
  assert.ok("error" in r && r.error.includes("https"));
});
test("빈 조회수는 null이고 범위 밖 fit은 오류다", () => {
  const ok = ideaInputFromForm({ title: "x", source_url: "https://a.b", views: "", demand: "10", primary_sources: "1", fit: "1", covered_before: true, policy_flags: "" });
  assert.ok("input" in ok && ok.input.views === null);
  const bad = ideaInputFromForm({ title: "x", source_url: "https://a.b", demand: "10", primary_sources: "1", fit: "1.5", covered_before: false, policy_flags: "" });
  assert.ok("error" in bad);
});
test("조회수 계열 숫자 검증", () => {
  const base = { title: "x", source_url: "https://a.b", demand: "10", primary_sources: "1", fit: "1", covered_before: true, policy_flags: "" };
  const cap = ideaInputFromForm({ ...base, channel_avg_views: "1000000000001" });
  assert.deepEqual(cap, { error: "채널 평균 조회수은(는) 1조 이하로 입력하세요" });
  for (const bad of ["1e3", "-1", "1.5"]) {
    assert.ok("error" in ideaInputFromForm({ ...base, views: bad }), bad);
    assert.ok("error" in ideaInputFromForm({ ...base, channel_avg_views: bad }), bad);
  }
});
test("브리프 프리셋과 덮어쓰기는 비어 있지 않은 값만 보낸다", () => {
  const base = { title: "x", source_url: "https://a.b", demand: "10", primary_sources: "1", fit: "1", covered_before: false, policy_flags: "" };
  const plain = ideaInputFromForm(base);
  assert.ok("input" in plain);
  assert.equal("brief_preset" in plain.input, false);
  assert.equal("brief" in plain.input, false);
  const withBrief = ideaInputFromForm({ ...base, brief_preset: "exam-transfer", brief_reader: " 편입 준비생 ", brief_problem: "", brief_outcome: "", brief_cta: "무료 체크리스트", brief_language: "en" });
  assert.ok("input" in withBrief);
  assert.equal(withBrief.input.brief_preset, "exam-transfer");
  assert.deepEqual(withBrief.input.brief, { reader: "편입 준비생", cta: "무료 체크리스트", language: "en" });
  const badLang = ideaInputFromForm({ ...base, brief_language: "fr" });
  assert.ok("error" in badLang && badLang.error.includes("언어"));
});

const idea = { id: "idea-one", title: "편입 준비", state: "candidate", score: 0, outlier_band: "unknown", reasons: [], blocked: ["1차 출처 없음"], edit_hash: "a".repeat(64) } as Idea;

test("질문 출처 보완은 실제 URL 목록·확인·읽은 판본만 보내고 숫자를 만들어 보내지 않는다", () => {
  let draft = changeIdeaSourcesDraft(ideaSourcesDraft(idea), " https://example.edu/transfer \nhttps://example.edu/english ");
  assert.ok("error" in ideaSourcesInput(draft));
  draft = { ...draft, confirmed: true };
  assert.deepEqual(ideaSourcesInput(draft), { input: { source_urls: ["https://example.edu/transfer", "https://example.edu/english"], operator_verified: true, expected_hash: idea.edit_hash } });
  assert.ok("error" in ideaSourcesInput({ ...draft, text: "http://example.edu/a" }));
  assert.ok("error" in ideaSourcesInput({ ...draft, text: "https://user:pass@example.edu/a" }));
  assert.ok("error" in ideaSourcesInput({ ...draft, baseHash: "" }));
  assert.equal(changeIdeaSourcesDraft(draft, "https://example.edu/new").confirmed, false);
});

test("미편집 출처는 최신 카드로 동기화하고 편집 중 외부 갱신은 입력과 예전 판본을 보존한다", () => {
  const original = ideaSourcesDraft(idea);
  const next = { ...idea, source_urls: ["https://example.edu/remote"], edit_hash: "b".repeat(64) };
  const clean = syncIdeaSourcesDraft(original, next);
  assert.equal(clean.text, next.source_urls[0]); assert.equal(clean.baseHash, next.edit_hash); assert.equal(clean.dirty, false);
  const edited = changeIdeaSourcesDraft(original, "https://example.edu/mine");
  assert.deepEqual(syncIdeaSourcesDraft(edited, next), edited);
  const saved = ideaSourcesDraft({ ...next, source_urls: [edited.text] });
  assert.equal(saved.dirty, false); assert.equal(saved.text, edited.text);
});
