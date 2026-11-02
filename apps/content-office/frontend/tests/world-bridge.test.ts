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

test("주식 팀 시세 확인 신호는 통과하고 매매 같은 다른 신호는 막는다", async () => {
  const { isStocksAction, isDevAction } = await import("../lib/world-bridge.ts");
  const refresh = parseWorldMessage({ source: "office-world", type: "action", action: "stocks-refresh", itemId: "stocks-quotes" });
  assert.deepEqual(refresh, { type: "action", action: "stocks-refresh", itemId: "stocks-quotes" });
  for (const action of ["stocks-buy", "stocks-sell", "stocks-order"])
    assert.equal(parseWorldMessage({ source: "office-world", type: "action", action, itemId: "stocks-quotes" }), null);
  assert.equal(isStocksAction("stocks-refresh"), true);
  assert.equal(isStocksAction("draft"), false);
  assert.equal(isDevAction("stocks-refresh"), false);
});

test('assistant-open accepts only actual native profiles and no extra command fields', () => {
  for (const assistant of ['lumi', 'ada', 'ethan', 'mia', 'noah', 'oliver', 'sam', 'mybots-sage', 'default']) {
    const message = parseWorldMessage({ source: 'office-world', type: 'assistant-open', assistant });
    assert.deepEqual(message, { type: 'assistant-open', assistant });
    assert.deepEqual(routeWorldMessage(message!, idle), { kind: 'assistant' });
  }
  assert.deepEqual(parseWorldMessage({ source: 'office-world', type: 'assistant-open' }), { type: 'assistant-open', assistant: 'lumi' });
  for (const patch of [{ assistant: 'director' }, { assistant: '__proto__' }, { assistant: null }, { assistant: 'ada', text: 'send now' }, { assistant: 'ada', itemId: 'native' }]) {
    assert.equal(parseWorldMessage({ source: 'office-world', type: 'assistant-open', ...patch }), null);
  }
});

test('assistant report actions identify a verified exact native report and reject stale or malformed references', async () => {
  const bridge: any = await import('../lib/world-bridge.ts');
  assert.equal(typeof bridge.parseAssistantReportAction, 'function');
  assert.equal(typeof bridge.matchesAssistantReportRef, 'function');
  const reference = { request_id: 'aa3a151d-72e8-4abf-b09d-10d416279c41', task_id: 't_final123', run_id: 9, event_id: 12 };
  const request = { ...reference, board: 'heobrain-office', status: 'completed', native_status: 'done',
    report: { ...reference, summary: '확인한 보고', verified: true },
    events: [{ id: 12, task_id: reference.task_id, run_id: 9, kind: 'completed', assignee: 'lumi' }] };
  for (const action of ['visit', 'result']) {
    const message = { source: 'content-office', type: 'assistant-report-action', action, ...reference };
    const parsed = bridge.parseAssistantReportAction(message);
    assert.deepEqual(parsed, { type: 'assistant-report-action', action, ...reference });
    assert.equal(bridge.matchesAssistantReportRef(parsed, request), true);
    for (const patch of [{ task_id: 't_other' }, { run_id: 8 }, { event_id: 11 }, { request_id: 'bbbbbbbb-72e8-4abf-b09d-10d416279c41' }]) {
      assert.equal(bridge.matchesAssistantReportRef({ ...parsed, ...patch }, request), false);
    }
    for (const patch of [{ source: 'office-world' }, { action: 'publish' }, { run_id: 1.5 }, { event_id: '12' }, { task_id: '../private' }, { request_id: 'bad' }, { url: 'https://other.test' }]) {
      assert.equal(bridge.parseAssistantReportAction({ ...message, ...patch }), null);
    }
  }
  for (const patch of [{ status: 'running' }, { native_status: 'running' }, { report: { ...request.report, verified: false } }, { events: [] }]) {
    assert.equal(bridge.matchesAssistantReportRef(reference, { ...request, ...patch }), false);
  }
});

test('assistant report replies use bounded plain messages with the exact action reference', async () => {
  const bridge: any = await import('../lib/world-bridge.ts');
  assert.equal(typeof bridge.parseAssistantReportResult, 'function');
  const reply = { source: 'office-world', type: 'assistant-report-result', action: 'visit', request_id: 'aa3a151d-72e8-4abf-b09d-10d416279c41', task_id: 't_final123', run_id: 9, event_id: 12, ok: true, message: '접수 작업실을 열었습니다.' };
  const { source: _source, ...expected } = reply;
  assert.deepEqual(bridge.parseAssistantReportResult(reply), expected);
  for (const patch of [{ source: 'content-office' }, { ok: 'true' }, { action: 'delete' }, { message: 'x'.repeat(401) }, { message: '/home/private' }, { message: 'token=private' }, { message: '\u202ehidden' }, { target: 'studio' }]) {
    assert.equal(bridge.parseAssistantReportResult({ ...reply, ...patch }), null);
  }
});
