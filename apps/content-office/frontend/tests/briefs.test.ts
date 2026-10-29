import test from "node:test";
import assert from "node:assert/strict";
import { briefDraftForJob, briefDraftFromBrief, briefFormFromBrief, briefOverridesFromForm, axisLabel, briefSummary, changeBriefDraft, presetLabel, syncBriefDraft, updateBriefDrafts, type BriefDraft } from "../lib/briefs.ts";

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

const originalBrief = { preset: "transfer-admission", axis: "A", label: "편입", reader: "기존 독자", problem: "기존 문제", outcome: "학습 계획", cta: "기존 자료", topic: "편입 영어", prior_knowledge: "수능 독해", tone: "해요체", language: "ko" };

test("같은 프리셋도 미편집 폼은 새 브리프 판본으로 동기화한다", () => {
  const initial = briefDraftFromBrief(originalBrief, "a".repeat(64));
  assert.equal(syncBriefDraft(initial, { ...originalBrief }, initial.baseHash), initial);
  assert.equal(syncBriefDraft(initial, undefined, undefined), initial);
  const latest = { ...originalBrief, reader: "다른 탭의 새 독자" };
  const synced = syncBriefDraft(initial, latest, "b".repeat(64));
  assert.equal(synced.form.brief_reader, latest.reader);
  assert.equal(synced.baseHash, "b".repeat(64));
  assert.equal(synced.dirty, false);
});

test("편집 중 외부 변경은 입력과 기준 판본을 보존하고 명시적 다시 불러오기로만 초기화한다", () => {
  const initial = briefDraftFromBrief(originalBrief, "a".repeat(64));
  const edited = changeBriefDraft(initial, "brief_cta", "내가 입력한 CTA");
  const external = { ...originalBrief, preset: "ai-agent", reader: "다른 탭의 독자" };
  const latestHash = "b".repeat(64);
  const conflicted = syncBriefDraft(edited, external, latestHash);
  assert.equal(conflicted, edited);
  assert.equal(conflicted.form.brief_cta, "내가 입력한 CTA");
  assert.equal(conflicted.dirty && conflicted.baseHash !== latestHash, true);
  const reloaded = briefDraftFromBrief(external, latestHash);
  assert.equal(reloaded.form.brief_reader, external.reader);
  assert.equal(reloaded.form.brief_cta, originalBrief.cta);
  assert.equal(reloaded.dirty, false);
});

test("저장 성공의 새 기준 판본은 자기 변경을 충돌로 보지 않고 후속 외부 변경을 동기화한다", () => {
  const changed = { ...originalBrief, cta: "저장한 CTA" };
  const saved = briefDraftFromBrief(changed, "b".repeat(64));
  assert.equal(syncBriefDraft(saved, changed, saved.baseHash), saved);
  const next = syncBriefDraft(saved, { ...changed, problem: "저장 뒤 외부 변경" }, "c".repeat(64));
  assert.equal(next.form.brief_cta, "저장한 CTA");
  assert.equal(next.form.brief_problem, "저장 뒤 외부 변경");
  assert.equal(next.dirty, false);
});

test("작업·화면 왕복 뒤에도 각 작업의 브리프 입력과 기준 판본을 따로 복원한다", () => {
  const first = { id: "job-a", brief: originalBrief, brief_hash: "a".repeat(64) };
  const second = { id: "job-b", brief: { ...originalBrief, reader: "둘째 독자" }, brief_hash: "b".repeat(64) };
  let drafts: Record<string, BriefDraft> = {};
  drafts = updateBriefDrafts(drafts, first, (current) => changeBriefDraft(current, "brief_cta", "첫 작업의 입력"));
  const firstDraft = drafts[first.id];
  assert.equal(briefDraftForJob(drafts, second).form.brief_cta, originalBrief.cta);
  drafts = updateBriefDrafts(drafts, second, (current) => changeBriefDraft(current, "brief_reader", "둘째 작업의 입력"));
  assert.equal(briefDraftForJob(drafts, first), firstDraft);
  assert.equal(briefDraftForJob(drafts, first).form.brief_cta, "첫 작업의 입력");
  assert.equal(briefDraftForJob(drafts, second).form.brief_reader, "둘째 작업의 입력");
  const external = { ...first, brief: { ...originalBrief, cta: "서버에서 바뀐 CTA" }, brief_hash: "c".repeat(64) };
  const restored = briefDraftForJob(drafts, external);
  assert.equal(restored, firstDraft);
  assert.notEqual(restored.baseHash, external.brief_hash);
  assert.equal(restored.form.brief_cta, "첫 작업의 입력");
});

