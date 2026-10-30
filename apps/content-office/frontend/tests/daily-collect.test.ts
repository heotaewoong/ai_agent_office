import test from "node:test";
import assert from "node:assert/strict";
import { parseDailyCollectForm, runSummary, validCollectMaxKrw, validCollectMinutes, validTimeKst } from "../lib/daily-collect.ts";

test("수집 시각은 HH:MM(00:00~23:59)만 받는다", () => {
  assert.equal(validTimeKst("07:00"), "07:00");
  assert.equal(validTimeKst(" 23:59 "), "23:59");
  for (const bad of ["7:00", "24:00", "07:60", "0700", "07:00:00", "", "ab:cd"]) assert.equal(validTimeKst(bad), null, bad);
});

test("작업 시간은 5~30분, 비용 상한은 10~1000원의 정수", () => {
  assert.equal(validCollectMinutes("5"), 5);
  assert.equal(validCollectMinutes("30"), 30);
  for (const bad of ["4", "31", "15.5", "-5", "", "abc"]) assert.equal(validCollectMinutes(bad), null, bad);
  assert.equal(validCollectMaxKrw("10"), 10);
  assert.equal(validCollectMaxKrw("1000"), 1000);
  for (const bad of ["9", "1001", "100.5", "", "1e3"]) assert.equal(validCollectMaxKrw(bad), null, bad);
});

test("폼 값이 모두 맞을 때만 저장할 설정을 만든다", () => {
  assert.deepEqual(parseDailyCollectForm({ enabled: true, time: "06:30", minutes: "20", maxKrw: "200" }), {
    ok: true,
    patch: { enabled: true, time_kst: "06:30", minutes: 20, max_krw: 200 },
  });
  const bad = parseDailyCollectForm({ enabled: false, time: "6:30", minutes: "45", maxKrw: "5" });
  assert.equal(bad.ok, false);
  if (!bad.ok) assert.equal(bad.errors.length, 3);
});

test("마지막 실행은 상태·기사·비용을 한국어로 요약한다", () => {
  assert.equal(runSummary(null), "아직 자동 수집 기록이 없습니다.");
  const done = runSummary({ date: "2026-10-30", status: "completed", articles: 42, new_articles: 7, spent_krw: 12, max_krw: 100 });
  assert.ok(done.includes("2026-10-30") && done.includes("완료") && done.includes("새 기사 7건") && done.includes("12원"));
  assert.ok(runSummary({ date: "2026-10-30", status: "stopped_cost_cap", articles: 40, new_articles: 3, spent_krw: 96, max_krw: 100 }).includes("비용 상한"));
  assert.ok(runSummary({ date: "2026-10-30", status: "skipped", reason: "operator_window_open" }).includes("운영자"));
  assert.ok(runSummary({ date: "2026-10-30", status: "mystery" }).includes("mystery"));
});
