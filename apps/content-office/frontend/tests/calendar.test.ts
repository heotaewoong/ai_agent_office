import test from "node:test";
import assert from "node:assert/strict";
import { dDayLabel, timelinessPercent } from "../lib/calendar.ts";

test("다음 시험이 있으면 'D-일수' 배지를 만든다", () => {
  assert.equal(dDayLabel({ name: "정보처리기사 필기", date: "2026-11-30", days_left: 32 }), "정보처리기사 필기 D-32");
  assert.equal(dDayLabel({ name: "오픽", date: "2026-10-29", days_left: 0 }), "오픽 D-Day");
  assert.equal(dDayLabel({ name: "오픽", date: "2026-10-26", days_left: -3 }), "오픽 D+3");
});

test("다음 시험이 없으면 빈 문자열", () => {
  assert.equal(dDayLabel(null), "");
  assert.equal(dDayLabel(undefined), "");
  assert.equal(dDayLabel({ name: "", date: "2026-11-30", days_left: 10 }), "D-10");
});

test("시의성 0~1을 0~100 정수로 바꾸고 범위를 벗어나면 자른다", () => {
  assert.equal(timelinessPercent(0.5), 50);
  assert.equal(timelinessPercent(1.2), 100);
  assert.equal(timelinessPercent(-1), 0);
  assert.equal(timelinessPercent(undefined), 0);
  assert.equal(timelinessPercent(Number.NaN), 0);
});
