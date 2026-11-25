import test from "node:test";
import assert from "node:assert/strict";
import { countIdeas, filterIdeas, ideaStatus, outlierLabel } from "../lib/idea-bank.ts";

const ideas = [
  { id: "a", title: "오픽 IM2에서 막힌 분을 위한 첫 7일", state: "candidate" as const, blocked: [] },
  { id: "b", title: "수면과 집중력", state: "candidate" as const, blocked: ["1차 출처 없음"] },
  { id: "c", title: "Claude Code 시작하기", state: "selected" as const, blocked: [] },
];

test("기획 상태는 작업 만듦, 막힘, 작업 가능 순서로 판단한다", () => {
  assert.deepEqual(ideaStatus(ideas[0]), { key: "ready", label: "작업 가능", tone: "blue" });
  assert.deepEqual(ideaStatus(ideas[1]), { key: "blocked", label: "막힘 1", tone: "red" });
  assert.equal(ideaStatus({ state: "selected", blocked: ["1차 출처 없음"] }).key, "selected");
});

test("측정값 없는 반응 구간은 화면에 쓰지 않는다", () => {
  assert.equal(outlierLabel("unknown"), "");
  assert.equal(outlierLabel(undefined), "");
  assert.equal(outlierLabel("10x+"), "평소의 10배 넘는 반응");
});

test("필터와 검색어를 함께 적용하고 개수를 센다", () => {
  assert.deepEqual(countIdeas(ideas), { all: 3, ready: 1, blocked: 1, selected: 1 });
  assert.deepEqual(filterIdeas(ideas, "blocked", "").map((idea) => idea.id), ["b"]);
  assert.deepEqual(filterIdeas(ideas, "all", "claude 시작").map((idea) => idea.id), ["c"]);
  assert.deepEqual(filterIdeas(ideas, "ready", "수면"), []);
});
