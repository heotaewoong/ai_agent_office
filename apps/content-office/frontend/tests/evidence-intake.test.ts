import test from "node:test";
import assert from "node:assert/strict";
import { readFileSync } from "node:fs";
import { createRequire } from "node:module";
import ts from "typescript";
import { packagingRequired } from "../lib/packaging.ts";
import { evidenceInputAllowed } from "../lib/workflow.ts";

type Element = { type?: string; props: Record<string, any> };
const require = createRequire(import.meta.url);
const source = ts.createSourceFile("support-panels.tsx", readFileSync(new URL("../app/support-panels.tsx", import.meta.url), "utf8"), ts.ScriptTarget.Latest, true, ts.ScriptKind.TSX);
const declaration = source.statements.find(node => ts.isFunctionDeclaration(node) && node.name?.text === "EvidenceIntake");
assert.ok(declaration);
const compiled = ts.transpileModule(declaration.getText(source), { compilerOptions: { module: ts.ModuleKind.CommonJS, jsx: ts.JsxEmit.ReactJSX } }).outputText;

function fixture(overrides: Record<string, any> = {}) {
  const requests: unknown[][] = [], changes: unknown[] = [], pending: Promise<unknown>[] = [];
  let visits = 0;
  const module = { exports: {} as { EvidenceIntake?: (props: Record<string, any>) => Element } };
  Function("require", "module", "exports", "api", "evidenceInputAllowed", "packagingRequired", "Icon", compiled)(
    require, module, module.exports, { registerEvidence: async (...args: unknown[]) => { requests.push(args); } }, evidenceInputAllowed, packagingRequired, () => null,
  );
  const props = {
    job: { id: "job_idea", state: "research_ready", source_hash: "version-1", article: { origin: "idea", url: "https://example.com/source", evidence: [] }, packaging: null },
    model: "gpt-5.5", busy: false, dirty: false,
    draft: { text: "공개 출처의 사용 권한을 확인한 본문입니다. ".repeat(20), version: "version-1", acknowledged: true },
    onChange: (value: unknown) => changes.push(value), onPackaging: () => { visits++; },
    action: (_label: string, execute: () => Promise<unknown>) => { const result = execute().then(() => true); pending.push(result); return result; },
    ...overrides,
  };
  const tree = module.exports.EvidenceIntake!(props);
  const nodes: Element[] = [];
  function visit(value: any) { if (Array.isArray(value)) value.forEach(visit); else if (value && typeof value === "object" && value.props) { nodes.push(value); visit(value.props.children); } }
  visit(tree);
  function text(value: any): string { return Array.isArray(value) ? value.map(text).join("") : value && typeof value === "object" ? text(value.props?.children) : typeof value === "string" ? value : ""; }
  const submit = nodes.find(node => node.type === "button" && text(node).includes("근거 등록하고"))!;
  return { props, tree, nodes, submit, requests, changes, pending, text: text(tree), visits: () => visits };
}

test("기획이 미확정이면 원문·동의를 보존하고 요청을 막은 채 기획 이동을 제공한다", async () => {
  const view = fixture();
  assert.equal(view.submit.props.disabled, true);
  assert.equal(view.nodes.find(node => node.type === "textarea")?.props.value, view.props.draft.text);
  assert.equal(view.nodes.find(node => node.type === "textarea")?.props.disabled, false);
  assert.equal(view.nodes.find(node => node.type === "input" && node.props.type === "checkbox")?.props.checked, true);
  view.submit.props.onClick();
  await Promise.all(view.pending);
  assert.equal(view.requests.length, 0); assert.deepEqual(view.changes, []);
  const visit = view.nodes.find(node => node.type === "button" && view.text.includes("제목·썸네일·후크") && node !== view.submit);
  assert.ok(visit); visit.props.onClick(); assert.equal(view.visits(), 1);
});

test("확정된 기획과 RSS는 기존 원문·해시로 요청하고 성공한 뒤에만 입력을 비운다", async () => {
  for (const article of [{ origin: "idea", evidence: [] }, { origin: "rss", evidence: [] }]) {
    const view = fixture({ job: { id: "job_ready", state: "research_ready", source_hash: "version-1", article, packaging: article.origin === "idea" ? { packaging_hash: "ready" } : null } });
    assert.equal(view.submit.props.disabled, false);
    view.submit.props.onClick(); await Promise.all(view.pending);
    assert.deepEqual(view.requests, [["job_ready", view.props.draft.text, "version-1"]]);
    assert.deepEqual(view.changes, [null]);
    assert.ok(view.text.includes("gpt-5.5"));
    assert.ok(!view.text.includes("Gemini"));
  }
});

test("확정된 기획도 동의·편집·버전 충돌 차단을 우회하지 못한다", async () => {
  for (const state of [{ busy: true }, { dirty: true }, { draft: { text: "원문".repeat(100), version: "old", acknowledged: true } }, { draft: { text: "원문".repeat(100), version: "version-1", acknowledged: false } }]) {
    const view = fixture({ job: { id: "job_ready", state: "research_ready", source_hash: "version-1", article: { origin: "idea" }, packaging: { packaging_hash: "ready" } }, ...state });
    assert.equal(view.submit.props.disabled, true);
    view.submit.props.onClick(); await Promise.all(view.pending);
    assert.deepEqual(view.requests, []); assert.deepEqual(view.changes, []);
  }
});
