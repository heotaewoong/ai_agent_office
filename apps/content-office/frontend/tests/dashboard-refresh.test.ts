import test from "node:test";
import assert from "node:assert/strict";
import { readFileSync } from "node:fs";
import { runInNewContext } from "node:vm";
import ts from "typescript";
import { createDashboardRefreshGuard } from "../lib/dashboard-refresh.ts";

const page = ts.createSourceFile("page.tsx", readFileSync(new URL("../app/page.tsx", import.meta.url), "utf8"), ts.ScriptTarget.Latest, true, ts.ScriptKind.TSX);

function pageFunction(name: "loadDashboard" | "action" | "effect") {
  let code = "";
  function visit(node: ts.Node) {
    if (name === "loadDashboard" && ts.isVariableDeclaration(node) && node.name.getText(page) === name && node.initializer && ts.isCallExpression(node.initializer)) code = node.initializer.arguments[0].getText(page);
    if (name === "action" && ts.isFunctionDeclaration(node) && node.name?.text === name) code = `(${node.getText(page)})`;
    if (name === "effect" && ts.isCallExpression(node) && node.expression.getText(page) === "useEffect" && node.arguments[0]?.getText(page).includes("dashboardRefresh.current.activate")) code = node.arguments[0].getText(page);
    ts.forEachChild(node, visit);
  }
  visit(page);
  assert.ok(code, `실제 page의 ${name}을 검사합니다`);
  return ts.transpileModule(`(${code})`, { compilerOptions: { target: ts.ScriptTarget.ES2022 } }).outputText;
}

type Reply = { version: string; articles: { id: string }[]; jobs: { id: string }[] };
function harness(activate = true) {
  const guard = createDashboardRefreshGuard();
  if (activate) guard.activate(true);
  const pending: { resolve: (reply: Reply) => void; reject: (error: Error) => void }[] = [];
  const state = { dashboard: null as Reply | null, connected: false, error: "", dashboardError: "", loading: true, selected: ["article_new"], busy: "", notice: "" };
  const events = new Map<string, () => void>();
  const intervals = new Map<number, () => void>();
  const document = { hidden: false, addEventListener: (name: string, callback: () => void) => events.set(name, callback), removeEventListener: (name: string) => events.delete(name) };
  const context = {
    api: { dashboard: () => new Promise<Reply>((resolve, reject) => pending.push({ resolve, reject })) },
    dashboardRefresh: { current: guard }, alive: { current: true },
    jobRefresh: { current: { activeId: "job_keep", invalidate() {} } },
    selectJob() {}, setDashboard: (value: Reply) => { state.dashboard = value; },
    setConnected: (value: boolean) => { state.connected = value; }, setLastLoaded() {},
    setSelected: (update: (current: string[]) => string[]) => { state.selected = update(state.selected); },
    setError: (value: string) => { state.error = value; }, setLoading: (value: boolean) => { state.loading = value; },
    setDashboardError: (value: string) => { state.dashboardError = value; },
    setBusy: (value: string) => { state.busy = value; }, setNotice: (value: string) => { state.notice = value; },
    setNow() {}, document,
    setInterval: (callback: () => void) => { const id = intervals.size + 1; intervals.set(id, callback); return id; },
    clearInterval: (id: number) => intervals.delete(id),
    busy: "", connected: true, loadJob: async () => {}, OfficeApiError: class extends Error { status = 0; }, Date, Error,
  };
  const load = runInNewContext(pageFunction("loadDashboard"), context) as (force?: boolean) => Promise<void>;
  const linked = { ...context, loadDashboard: load };
  const action = runInNewContext(pageFunction("action"), linked) as (label: string, execute: () => Promise<void>, success: string) => Promise<true | string>;
  const mount = runInNewContext(pageFunction("effect"), linked) as () => () => void;
  return { guard, pending, state, load, action, mount, events, intervals, document, alive: context.alive };
}

const oldReply = { version: "old", articles: [{ id: "article_old" }], jobs: [{ id: "job_keep" }] };
const newReply = { version: "new", articles: [{ id: "article_new" }], jobs: [{ id: "job_keep" }] };
const flush = () => new Promise<void>((resolve) => setImmediate(resolve));

test("일반 목록 조회는 겹치지 않고 강제 갱신만 이전 응답을 대체한다", async () => {
  const h = harness();
  const old = h.load();
  await h.load();
  assert.equal(h.pending.length, 1);
  const fresh = h.load(true);
  assert.equal(h.pending.length, 2);
  h.pending[1].resolve(newReply);
  await fresh;
  h.pending[0].resolve(oldReply);
  await old;
  assert.equal(h.state.dashboard, newReply);
  assert.deepEqual(h.state.selected, ["article_new"]);
  assert.equal(h.state.connected, true);
  assert.equal(h.state.loading, false);
});

test("옛 실패와 finally는 새 연결·선택·초기 로딩을 바꾸지 않는다", async () => {
  const h = harness();
  const old = h.load();
  const fresh = h.load(true);
  await old;
  assert.equal(h.state.loading, true);
  h.pending[1].resolve(newReply);
  await fresh;
  h.pending[0].reject(new Error("옛 요청 실패"));
  await flush();
  assert.equal(h.state.dashboard, newReply);
  assert.equal(h.state.connected, true);
  assert.equal(h.state.error, "");
  assert.equal(h.state.dashboardError, "");
  assert.deepEqual(h.state.selected, ["article_new"]);
});

