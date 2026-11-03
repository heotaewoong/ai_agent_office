import { createHash } from 'node:crypto';
import { test, expect, type Page } from '@playwright/test';

const requestId = 'aaaaaaaa-aaaa-4aaa-8aaa-aaaaaaaaaaaa';
const jobId = 'job_0123456789abcdef';
const body = '연결 검증에서만 사용하는 독립적인 합성 원고입니다. '.repeat(7);
const summary = '# 합성 원고 연결 검증\n\n' + body;
const hash = (text: string) => createHash('sha256').update(text).digest('hex');
const candidate = { request_id: requestId, task_id: 't_synthetic_final', run_id: 7, event_id: 31,
  title: '합성 원고 연결 검증', body_length: body.length, report_sha256: hash(summary), body_sha256: hash(body), job: null };
const job = { id: jobId, title: candidate.title, state: 'research_ready', source_hash: 'c'.repeat(64),
  source_packet: { title: candidate.title, body, quality: { status: 'unverified', critical: true }, preserve_original: true, evidence: [] },
  article: { id: 'synthetic-owned-source', title: candidate.title, url: '', operator_source_text: body, preserve_original: true },
  selections: { blog: true, video: false, pdf: false, cards: false }, source_approval: null, release_approval: null,
  manifest: null, tasks: [], events: [], drafts: [] };
const saved = { ...candidate, job: { id: jobId, source_hash: job.source_hash, current_source_hash: job.source_hash, state: job.state } };

async function setup(page: Page, mode: 'new' | 'saved' | 'failed' | 'delayed' = 'new') {
  const writes: { path: string; body: unknown }[] = [], errors: string[] = [], reads: string[] = [];
  let linked = mode === 'saved';
  let release = () => {};
  const pending = new Promise<void>(resolve => { release = resolve; });
  page.on('pageerror', error => errors.push(error.message));
  // This test covers the real React report/routes, without repeating the separate 3D suite.
  await page.route('**/world/index.html?*', route => route.fulfill({ contentType: 'text/html', body: '<!doctype html><title>3D boundary outside this test</title>' }));
  await page.route('https://**', route => route.abort());
  await page.route('**/api/**', async route => {
    const req = route.request(), path = new URL(req.url()).pathname;
    if (req.method() === 'GET') reads.push(path);
    else writes.push({ path, body: req.postDataJSON() });
    let value: unknown;
    if (path === '/api/session') value = { csrf: 'synthetic-content-csrf' };
    else if (path === '/api/dashboard') value = { articles: [], jobs: [], feeds: [], agents: [], events: [], tasks: [],
      budget: { cap_krw: 0, spent_krw: 0, reserved_krw: 0, remaining_krw: 0 }, window: { status: 'closed' }, provider: { configured: false }, knowledge: {} };
    else if (path === '/api/jobs/summaries') value = { jobs: [] };
    else if (path === '/api/assistant/reports') value = { reports: [] };
    else if (path === `/api/assistant/requests/${requestId}`) value = {
      request_id: requestId, native_task_id: 't_synthetic_root', board: 'heobrain-office', status: 'completed', native_status: 'done',
      assignee: 'lumi', title: '합성 비서 업무', updated_at: 1, current_run_id: null, error: null,
      events: [{ id: 31, task_id: candidate.task_id, run_id: 7, kind: 'completed', assignee: 'lumi', created_at: 1 }],
      report: { summary, verified: true, task_id: candidate.task_id, run_id: 7, event_id: 31 },
      delivery: { slack: 'not_attached', external_delivery_verified: false }, content: linked ? saved : candidate,
    };
    else if (path === `/api/assistant/requests/${requestId}/content-job`) {
      expect(req.method()).toBe('POST');
      expect(req.headers()['x-office-csrf']).toBe('synthetic-content-csrf');
      expect(req.postDataJSON()).toEqual({ task_id: candidate.task_id, run_id: 7, event_id: 31,
        report_sha256: candidate.report_sha256, body_sha256: candidate.body_sha256 });
      if (mode === 'failed') return route.fulfill({ status: 409, json: { detail: '합성 판본 충돌 · 기존 원고 보존' } });
      if (mode === 'delayed') await pending;
      linked = true; value = { content: saved };
    } else if (path === `/api/jobs/${jobId}`) value = job;
    else if (path === '/api/briefs') value = { presets: [] };
    else if (path === '/api/channels') value = { channels: [] };
    else if (path.endsWith('/deliveries')) value = { deliveries: [] };
    await route.fulfill({ status: value === undefined ? 404 : 200, json: value ?? { detail: 'Synthetic test endpoint unavailable' } });
  });
  await page.goto(`/office3d?assistant_request=${requestId}`);
  await page.getByRole('button', { name: '루미와 대화하기', exact: true }).click();
  const dialog = page.getByRole('dialog', { name: '루미와 대화' });
  await expect(dialog.getByRole('region', { name: '콘텐츠 원고 연결' })).toBeVisible();
  return { dialog, writes, reads, errors, release };
}

