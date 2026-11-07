import { createHash } from 'node:crypto';
import { test, expect, type Page } from '@playwright/test';
import AxeBuilder from '@axe-core/playwright';
import type { BenchmarkItem, BenchmarkMetric, BenchmarkOverview } from '../../lib/benchmarks';
import type { BenchmarkResearchInputRun, BenchmarkResearchRun } from '../../lib/benchmark-research';
import type { AssistantRequest } from '../../lib/assistant-requests';

const registryHash = 'a'.repeat(64), snapshotHash = 'b'.repeat(64), captureHash = 'c'.repeat(64);
const csrf = 'synthetic-research-csrf';
const packetText = '합성 검증 요청문: 선택한 공개 관측 원문만 조사하고 세이지 분석·독립 검토·루미 최종 보고를 구분합니다.';
const publicSourceUrl = 'https://www.youtube.com/watch?v=--Quy-4QTMs';
const reportSummary = `합성 최종 보고입니다. 세이지가 원문 관측을 분석하고 에이다가 독립 검토했습니다. 누적 공개 반응과 실제 콘텐츠 성과를 구분해 작은 재현 실험을 제안합니다.\n공개 원문 형식 검증 링크: ${publicSourceUrl}`;
const receipt = { task_id: 't_fixture_lumi_final', run_id: 24, event_id: 34,
  report_sha256: createHash('sha256').update(reportSummary).digest('hex'), body_sha256: 'd'.repeat(64) };
const observed = (value: number, raw_text = String(value), precision: BenchmarkMetric['precision'] = 'exact'): BenchmarkMetric => ({ value, raw_text, precision, availability: 'observed' });

function overview(windowOpen: boolean): BenchmarkOverview {
  const now = Date.now(), checked = new Date(now).toISOString();
  const items: BenchmarkItem[] = Array.from({ length: 8 }, (_, index) => {
    const instagram = index < 6;
    return {
      id: `fixture-evidence-${index}`, title: `합성 원문 관측 ${index + 1}`,
      url: instagram ? `https://www.instagram.com/p/fixture-${index}/` : `https://www.youtube.com/watch?v=fixture-${index}`,
      source_id: instagram ? 'every-ig' : 'success-yt', creator_id: instagram ? 'every' : 'success',
      source_name: instagram ? 'every._ai' : '성공지식백과', platform: instagram ? 'instagram' : 'youtube', fields: ['AI 활용'],
      published_at: new Date(now - (index === 0 ? 13 * 86400000 : (index + 1) * 3600000)).toISOString(), checked_at: checked,
      summary: '브라우저 계약 검사 전용 합성 메타데이터입니다. 실제 크리에이터 자료나 운영 실행이 아닙니다.',
      verification_state: 'metadata_only', idea_angle: '내 자료로 재현하고 실패 조건을 함께 기록하기',
      metrics: index === 0 ? { views: { value: null, availability: 'not_visible', raw_text: '', precision: 'unknown' }, likes: observed(0), comments: observed(5800, '5.8천', 'approximate') }
        : { views: observed(index * 10000), likes: observed(index === 1 ? 900 : index * 10), comments: observed(index) },
      provenance: { method: instagram ? 'browser_public_observation' : 'youtube_rss', source_url: instagram ? 'https://www.instagram.com/every._ai/' : 'https://www.youtube.com/@success_wiki', observed_at: checked,
        capture_sha256: instagram ? captureHash : null, scope: '합성 공개 표본 8건만 비교하며 전체 인기 순위는 확인하지 않았습니다.' },
    };
  });
  return {
    registry: { sources: [
      { id: 'every-ig', creator_id: 'every', name: 'every._ai', platform: 'instagram', url: 'https://www.instagram.com/every._ai/', fields: ['AI 활용'] },
      { id: 'success-yt', creator_id: 'success', name: '성공지식백과', platform: 'youtube', url: 'https://www.youtube.com/@success_wiki', channel_id: 'UC-SyuGFlZXpGdR7WszgYBhw', fields: ['AI 활용'] },
    ] }, registry_hash: registryHash, snapshot_hash: snapshotHash, fields: ['AI 활용'], platforms: { instagram: 'Instagram', youtube: 'YouTube' }, items,
    sources_status: [{ source_id: 'every-ig', state: 'ok', method: 'browser_public_observation', checked_at: checked, count: 6, error: null, note: '연결 브라우저 공개 관측 · 무인 API 수집 아님' }],
    activity: { state: 'completed', updated_at: checked, error: null }, window_open: windowOpen, ideas: [],
  };
}