test("실제 action 완료 뒤에는 대기 중 poll을 무효화하고 최신 목록을 요청한다", async () => {
  const h = harness();
  const old = h.load();
  const action = h.action("저장", async () => {}, "저장 완료");
  await flush();
  assert.equal(h.pending.length, 2);
  h.pending[1].resolve(newReply);
  assert.equal(await action, true);
  h.pending[0].resolve(oldReply);
  await old;
  assert.equal(h.state.dashboard, newReply);
  assert.deepEqual(h.state.selected, ["article_new"]);
  assert.equal(h.state.notice, "저장 완료");
  assert.equal(h.state.busy, "");
});

test("현재 요청 실패는 로딩을 끝내고 다음 poll의 연결 복구를 허용한다", async () => {
  const h = harness();
  const failed = h.load();
  h.pending[0].reject(new Error("현재 연결 실패"));
  await failed;
  assert.equal(h.state.connected, false);
  assert.equal(h.state.loading, false);
  assert.equal(h.state.dashboardError, "현재 연결 실패");
  assert.equal(h.state.error, "");
  h.state.error = "별도 원고 승인 오류";
  const recovered = h.load();
  assert.equal(h.pending.length, 2);
  h.pending[1].resolve(newReply);
  await recovered;
  assert.equal(h.state.connected, true);
  assert.equal(h.state.dashboard, newReply);
  assert.equal(h.state.dashboardError, "");
  assert.equal(h.state.error, "별도 원고 승인 오류");
});

test("응답이 취소를 무시해도 30초 후 로딩·진행 중 잠금을 풀고 늦은 성공을 무시한다", async (t) => {
  t.mock.timers.enable({ apis: ["setTimeout"] });
  const h = harness();
  const stalled = h.load();
  t.mock.timers.tick(30_000);
  await stalled;
  assert.equal(h.state.loading, false);
  assert.equal(h.state.connected, false);
  assert.match(h.state.dashboardError, /시간이 초과/);
  const fresh = h.load();
  h.pending[1].resolve(newReply);
  await fresh;
  h.pending[0].resolve(oldReply);
  await flush();
  assert.equal(h.state.dashboard, newReply);
  assert.equal(h.state.connected, true);
});

test("hidden 동안 조회를 멈추고 visible 복귀는 즉시 새 목록을 읽는다", async () => {
  const h = harness(false);
  const cleanup = h.mount();
  assert.equal(h.pending.length, 1);
  const tick = [...h.intervals.values()][0];
  tick();
  assert.equal(h.pending.length, 1);
  h.document.hidden = true;
  h.events.get("visibilitychange")!();
  tick();
  await h.load(true);
  assert.equal(h.pending.length, 1);
  await flush();
  assert.equal(h.state.loading, true);
  h.document.hidden = false;
  h.events.get("visibilitychange")!();
  assert.equal(h.pending.length, 2);
  h.pending[1].resolve(newReply);
  await flush();
  h.pending[0].reject(new Error("hidden 전 요청 실패"));
  await flush();
  assert.equal(h.state.dashboard, newReply);
  assert.equal(h.state.connected, true);
  assert.equal(h.state.error, "");
  cleanup();
  assert.equal(h.events.size, 0);
  assert.equal(h.intervals.size, 0);
});

test("처음 hidden이면 요청하지 않고 StrictMode cleanup 뒤 이전 응답을 복원하지 않는다", async () => {
  const h = harness(false);
  h.document.hidden = true;
  const cleanupHidden = h.mount();
  assert.equal(h.pending.length, 0);
  cleanupHidden();
  h.document.hidden = false;
  const cleanupFirst = h.mount();
  assert.equal(h.pending.length, 1);
  cleanupFirst();
  const cleanupSecond = h.mount();
  assert.equal(h.pending.length, 2);
  h.pending[0].resolve(oldReply);
  await flush();
  assert.equal(h.state.dashboard, null);
  assert.equal(h.state.loading, true);
  h.pending[1].resolve(newReply);
  await flush();
  assert.equal(h.state.dashboard, newReply);
  assert.equal(h.state.connected, true);
  cleanupSecond();
  assert.equal(h.alive.current, false);
  assert.equal(h.events.size, 0);
  assert.equal(h.intervals.size, 0);
  await h.load(true);
  assert.equal(h.pending.length, 2);
});

test("교체·완료·cleanup은 이전 타이머를 취소해 이후 요청을 끊지 않는다", async (t) => {
  t.mock.timers.enable({ apis: ["setTimeout"] });
  const guard = createDashboardRefreshGuard();
  guard.activate(true);
  const first = guard.begin()!;
  const cancelled = guard.wait(first, new Promise<never>(() => {})).catch(() => "cancelled");
  t.mock.timers.tick(15_000);
  const second = guard.begin(true)!;
  assert.equal(await cancelled, "cancelled");
  t.mock.timers.tick(15_000);
  assert.equal(second.controller.signal.aborted, false);
  assert.equal(guard.settle(first), false);
  assert.equal(guard.begin(), null);
  assert.equal(guard.settle(second), true);
  const third = guard.begin()!;
  guard.deactivate();
  assert.equal(third.controller.signal.aborted, true);
  guard.activate(true);
  const fourth = guard.begin()!;
  assert.equal(fourth.controller.signal.aborted, false);
  guard.settle(fourth);
});
