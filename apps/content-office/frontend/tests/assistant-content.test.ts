import test from 'node:test';
import assert from 'node:assert/strict';
import { createHash } from 'node:crypto';
import { readFileSync } from 'node:fs';
import { createRequire } from 'node:module';
import { createElement } from 'react';
import { renderToStaticMarkup } from 'react-dom/server';
import ts from 'typescript';
import { api } from '../lib/api.ts';
import { officeHref } from '../lib/navigation.ts';

const implementation: any = await import('../lib/assistant-requests.ts');
const requestId = 'aab3151d-72e8-4abf-b09d-10d416279c41';
const summary = '# 합성 검토 원고\n\n' + '검사에만 쓰는 독립적인 합성 문장입니다. '.repeat(8);
const report = { summary, verified: true, task_id: 't_synthetic_final', run_id: 7, event_id: 31 };
const candidate = { request_id: requestId, task_id: report.task_id, run_id: 7, event_id: 31,
  title: '합성 검토 원고', body_length: 200, report_sha256: createHash('sha256').update(summary).digest('hex'),
  body_sha256: 'b'.repeat(64), job: null };
const job = { id: 'job_0123456789abcdef', source_hash: 'c'.repeat(64), current_source_hash: 'c'.repeat(64), state: 'source_review' };
const saved = { ...candidate, job };
const complete = (content: unknown = candidate) => ({ request_id: requestId, native_task_id: 't_synthetic_root', board: 'heobrain-office',
  status: 'completed', native_status: 'done', assignee: 'lumi', title: '합성 업무', updated_at: 1, current_run_id: null,
  events: [{ id: 31, task_id: report.task_id, run_id: 7, kind: 'completed', assignee: 'lumi', created_at: 1 }], report, error: null, content });
async function controller(content: unknown = candidate) {
  const value = implementation.createAssistantRequestsController();
  value.setAvailability(true, true); value.setDraft('보존해야 할 합성 입력');
  await value.submit(async () => ({ request_id: requestId, native_task_id: 't_synthetic_root', board: 'heobrain-office', status: 'queued' }), () => requestId);
  await value.refresh(async () => complete(content));
  return value;
}
function completion() {
  const url = new URL('../app/assistant-chat.tsx', import.meta.url), exports: any = {};
  const code = ts.transpileModule(readFileSync(url, 'utf8'), { compilerOptions: { module: ts.ModuleKind.CommonJS, jsx: ts.JsxEmit.ReactJSX, target: ts.ScriptTarget.ES2022 } }).outputText;
  const require = createRequire(url);
  new Function('require', 'exports', code)((name: string) => name === 'next/navigation' ? { useRouter: () => ({ push() {} }) } : require(name), exports);
  return exports.AssistantCompletion;
}

test('verified content metadata retains exact request/report references and its saved job', () => {
  assert.deepEqual(implementation.parseAssistantRequest(complete(), requestId).content, candidate);
  assert.deepEqual(implementation.parseAssistantRequest(complete(saved), requestId).content, saved);
});

test('content titles accept the server boundary of 200 characters and reject 201 without hiding the report', () => {
  const accepted = implementation.parseAssistantRequest(complete({ ...candidate, title: '가'.repeat(200) }), requestId);
  assert.equal(accepted.content?.title, '가'.repeat(200));
  const rejected = implementation.parseAssistantRequest(complete({ ...candidate, title: '가'.repeat(201) }), requestId);
  assert.equal(rejected.content, undefined);
  assert.deepEqual(rejected.report, report);
});

test('malformed optional content never discards the original report or creates a link', () => {
  for (const patch of [{ request_id: 'bbbbbbbb-72e8-4abf-b09d-10d416279c41' }, { task_id: 't_other' }, { run_id: 8 }, { event_id: 32 },
    { title: '../private' }, { title: 'x'.repeat(201) }, { title: 'title\nother' }, { body_length: 99 }, { body_length: 50001 }, { body_length: 100.5 },
    { report_sha256: 'invalid' }, { body_sha256: 'B'.repeat(64) }, { job: { ...job, id: 'job_../../other' } },
    { job: { ...job, source_hash: null } }, { job: { ...job, current_source_hash: 'wrong' } }, { job: { ...job, state: 'Bearer private' } }]) {
    const parsed = implementation.parseAssistantRequest(complete({ ...candidate, ...patch }), requestId);
    assert.deepEqual(parsed.report, report);
    assert.equal(parsed.content, undefined, JSON.stringify(patch));
  }
  for (const content of [null, [], 3, { ...candidate, extra: 'untrusted' }]) {
    const parsed = implementation.parseAssistantRequest(complete(content), requestId);
    assert.deepEqual(parsed.report, report); assert.equal(parsed.content, undefined);
  }
  const unverified = implementation.parseAssistantRequest({ ...complete(), report: { ...report, verified: false } }, requestId);
  assert.equal(unverified.content, undefined); assert.equal(unverified.report.verified, false);
});

