import { readFileSync } from 'node:fs';
import { test, expect } from '@playwright/test';

for (const mobile of [false, true]) test(`3D viewer height controls preserve the panel and do not write data (${mobile ? 'mobile' : 'PC'})`, async ({ page }) => {
  await page.setViewportSize(mobile ? { width: 390, height: 844 } : { width: 1280, height: 900 });
  const writes: string[] = [];
  const space = JSON.parse(readFileSync(new URL('../../../../../sites/office-world/data/space.json', import.meta.url), 'utf8'));
  await page.route('**/api/**', async route => {
    const request = route.request(), path = new URL(request.url()).pathname;
    if (request.method() !== 'GET') { writes.push(path); return route.abort(); }
    let body: unknown = {};
    if (path === '/api/space') body = space;
    else if (path === '/api/session') body = { csrf: 'local-layout-test' };
    else if (path === '/api/dashboard') body = { articles: [], jobs: [], feeds: [], agents: [], events: [], tasks: [], budget: { cap_krw: 0, spent_krw: 0, reserved_krw: 0, remaining_krw: 0 }, window: { status: 'closed', authorized_end: '2026-10-01T00:00:00Z' }, provider: { model: 'fixture', configured: false }, knowledge: {} };
    else if (path === '/api/jobs/summaries') body = { jobs: [] };
    await route.fulfill({ contentType: 'application/json', body: JSON.stringify(body) });
  });
  await page.goto('/office3d');
  const shell = page.locator('.world-frame-resizer');
  const frame = page.frameLocator('iframe[title="오피스 월드"]');
  await frame.locator('#department-nav button').nth(1).click();
  const body = frame.locator('#panel-body');
  await expect(body).toBeVisible();
  const height = await shell.evaluate(el => el.getBoundingClientRect().height);
  expect(height).toBeGreaterThanOrEqual((mobile ? 844 : 900) - 64);
  const contentHeight = await body.evaluate(el => el.getBoundingClientRect().height);
  await page.getByRole('button', { name: '화면 길게', exact: true }).click();
  await expect.poll(() => shell.evaluate(el => el.getBoundingClientRect().height)).toBe(height + 160);
  await expect.poll(() => body.evaluate(el => el.getBoundingClientRect().height)).toBeGreaterThan(contentHeight + 100);
  await page.getByRole('button', { name: '화면 짧게', exact: true }).click();
  await expect.poll(() => shell.evaluate(el => el.getBoundingClientRect().height)).toBe(height);
  await expect(frame.locator('#panel-close')).toBeVisible();
  await page.getByRole('button', { name: '전체화면', exact: true }).click();
  await expect.poll(() => shell.evaluate(el => Math.round(el.getBoundingClientRect().height))).toBe(mobile ? 844 : 900);
  await expect(frame.locator('#panel-body')).toBeVisible();
  await page.getByRole('button', { name: '원래 크기', exact: true }).click();
  await expect.poll(() => shell.evaluate(el => el.getBoundingClientRect().height)).toBe(height);
  await expect(frame.locator('#panel-body')).toBeVisible();
  expect(writes).toEqual([]);
});
