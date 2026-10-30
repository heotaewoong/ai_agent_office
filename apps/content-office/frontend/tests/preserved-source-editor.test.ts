import test from "node:test";
import assert from "node:assert/strict";
import { readFileSync } from "node:fs";
import { createRequire } from "node:module";
import ts from "typescript";
import * as workflow from "../lib/workflow.ts";
import { packagingRequired } from "../lib/packaging.ts";

type Element = { type?: unknown; props: Record<string, any> };
const require = createRequire(import.meta.url);
const source = ts.createSourceFile("page.tsx", readFileSync(new URL("../app/page.tsx", import.meta.url), "utf8"), ts.ScriptTarget.Latest, true, ts.ScriptKind.TSX);
const declaration = source.statements.find(node => ts.isFunctionDeclaration(node) && node.name?.text === "Studio");
assert.ok(declaration);
const compiled = ts.transpileModule(declaration.getText(source), { compilerOptions: { module: ts.ModuleKind.CommonJS, jsx: ts.JsxEmit.ReactJSX } }).outputText;
const components = new Set<string>();
function collectComponents(node: ts.Node) {
  if ((ts.isJsxOpeningElement(node) || ts.isJsxSelfClosingElement(node)) && ts.isIdentifier(node.tagName) && /^[A-Z]/.test(node.tagName.text)) components.add(node.tagName.text);
  ts.forEachChild(node, collectComponents);
}
collectComponents(declaration);

function fixture(preserveOriginal: boolean | undefined) {
  const original = "# 직접 쓴 글\n\n표현과 줄바꿈을 그대로 보존합니다.\n\n```text\n공백  \n```\n";
  const job = { id: "job-preserved", title: "기존 제목", state: "source_review", source_hash: "a".repeat(64),
    article: { id: "own-article", url: "https://example.test/own-article", preserve_original: preserveOriginal, operator_source_text: original },
    source_packet: { title: "기존 제목", body: original, evidence: [], quality: { status: "passed", critical: false, reviews: [] } },
    selections: { blog: true, video: true, pdf: false, cards: false } };
  const changes: { id: string; draft: Record<string, unknown> }[] = [];
  const hooks: any[] = [], effects: (() => void)[] = [];
  let cursor = 0;
  const useState = (initial: any) => { const index = cursor++; if (!(index in hooks)) hooks[index] = initial; return [hooks[index], (value: any) => { hooks[index] = typeof value === "function" ? value(hooks[index]) : value; }]; };
  const useRef = (initial: any) => { const index = cursor++; return hooks[index] ??= { current: initial }; };
  const useEffect = (effect: () => void, deps: any[]) => { const index = cursor++, previous = hooks[index]; if (!previous || deps.some((value, i) => !Object.is(value, previous[i]))) { hooks[index] = deps; effects.push(effect); } };
  // Child panels are outside this editor test; Studio and its event handlers execute unchanged.
  const scope = { require, exports: {}, useState, useRef, useEffect, ...workflow, packagingRequired,
    ...Object.fromEntries([...components].map(name => [name, () => null])) };
  const Studio = Function(...Object.keys(scope), `${compiled}\nreturn Studio;`)(...Object.values(scope));
  const props = { job, busy: false, onDraftChange: (id: string, draft: Record<string, unknown>) => changes.push({ id, draft }),
    onIntakeChange: () => {}, onBriefDraftChange: () => {}, onOfferDraftChange: () => {}, onSaved: () => {}, onDelivery: () => {},
    action: () => assert.fail("Editing must not start an API action") };
  const text = (value: any): string => Array.isArray(value) ? value.map(text).join("") : value?.props ? text(value.props.children) : typeof value === "string" || typeof value === "number" ? String(value) : "";
  function render() {
    cursor = 0;
    const tree = Studio(props), nodes: Element[] = [];
    function visit(value: any) { if (Array.isArray(value)) value.forEach(visit); else if (value?.props) { nodes.push(value); visit(value.props.children); } }
    visit(tree); effects.splice(0).forEach(effect => effect());
    const title = nodes.find(node => node.props.id === "draft-title"), body = nodes.find(node => node.props.id === "draft-body");
    assert.ok(title); assert.ok(body);
    return { title, body, nodes, text: text(tree) };
  }
  return { original, job, changes, render };
}

test("원문 보존 본문은 읽기 전용이며 직접 change 호출도 상태와 입력 캐시를 바꾸지 않는다", () => {
  const view = fixture(true), initial = view.render();
  assert.equal(initial.body.props.readOnly, true);
  assert.equal(initial.body.props.disabled, false);
  assert.equal(initial.body.props.value, view.original);
  const help = initial.nodes.find(node => node.props.id === initial.body.props["aria-describedby"]);
  assert.ok(help); assert.match(initial.text, /전체 글을 다시 등록/);
  initial.body.props.onChange({ target: { value: "직접 바꾸려는 본문" } });
  assert.deepEqual(view.changes, []);
  const current = view.render();
  assert.equal(current.body.props.value, view.original);
  assert.equal(current.title.props.value, view.job.title);
  assert.doesNotMatch(current.text, /저장하지 않은 변경/);
});

test("원문 보존 모드에서도 제목 편집은 원문 본문과 판본을 유지해 입력 캐시에 반영한다", () => {
  const view = fixture(true), initial = view.render();
  assert.equal(initial.title.props.disabled, false);
  initial.title.props.onChange({ target: { value: "새 파생 제목" } });
  assert.deepEqual(view.changes, [{ id: view.job.id, draft: { title: "새 파생 제목", body: view.original, baseHash: view.job.source_hash } }]);
  const current = view.render();
  assert.equal(current.title.props.value, "새 파생 제목");
  assert.equal(current.body.props.value, view.original);
  assert.equal(current.body.props.readOnly, true);
  assert.match(current.text, /저장하지 않은 변경/);
});

test("요약 모드와 기존 미지정 모드는 본문 편집을 허용하고 제목과 판본을 보존한다", () => {
  for (const mode of [false, undefined]) {
    const view = fixture(mode), initial = view.render();
    assert.equal(initial.body.props.readOnly, false);
    initial.body.props.onChange({ target: { value: "수정한 요약 본문" } });
    assert.deepEqual(view.changes, [{ id: view.job.id, draft: { title: view.job.title, body: "수정한 요약 본문", baseHash: view.job.source_hash } }]);
    const current = view.render();
    assert.equal(current.body.props.value, "수정한 요약 본문");
    assert.equal(current.title.props.value, view.job.title);
    assert.match(current.text, /저장하지 않은 변경/);
  }
});
