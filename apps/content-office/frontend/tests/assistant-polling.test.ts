import test from 'node:test';
import assert from 'node:assert/strict';
import { readFileSync } from 'node:fs';
import { createRequire } from 'node:module';
import { renderToStaticMarkup } from 'react-dom/server';
import ts from 'typescript';
import { createAssistantRequestsController } from '../lib/assistant-requests.ts';

const requestId = 'aa3a151d-72e8-4abf-b09d-10d416279c41';
const blocked = () => ({ request_id: requestId, native_task_id: 't_fixture', board: 'heobrain-office',
  status: 'blocked', native_status: 'blocked', assignee: 'lumi', title: '보완 대기', updated_at: 1793624400,
  current_run_id: null, events: [{ id: 10, task_id: 't_fixture', run_id: 8, kind: 'blocked', created_at: 1793624400, assignee: 'lumi' }],
  report: null, error: { code: 'human_action_required', message: '보완을 기다립니다' } });
const completed = () => ({ ...blocked(), status: 'completed', native_status: 'done',
  events: [{ id: 11, task_id: 't_fixture', run_id: 9, kind: 'completed', created_at: 1793624460, assignee: 'lumi' }],
  report: { summary: '보완 후 검토를 마쳤습니다.', verified: true, task_id: 't_fixture', run_id: 9, event_id: 11 }, error: null });
const flush = () => new Promise(resolve => setImmediate(resolve));

test('actual AssistantChat effect keeps a slow blocked timer and returns a later report with its dialog closed', async () => {
  const controller = createAssistantRequestsController();
  controller.restore(requestId); controller.setAvailability(true, false);
  await controller.refresh(async () => blocked());
  const previous = { window: globalThis.window, document: globalThis.document, sessionStorage: globalThis.sessionStorage };
  const timers = new Map<number, { callback: () => void; delay: number }>();
  let timerId = 0, reads = 0, writes = 0, finished = false;
  const observations: any[] = [];
  let effects: Array<() => any> = [], layouts: Array<() => any> = [], stateIndex = 0;
  const url = new URL('../app/assistant-chat.tsx', import.meta.url), require = createRequire(url);
  const react = { ...require('react'),
    useState: () => [stateIndex++ === 0 ? controller : false, () => {}],
    useRef: (value: any) => ({ current: value }), useId: () => 'fixture-id', useCallback: (value: any) => value,
    useSyncExternalStore: (_subscribe: any, snapshot: any) => snapshot(),
    useEffect: (effect: () => any) => { effects.push(effect); },
    useLayoutEffect: (effect: () => any) => { layouts.push(effect); },
  };
  const code = ts.transpileModule(readFileSync(url, 'utf8'), { compilerOptions: {
    module: ts.ModuleKind.CommonJS, jsx: ts.JsxEmit.ReactJSX, target: ts.ScriptTarget.ES2022,
  } }).outputText;
  const exports: any = {};
  new Function('require', 'exports', code)((name: string) => name === 'react' ? react : require(name), exports);
  (globalThis as any).window = {
    setInterval(callback: () => void, delay: number) { const id = ++timerId; timers.set(id, { callback, delay }); return id; },
    clearInterval(id: number) { timers.delete(id); },
  };
  (globalThis as any).document = { hidden: false, addEventListener() {}, removeEventListener() {} };
  (globalThis as any).sessionStorage = { getItem() { return null; } };
  const render = () => {
    effects = []; layouts = []; stateIndex = 0;
    const tree = exports.AssistantChat({ connected: true, openSignal: 0,
      createRequest: async () => { writes++; }, loadRequest: async () => { reads++; return finished ? completed() : blocked(); },
      onObservation: (value: any) => observations.push(value),
    });
    layouts.forEach(effect => effect());
    const cleanups = effects.map(effect => effect());
    return { tree, cleanup() { cleanups.forEach(cleanup => { if (typeof cleanup === 'function') cleanup(); }); } };
  };
  let mounted: ReturnType<typeof render> | undefined;
  try {
    mounted = render(); await flush();
    assert.equal(timers.size, 1, 'a blocked native task must retain its actual component polling effect');
    const timer = [...timers.values()][0];
    assert.equal(timer.delay, 30_000);
    assert.equal(reads, 1);
    finished = true; timer.callback(); await flush();
    assert.equal(controller.getSnapshot().request?.report?.verified, true);
    mounted.cleanup(); mounted = render();
    assert.equal(observations.at(-1).report.verified, true);
    const html = renderToStaticMarkup(mounted.tree);
    assert.match(html, /루미의 완료 보고가 도착했습니다/);
    assert.doesNotMatch(html, /<dialog[^>]*\sopen(?:=|>)/);
    assert.equal(timers.size, 0, 'verified completion stops the polling effect');
    assert.equal(writes, 0, 'blocked resumption is GET only; no POST, wake or unblock');
  } finally {
    mounted?.cleanup();
    for (const [key, value] of Object.entries(previous)) {
      if (value === undefined) delete (globalThis as any)[key]; else (globalThis as any)[key] = value;
    }
  }
});

