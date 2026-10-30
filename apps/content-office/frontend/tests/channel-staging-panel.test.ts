import test from "node:test";
import assert from "node:assert/strict";
import { readFileSync } from "node:fs";
import { createRequire } from "node:module";
import ts from "typescript";
import * as readiness from "../lib/delivery-readiness.ts";
import * as workflow from "../lib/workflow.ts";
import * as channels from "../lib/channels.ts";
import * as settings from "../lib/settings.ts";

const require = createRequire(import.meta.url);
const compiled = ts.transpileModule(readFileSync(new URL("../app/youtube-panel.tsx", import.meta.url), "utf8"), { compilerOptions: { module: ts.ModuleKind.CommonJS, jsx: ts.JsxEmit.ReactJSX } }).outputText;
type Element = { type?: string; props: Record<string, any> };
const tick = () => new Promise<void>((resolve) => setImmediate(resolve));
const snapshot = (jobId = "job-one", label = "현재 채널") => ({ job_id: jobId, source_hash: "a".repeat(64), manifest_hash: "b".repeat(64), current_release: true, recorded_current: false, recorded_at: null, stage_hash: "c".repeat(64), blockers: [], notes: [], channels: [{ channel_key: "threads_main", label, platform: "threads", locale: "ko", local_ready: true, status: "local_ready", external_state: "not_connected", external_draft_created: false, external_id: null, can_upload_private: false, blockers: [], required_files: ["threads-main.txt"], files: [] }] });

function fixture(t: { after: (fn: () => void) => void }) {
  let job = { id: "job-one", updated_at: "v1", source_hash: "a".repeat(64), source_packet: { audience: { language: "ko" } }, brief: { language: "ko" } };
  let cursor = 0;
  const hooks: any[] = [], effects: (() => void)[] = [];
  const requests: { id: string; resolve: (data: unknown) => void; reject: (cause: Error) => void }[] = [];
  const writes: { id: string; hash: string }[] = [];
  const same = (old: any, deps: any[]) => old && deps.every((value, i) => Object.is(value, old.deps[i]));
  const react = {
    useState: (initial: any) => { const index = cursor++; if (!(index in hooks)) hooks[index] = initial; return [hooks[index], (value: any) => { hooks[index] = typeof value === "function" ? value(hooks[index]) : value; }]; },
    useRef: (initial: any) => { const index = cursor++; return hooks[index] ??= { current: initial }; },
    useCallback: (fn: any, deps: any[]) => { const index = cursor++; if (!same(hooks[index], deps)) hooks[index] = { deps, fn }; return hooks[index].fn; },
    useEffect: (effect: () => any, deps: any[]) => { const index = cursor++; const old = hooks[index]; if (!same(old, deps)) effects.push(() => { old?.cleanup?.(); hooks[index] = { deps, cleanup: effect() }; }); },
  };
  const unmount = () => hooks.forEach((hook) => hook?.cleanup?.());
  t.after(unmount);
  const api = {
    channelStaging: (id: string) => new Promise((resolve, reject) => requests.push({ id, resolve, reject })),
    recordChannelStaging: async (id: string, hash: string) => { writes.push({ id, hash }); return { ...snapshot(id), recorded_current: true, recorded_at: "2026-10-30T00:00:00Z" }; },
  };
  const modules: Record<string, unknown> = { react, "../lib/api": { api }, "../lib/delivery-readiness": readiness, "../lib/workflow": workflow, "../lib/channels": channels, "../lib/settings": settings, "./icons": { Icon: () => null } };
  const module = { exports: {} as { ChannelHandoffPanel: (props: any) => Element } };
  Function("require", "module", "exports", compiled)((name: string) => modules[name] ?? require(name), module, module.exports);
  const text = (value: any): string => Array.isArray(value) ? value.map(text).join("") : value?.props ? text(value.props.children) : typeof value === "string" || typeof value === "number" ? String(value) : "";
  function render() {
    cursor = 0;
    const tree = module.exports.ChannelHandoffPanel({ job, busy: false, action: async (_label: string, execute: () => Promise<unknown>) => { try { await execute(); return true; } catch (cause) { return String(cause); } } });
    const nodes: Element[] = [];
    const visit = (value: any) => { if (Array.isArray(value)) value.forEach(visit); else if (value?.props) { nodes.push(value); visit(value.props.children); } };
    visit(tree);
    effects.splice(0).forEach((effect) => effect());
    return { text: text(tree), record: nodes.find((node) => node.type === "button" && text(node) === "앱 배포대기 장부에 기록")!, refresh: nodes.find((node) => node.type === "button" && text(node) === "상태 다시 확인")!, alert: nodes.find((node) => node.props.role === "alert"), status: nodes.find((node) => node.props.role === "status"), region: nodes.find((node) => node.props.role === "region") };
  }
  return { render, requests, writes, update: (updatedAt: string) => { job = { ...job, updated_at: updatedAt }; }, unmount };
}

test("준비표의 늦은 성공과 실패는 현재 판본을 덮거나 기록 버튼을 열지 않는다", async (t) => {
  const view = fixture(t);
  view.render();
  assert.ok(view.render().status);
  view.update("v2"); view.render();
  view.requests[1].resolve(snapshot("job-one", "최신 채널")); await tick();
  assert.match(view.render().text, /최신 채널/);
  view.requests[0].resolve(snapshot("job-one", "이전 채널")); await tick();
  assert.doesNotMatch(view.render().text, /이전 채널/);
  assert.equal(view.render().record.props.disabled, false);
  view.render().refresh.props.onClick();
  view.update("v3"); view.render();
  view.requests[2].reject(new Error("이전 오류")); await tick();
  assert.doesNotMatch(view.render().text, /이전 오류/);
  assert.equal(view.render().record.props.disabled, true);
  view.requests[3].resolve(snapshot("job-one", "세 번째 판본")); await tick();
  assert.match(view.render().text, /세 번째 판본/);
});

test("빈 준비표와 조회 실패는 경고와 잠긴 기록 버튼을 보여주고 명시 재조회로 복구한다", async (t) => {
  const view = fixture(t);
  view.render();
  view.requests[0].resolve({ ...snapshot(), channels: [] }); await tick();
  assert.ok(view.render().alert);
  assert.equal(view.render().record.props.disabled, true);
  view.render().refresh.props.onClick();
  view.requests[1].reject(new Error("합성 연결 실패")); await tick();
  assert.match(view.render().text, /합성 연결 실패/);
  assert.equal(view.render().record.props.disabled, true);
  view.render().refresh.props.onClick();
  view.requests[2].resolve(snapshot()); await tick();
  const recovered = view.render();
  assert.equal(recovered.alert, undefined);
  assert.equal(recovered.record.props.disabled, false);
  assert.equal(recovered.region?.props.tabIndex, 0);
  assert.match(recovered.region?.props["aria-label"], /스크롤/);
  recovered.record.props.onClick(); await tick();
  assert.deepEqual(view.writes, [{ id: "job-one", hash: "c".repeat(64) }]);
});
