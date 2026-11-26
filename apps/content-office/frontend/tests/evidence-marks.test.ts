import assert from "node:assert/strict";
import test from "node:test";
import { REJECT_REASONS, freshness, highlightParts } from "../lib/evidence-marks.ts";

test("반려 이유는 서버와 같은 여섯 가지다", () => {
  assert.deepEqual(REJECT_REASONS.map((reason) => reason.key), ["fact", "explanation", "style", "design", "rights", "format"]);
});

test("발행일이 1년 넘으면 표시한다", () => {
  const today = new Date("2026-11-26T00:00:00Z");
  assert.deepEqual(freshness("2025-11-26", today), { label: "발행 2025-11-26", stale: false });
  assert.deepEqual(freshness("2024-03-01", today), { label: "발행 2024-03-01 · 1년 넘음", stale: true });
  assert.equal(freshness(undefined, today), null);
  assert.equal(freshness("어제", today), null);
});

test("핵심 문장만 표시하고 문단은 그대로 둔다", () => {
  const quote = "첫 문장이에요. 커피는 6시간 전에 끊어요. 끝 문장이에요.";
  const parts = highlightParts(quote, "커피는 6시간 전에 끊어요.");
  assert.equal(parts.map((part) => part.text).join(""), quote);
  assert.deepEqual(parts.filter((part) => part.mark).map((part) => part.text), ["커피는 6시간 전에 끊어요."]);
  assert.deepEqual(highlightParts(quote, "문단에 없는 문장"), [{ text: quote, mark: false }]);
  assert.deepEqual(highlightParts(quote), [{ text: quote, mark: false }]);
});
