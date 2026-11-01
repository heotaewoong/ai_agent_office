import test from 'node:test';
import assert from 'node:assert/strict';
import { readFileSync, existsSync } from 'node:fs';
import { createRequire } from 'node:module';
import { createElement } from 'react';
import { renderToStaticMarkup } from 'react-dom/server';
import ts from 'typescript';

test('React panel starts collapsed and read-only without fetching during render', () => {
  const url = new URL('../app/assistant-reports.tsx', import.meta.url);
  assert.ok(existsSync(url), 'React report panel must exist');
  const source = readFileSync(url, 'utf8');
  const code = ts.transpileModule(source, { compilerOptions: { module: ts.ModuleKind.CommonJS, jsx: ts.JsxEmit.ReactJSX, target: ts.ScriptTarget.ES2022 } }).outputText;
  const exports: any = {};
  new Function('require', 'exports', code)(createRequire(url), exports);
  for (const connected of [false, true]) {
    let calls = 0;
    const html = renderToStaticMarkup(createElement(exports.AssistantReports, { connected, loadReports: async () => { calls++; return { reports: [] }; } }));
    assert.match(html, /비서 협업 보고/);
    assert.match(html, /aria-expanded="false"/);
    assert.match(html, /원고 승인①·제작·게시와 별개/);
    assert.doesNotMatch(html, /<textarea|<input|보고가 0건/);
    assert.equal(calls, 0);
  }
});

const modulePath = '../lib/assistant-reports.ts';
const implementation: any = await import(modulePath).catch(() => null);
function deferred() {
  let resolve!: (value: unknown) => void;
  let reject!: (reason: unknown) => void;
  const promise = new Promise<unknown>((yes, no) => { resolve = yes; reject = no; });
  return { promise, resolve, reject };
}

test('request gate blocks collapsed/disconnected and concurrent loads', async () => {
  assert.equal(typeof implementation?.createAssistantReportsController, 'function', 'request controller must exist');
  const controller = implementation.createAssistantReportsController();
  let calls = 0;
  const pending = deferred();
  const load = () => { calls++; return pending.promise; };
  await controller.refresh(load);
  controller.setAvailability(true, false);
  await controller.refresh(load);
  controller.setAvailability(false, true);
  await controller.refresh(load);
  assert.equal(calls, 0);
  controller.setAvailability(true, true);
  const first = controller.refresh(load);
  await controller.refresh(load);
  assert.equal(calls, 1);
  assert.equal(controller.getSnapshot().status, 'loading');
  pending.resolve({ reports: [sample()] });
  await first;
  assert.equal(controller.getSnapshot().status, 'success');
  assert.equal(controller.getSnapshot().reports.length, 1);
});

test('close, disconnect and unmount invalidation discard late success and error, even after reopening', async () => {
  for (const action of ['close', 'disconnect', 'unmount']) for (const reject of [false, true]) {
    const controller = implementation.createAssistantReportsController();
    controller.setAvailability(true, true);
    const pending = deferred();
    const first = controller.refresh(() => pending.promise);
    if (action === 'unmount') {
      assert.equal(typeof controller.invalidate, 'function', 'unmount invalidation must exist');
      controller.invalidate();
    } else controller.setAvailability(action !== 'disconnect', action !== 'close');
    controller.setAvailability(true, true);
    const before = controller.getSnapshot();
    if (reject) pending.reject(new Error('/home/private/secret')); else pending.resolve({ reports: [sample()] });
    await first;
    assert.equal(controller.getSnapshot(), before, action + ' late response must not publish');
    await controller.refresh(async () => ({ reports: [] }));
    assert.equal(controller.getSnapshot().status, 'success');
    assert.deepEqual(controller.getSnapshot().reports, []);
  }
});

