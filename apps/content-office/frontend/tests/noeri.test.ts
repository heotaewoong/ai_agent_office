import test from "node:test";
import assert from "node:assert/strict";
import { NOERI_LABELS, NOERI_MOODS, noeriStatus, storyMood } from "../lib/noeri.ts";

test("뇌리 표정마다 한국어 이름이 있다", () => {
  assert.equal(NOERI_MOODS.length, 7);
  for (const mood of NOERI_MOODS) assert.ok(NOERI_LABELS[mood]);
});

test("파이프라인 화면의 뇌리는 서버 기록으로만 표정을 고른다", () => {
  assert.equal(noeriStatus({ windowOpen: false }).mood, "calm");
  assert.equal(noeriStatus({ windowOpen: true, worker: "online" }).mood, "thinking");
  assert.equal(noeriStatus({ windowOpen: true, worker: null }).mood, "curious");
  assert.equal(noeriStatus({ windowOpen: true, worker: "online", failedTests: true }).mood, "surprised");
});

test("그림 기억 이야기 패널의 뇌리 표정", () => {
  assert.equal(storyMood(null, false), "happy");
  assert.equal(storyMood(null, true), "thinking");
  assert.equal(storyMood({ checks: { passed: true } }, false), "proud");
  assert.equal(storyMood({ checks: { passed: false } }, false), "tired");
});