for (const width of [1440, 390]) test(`원고 저장은 한 번만 요청하고 목록에 없는 정확한 작업실로 이동한다 (${width})`, async ({ page }) => {
  await page.setViewportSize({ width, height: 1000 });
  const h = await setup(page), save = h.dialog.getByRole('button', { name: '원고 저장하고 작업실 열기', exact: true });
  expect(h.writes).toEqual([]);
  await save.focus();
  expect((await save.boundingBox())!.height).toBeGreaterThanOrEqual(44);
  await page.keyboard.press('Enter');
  await expect(page).toHaveURL(new RegExp(`/scripts/${jobId}$`), { timeout: 15000 });
  await expect.poll(() => h.reads.includes(`/api/jobs/${jobId}`)).toBe(true);
  expect(h.writes).toHaveLength(1);
  expect(h.writes[0].path).toBe(`/api/assistant/requests/${requestId}/content-job`);
  expect(h.errors).toEqual([]);
  expect(await page.evaluate(() => document.documentElement.scrollWidth <= innerWidth)).toBe(true);
});

for (const width of [1440, 390]) test(`저장된 원고의 출고함 링크는 같은 작업을 열고 제작/승인을 만들지 않는다 (${width})`, async ({ page }, testInfo) => {
  await page.setViewportSize({ width, height: 1000 });
  const h = await setup(page, 'saved');
  await expect(h.dialog.getByRole('link', { name: '원고 작업실 열기', exact: true })).toHaveAttribute('href', `/scripts/${jobId}`);
  await expect(h.dialog).toContainText('원고 승인①·제작·출고 승인② 상태는 별도');
  await expect(h.dialog.getByRole('link', { name: '원고 작업실 열기', exact: true })).toBeVisible();
  await page.screenshot({ path: testInfo.outputPath('completion-links.png') });
  await h.dialog.getByRole('link', { name: '제작·출고함 보기', exact: true }).click();
  await expect(page).toHaveURL(new RegExp(`/publish\\?job=${jobId}$`));
  await expect.poll(() => h.reads.includes(`/api/jobs/${jobId}`)).toBe(true);
  expect(h.writes).toEqual([]); expect(h.errors).toEqual([]);
});

test('저장 거절은 기존 보고를 보존하고 자동으로 다시 전송하지 않는다', async ({ page }) => {
  const h = await setup(page, 'failed');
  await h.dialog.getByRole('button', { name: '원고 저장하고 작업실 열기', exact: true }).click();
  await expect(h.dialog.getByRole('alert')).toContainText('합성 판본 충돌');
  await expect(h.dialog.getByRole('region', { name: '검증된 비서 보고' })).toContainText(summary);
  expect(page.url()).toContain('/office3d'); expect(h.writes).toHaveLength(1);
  await h.dialog.getByRole('button', { name: '닫기', exact: true }).click();
  await page.getByRole('button', { name: '루미와 대화하기', exact: true }).click();
  expect(h.writes).toHaveLength(1); expect(h.errors).toEqual([]);
});

test('닫은 뒤 도착한 저장 응답은 원고만 연결하고 화면을 빼앗지 않는다', async ({ page }) => {
  const h = await setup(page, 'delayed');
  await h.dialog.getByRole('button', { name: '원고 저장하고 작업실 열기', exact: true }).click();
  await expect.poll(() => h.writes.length).toBe(1);
  await page.keyboard.press('Escape');
  await expect(h.dialog).not.toBeVisible();
  await page.getByRole('button', { name: '루미와 대화하기', exact: true }).click();
  h.release();
  await expect(h.dialog.getByRole('link', { name: '원고 작업실 열기', exact: true })).toBeVisible();
  expect(page.url()).toContain('/office3d'); expect(h.writes).toHaveLength(1); expect(h.errors).toEqual([]);
});