test('load failures, auth failures and unsupported responses stay errors and can be refreshed', async () => {
  const controller = implementation.createAssistantReportsController();
  controller.setAvailability(true, true);
  for (const failure of [{ status: 401 }, { status: 403 }, new Error('/home/private')]) {
    await controller.refresh(async () => { throw failure; });
    assert.equal(controller.getSnapshot().status, 'error');
    assert.ok(!controller.getSnapshot().error.includes('/home'));
  }
  await controller.refresh(async () => ({ error: 'unauthorized', reports: [] }));
  assert.equal(controller.getSnapshot().status, 'error');
  await controller.refresh(async () => ({ reports: [] }));
  assert.equal(controller.getSnapshot().status, 'success');
});

test('accepts timezone-aware ISO timestamps but blocks embedded private paths', () => {
  const offset = { ...sample(), reported_at: '2026-11-01T19:00:00+09:00' };
  assert.deepEqual(implementation.parseAssistantReports({ reports: [offset] }), [offset]);
  for (const summary of ['경로:/home/private/notes', '자료:../private/notes', '경로:%2Fhome%2Fprivate', '경로:C:\\Users\\private']) {
    assert.throws(() => implementation.parseAssistantReports({ reports: [{ ...sample(), summary }] }));
  }
});

const sample = () => ({ id: 'report_02', work_id: 'work_02', title: '협업 검토', summary: '요약 교차검토 완료', scope: 'dm_review', reported_at: '2026-11-01T10:00:00Z', participants: ['Lumi', 'Ethan', 'Ada'], limitations: ['원문 독립 감사 미확인'], evidence_count: 2 });

test('valid report summaries and explicit empty envelope are parsed', () => {
  assert.equal(typeof implementation?.parseAssistantReports, 'function', 'report parser must exist');
  assert.deepEqual(implementation.parseAssistantReports({ reports: [sample()] }), [sample()]);
  assert.deepEqual(implementation.parseAssistantReports({ reports: [] }), []);
});

test('accepts the microsecond precision emitted by the existing Python store', () => {
  const report = { ...sample(), reported_at: '2026-01-01T00:00:00.123456+00:00' };
  assert.deepEqual(implementation.parseAssistantReports({ reports: [report] }), [report]);
});

test('supplementary characters use Python code point bounds for every display text field', () => {
  for (const [field, limit] of [['title', 160], ['summary', 1200], ['participants', 80], ['limitations', 400]] as const) {
    const patch = (count: number) => ({ [field]: field === 'participants' || field === 'limitations' ? ['😀'.repeat(count)] : '😀'.repeat(count) });
    const valid = { ...sample(), ...patch(limit) };
    assert.deepEqual(implementation.parseAssistantReports({ reports: [valid] }), [valid], field);
    assert.throws(() => implementation.parseAssistantReports({ reports: [{ ...sample(), ...patch(limit + 1) }] }), field);
  }
});

test('rejects malformed, authentication, oversized, duplicate and private payloads without empty fallback', () => {
  const bad: unknown[] = [null, [], {}, { error: 'Unauthorized', reports: [] }, { reports: null }, { reports: Array(101).fill(sample()) }, { reports: [sample(), sample()] }];
  for (const patch of [
    { id: '../private' }, { work_id: '/home/user' }, { scope: 'meeting' }, { reported_at: 'yesterday' },
    { reported_at: '2026-02-30T10:00:00Z' }, { title: '' }, { title: 'x'.repeat(161) },
    { evidence_count: -1 }, { evidence_count: 1.5 }, { evidence_count: NaN }, { evidence_count: Infinity }, { evidence_count: 10001 },
    { participants: [] }, { participants: ['Lumi', 'Lumi'] }, { participants: Array(21).fill('Lumi') },
    { limitations: Array(21).fill('미확인') }, { limitations: [3] }, { summary: '/home/private/notes' },
    { summary: '위치 C:\\Users\\private' }, { summary: 'Bearer abcdef12345' }, { summary: 'api_key=secret' },
    { summary: 'file:///private/notes' }, { raw_transcript: 'private chat' },
  ]) bad.push({ reports: [{ ...sample(), ...patch }] });
  for (const value of bad) assert.throws(() => implementation.parseAssistantReports(value), 'invalid data must fail closed');
  assert.equal(implementation.parseAssistantReports({ reports: [{ ...sample(), scope: 'group_review', limitations: [] }] })[0].scope, 'group_review');
});