type Write = { path: string; method: string; csrf: string | undefined; body: Record<string, unknown> };
async function harness(page: Page, options: { windowOpen?: boolean; failFirstStart?: boolean } = {}) {
  const data = overview(options.windowOpen ?? true);
  const writes: Write[] = [], unexpected: string[] = [], pageErrors: string[] = [], reads: string[] = [];
  let submitted: BenchmarkResearchInputRun | null = null, starts = 0;
  let frozenObservations: BenchmarkItem[] = [];
  let stage: 'sage' | 'review' | 'completed' = 'sage';
  page.on('pageerror', error => pageErrors.push(error.message));
  // Every API is fixture-only; no real source, assistant, operating data or external account is contacted.
  await page.route('https://**', route => route.abort());
  function run(): BenchmarkResearchRun {
    const input = submitted!;
    const final = stage === 'completed';
    const execution: AssistantRequest = {
      request_id: input.request_id, native_task_id: 't_fixture_lumi_root', board: 'heobrain-office', status: final ? 'completed' : 'running',
      native_status: final ? 'done' : 'running', assignee: stage === 'sage' ? 'mybots-sage' : stage === 'review' ? 'ada' : 'lumi',
      title: '합성 공개자료 조사', updated_at: 1, current_run_id: final ? null : stage === 'sage' ? 21 : 22, error: null,
      delivery: { slack: 'not_attached', external_delivery_verified: false },
      events: [
        { id: 31, task_id: 't_fixture_sage', run_id: 21, kind: stage === 'sage' ? 'running' : 'completed', assignee: 'mybots-sage', created_at: 1 },
        ...(stage !== 'sage' ? [{ id: 32, task_id: 't_fixture_review', run_id: 22, kind: final ? 'completed' : 'running', assignee: 'ada' as const, created_at: 2 }] : []),
        ...(final ? [{ id: 34, task_id: receipt.task_id, run_id: receipt.run_id, kind: 'completed', assignee: 'lumi' as const, created_at: 3 }] : []),
      ], report: final ? { summary: reportSummary, verified: true, task_id: receipt.task_id, run_id: receipt.run_id, event_id: receipt.event_id } : null,
    };
    return { request_id: input.request_id, packet_hash: 'e'.repeat(64), registry_hash: registryHash, snapshot_hash: snapshotHash, item_ids: input.item_ids, observations: frozenObservations,
      created_at: new Date().toISOString(), execution, analysis_receipt: final ? receipt : null,
      budget_evidence: { cap_krw: 10000, spent_krw: 1200, reserved_krw: 300, remaining_krw: 8500, native_monetary_guard: false, billing_mode: 'existing_subscription' } };
  }
  await page.route('**/api/**', async route => {
    const req = route.request(), path = new URL(req.url()).pathname, method = req.method();
    const body = method === 'GET' ? {} : req.postDataJSON() as Record<string, unknown>;
    if (method === 'GET') reads.push(path);
    else writes.push({ path, method, csrf: req.headers()['x-office-csrf'], body });
    let value: unknown;
    if (path === '/api/session' && method === 'GET') value = { csrf };
    else if (path === '/api/dashboard' && method === 'GET') value = { articles: [], jobs: [], feeds: [], agents: [], events: [], tasks: [], budget: { cap_krw: 10000, spent_krw: 1200, reserved_krw: 300, remaining_krw: 8500 }, window: { status: data.window_open ? 'open' : 'closed' }, provider: { configured: false }, knowledge: {} };
    else if (path === '/api/benchmarks' && method === 'GET') value = data;
    else if (path === '/api/benchmarks/research-packet' && method === 'POST') value = { text: packetText, registry_hash: registryHash, snapshot_hash: snapshotHash };
    else if (path === '/api/benchmarks/research-runs' && method === 'POST') {
      submitted = body as unknown as BenchmarkResearchInputRun;
      if (!frozenObservations.length) frozenObservations = structuredClone(submitted.item_ids.map(id => data.items.find(item => item.id === id)!));
      if (++starts === 1 && options.failFirstStart) { await route.fulfill({ status: 503, json: { detail: '합성 접수 결과 불명 · 같은 요청 번호로 확인하세요.' } }); return; }
      value = run();
    } else if (/^\/api\/benchmarks\/research-runs\/[0-9a-f-]{36}$/.test(path) && method === 'GET') {
      if (!submitted || (starts === 1 && options.failFirstStart)) { await route.fulfill({ status: 404, json: { detail: '합성 실행 기록을 아직 확인하지 못했습니다.' } }); return; }
      expect(path.split('/').at(-1)).toBe(submitted.request_id);
      value = run();
    } else if (/^\/api\/benchmarks\/research-runs\/[0-9a-f-]{36}\/ideas$/.test(path) && method === 'POST') {
      expect(stage).toBe('completed');
      expect(body.receipt).toEqual(receipt);
      value = { id: 'idea_fixture_report', title: body.title, source_url: data.items.find(item => item.id === body.item_id)!.url, source_id: 'every-ig', platform: 'instagram', fields: ['AI 활용'], target_platforms: body.target_platforms,
        angle: body.angle, state: 'candidate', primary_sources: 0, score: 0, outlier_band: 'unknown', blocked: ['primary_sources'], reasons: [], origin: 'benchmark', edit_hash: 'f'.repeat(64) };
    } else if (method !== 'GET') { unexpected.push(`${method} ${path}`); await route.fulfill({ status: 500, json: { detail: 'Unexpected fixture write' } }); return; }
    else if (path === '/api/ideas') value = { ideas: [] };
    else if (path === '/api/questions') value = { questions: [], groups: [] };
    else if (path === '/api/channels') value = { channels: [] };
    else if (path === '/api/briefs') value = { default: '', presets: [] };
    else if (path === '/api/discovery') value = { config: { topic: '합성 조사', region: 'KR', platforms: ['youtube'], youtube_channels: [] }, config_hash: registryHash, platforms: { youtube: 'YouTube' }, plan: {}, window_open: data.window_open, stale: false, unconnected: [], snapshot: null };
    else if (path === '/api/jobs/summaries') value = { jobs: [] };
    else value = {};
    await route.fulfill({ json: value });
  });
  return { data, writes, unexpected, pageErrors, reads, stage: (next: typeof stage) => { stage = next; } };
}

