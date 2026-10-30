import test from "node:test";
import assert from "node:assert/strict";
import { parseWorldMessage, routeWorldMessage } from "../lib/world-bridge.ts";
test("유효한 메시지만 통과", () => {
  assert.deepEqual(parseWorldMessage({ source: "office-world", type: "open", view: "studio", itemId: "j1" }), { type: "open", view: "studio", itemId: "j1" });
  assert.deepEqual(parseWorldMessage({ source: "office-world", type: "action", action: "draft", itemId: "j1" }), { type: "action", action: "draft", itemId: "j1" });
  assert.equal(parseWorldMessage({ source: "other", type: "open" }), null);
  assert.equal(parseWorldMessage({ source: "office-world", type: "action", action: "approve", itemId: "j1" }), null);
  assert.equal(parseWorldMessage("x"), null);
});
const act = { source: "office-world", type: "action", action: "draft", itemId: "j1" };
const idle = { busy: false, connected: true, inFlight: false };
test("라우팅: 정상은 action, ready는 focus, open은 open", () => {
  assert.deepEqual(routeWorldMessage(parseWorldMessage(act)!, idle), { kind: "action" });
  assert.deepEqual(routeWorldMessage({ type: "ready" }, { ...idle, busy: true }), { kind: "focus" });
  assert.deepEqual(routeWorldMessage(parseWorldMessage({ source: "office-world", type: "open", view: "news", itemId: "j1" })!, { ...idle, connected: false }), { kind: "open" });
});
test("라우팅: 처리 중·미연결·진행 중 요청은 응답", () => {
  const m = parseWorldMessage(act)!;
  assert.deepEqual(routeWorldMessage(m, { ...idle, busy: true }), { kind: "reply", ok: false, message: "이미 처리 중입니다" });
  assert.deepEqual(routeWorldMessage(m, { ...idle, inFlight: true }), { kind: "reply", ok: false, message: "이미 처리 중입니다" });
  assert.deepEqual(routeWorldMessage(m, { ...idle, connected: false }), { kind: "reply", ok: false, message: "연결을 확인해 주세요" });
});

test("개발 팀 자동 배포 스위치 신호는 통과하고 콘텐츠 작업과 구분된다", async () => {
  const { isDevAction } = await import("../lib/world-bridge.ts");
  const on = parseWorldMessage({ source: "office-world", type: "action", action: "auto-deploy-on", itemId: "dev-auto" });
  assert.deepEqual(on, { type: "action", action: "auto-deploy-on", itemId: "dev-auto" });
  assert.equal(parseWorldMessage({ source: "office-world", type: "action", action: "deploy-now", itemId: "dev-auto" }), null);
  assert.equal(isDevAction("auto-deploy-off"), true);
  assert.equal(isDevAction("draft"), false);
});