test('saved content exposes official links without needing dashboard membership or implying produced files', () => {
  const html = renderToStaticMarkup(createElement(completion(), { request: complete(saved), busy: false, onAction() {} }));
  assert.match(html, /href="\/scripts\/job_0123456789abcdef"/);
  assert.match(html, /href="\/publish\?job=job_0123456789abcdef"/);
  assert.match(html, /원고 작업실 열기/); assert.match(html, /제작·출고함 보기/);
  assert.match(html, /원고 저장됨/); assert.match(html, /별도/);
  assert.ok(html.indexOf('원고 작업실 열기') < html.indexOf('# 합성 검토 원고'), 'the manuscript action precedes the long completion report');
  assert.doesNotMatch(html, /제작 완료|출고 승인 완료/);
  const edited = renderToStaticMarkup(createElement(completion(), { request: complete({ ...saved, job: { ...job, current_source_hash: 'd'.repeat(64) } }), busy: false, onAction() {} }));
  assert.match(edited, /연결 후 수정됨/);
  const invalid = renderToStaticMarkup(createElement(completion(), { request: complete({ ...saved, job: { ...job, id: 'javascript:bad' } }), busy: false, onAction() {} }));
  assert.doesNotMatch(invalid, /href=/); assert.match(invalid, /루미의 완료 보고/);
});