const board = (page: Page) => page.locator('section[aria-labelledby="benchmark-heading"]');
const runPanel = (page: Page) => page.getByRole('region', { name: '실제 세이지 조사와 최종 보고', exact: true });
async function chooseEvidence(page: Page, count: number) {
  await page.goto('/news?tab=creators');
  for (let index = 0; index < count; index++) await board(page).getByRole('checkbox', { name: `조사 근거로 선택 · 합성 원문 관측 ${index + 1}`, exact: true }).check();
  await page.getByRole('navigation', { name: '소식 보기', exact: true }).getByRole('link', { name: '경쟁사·아이디어', exact: true }).click();
  await board(page).getByRole('button', { name: '세이지 조사 요청문 준비', exact: true }).click();
  await expect(board(page).getByLabel('준비된 세이지 조사 요청문', { exact: true })).toHaveValue(packetText);
}

for (const width of [1440, 390]) test(`공개 반응의 비표시·실제 0·근사값과 과거 발행일을 구분한다 ${width}px`, async ({ page }, testInfo) => {
  const state = await harness(page);
  await page.setViewportSize({ width, height: 950 });
  await page.goto('/news?tab=creators');
  const card = board(page).locator('article').filter({ has: page.getByRole('heading', { name: '합성 원문 관측 1', exact: true }) });
  await expect(card.getByText('연결 브라우저 관측 · 과거 게시물 · 7일 초과', { exact: true })).toBeVisible();
  const metrics = card.locator('dl').first();
  await expect(metrics.locator('div').filter({ hasText: '누적 조회' }).locator('dd')).toHaveText('비표시');
  await expect(metrics.locator('div').filter({ hasText: '좋아요' }).locator('dd')).toHaveText('0');
  await expect(metrics.locator('div').filter({ hasText: '댓글' }).locator('dd')).toHaveText('5.8천 (근사)');
  await expect(metrics.locator('div').filter({ hasText: '리포스트' }).locator('dd')).toHaveText('미확인');
  const dates = await card.locator('dl').last().locator('dd').allTextContents();
  expect(dates[0]).not.toBe(dates[1]);
  await card.getByText('수집 근거와 비교 범위', { exact: true }).click();
  await expect(card.getByText(captureHash, { exact: true })).toBeVisible();
  await expect(card.getByText(/전체 플랫폼 인기 순위·증가 속도·영상 본문 검증을 뜻하지 않습니다/)).toBeVisible();
  const compare = board(page).getByLabel('표본 비교', { exact: true });
  await expect(compare).toBeDisabled();
  await board(page).getByLabel('출처 플랫폼', { exact: true }).selectOption('instagram');
  await expect(compare).toBeEnabled();
  await compare.selectOption('likes');
  await expect(board(page).locator('#benchmark-news-candidates article').first().getByRole('heading')).toHaveText('합성 원문 관측 2');
  await expect(board(page).getByRole('heading', { name: '합성 원문 관측 8', exact: true })).toHaveCount(0);
  await board(page).getByLabel('출처 플랫폼', { exact: true }).selectOption('all');
  await expect(compare).toBeDisabled();
  await expect(board(page).locator('#benchmark-news-candidates article').first().getByRole('heading')).toHaveText('합성 원문 관측 2');
  expect(await page.evaluate(() => document.documentElement.scrollWidth <= innerWidth)).toBe(true);
  await page.screenshot({ path: testInfo.outputPath(`2026-11-07_실제경쟁사_browser_metrics_${width}.png`) });
  expect(state.writes).toEqual([]); expect(state.unexpected).toEqual([]); expect(state.pageErrors).toEqual([]);
});

