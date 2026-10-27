import test from "node:test";
import assert from "node:assert/strict";
import { ideaInputFromForm } from "../lib/ideas.ts";

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