test('native report keeps slow Slack receipt reads and an already-read report is not announced again', async () => {
  const controller = createAssistantRequestsController();
  const pending = () => ({ ...completed(), delivery: { slack: 'sent_unverified', external_delivery_verified: false } });
  const confirmed = () => ({ ...completed(), delivery: { slack: 'confirmed', external_delivery_verified: true,
    notice_ref: { request_id: requestId, task_id: 't_fixture', run_id: 9, event_id: 11, terminal_state: 'completed' } } });
  controller.restore(requestId); controller.setAvailability(true, false);
  await controller.refresh(async () => pending());
  const previous: any = { window: globalThis.window, document: globalThis.document, sessionStorage: globalThis.sessionStorage,
    HTMLElement: globalThis.HTMLElement, requestAnimationFrame: globalThis.requestAnimationFrame };
  const timers = new Map<number, { callback: () => void; delay: number }>();
  let timerId = 0, reads = 0, writes = 0, delivered = false;
  const observations: any[] = [], stateValues: any[] = [controller, false], refs: any[] = [];
  let effects: Array<() => any> = [], layouts: Array<() => any> = [], stateIndex = 0, refIndex = 0;
  const url = new URL('../app/assistant-chat.tsx', import.meta.url), require = createRequire(url);
  const react = { ...require('react'),
    useState: () => { const index = stateIndex++; return [stateValues[index], (value: any) => { stateValues[index] = value; }]; },
    useRef: (value: any) => { const index = refIndex++; return refs[index] ||= { current: value }; },
    useId: () => 'fixture-id', useCallback: (value: any) => value,
    useSyncExternalStore: (_subscribe: any, snapshot: any) => snapshot(),
    useEffect: (effect: () => any) => { effects.push(effect); },
    useLayoutEffect: (effect: () => any) => { layouts.push(effect); },
  };
  const code = ts.transpileModule(readFileSync(url, 'utf8'), { compilerOptions: {
    module: ts.ModuleKind.CommonJS, jsx: ts.JsxEmit.ReactJSX, target: ts.ScriptTarget.ES2022,
  } }).outputText;
  const exports: any = {};
  new Function('require', 'exports', code)((name: string) => name === 'react' ? react : require(name), exports);
  (globalThis as any).window = {
    setInterval(callback: () => void, delay: number) { const id = ++timerId; timers.set(id, { callback, delay }); return id; },
    clearInterval(id: number) { timers.delete(id); },
  };
  (globalThis as any).document = { hidden: false, activeElement: null, addEventListener() {}, removeEventListener() {} };
  (globalThis as any).sessionStorage = { getItem() { return null; } };
  (globalThis as any).HTMLElement = class {};
  (globalThis as any).requestAnimationFrame = (callback: () => void) => { callback(); return 1; };
  const find = (tree: any, predicate: (node: any) => boolean): any => {
    if (!tree) return null;
    if (Array.isArray(tree)) return tree.map(child => find(child, predicate)).find(Boolean);
    if (predicate(tree)) return tree;
    return find(tree.props?.children, predicate);
  };
  const render = () => {
    effects = []; layouts = []; stateIndex = 0; refIndex = 0;
    const tree = exports.AssistantChat({ connected: true, openSignal: 0,
      createRequest: async () => { writes++; }, loadRequest: async () => { reads++; return delivered ? confirmed() : pending(); },
      onObservation: (value: any) => observations.push(value),
    });
    layouts.forEach(effect => effect());
    const cleanups = effects.map(effect => effect());
    return { tree, cleanup() { cleanups.forEach(cleanup => { if (typeof cleanup === 'function') cleanup(); }); } };
  };
  let mounted: ReturnType<typeof render> | undefined;
  try {
    mounted = render(); await flush();
    assert.equal(timers.size, 1, 'native completion must not hide a pending Slack receipt');
    assert.equal([...timers.values()][0].delay, 30_000);
    let html = renderToStaticMarkup(mounted.tree);
    assert.match(html, /루미의 완료 보고가 도착했습니다/);
    assert.match(html, /Slack.*수신 확인 전/);
    find(mounted.tree, node => node.type === 'button' && node.props.children === '보고 열기').props.onClick();
    mounted.cleanup(); mounted = render(); await flush();
    find(mounted.tree, node => node.type === 'dialog').props.onClose();
    mounted.cleanup(); mounted = render(); await flush();
    assert.doesNotMatch(renderToStaticMarkup(mounted.tree), /루미의 완료 보고가 도착했습니다/);
    assert.equal([...timers.values()][0].delay, 30_000);
    delivered = true; [...timers.values()][0].callback(); await flush();
    mounted.cleanup(); mounted = render();
    html = renderToStaticMarkup(mounted.tree);
    assert.match(html, /Slack.*수신 확인/);
    assert.doesNotMatch(html, /루미의 완료 보고가 도착했습니다/);
    assert.doesNotMatch(html, /<dialog[^>]*\sopen(?:=|>)/);
    assert.equal(timers.size, 0);
    assert.equal(observations.at(-1).delivery.external_delivery_verified, true);
    assert.equal(observations.at(-1).report.event_id, 11);
    assert.ok(reads >= 2);
    assert.equal(writes, 0, 'delivery reconciliation never restarts native work');
  } finally {
    mounted?.cleanup();
    for (const [key, value] of Object.entries(previous)) {
      if (value === undefined) delete (globalThis as any)[key]; else (globalThis as any)[key] = value;
    }
  }
});
