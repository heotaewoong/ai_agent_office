import test from "node:test";
import assert from "node:assert/strict";
import { defaultIssueKey, validIssueKey, newsletterStateLabel } from "../lib/newsletter.ts";

test("회차 키는 서울 기준 'YYYY-MM-wN' (1~7일 w1, 8~14일 w2 …)", () => {
  assert.equal(defaultIssueKey(new Date("2026-10-29T00:00:00+09:00")), "2026-10-w5");
  assert.equal(defaultIssueKey(new Date("2026-10-01T00:00:00+09:00")), "2026-10-w1");
  assert.equal(defaultIssueKey(new Date("2026-10-07T23:59:00+09:00")), "2026-10-w1");
  assert.equal(defaultIssueKey(new Date("2026-10-08T00:00:00+09:00")), "2026-10-w2");
  // UTC 31일 23시는 서울 기준 11월 1일
  assert.equal(defaultIssueKey(new Date("2026-10-31T23:00:00Z")), "2026-11-w1");
});

test("회차 키 형식 검사", () => {
  assert.equal(validIssueKey("2026-10-w5"), true);
  assert.equal(validIssueKey("2026-10-w0"), false);
  assert.equal(validIssueKey("2026-10-w6"), false);
  assert.equal(validIssueKey("2026-1-w1"), false);
  assert.equal(validIssueKey(""), false);
});

test("회차 상태 이름", () => {
  assert.equal(newsletterStateLabel("draft"), "초안");
  assert.equal(newsletterStateLabel("approved"), "③ 회차 승인");
  assert.equal(newsletterStateLabel("rejected"), "반려");
  assert.equal(newsletterStateLabel("sent_manual"), "수동 발송 완료");
  assert.equal(newsletterStateLabel("other"), "other");
});
