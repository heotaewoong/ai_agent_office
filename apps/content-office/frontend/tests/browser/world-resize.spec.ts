import { readFileSync } from 'node:fs';
import { test, expect } from '@playwright/test';

const profilers = new WeakMap();
test.beforeEach(async ({ page }) => {
  const client = await page.context().newCDPSession(page);
  await client.send('Profiler.enable');
  await client.send('Profiler.start');
  await client.send('Performance.enable');
  await client.send('Tracing.start', { categories: 'devtools.timeline,cc,gpu', transferMode: 'ReturnAsStream' });
  profilers.set(page, client);
});
test.afterEach(async ({ page }, info) => {
  const client = profilers.get(page);
  if (!client) return;
  const { profile } = await client.send('Profiler.stop');
  const metrics = await client.send('Performance.getMetrics');
  const completed = new Promise<{ stream: string }>(resolve => client.once('Tracing.tracingComplete', resolve));
  await client.send('Tracing.end');
  const { stream } = await completed;
  const chunks: Buffer[] = [];
  for (;;) {
    const chunk = await client.send('IO.read', { handle: stream });
    chunks.push(Buffer.from(chunk.data, chunk.base64Encoded ? 'base64' : 'utf8'));
    if (chunk.eof) break;
  }
  await client.send('IO.close', { handle: stream });
  await info.attach('native-timeline', { body: Buffer.concat(chunks), contentType: 'application/json' });
  await info.attach('cpu-profile', { body: JSON.stringify(profile), contentType: 'application/json' });
  await info.attach('browser-metrics', { body: JSON.stringify(metrics), contentType: 'application/json' });
});

for (const mobile of [false, true]) test(`low-quality 3D viewer preserves panel, fullscreen chat and drafts without writes (${mobile ? 'mobile' : 'PC'})`, async ({ page }) => {
  // This loads the full Babylon world on software-rendered CI, beyond the UI-only default.
  // CI software rendering may take over 90s for the complete PC flow.
  // Keep every 15s assertion and the real world/fullscreen checks unchanged.
  test.setTimeout(180_000);
  // Use the real supported low-quality mode on runners without a physical GPU.
  await page.addInitScript(() => localStorage.setItem('heobrain.world-quality.v1', 'low'));
  await page.setViewportSize(mobile ? { width: 390, height: 844 } : { width: 1280, height: 900 });
  const writes: string[] = [];
  const space = JSON.parse(readFileSync(new URL('../../../../../sites/office-world/data/space.json', import.meta.url), 'utf8'));
  await page.route(url => url.pathname.startsWith('/api/'), async route => {
    const request = route.request(), path = new URL(request.url()).pathname;
    if (request.method() !== 'GET') { writes.push(path); return route.abort(); }
    let body: unknown = {};
    if (path === '/api/space') body = space;
    else if (path === '/api/session') body = { csrf: 'local-layout-test' };
    else if (path === '/api/dashboard') body = { articles: [], jobs: [], feeds: [], agents: [], events: [], tasks: [], budget: { cap_krw: 0, spent_krw: 0, reserved_krw: 0, remaining_krw: 0 }, window: { status: 'closed', authorized_end: '2026-10-01T00:00:00Z' }, provider: { model: 'fixture', configured: false }, knowledge: {} };
    else if (path === '/api/jobs/summaries') body = { jobs: [] };
    await route.fulfill({ contentType: 'application/json', body: JSON.stringify(body) });
  });
  const started = Date.now();
  async function phase(name: string, operation: () => Promise<void>) {
    console.info(JSON.stringify({ test: 'world-resize', viewport: mobile ? 'mobile' : 'PC', phase: name, state: 'start', elapsed_ms: Date.now() - started }));
    await test.step(name, operation);
    console.info(JSON.stringify({ test: 'world-resize', viewport: mobile ? 'mobile' : 'PC', phase: name, state: 'end', elapsed_ms: Date.now() - started }));
  }
  await phase('load real 3D iframe', async () => { await page.goto('/office3d'); });
  const shell = page.locator('.world-frame-resizer');
  const frame = page.frameLocator('iframe[title="오피스 월드"]');
  const body = frame.locator('#panel-body');
  await expect.poll(() => frame.locator('#scene').evaluate(() => {
    const state = (window as unknown as { __officeWorld: { world: { scene: { getFrameId(): number } } } }).__officeWorld;
    return state?.world.scene.getFrameId() ?? 0;
  }), { timeout: 15_000 }).toBeGreaterThan(0);
  // Mobile uses a horizontal department strip; keyboard navigation must reveal its next item.
  await phase('open team panel with keyboard', async () => {
    await frame.locator('#department-nav button').first().focus();
    await page.keyboard.press('Tab');
    await page.keyboard.press('Enter');
    await expect(body).toBeVisible();
  });
  const height = await shell.evaluate(el => el.getBoundingClientRect().height);
  expect(height).toBeGreaterThanOrEqual((mobile ? 844 : 900) - 64);
  const contentHeight = await body.evaluate(el => el.getBoundingClientRect().height);
  await phase('grow viewer and panel body', async () => {
    await page.getByRole('button', { name: '화면 길게', exact: true }).click();
    await expect.poll(() => shell.evaluate(el => el.getBoundingClientRect().height), { timeout: 15_000 }).toBe(height + 160);
    // Wrapped headers reserve different space at each width; usable body space must still grow.
    await expect.poll(() => body.evaluate(el => el.getBoundingClientRect().height), { timeout: 15_000 }).toBeGreaterThan(contentHeight);
  });
  await phase('restore viewer height', async () => {
    await page.getByRole('button', { name: '화면 짧게', exact: true }).click();
    await expect.poll(() => shell.evaluate(el => el.getBoundingClientRect().height), { timeout: 15_000 }).toBe(height);
    await expect(frame.locator('#panel-close')).toBeVisible();
  });
  await phase('enter native fullscreen', async () => {
    await page.getByRole('button', { name: '전체화면', exact: true }).click();
    await expect.poll(() => shell.evaluate(el => Math.round(el.getBoundingClientRect().height)), { timeout: 15_000 }).toBe(mobile ? 844 : 900);
    await expect(frame.locator('#panel-body')).toBeVisible();
  });
  await phase('preserve assistant draft above fullscreen', async () => {
    // Exercise the real modal above the Fullscreen top layer, preserving unsent input.
    await frame.locator('body').evaluate(() => parent.postMessage({ source: 'office-world', type: 'assistant-open', assistant: 'ada' }, location.origin));
    const dialog = page.getByRole('dialog', { name: '에이다에게 업무 요청' });
    await expect(dialog).toBeVisible();
    await expect(dialog).toHaveJSProperty('open', true);
    await dialog.getByRole('textbox').fill('전체화면 대화 입력 보존 확인');
    await dialog.getByRole('button', { name: '닫기', exact: true }).click();
  });
  await phase('exit fullscreen and reopen unsent draft', async () => {
    await page.getByRole('button', { name: '원래 크기', exact: true }).click();
    await expect.poll(() => shell.evaluate(el => el.getBoundingClientRect().height), { timeout: 15_000 }).toBe(height);
    await expect(frame.locator('#panel-body')).toBeVisible();
    await page.getByRole('button', { name: '루미와 대화하기', exact: true }).click();
    await expect(page.getByRole('dialog').getByRole('textbox')).toHaveValue('전체화면 대화 입력 보존 확인');
  });
  expect(writes).toEqual([]);
});
