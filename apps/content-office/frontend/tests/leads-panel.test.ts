import test from "node:test";
import assert from "node:assert/strict";
import { readFileSync } from "node:fs";
import { createRequire } from "node:module";
import ts from "typescript";
import * as leadHelpers from "../lib/leads.ts";
import { formatDate } from "../lib/workflow.ts";

const require = createRequire(import.meta.url);
const source = ts.createSourceFile("leads-panel.tsx", readFileSync(new URL("../app/leads-panel.tsx", import.meta.url), "utf8"), ts.ScriptTarget.Latest, true, ts.ScriptKind.TSX);
const declaration = source.statements.find(node => ts.isFunctionDeclaration(node) && node.name?.text === "LeadsPanel");
assert.ok(declaration);
const compiled = ts.transpileModule(declaration.getText(source), { compilerOptions: { module: ts.ModuleKind.CommonJS, jsx: ts.JsxEmit.ReactJSX } }).outputText;
type Element = { type?: string; props: Record<string, any> };
const tick = () => new Promise<void>((resolve) => setImmediate(resolve));

function fixture() {
  let cursor = 0;
  const hooks: any[] = [], effects: (() => void)[] = [], requests: any[] = [];
  const same = (old: any, deps: any[]) => old && deps.every((value, i) => Object.is(value, old.deps[i]));
  const useState = (initial: any) => { const index = cursor++; if (!(index in hooks)) hooks[index] = typeof initial === "function" ? initial() : initial; return [hooks[index], (value: any) => { hooks[index] = typeof value === "function" ? value(hooks[index]) : value; }]; };
  const useCallback = (fn: any, deps: any[]) => { const index = cursor++; if (!same(hooks[index], deps)) hooks[index] = { deps, fn }; return hooks[index].fn; };
  const useEffect = (effect: () => any, deps: any[]) => { const index = cursor++; if (!same(hooks[index], deps)) effects.push(() => { hooks[index] = { deps, cleanup: effect() }; }); };
  const api = { leads: async () => ({ leads: [] }), leadSummary: async () => ({ total: 0, consented: 0, withdrawn: 0, by_magnet: {}, by_source: {} }), addLead: async (input: any) => { requests.push(input); return { lead: { id: "synthetic-lead" } }; } };
  const module = { exports: {} as { LeadsPanel: (props: any) => Element } };
  Function("require", "module", "exports", "useState", "useCallback", "useEffect", "useId", "api", "formatDate", "Icon", "PublicLeadLinks", ...Object.keys(leadHelpers), compiled)(require, module, module.exports, useState, useCallback, useEffect, () => "lead-fixture", api, formatDate, () => null, () => null, ...Object.values(leadHelpers));
  const text = (value: any): string => Array.isArray(value) ? value.map(text).join("") : value?.props ? text(value.props.children) : typeof value === "string" || typeof value === "number" ? String(value) : "";
  function render() {
    cursor = 0;
    const tree = module.exports.LeadsPanel({ busy: false, action: async (_label: string, execute: () => Promise<unknown>) => { await execute(); return true; } }), nodes: Element[] = [];
    const visit = (value: any) => { if (Array.isArray(value)) value.forEach(visit); else if (value?.props) { nodes.push(value); visit(value.props.children); } };
    visit(tree); effects.splice(0).forEach((effect) => effect());
    return { text: text(tree), field: (name: string) => nodes.find(node => node.props.id === `lead-fixture-${name}`)!, form: nodes.find(node => node.type === "form")!, submit: nodes.find(node => node.type === "button" && node.props.type === "submit")!, alert: nodes.find(node => node.props.role === "alert") };
  }
  function fill() {
    for (const [field, value] of [["email", "reader@example.com"], ["magnet", "synthetic-notes"], ["source", "newsletter"], ["version", "v1"], ["consent", "뉴스레터라는 단어를 포함한 실제 동의 문구"]]) render().field(field).props.onChange({ target: { value } });
    render().field("confirmed").props.onChange({ target: { checked: true } });
  }
  return { render, fill, requests };
}

test("별도 뉴스레터 확인은 기본 꺼짐이고 일반 확인만 한 신청은 자료 전달 목적으로 기록한다", async () => {
  const view = fixture();
  assert.equal(view.render().field("newsletter-confirmed").props.checked, false);
  assert.match(view.render().text, /체크만으로 실제 동의가 생기지는 않습니다/);
  view.fill();
  assert.equal(view.render().field("newsletter-confirmed").props.checked, false);
  view.render().form.props.onSubmit({ preventDefault() {} }); await tick();
  assert.equal(view.requests[0].consent_purpose, "lead_magnet_delivery");
  assert.equal(view.requests[0].consent_text, "뉴스레터라는 단어를 포함한 실제 동의 문구");
});

test("별도 확인을 명시한 등록만 뉴스레터 목적이며 성공 후 두 확인과 이메일을 초기화한다", async () => {
  const view = fixture(); view.render(); view.fill();
  view.render().field("newsletter-confirmed").props.onChange({ target: { checked: true } });
  view.render().form.props.onSubmit({ preventDefault() {} }); await tick();
  assert.equal(view.requests[0].consent_purpose, "newsletter");
  assert.equal("newsletter_consent_confirmed" in view.requests[0], false);
  assert.equal(view.render().field("newsletter-confirmed").props.checked, false);
  assert.equal(view.render().field("confirmed").props.checked, false);
  assert.equal(view.render().field("email").props.value, "");
});

test("독자나 동의 문구를 바꾸면 별도 뉴스레터 확인을 다시 요구하며 일반 동의도 우회하지 않는다", async () => {
  const view = fixture(); view.render(); view.fill();
  view.render().field("newsletter-confirmed").props.onChange({ target: { checked: true } });
  view.render().field("email").props.onChange({ target: { value: "another@example.com" } });
  assert.equal(view.render().field("newsletter-confirmed").props.checked, false);
  view.render().field("newsletter-confirmed").props.onChange({ target: { checked: true } });
  assert.equal(view.render().submit.props.disabled, true);
  view.render().form.props.onSubmit({ preventDefault() {} }); await tick();
  assert.equal(view.requests.length, 0); assert.ok(view.render().alert);
});