test('an unsaved candidate offers an explicit save action and disables it while busy', () => {
  const html = renderToStaticMarkup(createElement(completion(), { request: complete(), busy: true, onAction() {}, onSaveContent: async () => null }));
  assert.match(html, /원고 저장하고 작업실 열기/);
  assert.equal((html.match(/disabled=""/g) || []).length, 3);
  assert.doesNotMatch(html, /href="\/scripts/);
});

test('save progress and refusal remain beside the action before a long report', () => {
  const html = renderToStaticMarkup(createElement(completion(), { request: complete(), busy: true,
    onAction() {}, onSaveContent: async () => null, contentPending: true, contentError: '기존 원고를 보존한 연결 거절' }));
  assert.match(html, /원고 저장 확인 중/);
  assert.ok(html.indexOf('기존 원고를 보존한 연결 거절') > 0);
  assert.ok(html.indexOf('기존 원고를 보존한 연결 거절') < html.indexOf('# 합성 검토 원고'));
});

test('a deleted linked job keeps the report but cannot open or duplicate that content', () => {
  const html = renderToStaticMarkup(createElement(completion(), { request: complete({ ...saved, job: { ...job, state: 'deleted' } }), busy: false, onAction() {} }));
  assert.match(html, /원고를 복원한 뒤 열 수 있습니다/);
  assert.match(html, /루미의 완료 보고/);
  assert.doesNotMatch(html, /href=|원고 저장하고 작업실 열기|원고 저장됨/);
});

test('save submits only the current immutable references and returns the official new job once', async () => {
  const value = await controller();
  assert.equal(typeof value.saveContent, 'function');
  let calls = 0;
  const result = await value.saveContent(async (id: string, body: unknown) => {
    calls++; assert.equal(id, requestId);
    assert.deepEqual(body, { task_id: report.task_id, run_id: 7, event_id: 31, report_sha256: candidate.report_sha256, body_sha256: 'b'.repeat(64) });
    return saved;
  });
  assert.equal(officeHref('studio', result.job.id), '/scripts/job_0123456789abcdef');
  assert.deepEqual(value.getSnapshot().request.content, saved);
  assert.equal(value.getSnapshot().draft, '보존해야 할 합성 입력');
  await value.saveContent(async () => { calls++; return saved; });
  assert.equal(calls, 1);
});

test('failed saves and mismatched result hashes preserve the report/draft and never return navigation', async () => {
  for (const respond of [async () => { throw new Error('offline'); }, async () => ({ ...saved, body_sha256: 'e'.repeat(64) }), async () => candidate]) {
    const value = await controller();
    assert.equal(typeof value.saveContent, 'function');
    assert.equal(await value.saveContent(respond), null);
    assert.deepEqual(value.getSnapshot().request.report, report);
    assert.equal(value.getSnapshot().request.content.job, null);
    assert.equal(value.getSnapshot().draft, '보존해야 할 합성 입력');
    assert.match(value.getSnapshot().contentError, /보존|확인/);
    assert.equal(value.getSnapshot().contentPending, false);
  }
});

test('a metadata hash not matching the current report cannot issue a save POST', async () => {
  const value = await controller({ ...candidate, report_sha256: 'f'.repeat(64) });
  assert.equal(typeof value.saveContent, 'function');
  let calls = 0;
  assert.equal(await value.saveContent(async () => { calls++; return saved; }), null);
  assert.equal(calls, 0); assert.deepEqual(value.getSnapshot().request.report, report);
});

test('a later GET can recover a persisted job after an uncertain POST without another save', async () => {
  const value = await controller(); let calls = 0;
  await value.saveContent(async () => { calls++; throw new Error('response lost'); });
  assert.ok(value.getSnapshot().contentError);
  await value.refresh(async () => complete(saved));
  assert.deepEqual(value.getSnapshot().request.content, saved);
  assert.equal(value.getSnapshot().contentError, null);
  assert.equal(calls, 1);
});

test('a job deleted during save is retained for restoration without returning a navigation target', async () => {
  const value = await controller();
  assert.equal(await value.saveContent(async () => ({ ...saved, job: { ...job, state: 'deleted' } })), null);
  assert.equal(value.getSnapshot().request.content.job.state, 'deleted');
});

test('safe API refusal details explain the action while the report is preserved', async () => {
  const value = await controller(), error = new Error('연결한 원고를 복원해 주세요.'); error.name = 'OfficeApiError';
  await value.saveContent(async () => { throw error; });
  assert.match(value.getSnapshot().contentError, /연결한 원고를 복원/);
  assert.deepEqual(value.getSnapshot().request.report, report);
});

test('a pending save ignores double clicks and closed/reopened dialogs cannot steal navigation', async () => {
  const value = await controller();
  assert.equal(typeof value.saveContent, 'function');
  let resolve!: (value: unknown) => void, calls = 0;
  const pending = value.saveContent(async () => { calls++; return new Promise(yes => { resolve = yes; }); });
  while (!resolve) await new Promise(yes => setImmediate(yes));
  assert.equal(value.getSnapshot().contentPending, true);
  assert.equal(await value.saveContent(async () => { calls++; return saved; }), null);
  value.setAvailability(true, false); value.setAvailability(true, true);
  resolve(saved);
  assert.equal(await pending, null); assert.equal(calls, 1);
  assert.deepEqual(value.getSnapshot().request.content, saved, 'persisted metadata is available on a later read');
});

test('late saves do not replace a new request or a newer completed report', async () => {
  for (const changed of ['new-request', 'new-report']) {
    const value = await controller();
    assert.equal(typeof value.saveContent, 'function');
    let resolve!: (value: unknown) => void;
    const pending = value.saveContent(async () => new Promise(yes => { resolve = yes; }));
    while (!resolve) await new Promise(yes => setImmediate(yes));
    if (changed === 'new-request') assert.equal(value.newRequest(), true);
    else await value.refresh(async () => ({ ...complete(), report: { ...report, summary: '현재 판본으로 바뀐 합성 보고' } }));
    resolve(saved); assert.equal(await pending, null);
    if (changed === 'new-request') assert.equal(value.getSnapshot().request, null);
    else assert.equal(value.getSnapshot().request.report.summary, '현재 판본으로 바뀐 합성 보고');
  }
});

test('content-job uses the existing same-origin CSRF POST client without creating work or approvals', async t => {
  const previous = globalThis.fetch; t.after(() => { globalThis.fetch = previous; });
  const method = (api as any).saveAssistantContentJob;
  assert.equal(typeof method, 'function');
  const calls: string[] = [];
  globalThis.fetch = async (input, init) => {
    calls.push(String(input));
    if (String(input) === '/api/session') return Response.json({ csrf: 'content-fixture' });
    assert.equal(String(input), '/api/assistant/requests/' + requestId + '/content-job');
    assert.equal(init?.method, 'POST'); assert.equal(init?.credentials, 'same-origin');
    assert.equal((init?.headers as Record<string, string>)['X-Office-CSRF'], 'content-fixture');
    assert.deepEqual(JSON.parse(String(init?.body)), { task_id: report.task_id, run_id: 7, event_id: 31, report_sha256: candidate.report_sha256, body_sha256: 'b'.repeat(64) });
    return Response.json({ content: saved });
  };
  assert.deepEqual(await method(requestId, { task_id: report.task_id, run_id: 7, event_id: 31, report_sha256: candidate.report_sha256, body_sha256: 'b'.repeat(64) }), saved);
  assert.equal(calls.length, 2);
});
