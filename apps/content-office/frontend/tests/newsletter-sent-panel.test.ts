import test from "node:test";
import assert from "node:assert/strict";
import { readFileSync } from "node:fs";
import { createRequire } from "node:module";
import ts from "typescript";
import * as newsletter from "../lib/newsletter.ts";
import { approvalIsCurrent, formatDate } from "../lib/workflow.ts";

type Element = { type?: unknown; props: Record<string, any> };
const require = createRequire(import.meta.url);
const compiled = ts.transpileModule(readFileSync(new URL("../app/newsletter-panel.tsx", import.meta.url), "utf8"), { compilerOptions: { module: ts.ModuleKind.CommonJS, jsx: ts.JsxEmit.ReactJSX } }).outputText;
const tick = () => new Promise<void>(resolve => setImmediate(resolve));

function fixture(reviewHash: string | undefined) {
  const issue = { id: "issue-one", job_id: "job-one", state: "approved", issue_key: "2026-10-w5", subject: "읽은 판본 A", markdown: "# 읽은 판본 A",
    hash: "c".repeat(64), review_hash: reviewHash, recipients_hash: "d".repeat(64), recipient_count: 1, built_at: "2026-10-30T01:00:00Z" };
  const newer = { ...issue, subject: "서버의 새 판본 B", markdown: "# 서버의 새 판본 B", hash: "e".repeat(64), review_hash: "b".repeat(64) };
  const writes: unknown[][] = [], order: string[] = [], pending: Promise<unknown>[] = [];
  const hooks: any[] = [], effects: (() => void)[] = [];
  let cursor = 0, reads = 0, confirmations = 0, complete: (value: unknown) => void = () => {};
  const same = (old: any, deps: any[]) => old && deps.every((value, i) => Object.is(value, old.deps[i]));
  const react = {
    useId: () => "synthetic-newsletter",
    useState: (initial: any) => { const index = cursor++; if (!(index in hooks)) hooks[index] = typeof initial === "function" ? initial() : initial; return [hooks[index], (value: any) => { hooks[index] = typeof value === "function" ? value(hooks[index]) : value; }]; },
    useCallback: (fn: any, deps: any[]) => { const index = cursor++; if (!same(hooks[index], deps)) hooks[index] = { deps, fn }; return hooks[index].fn; },
    useEffect: (effect: () => void, deps: any[]) => { const index = cursor++; if (!same(hooks[index], deps)) { hooks[index] = { deps }; effects.push(effect); } },
  };
  const api = {
    newsletters: async () => { reads++; order.push("read"); return { issues: [reads === 1 ? issue : newer] }; },
    newsletterExportUrl: (id: string) => `/synthetic/export/${id}`,
    markNewsletterSent: (...args: unknown[]) => { writes.push(args); order.push("sent"); return new Promise(resolve => { complete = resolve; }); },
  };
  const module = { exports: {} as { NewsletterPanel: (props: any) => Element } };
  const modules: Record<string, unknown> = { react, "../lib/api": { api }, "../lib/newsletter": newsletter,
    "../lib/workflow": { approvalIsCurrent, formatDate }, "./icons": { Icon: () => null } };
  Function("require", "module", "exports", "window", compiled)(
    (name: string) => modules[name] ?? require(name), module, module.exports,
    { confirm: () => { confirmations++; order.push("confirm"); return true; } },
  );
  const props = { job: { id: "job-one", title: "합성 시험", state: "release_approved", updated_at: "v1", source_hash: "source-one",
    release_approval: { decision: "approved", version: "manifest-one" }, manifest: { hash: "manifest-one", source_hash: "source-one" } }, busy: false,
    action: (_label: string, execute: () => Promise<unknown>) => { const result = execute().then(() => true); pending.push(result); return result; } };
  const text = (value: any): string => Array.isArray(value) ? value.map(text).join("") : value?.props ? text(value.props.children) : typeof value === "string" ? value : "";
  function render() {
    cursor = 0;
    const tree = module.exports.NewsletterPanel(props), nodes: Element[] = [];
    const visit = (value: any) => { if (Array.isArray(value)) value.forEach(visit); else if (value?.props) { nodes.push(value); visit(value.props.children); } };
    visit(tree); effects.splice(0).forEach(effect => effect());
    return { text: text(tree), sent: nodes.find(node => node.type === "button" && text(node).trim() === "발송 완료로 표시") };
  }
  return { issue, writes, order, pending, render, complete: () => complete({ ...issue, state: "sent_manual" }), reads: () => reads, confirmations: () => confirmations };
}

test("승인 회차라도 읽은 판본 토큰이 없거나 손상되면 발송 표시와 직접 클릭 호출을 차단한다", async () => {
  for (const hash of [undefined, "", "bad", "A".repeat(64)]) {
    const view = fixture(hash); view.render(); await tick();
    const shown = view.render();
    assert.ok(shown.sent); assert.equal(shown.sent.props.disabled, true);
    shown.sent.props.onClick(); await tick();
    assert.deepEqual(view.writes, []);
    assert.equal(view.confirmations(), 0);
    assert.equal(view.reads(), 1);
  }
});

test("발송 표시는 화면에 읽은 A 토큰을 보내고 새 B 판본을 먼저 조회해 요청을 바꾸지 않는다", async () => {
  const hash = "a".repeat(64), view = fixture(hash);
  view.render(); await tick();
  const shown = view.render();
  assert.match(shown.text, /읽은 판본 A/);
  assert.ok(shown.sent); assert.equal(shown.sent.props.disabled, false);
  shown.sent.props.onClick();
  assert.deepEqual(view.writes, [[view.issue.id, hash]]);
  assert.deepEqual(view.order, ["read", "confirm", "sent"]);
  assert.equal(view.reads(), 1);
  // A successful mark may refresh the list; it must never resubmit that newer edition.
  view.complete(); await Promise.all(view.pending); await tick();
  assert.equal(view.reads(), 2);
  assert.match(view.render().text, /서버의 새 판본 B/);
  assert.deepEqual(view.writes, [[view.issue.id, hash]]);
});
