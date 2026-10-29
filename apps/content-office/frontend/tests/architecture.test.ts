import test from "node:test";
import assert from "node:assert/strict";
import { costRows, shortCommit, testSummary } from "../lib/architecture.ts";

test("costRows joins live usage to the documented tasks", () => {
  const rows = costRows(
    [
      { task: "원고 생성", role: "gen", unit: "원고 1편", where: "제작 설정" },
      { task: "퀴즈", role: "quiz", unit: "1회", where: "제작 설정" },
    ],
    [
      { role: "gen", model: "gpt-5.4-mini", calls: 2, krw: 42.5, per_call: 21.2 },
      { role: "gen", model: "gemini-3.8-flash", calls: 1, krw: 10, per_call: 10 },
    ],
  );
  assert.deepEqual(rows[0].models, ["gpt-5.4-mini", "gemini-3.8-flash"]);
  assert.equal(rows[0].calls, 3);
  assert.equal(rows[0].perCall, 17.5);
  assert.equal(rows[1].calls, 0);
  assert.equal(rows[1].perCall, null);
});

test("testSummary reads backend and frontend counts and flags failures", () => {
  assert.deepEqual(testSummary(null), { text: "배포 기록 없음", failed: false });
  const ok = testSummary({ commit: "abc", deployed_at: "2026-10-30T00:00:00Z", tests: { backend: { passed: 434, failed: 0, skipped: 7 }, frontend: { passed: 54, failed: 0 } } });
  assert.equal(ok.text, "백엔드 434 통과 · 화면 54 통과");
  assert.equal(ok.failed, false);
  const bad = testSummary({ commit: "abc", deployed_at: "x", tests: { backend: { passed: 430, failed: 2 }, frontend: { passed: 54, failed: 0 } } });
  assert.equal(bad.failed, true);
  assert.ok(bad.text.includes("2 실패"));
  assert.equal(shortCommit("5938967abcdef"), "5938967");
  assert.equal(shortCommit(null), "확인 불가");
});
