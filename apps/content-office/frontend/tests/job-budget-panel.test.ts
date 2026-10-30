import test from "node:test";
import assert from "node:assert/strict";
import { readFileSync } from "node:fs";
import { createRequire } from "node:module";
import ts from "typescript";
import { formatMoney } from "../lib/workflow.ts";

const require = createRequire(import.meta.url);
const source = ts.createSourceFile("support-panels.tsx", readFileSync(new URL("../app/support-panels.tsx", import.meta.url), "utf8"), ts.ScriptTarget.Latest, true, ts.ScriptKind.TSX);
const declaration = source.statements.find(node => ts.isFunctionDeclaration(node) && node.name?.text === "JobBudgetPanel");
assert.ok(declaration);
const compiled = ts.transpileModule(declaration.getText(source), { compilerOptions: { module: ts.ModuleKind.CommonJS, jsx: ts.JsxEmit.ReactJSX } }).outputText;
type Element = { type?: string; props: Record<string, any> };
const tick = () => new Promise<void>((resolve) => setImmediate(resolve));
const snapshot = (jobId = "job-one", overrides = {}) => ({ job_id: jobId, cap_krw: null, spent_krw: 0, reserved_krw: 400, remaining_krw: null, overrun_krw: 0, hash: "a".repeat(64), configured_by: null, configured_at: null, ...overrides });

function fixture(t: { after: (fn: () => void) => void }) {
  let props = { jobId: "job-one", globalCap: 10000, refreshKey: "v1", busy: false }, cursor = 0;
  const hooks: any[] = [], effects: (() => void)[] = [];
  const reads: { id: string; resolve: (value: unknown) => void; reject: (cause: Error) => void }[] = [];
  const writes: { id: string; cap: number; hash: string; resolve: (value: unknown) => void; reject: (cause: Error) => void }[] = [];
  const same = (old: any, deps: any[]) => old && deps.every((value, i) => Object.is(value, old.deps[i]));
  const useState = (initial: any) => { const index = cursor++; if (!(index in hooks)) hooks[index] = initial; return [hooks[index], (value: any) => { hooks[index] = typeof value === "function" ? value(hooks[index]) : value; }]; };
  const useRef = (initial: any) => { const index = cursor++; return hooks[index] ??= { current: initial }; };
  const useCallback = (fn: any, deps: any[]) => { const index = cursor++; if (!same(hooks[index], deps)) hooks[index] = { deps, fn }; return hooks[index].fn; };
  const useEffect = (effect: () => any, deps: any[]) => { const index = cursor++; const old = hooks[index]; if (!same(old, deps)) effects.push(() => { old?.cleanup?.(); hooks[index] = { deps, cleanup: effect() }; }); };
  t.after(() => hooks.forEach((hook) => hook?.cleanup?.()));
  const api = {
    jobBudget: (id: string) => new Promise((resolve, reject) => reads.push({ id, resolve, reject })),
    setJobBudget: (id: string, cap: number, hash: string) => new Promise((resolve, reject) => writes.push({ id, cap, hash, resolve, reject })),
  };
  const module = { exports: {} as { JobBudgetPanel: (props: any) => Element } };
  Function("require", "module", "exports", "useState", "useRef", "useCallback", "useEffect", "api", "formatMoney", compiled)(require, module, module.exports, useState, useRef, useCallback, useEffect, api, formatMoney);
  const text = (value: any): string => Array.isArray(value) ? value.map(text).join("") : value?.props ? text(value.props.children) : typeof value === "string" || typeof value === "number" ? String(value) : "";
  function render() {
    cursor = 0;
    const tree = module.exports.JobBudgetPanel(props), nodes: Element[] = [];
    const visit = (value: any) => { if (Array.isArray(value)) value.forEach(visit); else if (value?.props) { nodes.push(value); visit(value.props.children); } };
    visit(tree); effects.splice(0).forEach((effect) => effect());
    return { text: text(tree), input: nodes.find((node) => node.type === "input")!, save: nodes.find((node) => node.type === "button" && text(node) === "작업 상한 설정")!, reload: nodes.find((node) => node.type === "button" && text(node) === "예산 다시 조회")!, alert: nodes.find((node) => node.props.role === "alert") };
  }
  return { render, reads, writes, update: (patch: Partial<typeof props>) => { props = { ...props, ...patch }; } };
}