test("자기 저장의 완료 콜백은 해당 초안만 비우고 새 서버 판본을 기준으로 다시 연다", () => {
  const job = { id: "job-a", brief: originalBrief, brief_hash: "a".repeat(64) };
  const other = { ...job, id: "job-b" };
  let drafts: Record<string, BriefDraft> = {};
  drafts = updateBriefDrafts(drafts, job, (current) => changeBriefDraft(current, "brief_cta", "저장한 CTA"));
  drafts = updateBriefDrafts(drafts, other, (current) => changeBriefDraft(current, "brief_reader", "다른 작업의 독자"));
  const submitted = drafts[job.id];
  const saved = { ...job, brief: { ...originalBrief, cta: "저장한 CTA" }, brief_hash: "b".repeat(64) };
  drafts = updateBriefDrafts(drafts, job, (current) => current === submitted ? briefDraftFromBrief(saved.brief, saved.brief_hash) : current);
  assert.deepEqual(Object.keys(drafts), [other.id]);
  const reopened = briefDraftForJob(drafts, saved);
  assert.equal(reopened.dirty, false);
  assert.equal(reopened.baseHash, saved.brief_hash);
  assert.equal(reopened.form.brief_cta, "저장한 CTA");
  assert.equal(briefDraftForJob(drafts, other).form.brief_reader, "다른 작업의 독자");
});

test("늦은 저장 완료는 제출 후 입력한 새 초안을 지우지 않는다", () => {
  const job = { id: "job-a", brief: originalBrief, brief_hash: "a".repeat(64) };
  let drafts: Record<string, BriefDraft> = {};
  drafts = updateBriefDrafts(drafts, job, (current) => changeBriefDraft(current, "brief_cta", "제출한 CTA"));
  const submitted = drafts[job.id];
  drafts = updateBriefDrafts(drafts, job, (current) => changeBriefDraft(current, "brief_cta", "아직 제출하지 않은 입력"));
  const latest = drafts[job.id];
  drafts = updateBriefDrafts(drafts, job, (current) => current === submitted ? briefDraftFromBrief({ ...originalBrief, cta: "제출한 CTA" }, "b".repeat(64)) : current);
  assert.equal(drafts[job.id], latest);
  assert.equal(drafts[job.id].form.brief_cta, "아직 제출하지 않은 입력");
});

test("명시적 다시 불러오기는 한 작업의 초안만 버리며 미편집 조회는 캐시를 만들지 않는다", () => {
  const job = { id: "job-a", brief: originalBrief, brief_hash: "a".repeat(64) };
  let drafts: Record<string, BriefDraft> = {};
  assert.equal(updateBriefDrafts(drafts, job, (current) => current), drafts);
  drafts = updateBriefDrafts(drafts, job, (current) => changeBriefDraft(current, "brief_reader", "버릴 입력"));
  const latest = { ...job, brief: { ...originalBrief, reader: "새 서버 독자" }, brief_hash: "b".repeat(64) };
  drafts = updateBriefDrafts(drafts, latest, () => briefDraftFromBrief(latest.brief, latest.brief_hash));
  assert.deepEqual(drafts, {});
  assert.equal(briefDraftForJob(drafts, latest).form.brief_reader, "새 서버 독자");
  assert.equal(briefDraftForJob(drafts, latest).baseHash, latest.brief_hash);
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
