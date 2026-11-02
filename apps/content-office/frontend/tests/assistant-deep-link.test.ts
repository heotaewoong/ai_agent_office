import test from 'node:test';
import assert from 'node:assert/strict';
import { readFileSync } from 'node:fs';
import { createRequire } from 'node:module';
import ts from 'typescript';
import * as implementation from '../lib/assistant-requests.ts';

const stored = 'aa3a151d-72e8-4abf-b09d-10d416279c41';
const linked = 'bbbbbbbb-72e8-4abf-b09d-10d416279c41';
const select = (...args: any[]) => (implementation as any).initialAssistantRequestId(...args);

test('one canonical UUID deep link selects an existing request; absent link uses only a valid saved UUID', () => {
  assert.equal(typeof (implementation as any).initialAssistantRequestId, 'function');
  assert.equal(select('?assistant_request=' + linked, stored), linked);
  assert.equal(select('?assistant_request=' + linked.toUpperCase(), stored), linked);
  assert.equal(select('?view=office', stored), stored);
  assert.equal(select('', 'not-a-uuid'), null);
});

test('invalid or ambiguous explicit request links never fall back to another saved conversation', () => {
  for (const query of ['?assistant_request=', '?assistant_request=../private', '?assistant_request=%2fhome%2fprivate',
    '?assistant_request=' + linked + '&assistant_request=' + stored,
    '?assistant_request=' + linked + '&assistant_request=' + linked]) assert.equal(select(query, stored), null);
});

test('initial restoration never replaces an unsent draft or an already-selected request', () => {
  const controller = implementation.createAssistantRequestsController();
  controller.setDraft('아직 보내지 않은 입력'); controller.restore(linked);
  assert.equal(controller.getSnapshot().draft, '아직 보내지 않은 입력');
  assert.equal(controller.getSnapshot().submission, null);
  const selected = implementation.createAssistantRequestsController(); selected.restore(stored); selected.restore(linked);
  assert.equal(selected.getSnapshot().submission?.request_id, stored);
});

test('actual AssistantChat initial link effect persists only UUID and performs GET without POST', async () => {
  const controller = implementation.createAssistantRequestsController();
  const previous: any = { window: globalThis.window, document: globalThis.document, sessionStorage: globalThis.sessionStorage };
  let effects: Array<() => any> = [], layouts: Array<() => any> = [], index = 0;
  const reads: string[] = [], writes: unknown[] = [], storage: string[][] = [];
  const url = new URL('../app/assistant-chat.tsx', import.meta.url), require = createRequire(url);
  const react = { ...require('react'),
    useState: () => [index++ === 0 ? controller : false, () => {}],
    useRef: (value: any) => ({ current: value }), useId: () => 'fixture-id', useCallback: (value: any) => value,
    useSyncExternalStore: (_subscribe: any, snapshot: any) => snapshot(),
    useEffect: (effect: () => any) => effects.push(effect), useLayoutEffect: (effect: () => any) => layouts.push(effect),
  };
  const code = ts.transpileModule(readFileSync(url, 'utf8'), { compilerOptions: { module: ts.ModuleKind.CommonJS, jsx: ts.JsxEmit.ReactJSX, target: ts.ScriptTarget.ES2022 } }).outputText;
  const exports: any = {};
  new Function('require', 'exports', code)((name: string) => name === 'react' ? react : require(name), exports);
  (globalThis as any).window = { location: { search: '?assistant_request=' + linked }, setInterval() { return 1; }, clearInterval() {} };
  (globalThis as any).document = { hidden: false, addEventListener() {}, removeEventListener() {} };
  let storedValue = stored;
  (globalThis as any).sessionStorage = { getItem() { return storedValue; }, setItem(key: string, value: string) { storedValue = value; storage.push([key, value]); } };
  const render = () => {
    effects = []; layouts = []; index = 0;
    exports.AssistantChat({ connected: true, openSignal: 0, createRequest: async (body: unknown) => { writes.push(body); },
      loadRequest: async (id: string) => { reads.push(id); throw new Error('fixture read unavailable'); }, onObservation() {} });
    layouts.forEach(effect => effect()); return effects.map(effect => effect());
  };
  let cleanups: any[] = [];
  try {
    cleanups = render(); await new Promise(resolve => setImmediate(resolve));
    assert.equal(controller.getSnapshot().submission?.request_id, linked);
    cleanups.forEach(cleanup => { if (typeof cleanup === 'function') cleanup(); });
    cleanups = render(); await new Promise(resolve => setImmediate(resolve));
    assert.deepEqual(reads, [linked]); assert.deepEqual(writes, []);
    assert.deepEqual(storage, [['heobrain.assistant-request.v1', linked]]);
    assert.equal(controller.getSnapshot().submission?.text, '');
  } finally {
    cleanups.forEach(cleanup => { if (typeof cleanup === 'function') cleanup(); });
    for (const [key, value] of Object.entries(previous)) {
      if (value === undefined) delete (globalThis as any)[key]; else (globalThis as any)[key] = value;
    }
  }
});
