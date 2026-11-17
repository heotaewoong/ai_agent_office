import test from 'node:test';
import assert from 'node:assert/strict';
import { readFileSync } from 'node:fs';

const moduleUrl = new URL('../../../../sites/office-world/orbit/operational.js', import.meta.url);
const source = readFileSync(moduleUrl, 'utf8');
const { projectDashboard, createOperationalStore, safeText } = await import(`data:text/javascript;base64,${Buffer.from(source).toString('base64')}`);
const dashboard = () => ({
  jobs: [
    { id: 'one', title: '첫 원고', state: 'source_review' },
    { id: 'two', title: '출고 검토', state: 'partial_release_review' },
    { id: 'three', title: '보류', state: 'blocked' },
    { id: 'four', title: '원고 수정', state: 'source_rejected' },
  ],
  tasks: [{ id: 'task1', kind: 'draft', state: 'unknown', payload: { job_id: 'one', secret: 'NEVER DISPLAY' }, result: { body: 'PRIVATE BODY' } }],
  budget: { cap_krw: 10000, spent_krw: 0, remaining_krw: 10000 },
  window: { status: 'CLOSED' }, newsletters: { draft: 2 },
});

test('dashboard counts content work only, preserves unknowns, and drops private task payloads', () => {
  const result = projectDashboard(dashboard());
  assert.equal(result.jobs.length, 4);
  assert.equal(result.blockedCount, 2);
  assert.equal(result.approvalCount, 2);
  assert.equal(result.windowClosed, true);
  assert.equal(result.tasks[0].state, 'unknown');
  assert.equal(result.tasks[0].jobId, 'one');
  assert.equal(JSON.stringify(result).includes('PRIVATE BODY'), false);
  assert.equal(JSON.stringify(result).includes('NEVER DISPLAY'), false);
  assert.equal(result.budget.spent_krw, 0);
  assert.equal(result.budget.reserved_krw, null);
});

test('invalid or partial job lists never become a false zero work report', () => {
  for (const data of [{}, { jobs: null }, { jobs: [{ id: 'broken' }] }, { jobs: [{ id: 'x', state: 'done' }, { id: 'x', state: 'blocked' }] }]) {
    assert.throws(() => projectDashboard(data), /형식/);
  }
  const result = projectDashboard({ jobs: [] });
  assert.equal(result.jobs.length, 0);
  assert.equal(result.windowClosed, null);
  assert.equal(result.tasks, null);
});

test('failed refresh retains last successful data and timestamp; only fixed GET routes are used', async () => {
  const requests: Array<{ url: string; options: RequestInit }> = [];
  let fail = false;
  const state = createOperationalStore(async (url: string, options: RequestInit) => {
    requests.push({ url, options });
    return { ok: !fail, status: fail ? 503 : 200, json: async () => dashboard() };
  });
  await state.refresh('dashboard');
  const good = state.get('dashboard');
  assert.equal(good.state, 'ready');
  fail = true;
  await state.refresh('dashboard');
  const stale = state.get('dashboard');
  assert.equal(stale.state, 'stale');
  assert.equal(stale.data.jobs.length, 4);
  assert.equal(stale.fetchedAt, good.fetchedAt);
  assert.equal(requests[0].url, '/api/dashboard?compact=true&task_results=false');
  assert.equal(requests[0].options.method, 'GET');
  assert.equal(requests[0].options.credentials, 'same-origin');
  assert.equal(requests[0].options.cache, 'no-store');
  await assert.rejects(state.refresh('assistant/requests/not-allowed'), /허용/);
  assert.equal(requests.length, 2);
  state.destroy();
});

test('fresh failure remains unverified and a cancelled old response cannot replace newer data', async () => {
  const failed = createOperationalStore(async () => { throw new Error('server secret'); });
  await failed.refresh('dashboard');
  assert.equal(failed.get('dashboard').state, 'error');
  assert.equal(failed.get('dashboard').data, null);
  assert.equal(failed.get('dashboard').fetchedAt, null);
  assert.equal(failed.get('dashboard').message.includes('server secret'), false);
  failed.destroy();
  let resolveOld: (value: unknown) => void = () => {};
  let calls = 0;
  const state = createOperationalStore(async () => ++calls === 1 ? new Promise(resolve => { resolveOld = resolve; }) : ({ ok: true, json: async () => ({ jobs: [] }) }));
  const old = state.refresh('dashboard');
  await state.refresh('dashboard');
  resolveOld({ ok: true, json: async () => dashboard() });
  await old;
  assert.equal(state.get('dashboard').data.jobs.length, 0);
  state.destroy();
});

test('search is URL encoded, unknown sections are rejected, and display text redacts credential patterns', async () => {
  const urls: string[] = [];
  const state = createOperationalStore(async (url: string) => { urls.push(url); return { ok: true, json: async () => ({ summary: {}, results: [] }) }; });
  await state.refresh('knowledge', '오픽 & 자동화');
  assert.equal(urls[0], '/api/knowledge?query=%EC%98%A4%ED%94%BD%20%26%20%EC%9E%90%EB%8F%99%ED%99%94&limit=10');
  assert.equal(safeText('Bearer topSecretToken email@example.com').includes('topSecretToken'), false);
  assert.equal(safeText('Bearer topSecretToken email@example.com').includes('email@example.com'), false);
  state.destroy();
});
