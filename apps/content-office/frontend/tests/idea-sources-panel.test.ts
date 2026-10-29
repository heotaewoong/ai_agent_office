import test from "node:test";
import assert from "node:assert/strict";
import { readFileSync } from "node:fs";
import { createRequire } from "node:module";
import ts from "typescript";
import * as helpers from "../lib/ideas.ts";
import type { Idea } from "../lib/types.ts";

const require = createRequire(import.meta.url);
const compiled = ts.transpileModule(readFileSync(new URL("../app/idea-sources-panel.tsx", import.meta.url), "utf8"), { compilerOptions: { module: ts.ModuleKind.CommonJS, jsx: ts.JsxEmit.ReactJSX } }).outputText;
type Node = { type?: string; props: Record<string, any> };
const nextTick = () => new Promise<void>((resolve) => setImmediate(resolve));

function fixture(t: { after: (fn: () => void) => void }, overrides: Partial<Idea> = {}, shared?: Record<string, helpers.IdeaSourcesDraft>) {
  let idea = { id: "idea-one", title: "편입 준비", state: "candidate", score: 0, outlier_band: "unknown", reasons: [], blocked: ["1차 출처 없음"], edit_hash: "a".repeat(64), ...overrides } as Idea;
  let cursor = 0;
  const hooks: any[] = [], effects: (() => void)[] = [], requests: any[] = [], editing: boolean[] = [];
  const listeners = new Map<string, any>();
  const browserWindow = { addEventListener: (name: string, fn: any) => listeners.set(name, fn), removeEventListener: (name: string) => listeners.delete(name) };
  const unmount = () => hooks.forEach((hook) => hook?.cleanup?.());
  t.after(unmount);
  const react = {
    useId: () => "source-fixture",
    useState: (initial: any) => { const index = cursor++; if (!(index in hooks)) hooks[index] = typeof initial === "function" ? initial() : initial; return [hooks[index], (value: any) => { hooks[index] = typeof value === "function" ? value(hooks[index]) : value; }]; },
    useEffect: (effect: () => any, deps: any[]) => { const index = cursor++; const old = hooks[index]; if (!old || deps.some((value, i) => !Object.is(value, old.deps[i]))) effects.push(() => { old?.cleanup?.(); hooks[index] = { deps, cleanup: effect() }; }); },
  };
  const api = {
    ideas: async () => ({ ideas: [idea] }),
    updateIdeaSources: async (id: string, input: any) => {
      requests.push({ id, input });
      return { ...idea, source_url: input.source_urls[0], source_urls: input.source_urls, operator_verified_sources: input.source_urls.length, edit_hash: "b".repeat(64), blocked: [] } as Idea;
    },
  };
  const module = { exports: {} as { IdeaSourcesPanel: (props: any) => Node } };
  Function("require", "module", "exports", "window", compiled)((name: string) => name === "react" ? react : name === "../lib/api" ? { api } : name === "../lib/ideas" ? helpers : require(name), module, module.exports, browserWindow);
  const props = { onSaved: (saved: Idea) => { idea = saved; }, onEditingChange: (_id: string, pending: boolean) => editing.push(pending),
    ...(shared ? { onDraftChange: (id: string, draft: helpers.IdeaSourcesDraft | null) => { if (draft) shared[id] = draft; else delete shared[id]; } } : {}) };
  const text = (value: any): string => Array.isArray(value) ? value.map(text).join("") : value?.props ? text(value.props.children) : typeof value === "string" || typeof value === "number" ? String(value) : "";
  function render() {
    cursor = 0;
    const tree = module.exports.IdeaSourcesPanel({ idea, cached: shared?.[idea.id], ...props });
    const nodes: Node[] = [];
    const visit = (value: any) => { if (Array.isArray(value)) value.forEach(visit); else if (value?.props) { nodes.push(value); visit(value.props.children); } };
    visit(tree); effects.splice(0).forEach((effect) => effect());
    return { text: text(tree), textarea: nodes.find((node) => node.type === "textarea")!, confirm: nodes.find((node) => node.type === "input")!, form: nodes.find((node) => node.type === "form")!, save: nodes.find((node) => node.type === "button" && node.props.type === "submit")!, reload: nodes.find((node) => node.type === "button" && node.props.type === "button")! };
  }
  return { render, requests, editing, listeners, unmount, current: () => idea, update: (value: Partial<Idea>) => { idea = { ...idea, ...value }; } };
}