test("예산 미구현·빈 응답은 0원 성공으로 표시하지 않고 재조회로 미설정과 실제 사용량을 확인한다", async (t) => {
  const view = fixture(t); view.render();
  view.reads[0].reject(new Error("404 API 미구현")); await tick();
  assert.ok(view.render().alert); assert.equal(view.render().save.props.disabled, true);
  assert.doesNotMatch(view.render().text, /쓴 금액/);
  view.render().reload.props.onClick(); view.reads[1].resolve({}); await tick();
  assert.match(view.render().text, /숫자와 판본/);
  view.render().reload.props.onClick(); view.reads[2].resolve(snapshot()); await tick();
  assert.match(view.render().text, /미설정 · 전체 제한 적용/);
  assert.match(view.render().text, /예약·결과 불명400원/);
  assert.equal(view.render().save.props.disabled, false);
});

test("빈값·0·소수·지수·전체 초과는 저장하지 않고 명시 설정만 현재 해시로 보낸다", async (t) => {
  const view = fixture(t); view.render(); view.reads[0].resolve(snapshot()); await tick();
  for (const value of ["", "0", "-1", "1.5", "1e3", "10001"]) {
    view.render().input.props.onChange({ target: { value } });
    assert.equal(view.render().save.props.disabled, true);
    view.render().save.props.onClick(); assert.equal(view.writes.length, 0);
  }
  view.render().input.props.onChange({ target: { value: "1000" } });
  view.render().save.props.onClick(); view.render().save.props.onClick();
  assert.equal(view.writes.length, 1);
  assert.deepEqual({ id: view.writes[0].id, cap: view.writes[0].cap, hash: view.writes[0].hash }, { id: "job-one", cap: 1000, hash: "a".repeat(64) });
  view.writes[0].resolve(snapshot("job-one", { cap_krw: 1000, remaining_krw: 600, hash: "b".repeat(64) })); await tick();
  assert.match(view.render().text, /상한을 1,000원으로 기록/);
  assert.match(view.render().text, /예약·결과 불명400원/);
});

test("다른 작업의 늦은 예산 성공·실패를 무시하고 충돌 후 입력을 보존한다", async (t) => {
  const view = fixture(t); view.render();
  view.update({ jobId: "job-two" }); view.render();
  view.reads[1].resolve(snapshot("job-two", { spent_krw: 22 })); await tick();
  view.reads[0].resolve(snapshot("job-one", { spent_krw: 111 })); await tick();
  assert.match(view.render().text, /쓴 금액\(추정\)22원/); assert.doesNotMatch(view.render().text, /111원/);
  view.render().reload.props.onClick(); view.update({ refreshKey: "v2" }); view.render();
  view.reads[2].reject(new Error("오래된 실패")); await tick();
  assert.doesNotMatch(view.render().text, /오래된 실패/);
  view.reads[3].resolve(snapshot("job-two", { hash: "b".repeat(64) })); await tick();
  view.render().input.props.onChange({ target: { value: "1700" } }); view.render().save.props.onClick();
  view.writes[0].reject(new Error("업무 예산 설정이 변경되었습니다")); await tick();
  assert.match(view.render().text, /설정이 변경/); assert.equal(view.render().input.props.value, "1700");
  assert.equal(view.render().save.props.disabled, true);
  view.render().reload.props.onClick(); view.reads[4].resolve(snapshot("job-two", { hash: "c".repeat(64) })); await tick();
  view.render().save.props.onClick(); assert.equal(view.writes[1].hash, "c".repeat(64));
});
