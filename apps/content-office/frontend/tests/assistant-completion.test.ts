import test from 'node:test';
import assert from 'node:assert/strict';
import { readFileSync } from 'node:fs';
import { createRequire } from 'node:module';
import { createElement } from 'react';
import { renderToStaticMarkup } from 'react-dom/server';
import ts from 'typescript';
import { createAssistantRequestsController } from '../lib/assistant-requests.ts';

function component() {
  const url = new URL('../app/assistant-chat.tsx', import.meta.url);
  const code = ts.transpileModule(readFileSync(url, 'utf8'), { compilerOptions: { module: ts.ModuleKind.CommonJS, jsx: ts.JsxEmit.ReactJSX, target: ts.ScriptTarget.ES2022 } }).outputText;
  const exports: any = {};
  new Function('require', 'exports', code)(createRequire(url), exports);
  assert.equal(typeof exports.AssistantCompletion, 'function', 'verified report actions must be a renderable UI');
  return exports.AssistantCompletion;
}
const report = { summary: '검증된 결과 <script>bad()</script>', verified: true, task_id: 't_final123', run_id: 13, event_id: 129 };
const request = { request_id: '06705a52-bc32-4e80-9334-6444c471d34c', board: 'heobrain-office', status: 'completed', native_status: 'done', report,
  events: [{ id: 129, task_id: report.task_id, run_id: 13, kind: 'completed', assignee: 'lumi' }] };

test('verified matching Lumi report exposes both actions with exact report context and no side effect on render', () => {
  const Completion = component(); let calls = 0;
  const html = renderToStaticMarkup(createElement(Completion, { request, busy: false, onAction() { calls++; } }));
  assert.match(html, /작업실로 이동/); assert.match(html, /결과물 열기/);
  assert.match(html, /t_final123/); assert.match(html, /129/);
  assert.match(html, /&lt;script&gt;/); assert.doesNotMatch(html, /<script>/);
  assert.equal(calls, 0);
});

test('missing, unverified, stale or foreign completion cannot offer movement or result actions', () => {
  const Completion = component();
  for (const patch of [{ report: null }, { report: { ...report, verified: false } }, { report: { ...report, event_id: 128 } }, { status: 'running' }, { events: [] }, { events: [{ ...request.events[0], assignee: 'ada' }] }]) {
    const html = renderToStaticMarkup(createElement(Completion, { request: { ...request, ...patch }, busy: false, onAction() {} }));
    assert.doesNotMatch(html, /작업실로 이동|결과물 열기/);
  }
});

test('pending report action disables repeated clicks and explains what result can actually be opened', () => {
  const html = renderToStaticMarkup(createElement(component(), { request, busy: true, onAction() {} }));
  assert.equal((html.match(/disabled=""/g) || []).length, 2);
  assert.match(html, /비서 업무실/); assert.match(html, /완료 보고/);
  assert.doesNotMatch(html, /href="(?:file|https?):/);
});

test('explicit Lumi entry selects Lumi after another NPC while preserving the unsent draft', () => {
  const controller = createAssistantRequestsController(); controller.selectAssistant('ada'); controller.setDraft('지워지면 안 되는 업무');
  const url = new URL('../app/assistant-chat.tsx', import.meta.url), require = createRequire(url);
  const react = { ...require('react'), useState: (() => { let i = 0; return () => [i++ === 0 ? controller : false, () => {}]; })(),
    useRef: (value: unknown) => ({ current: value }), useId: () => 'id', useCallback: (value: unknown) => value,
    useSyncExternalStore: (_subscribe: unknown, snapshot: () => unknown) => snapshot(), useEffect() {}, useLayoutEffect() {} };
  const exports: any = {}, code = ts.transpileModule(readFileSync(url, 'utf8'), { compilerOptions: { module: ts.ModuleKind.CommonJS, jsx: ts.JsxEmit.ReactJSX, target: ts.ScriptTarget.ES2022 } }).outputText;
  new Function('require', 'exports', code)((name: string) => name === 'react' ? react : require(name), exports);
  const previous = { document: globalThis.document, HTMLElement: globalThis.HTMLElement };
  try {
    (globalThis as any).document = { activeElement: null }; (globalThis as any).HTMLElement = class {};
    const tree = exports.AssistantChat({ connected: true, openSignal: 0, createRequest() {}, loadRequest() {}, onObservation() {} });
    const all = (node: any): any[] => !node || typeof node !== 'object' ? [] : [node, ...[node.props?.children].flat(Infinity).flatMap(all)];
    const button = all(tree).find(node => node.type === 'button' && node.props.children === '루미와 대화하기');
    assert.ok(button); button.props.onClick();
    assert.equal(controller.getSnapshot().selectedAssistant, 'lumi');
    assert.equal(controller.getSnapshot().draft, '지워지면 안 되는 업무');
  } finally {
    for (const [key, value] of Object.entries(previous)) { if (value === undefined) delete (globalThis as any)[key]; else (globalThis as any)[key] = value; }
  }
});

test('successful report navigation gives focus to the world after closing instead of the old trigger', async () => {
  const controller = createAssistantRequestsController(); controller.setAvailability(true, true); controller.restore(request.request_id);
  await controller.refresh(async () => ({ ...request, native_task_id: 't_root123', assignee: 'lumi', title: '검증 업무', updated_at: 1, current_run_id: null, error: null,
    events: request.events.map(event => ({ ...event, created_at: 1 })) }));
  assert.ok(controller.getSnapshot().request);
  const url = new URL('../app/assistant-chat.tsx', import.meta.url), require = createRequire(url);
  const react = { ...require('react'), useState: (() => { let i = 0; return () => [i++ === 0 ? controller : false, () => {}]; })(),
    useRef: (value: unknown) => ({ current: value }), useId: () => 'id', useCallback: (value: unknown) => value,
    useSyncExternalStore: (_subscribe: unknown, snapshot: () => unknown) => snapshot(), useEffect() {}, useLayoutEffect() {} };
  const exports: any = {}, code = ts.transpileModule(readFileSync(url, 'utf8'), { compilerOptions: { module: ts.ModuleKind.CommonJS, jsx: ts.JsxEmit.ReactJSX, target: ts.ScriptTarget.ES2022 } }).outputText;
  new Function('require', 'exports', code)((name: string) => name === 'react' ? react : require(name), exports);
  const previous = globalThis.requestAnimationFrame; let opened = 0, oldFocus = 0;
  try {
    (globalThis as any).requestAnimationFrame = (fn: () => void) => fn();
    const tree = exports.AssistantChat({ connected: true, openSignal: 0, createRequest() {}, loadRequest() {}, onObservation() {},
      onReportAction: async () => '열었습니다.', onReportOpened() { opened++; } });
    const all = (node: any): any[] => !node || typeof node !== 'object' ? [] : [node, ...[node.props?.children].flat(Infinity).flatMap(all)];
    const nodes = all(tree), dialog = nodes.find(node => node.type === 'dialog');
    nodes.find(node => node.type === 'button' && node.props.children === '루미와 대화하기').props.ref.current = { focus() { oldFocus++; } };
    dialog.props.ref.current = { open: true, close() { this.open = false; dialog.props.onClose(); } };
    nodes.find(node => node.type === exports.AssistantCompletion).props.onAction('result');
    await new Promise(resolve => setImmediate(resolve));
    assert.equal(opened, 1); assert.equal(oldFocus, 0);
  } finally { if (previous === undefined) delete (globalThis as any).requestAnimationFrame; else globalThis.requestAnimationFrame = previous; }
});