for (const width of [1440, 390]) test(`선택한 6개 원문과 스냅샷만 조사 요청문에 담고 준비만으로 실행하지 않는다 ${width}px`, async ({ page }) => {
  const state = await harness(page);
  await page.setViewportSize({ width, height: 950 });
  await page.goto('/news?tab=creators');
  for (let index = 0; index < 6; index++) await board(page).getByRole('checkbox', { name: `조사 근거로 선택 · 합성 원문 관측 ${index + 1}`, exact: true }).check();
  await expect(board(page).getByRole('checkbox', { name: '조사 근거로 선택 · 합성 원문 관측 7', exact: true })).toBeDisabled();
  await page.getByRole('navigation', { name: '소식 보기', exact: true }).getByRole('link', { name: '경쟁사·아이디어', exact: true }).click();
  await board(page).getByRole('button', { name: '세이지 조사 요청문 준비', exact: true }).click();
  await expect(runPanel(page).getByRole('button', { name: '선택한 근거로 세이지 조사 시작', exact: true })).toBeEnabled();
  await expect(board(page).getByRole('button', { name: '세이지 조사 요청문 검토', exact: true })).toHaveCount(0);
  expect(state.writes).toEqual([{ path: '/api/benchmarks/research-packet', method: 'POST', csrf, body: { source_ids: ['every-ig'], fields: [], platforms: [], expected_hash: registryHash,
    item_ids: state.data.items.slice(0, 6).map(item => item.id), snapshot_hash: snapshotHash } }]);
  await board(page).getByLabel('출처 플랫폼', { exact: true }).selectOption('instagram');
  await expect(runPanel(page).getByRole('button', { name: '선택한 근거로 세이지 조사 시작', exact: true })).toBeDisabled();
  await expect(board(page).getByText('출처 또는 조사 조건이 바뀌었습니다. 요청문을 다시 준비하세요.', { exact: true })).toBeVisible();
  expect(state.reads.some(path => path.includes('research-runs') || path.includes('subscribe'))).toBe(false);
  expect(state.unexpected).toEqual([]); expect(state.pageErrors).toEqual([]);
});

