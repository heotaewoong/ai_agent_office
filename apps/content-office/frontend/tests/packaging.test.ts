import test from "node:test";
import assert from "node:assert/strict";
import { validatePackagingBrief, packagingRequired } from "../lib/packaging.ts";

const good = { titles: ["Claude 팀으로 블로그 자동화", "AI 팀 블로그", "자동화 3단계"], thumbnails: [{ text: "AI 팀", visual: "화면" }, { text: "AI 팀", visual: "화면" }, { text: "AI 팀", visual: "화면" }], hook: "Claude 팀으로 블로그를 끝낸 결과부터 봅니다", logline: "한 명이 팀처럼 일하는 법", reasons: ["수요", "실제 화면"] };

test("완성된 브리프는 문제 없음", () => assert.deepEqual(validatePackagingBrief(good), []));
test("제목 3안·썸네일 3안·이유 2~3개가 아니면 문제", () => {
  const issues = validatePackagingBrief({ ...good, titles: ["하나"], thumbnails: [], reasons: ["x"] });
  assert.ok(issues.some((i) => i.includes("제목")));
  assert.ok(issues.some((i) => i.includes("썸네일")));
  assert.ok(issues.some((i) => i.includes("이유")));
});
test("길이 상한을 넘으면 문제", () => {
  const issues = validatePackagingBrief({ ...good, titles: ["가".repeat(46), "b", "c"], thumbnails: [{ text: "가".repeat(13), visual: "v" }, { text: "a", visual: "v" }, { text: "a", visual: "v" }], hook: "가".repeat(121) });
  assert.equal(issues.length, 3);
});
test("빈 훅·로그라인은 문제", () => {
  assert.ok(validatePackagingBrief({ ...good, hook: " ", logline: "" }).length >= 2);
});
test("기획에서 시작했고 패키지가 없을 때만 필요", () => {
  assert.equal(packagingRequired({ article: { origin: "idea" } as never, packaging: null }), true);
  assert.equal(packagingRequired({ article: { origin: "idea" } as never, packaging: { packaging_hash: "h" } as never }), false);
  assert.equal(packagingRequired({ article: {} as never }), false);
});
test("빈 제목·빈 썸네일 글자는 문제", () => {
  const issues = validatePackagingBrief({ ...good, titles: ["a", "  ", "c"], thumbnails: [{ text: "", visual: "v" }, { text: "a", visual: "v" }, { text: " ", visual: "v" }] });
  assert.deepEqual(issues, ["제목 2안이 비어 있습니다", "썸네일 1안 글자가 비어 있습니다", "썸네일 3안 글자가 비어 있습니다"]);
});

test("title score subtracts for missing numbers, overclaims and AI tells, and never picks for the human", async () => {
  const { scoreTitle } = await import("../lib/packaging.ts");
  assert.equal(scoreTitle("편입 영어 단어, 한 달에 1,200개 외운 순서", "한 달에 1,200개").score, 100);
  const missing = scoreTitle("편입 영어 단어, 한 달에 3,000개 외운 순서", "한 달에 1,200개");
  assert.equal(missing.score, 60);
  assert.ok(missing.reasons[0].includes("3,000"));
  const hype = scoreTitle("누구나 쉽게 무조건 합격하는 최고의 방법");
  assert.ok(hype.score <= 55 && hype.reasons.some((reason) => reason.includes("무조건 합격")));
  assert.equal(scoreTitle("").score, 0);
});