test("출처 입력·동의는 선택을 잠그고 저장 성공 응답 뒤에만 보완 완료로 바뀐다", async (t) => {
  const view = fixture(t);
  assert.equal(view.render().save.props.disabled, true);
  view.render().textarea.props.onChange({ target: { value: "https://example.edu/transfer" } });
  assert.equal(view.render().save.props.disabled, true);
  view.render().confirm.props.onChange({ target: { checked: true } });
  let state = view.render();
  assert.equal(state.save.props.disabled, false); assert.equal(view.editing.at(-1), true);
  assert.equal(view.listeners.has("beforeunload"), true);
  state.form.props.onSubmit({ preventDefault() {} });
  assert.equal(view.render().save.props.disabled, true);
  await nextTick(); state = view.render();
  assert.equal(view.requests.length, 1);
  assert.equal(view.requests[0].id, "idea-one");
  assert.equal(view.requests[0].input.expected_hash, "a".repeat(64));
  assert.equal(state.textarea.props.value, "https://example.edu/transfer");
  assert.equal(state.confirm.props.checked, false); assert.equal(view.editing.at(-1), false);
  assert.ok(state.text.includes("운영자 확인 출처 수: 1개"));
  assert.ok(state.text.includes("독립 검증 결과가 아닙니다"));
  assert.equal(view.listeners.has("beforeunload"), false);
});

test("다른 화면의 기획 변경은 입력을 보존하고 저장을 막으며 명시 새로 읽기만 입력을 바꾼다", async (t) => {
  const view = fixture(t);
  view.render().textarea.props.onChange({ target: { value: "https://example.edu/mine" } });
  view.render().confirm.props.onChange({ target: { checked: true } });
  view.update({ edit_hash: "c".repeat(64), source_urls: ["https://example.edu/remote"] });
  let state = view.render();
  assert.equal(state.textarea.props.value, "https://example.edu/mine");
  assert.equal(state.save.props.disabled, true); assert.ok(state.text.includes("입력은 보존"));
  state.form.props.onSubmit({ preventDefault() {} }); await nextTick(); assert.equal(view.requests.length, 0);
  state.reload.props.onClick(); await nextTick(); state = view.render();
  assert.equal(state.textarea.props.value, "https://example.edu/remote"); assert.equal(state.confirm.props.checked, false);
  assert.equal(view.editing.at(-1), false);
  view.render().textarea.props.onChange({ target: { value: "https://example.edu/unsaved" } }); view.render();
  assert.equal(view.editing.at(-1), true); view.unmount(); assert.equal(view.editing.at(-1), false);
});

test("기획 판본이 없거나 이미 선택된 카드의 직접 submit도 저장을 우회하지 못한다", async (t) => {
  const view = fixture(t, { edit_hash: undefined });
  view.render().textarea.props.onChange({ target: { value: "https://example.edu/a" } });
  view.render().confirm.props.onChange({ target: { checked: true } });
  let state = view.render(); assert.equal(state.save.props.disabled, true);
  state.form.props.onSubmit({ preventDefault() {} }); await nextTick();
  view.update({ edit_hash: "b".repeat(64), state: "selected" });
  state = view.render(); assert.equal(state.save.props.disabled, true);
  state.form.props.onSubmit({ preventDefault() {} }); await nextTick();
  assert.equal(view.requests.length, 0);
});

test("부모의 기획별 캐시는 A·B·뷰 왕복 후 입력을 복원하고 명시 새로 읽기와 저장 성공 때만 지운다", async (t) => {
  const cache: Record<string, helpers.IdeaSourcesDraft> = {};
  const first = fixture(t, { id: "idea-A" }, cache);
  first.render().textarea.props.onChange({ target: { value: "https://example.edu/mine-A" } });
  first.render().confirm.props.onChange({ target: { checked: true } }); first.render(); first.unmount();
  const second = fixture(t, { id: "idea-B" }, cache);
  assert.equal(second.render().textarea.props.value, "");
  second.render().textarea.props.onChange({ target: { value: "https://example.edu/mine-B" } }); second.render(); second.unmount();
  const resumed = fixture(t, { id: "idea-A", edit_hash: "c".repeat(64), source_urls: ["https://example.edu/remote-A"] }, cache);
  let state = resumed.render();
  assert.equal(state.textarea.props.value, "https://example.edu/mine-A"); assert.equal(state.confirm.props.checked, true);
  assert.ok(state.text.includes("입력은 보존")); assert.equal(state.save.props.disabled, true);
  state.reload.props.onClick(); await nextTick(); state = resumed.render();
  assert.equal(state.textarea.props.value, "https://example.edu/remote-A"); assert.equal(cache["idea-A"], undefined);
  assert.equal(cache["idea-B"].text, "https://example.edu/mine-B");
  state.textarea.props.onChange({ target: { value: "https://example.edu/final-A" } });
  resumed.render().confirm.props.onChange({ target: { checked: true } });
  resumed.render().form.props.onSubmit({ preventDefault() {} }); await nextTick(); resumed.render();
  assert.equal(cache["idea-A"], undefined); resumed.unmount();
  const saved = fixture(t, resumed.current(), cache).render();
  assert.equal(saved.textarea.props.value, "https://example.edu/final-A"); assert.equal(saved.confirm.props.checked, false);
  assert.equal(cache["idea-B"].text, "https://example.edu/mine-B");
});