test('작업 시간이 닫혀 있으면 준비된 근거가 있어도 실제 조사 접수를 막는다', async ({ page }) => {
  const state = await harness(page, { windowOpen: false });
  await page.setViewportSize({ width: 390, height: 950 });
  await chooseEvidence(page, 1);
  await expect(runPanel(page).getByText('작업 시간이 종료됐습니다. 제작 설정에서 사용자가 작업 시간을 연 뒤 조사를 시작할 수 있습니다.', { exact: true })).toBeVisible();
  await expect(runPanel(page).getByRole('button', { name: '선택한 근거로 세이지 조사 시작', exact: true })).toBeDisabled();
  expect(state.writes.map(write => write.path)).toEqual(['/api/benchmarks/research-packet']);
  expect(state.unexpected).toEqual([]); expect(state.pageErrors).toEqual([]);
});

test('접수 결과 불명 뒤 새로고침해도 같은 UUID와 동결 근거로 재확인한다', async ({ page }) => {
  const state = await harness(page, { failFirstStart: true });
  await page.setViewportSize({ width: 390, height: 1050 });
  await chooseEvidence(page, 1);
  await runPanel(page).getByRole('button', { name: '선택한 근거로 세이지 조사 시작', exact: true }).click();
  await expect(runPanel(page).getByRole('button', { name: '같은 요청 번호로 접수 확인', exact: true })).toBeEnabled();
  const first = state.writes.find(write => write.path === '/api/benchmarks/research-runs')!;
  state.data.items[0].title = '새 관측에서 바뀐 제목';
  await page.reload();
  const panel = runPanel(page);
  await expect(panel.locator('code').first()).toHaveText(String(first.body.request_id));
  await expect(panel.getByRole('button', { name: '같은 요청 번호로 접수 확인', exact: true })).toBeEnabled();
  await panel.getByRole('button', { name: '같은 요청 번호로 접수 확인', exact: true }).click();
  await expect(panel.getByText(/실제 비서 조사 중/)).toBeVisible();
  const attempts = state.writes.filter(write => write.path === '/api/benchmarks/research-runs');
  expect(attempts).toHaveLength(2);
  expect(attempts[1].body).toEqual(first.body);
  state.stage('completed');
  await panel.getByRole('button', { name: '실행·보고 다시 확인', exact: true }).click();
  const evidence = panel.getByRole('combobox', { name: '분석에 사용한 근거', exact: true });
  await expect(evidence.getByRole('option', { name: '합성 원문 관측 1', exact: true })).toHaveCount(1);
  await expect(evidence.getByRole('option', { name: '새 관측에서 바뀐 제목', exact: true })).toHaveCount(0);
  expect(state.writes).toHaveLength(3);
  expect(state.writes.every(write => write.csrf === csrf)).toBe(true);
  expect(state.unexpected).toEqual([]); expect(state.pageErrors).toEqual([]);
});

