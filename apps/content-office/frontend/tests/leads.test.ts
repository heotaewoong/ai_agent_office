import test from "node:test";
import assert from "node:assert/strict";
import { validEmail, leadSourceLabel } from "../lib/leads.ts";

test("이메일 형식만 통과한다", () => {
  assert.equal(validEmail("reader@example.com"), true);
  assert.equal(validEmail("  reader@example.com  "), true);
  assert.equal(validEmail("reader@example"), false);
  assert.equal(validEmail("reader example@example.com"), false);
  assert.equal(validEmail("@example.com"), false);
  assert.equal(validEmail(""), false);
  assert.equal(validEmail(`${"a".repeat(250)}@example.com`), false);
});

test("리드 출처 이름", () => {
  assert.equal(leadSourceLabel("homepage"), "홈페이지");
  assert.equal(leadSourceLabel("manual"), "수동 등록");
  assert.equal(leadSourceLabel("x"), "x");
});
