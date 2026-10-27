import test from "node:test";
import assert from "node:assert/strict";
import { parseWorldMessage } from "../lib/world-bridge.ts";
test("유효한 메시지만 통과", () => {
  assert.deepEqual(parseWorldMessage({ source: "office-world", type: "open", view: "studio", itemId: "j1" }), { type: "open", view: "studio", itemId: "j1" });
  assert.deepEqual(parseWorldMessage({ source: "office-world", type: "action", action: "draft", itemId: "j1" }), { type: "action", action: "draft", itemId: "j1" });
  assert.equal(parseWorldMessage({ source: "other", type: "open" }), null);
  assert.equal(parseWorldMessage({ source: "office-world", type: "action", action: "approve", itemId: "j1" }), null);
  assert.equal(parseWorldMessage("x"), null);
});