for (const width of [1440, 390]) test(`불명 접수는 같은 UUID로 재확인하고 세이지·검토·루미 최종 영수증으로만 후보 저장한다 ${width}px`, async ({ page }, testInfo) => {
  const state = await harness(page, { failFirstStart: true });
  await page.setViewportSize({ width, height: 1050 });
  await chooseEvidence(page, 2);
  const panel = runPanel(page);
  await panel.getByRole('button', { name: '선택한 근거로 세이지 조사 시작', exact: true }).click();
  await expect(panel.getByRole('button', { name: '같은 요청 번호로 접수 확인', exact: true })).toBeEnabled();
  await expect(panel.getByRole('heading', { name: '이 분석을 내 아이디어로 연결', exact: true })).toHaveCount(0);
  await panel.getByRole('button', { name: '같은 요청 번호로 접수 확인', exact: true }).click();
  await expect(panel.getByText(/실제 비서 조사 중/)).toBeVisible();
  const attempts = state.writes.filter(write => write.path === '/api/benchmarks/research-runs');
  expect(attempts).toHaveLength(2);
  expect(attempts[0].body).toEqual(attempts[1].body);
  expect(attempts[0].body.request_id).toMatch(/^[a-f0-9]{8}-[a-f0-9]{4}-4[a-f0-9]{3}-[89ab][a-f0-9]{3}-[a-f0-9]{12}$/i);
  expect(attempts[0].body).toMatchObject({ expected_hash: registryHash, snapshot_hash: snapshotHash, item_ids: ['fixture-evidence-0', 'fixture-evidence-1'] });
  await panel.getByText(/실제 역할·실행 기록/).click();
  await expect(panel.getByText('세이지 · running · 실행 21 · 기록 31', { exact: true })).toBeVisible();
  state.stage('review');
  await panel.getByRole('button', { name: '실행·보고 다시 확인', exact: true }).click();
  await expect(panel.getByText('에이다 · running · 실행 22 · 기록 32', { exact: true })).toBeVisible();
  await expect(panel.getByRole('button', { name: '분석 근거를 연결해 후보 저장', exact: true })).toHaveCount(0);
  state.stage('completed');
  await panel.getByRole('button', { name: '실행·보고 다시 확인', exact: true }).click();
  await expect(panel.getByRole('region', { name: '세이지 조사 최종 보고', exact: true }).getByText(reportSummary, { exact: true })).toBeVisible();
  await expect(panel.getByText('루미 · completed · 실행 24 · 기록 34', { exact: true })).toBeVisible();
  await panel.getByRole('combobox', { name: '분석에 사용한 근거', exact: true }).selectOption('fixture-evidence-0');
  await panel.getByLabel('내 콘텐츠 제목', { exact: true }).fill('내 자료로 검증하는 자동화 실험');
  await panel.getByLabel('보고에서 가져올 관점·검증할 질문', { exact: true }).fill('원문과 다른 조건을 고정해 실패 사례까지 비교합니다.');
  await panel.getByRole('checkbox', { name: 'YouTube', exact: true }).check();
  await panel.getByRole('button', { name: '분석 근거를 연결해 후보 저장', exact: true }).click();
  await expect(panel.getByText(/승인⓪·원고·제작은 시작하지 않았습니다/)).toBeVisible();
  const ideaWrites = state.writes.filter(write => write.path.endsWith('/ideas'));
  expect(ideaWrites).toHaveLength(1);
  expect(ideaWrites[0].path).toBe(`/api/benchmarks/research-runs/${attempts[0].body.request_id}/ideas`);
  expect(ideaWrites[0].body).toEqual({ item_id: 'fixture-evidence-0', title: '내 자료로 검증하는 자동화 실험', angle: '원문과 다른 조건을 고정해 실패 사례까지 비교합니다.', target_platforms: ['youtube'], receipt });
  expect(state.writes).toHaveLength(4);
  expect(state.writes.every(write => write.csrf === csrf && write.method === 'POST')).toBe(true);
  expect(state.reads.some(path => path.includes('subscribe'))).toBe(false);
  expect(await page.evaluate(() => document.documentElement.scrollWidth <= innerWidth)).toBe(true);
  await expect(page.getByRole('link', { name: '본문으로 이동', exact: true })).not.toBeInViewport();
  await page.screenshot({ path: testInfo.outputPath(`2026-11-07_실제경쟁사_browser_viewport_${width}.png`) });
  await panel.screenshot({ path: testInfo.outputPath(`2026-11-07_실제경쟁사_browser_report_${width}.png`) });
  const audit = await new AxeBuilder({ page }).include('section[aria-label="실제 세이지 조사와 최종 보고"]').withTags(['wcag2a', 'wcag2aa', 'wcag21aa']).analyze();
  expect(audit.violations.filter(row => row.impact === 'critical' || row.impact === 'serious')).toEqual([]);
  expect(state.unexpected).toEqual([]); expect(state.pageErrors).toEqual([]);
});
