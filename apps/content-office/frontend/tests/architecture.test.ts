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

import { readFileSync } from "node:fs";
import { flowStages, imageRoute, pipelineSvg, type ArchitectureOverview, type FlowStep } from "../lib/architecture.ts";

const document = JSON.parse(readFileSync(new URL("../../backend/config/architecture.json", import.meta.url), "utf8")) as ArchitectureOverview["doc"];

test("pipeline keeps six stages, all four human approvals and actionable input/output contracts", () => {
  const before = JSON.stringify(document.flow);
  const rows = flowStages(document.flow);
  assert.equal(rows.length, 6);
  assert.deepEqual(rows.flatMap((row) => row.gates.map((gate) => gate.mark)), ["⓪", "①", "②", "③"]);
  assert.deepEqual(rows.map((row) => row.stage.id), ["collect", "plan", "draft", "produce", "deliver", "learn"]);
  for (const { stage } of rows) assert.ok(stage.input && stage.output && stage.entry && stage.items.length >= 4 && stage.who);
  assert.equal(JSON.stringify(document.flow), before);
  const gate = { kind: "gate", mark: "①", label: "원고 승인" } as FlowStep;
  assert.throws(() => flowStages([gate]), /공정/);
});

test("parallel outputs, independent coupon offers and consent/mail boundaries remain explicit", () => {
  assert.deepEqual(document.lanes?.map((lane) => lane.id), ["outputs", "offer", "audience"]);
  assert.match(document.lanes![0].boundary, /블로그.*영상/);
  assert.match(document.lanes![1].boundary, /발급.*가격\/주문/);
  assert.match(document.lanes![2].boundary, /미연결/);
  assert.ok(document.status.some((item) => item.text.includes("Hermes") && item.state === "off"));
  assert.deepEqual(document.unit_costs.map((row) => row.role), ["card_ko", "gen", "critique", "eval", "korean", "cards", "cards_review", "quiz", "card_image", "image"]);
  assert.equal(imageRoute("codex-subscription"), "Codex 구독 로그인");
  assert.equal(imageRoute("none"), "생성 이미지 끔");
  assert.equal(imageRoute("unknown-selection"), "unknown-selection");
});

test("editable SVG uses the same complete content and escapes document strings", () => {
  const svg = pipelineSvg(document);
  assert.equal((svg.match(/data-card="stage-/g) ?? []).length, 6);
  assert.equal((svg.match(/data-card="lane-/g) ?? []).length, 3);
  const text = svg.replace(/<[^>]+>/g, "");
  for (const step of document.flow) {
    if (step.kind === "stage") {
      assert.ok(text.includes(step.title), step.title);
      for (const item of step.items) assert.ok(text.includes(item), item);
    }
    if (step.kind === "gate") assert.ok(text.includes(step.mark + " " + step.label));
  }
  for (const lane of document.lanes ?? []) assert.ok(text.includes(lane.boundary));
  const hostile = { ...document, headline: '<script>alert("x")</script> & "test"' };
  const safe = pipelineSvg(hostile);
  assert.ok(!safe.includes("<script>"));
  assert.ok(safe.includes("&lt;script&gt;"));
  assert.ok(!/<image|<foreignObject|<script|https?:\/\//.test(svg.replace('xmlns="http://www.w3.org/2000/svg"', "")));
});


test("CI 검증형·누락·부분 배포 기록을 안전하게 표시하고 없는 검사 건수를 만들지 않는다", () => {
  const base={commit:"abc",deployed_at:"2026-10-30T10:00:00Z"};
  assert.deepEqual(testSummary({...base,tests:{ci:{source:"github-actions",check:"verify",completed_at:"2026-10-30T09:59:00Z"}}}),{text:"GitHub verify 통과 · 개별 검사 건수 미기록",failed:false});
  assert.deepEqual(testSummary(base),{text:"검사 결과 미기록",failed:false});
  assert.deepEqual(testSummary({...base,tests:{}}),{text:"검사 결과 미기록",failed:false});
  const partial=testSummary({...base,tests:{backend:{passed:4,failed:1}}});
  assert.equal(partial.failed,true);assert.match(partial.text,/화면 건수 미기록/);
});
