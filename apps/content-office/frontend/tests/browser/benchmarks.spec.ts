import { test, expect, type Page } from '@playwright/test';
import AxeBuilder from '@axe-core/playwright';
import type { BenchmarkOverview, BenchmarkIdeaInput, BenchmarkRegistryInput } from '../../lib/benchmarks';

const initialHash = 'a'.repeat(64);
const preparedText = '공개자료 조사 요청: every._ai의 AI 활용 콘텐츠를 조사해 주세요. 원문 URL·발행일·확인일과 주장/직접 관찰을 구분하고 새 콘텐츠 관점과 반례를 제안해 주세요. mybots-sage 작업자 조사와 독립 검토 후 루미가 최종 보고합니다. 외부 게시·DM·결제·새 예약·유료 호출은 하지 않습니다.';

function initialOverview(): BenchmarkOverview {
  const now = Date.now();
  const checked = new Date(now).toISOString();
  return {
    registry: { sources: [
      { id: 'every-ig', creator_id: 'every', name: 'every._ai', platform: 'instagram', url: 'https://www.instagram.com/every._ai/', fields: ['AI 활용', '업무 자동화'] },
      { id: 'success-yt', creator_id: 'success', name: '성공지식백과', platform: 'youtube', url: 'https://www.youtube.com/@successwiki', fields: ['공부법'], channel_id: 'UC-SyuGFlZXpGdR7WszgYBhw' },
    ] }, registry_hash: initialHash, fields: ['AI 활용', '업무 자동화', '공부법'], platforms: { instagram: 'Instagram', youtube: 'YouTube', website: '웹사이트' },
    items: [
      { id: 'ig-post', title: '회의록 프롬프트 실험', url: 'https://www.instagram.com/p/synthetic-one/', source_id: 'every-ig', creator_id: 'every', source_name: 'every._ai', platform: 'instagram', fields: ['AI 활용'], published_at: new Date(now - 3600000).toISOString(), checked_at: checked, summary: '공개 제목과 설명을 보관한 합성 자료입니다.', verification_state: 'metadata_only', idea_angle: '내 회의록으로 재현해 성공·실패 조건 비교' },
      { id: 'yt-post', title: '공부 루틴을 기록하는 방법', url: 'https://www.youtube.com/watch?v=synthetic-two', source_id: 'success-yt', creator_id: 'success', source_name: '성공지식백과', platform: 'youtube', fields: ['공부법'], published_at: new Date(now - 7200000).toISOString(), checked_at: checked, summary: '공개 RSS의 합성 설명입니다.', verification_state: 'stale_metadata', idea_angle: '직접 실행한 학습 기록과 비교' },
      { id: 'future', title: '미래 날짜가 있는 자료', url: 'https://www.youtube.com/watch?v=synthetic-future', source_id: 'success-yt', creator_id: 'success', source_name: '성공지식백과', platform: 'youtube', fields: ['공부법'], published_at: new Date(now + 86400000).toISOString(), checked_at: checked, summary: '', verification_state: 'metadata_only', idea_angle: '' },
    ],
    sources_status: [
      { source_id: 'every-ig', state: 'manual', method: 'manual', checked_at: null, count: null, error: null, note: 'Instagram 자동 수집 미연동. 원문을 확인하고 기획 후보를 등록하세요.' },
      { source_id: 'success-yt', state: 'failed', method: 'youtube_rss', checked_at: checked, count: null, error: '합성 RSS 연결 실패', note: '이전 관측 자료를 보존했습니다.' },
    ], activity: { state: 'failed', updated_at: checked, error: null }, window_open: false, ideas: [],
  };
}

// All API calls terminate in this fixture; no external sources, accounts or operating data are used.
async function boardHarness(page: Page, options: { failFirst?: boolean; empty?: boolean } = {}) {
  let overview = initialOverview();
  if (options.empty) overview.items = [];
  let reads = 0;
  const writes: { path: string; method: string; csrf?: string; body: Record<string, unknown> }[] = [];
  await page.route('**/api/**', async route => {
    const request = route.request(), path = new URL(request.url()).pathname, method = request.method();
    const body = method === 'GET' ? {} : request.postDataJSON() as Record<string, unknown>;
    if (method !== 'GET') writes.push({ path, method, csrf: request.headers()['x-office-csrf'], body });
    let response: unknown;
    if (path === '/api/benchmarks') {
      if (method === 'GET' && ++reads === 1 && options.failFirst) {
        await route.fulfill({ status: 503, contentType: 'application/json', body: JSON.stringify({ detail: '합성 보드 조회 실패' }) });
        return;
      }
      if (method === 'PUT') overview = { ...overview, registry: { sources: (body as unknown as BenchmarkRegistryInput).sources }, registry_hash: 'b'.repeat(64) };
      response = overview;
    } else if (path === '/api/benchmarks/ideas' && method === 'POST') {
      const input = body as unknown as BenchmarkIdeaInput;
      const idea = { id: 'idea-synthetic', title: input.title, source_url: input.source_url, source_id: input.source_id, creator_id: 'every', platform: 'instagram', fields: input.fields, target_platforms: input.target_platforms, angle: input.angle, state: 'candidate' as const, score: 0, outlier_band: 'unknown', blocked: ['primary_sources'], reasons: [], origin: 'benchmark', edit_hash: 'c'.repeat(64) };
      overview = { ...overview, ideas: [idea] };
      response = idea;
    } else if (path === '/api/benchmarks/research-packet' && method === 'POST') response = { text: preparedText, registry_hash: overview.registry_hash };
    else if (path === '/api/session') response = { csrf: 'benchmark-contract-token' };
    else if (path === '/api/dashboard') response = { articles: [], jobs: [], feeds: [], agents: [], events: [], tasks: [], budget: { cap_krw: 10000, spent_krw: 0, reserved_krw: 0, remaining_krw: 10000 }, window: { status: 'closed', authorized_end: '2026-10-01T00:00:00Z' }, provider: { model: 'synthetic', configured: false }, knowledge: {} };
    else if (path === '/api/jobs/summaries') response = { jobs: [] };
    else if (method !== 'GET') {
      await route.fulfill({ status: 500, contentType: 'application/json', body: JSON.stringify({ detail: 'Unexpected fixture write' }) });
      return;
    } else response = {};
    await route.fulfill({ contentType: 'application/json', body: JSON.stringify(response) });
  });
  return writes;
}

async function prepareResearch(page: Page) {
  const research = page.getByRole('region', { name: '세이지에게 조사 맡기기', exact: true });
  await research.getByRole('checkbox', { name: /every\._ai.*Instagram/ }).check();
  await research.getByRole('button', { name: '세이지 조사 요청문 준비', exact: true }).click();
  await expect(research.getByLabel('준비된 세이지 조사 요청문', { exact: true })).toHaveValue(preparedText);
  return research;
}

for (const width of [1440, 390]) test(`분야·출처·검색 필터는 쓰기 없이 동작하고 날짜와 접근성을 보존한다 ${width}px`, async ({ page }, testInfo) => {
  const writes = await boardHarness(page);
  await page.setViewportSize({ width, height: 950 });
  await page.goto('/benchmarks');
  const board = page.locator('section[aria-labelledby="benchmark-heading"]');
  await expect(board.getByRole('heading', { name: '회의록 프롬프트 실험', exact: true })).toBeVisible();
  await page.screenshot({ path: testInfo.outputPath(`benchmark-${width}.png`) });
  expect((await board.getByRole('button', { name: 'AI 활용', exact: true }).boundingBox())!.y).toBeLessThan(900);
  await expect(board.getByRole('heading', { name: '미래 날짜가 있는 자료', exact: true })).not.toBeVisible();
  await board.getByRole('button', { name: 'AI 활용', exact: true }).focus();
  await page.keyboard.press('Enter');
  await board.getByLabel('출처 플랫폼', { exact: true }).selectOption('instagram');
  await board.getByLabel('소식·크리에이터 검색', { exact: true }).fill('회의록');
  await expect(board.getByRole('heading', { name: '회의록 프롬프트 실험', exact: true })).toBeVisible();
  await expect(board.getByRole('heading', { name: '공부 루틴을 기록하는 방법', exact: true })).toHaveCount(0);
  await board.getByLabel('소식·크리에이터 검색', { exact: true }).fill('없는 결과');
  await expect(board.getByRole('heading', { name: '현재 필터에 맞는 소식이 없어요', exact: true })).toBeVisible();
  await board.getByRole('button', { name: '필터 초기화', exact: true }).click();
  await expect(board.getByRole('heading', { name: '공부 루틴을 기록하는 방법', exact: true })).toBeVisible();
  const search = board.getByLabel('소식·크리에이터 검색', { exact: true });
  expect((await search.boundingBox())!.height).toBeGreaterThanOrEqual(44);
  expect(await page.evaluate(() => document.documentElement.scrollWidth <= innerWidth)).toBe(true);
  const audit = await new AxeBuilder({ page }).include('section[aria-labelledby="benchmark-heading"]').withTags(['wcag2a', 'wcag2aa', 'wcag21aa']).analyze();
  expect(audit.violations.filter(row => row.impact === 'critical' || row.impact === 'serious')).toEqual([]);
  expect(writes).toEqual([]);
});

test('출처 편집은 읽어 온 등록 해시로 PUT 한 번만 보내고 다른 출처를 보존한다', async ({ page }) => {
  const writes = await boardHarness(page);
  await page.goto('/benchmarks');
  await page.getByText('경쟁사 등록·수집 상태 관리', { exact: false }).click();
  await page.getByRole('button', { name: '등록 편집 · every._ai', exact: true }).click();
  await page.getByLabel('크리에이터 이름', { exact: true }).fill('every._ai 검토 목록');
  await page.getByRole('button', { name: '등록 정보 저장', exact: true }).click();
  await expect(page.getByText(/경쟁사 등록 정보를 저장했습니다/)).toBeVisible();
  expect(writes).toHaveLength(1);
  expect(writes[0]).toMatchObject({ path: '/api/benchmarks', method: 'PUT', csrf: 'benchmark-contract-token', body: { expected_hash: initialHash } });
  const saved = writes[0].body as unknown as BenchmarkRegistryInput;
  expect(saved.sources.find(source => source.id === 'every-ig')?.name).toBe('every._ai 검토 목록');
  expect(saved.sources.find(source => source.id === 'success-yt')).toEqual(initialOverview().registry.sources[1]);
});

test('자동 수집 없는 Instagram도 실제 게시물 URL과 새 관점을 후보로 저장한다', async ({ page }) => {
  const writes = await boardHarness(page);
  await page.setViewportSize({ width: 390, height: 900 });
  await page.goto('/benchmarks');
  await page.getByText('경쟁사 등록·수집 상태 관리', { exact: false }).click();
  await page.getByRole('button', { name: '원문에서 아이디어 만들기 · every._ai', exact: true }).click();
  const editor = page.getByRole('region', { name: '내 콘텐츠의 관점으로 다듬기', exact: true });
  const url = editor.getByLabel(/확인한 게시물의 원문 주소/);
  await expect(url).toHaveValue('');
  await url.fill('https://www.instagram.com/p/manual-synthetic/');
  await editor.getByLabel('후보 제목', { exact: true }).fill('내 회의록으로 프롬프트 검증하기');
  const angle = editor.getByLabel('내가 더할 관점', { exact: true });
  await expect(angle).toHaveAttribute('maxlength', '1000');
  await angle.fill('같은 입력 자료로 결과와 실패 조건을 직접 비교한다.');
  await editor.getByRole('checkbox', { name: 'YouTube', exact: true }).check();
  await editor.getByRole('button', { name: '후보 아이디어 저장', exact: true }).click();
  await expect(page.getByText(/1차 근거 미확인 상태이며/)).toBeVisible();
  expect(writes).toHaveLength(1);
  expect(writes[0]).toMatchObject({ path: '/api/benchmarks/ideas', method: 'POST', body: { title: '내 회의록으로 프롬프트 검증하기', source_url: 'https://www.instagram.com/p/manual-synthetic/', source_id: 'every-ig', fields: ['AI 활용', '업무 자동화'], target_platforms: ['youtube'], expected_hash: initialHash } });
  expect(writes[0].body).not.toHaveProperty('operator_verified');
  expect(writes[0].body).not.toHaveProperty('primary_sources');
  await page.getByRole('button', { name: /^저장 아이디어/ }).click();
  await expect(page.getByRole('heading', { name: '내 회의록으로 프롬프트 검증하기', exact: true })).toBeVisible();
  await expect(page.getByText('Instagram 출처 · 후보 아이디어', { exact: true })).toBeVisible();
  await expect(page.getByText('게시 대상: YouTube', { exact: true })).toBeVisible();
});

test('전체 조건의 요청문은 준비 POST만 만들고 세이지 대화 검토가 자동 접수하지 않는다', async ({ page }) => {
  const writes = await boardHarness(page);
  await page.goto('/benchmarks');
  const research = await prepareResearch(page);
  expect(writes).toHaveLength(1);
  expect(writes[0]).toMatchObject({ path: '/api/benchmarks/research-packet', method: 'POST', body: { source_ids: ['every-ig'], fields: [], platforms: [], expected_hash: initialHash } });
  await research.getByRole('button', { name: '세이지 조사 요청문 검토', exact: true }).click();
  const dialog = page.getByRole('dialog', { name: '세이지에게 업무 요청', exact: true });
  await expect(dialog).toBeVisible();
  await expect(dialog.getByLabel('맡길 업무', { exact: true })).toHaveValue(preparedText);
  await expect(dialog.getByRole('button', { name: '실제 비서에게 보내기', exact: true })).toBeEnabled();
  expect(writes.map(write => write.path)).toEqual(['/api/benchmarks/research-packet']);
});

test('세이지 요청문 검토가 기존 루미 초안의 본문과 배정 대상을 덮어쓰지 않는다', async ({ page }) => {
  const writes = await boardHarness(page);
  await page.goto('/benchmarks');
  const firstResearch = await prepareResearch(page);
  await firstResearch.getByRole('button', { name: '세이지 조사 요청문 검토', exact: true }).click();
  await page.getByRole('dialog').getByRole('button', { name: '닫기', exact: true }).click();
  await page.getByRole('button', { name: '루미와 대화하기', exact: true }).click();
  const lumi = page.getByRole('dialog', { name: '루미와 대화', exact: true });
  await lumi.getByLabel('맡길 업무', { exact: true }).fill('기존 루미에게 맡길 업무 초안');
  await lumi.getByRole('button', { name: '닫기', exact: true }).click();
  const research = await prepareResearch(page);
  await research.getByRole('button', { name: '세이지 조사 요청문 검토', exact: true }).click();
  await expect(lumi).toBeVisible();
  await expect(lumi.getByLabel('맡길 업무', { exact: true })).toHaveValue('기존 루미에게 맡길 업무 초안');
  await expect(lumi.getByText(/기존 업무와 입력·배정 대상을 보존했습니다/)).toBeVisible();
  expect(writes.map(write => write.path)).toEqual(['/api/benchmarks/research-packet', '/api/benchmarks/research-packet']);
});

test('조회 실패는 재시도로 복구하고 빈 소식·수동 미연동·수집 실패를 구분한다', async ({ page }) => {
  const writes = await boardHarness(page, { failFirst: true, empty: true });
  await page.goto('/benchmarks');
  await expect(page.getByRole('alert').filter({ hasText: '합성 보드 조회 실패' })).toBeVisible();
  const retry = page.getByRole('button', { name: '보드 다시 불러오기', exact: true });
  await retry.focus(); await page.keyboard.press('Enter');
  await expect(page.getByRole('heading', { name: '아직 수집한 소식이 없어요', exact: true })).toBeVisible();
  await page.getByText('경쟁사 등록·수집 상태 관리', { exact: false }).click();
  await expect(page.getByText('합성 RSS 연결 실패', { exact: true })).toBeVisible();
  await expect(page.getByText(/Instagram 자동 수집 미연동/)).toBeVisible();
  await expect(page.getByRole('button', { name: '공개 소식 수집 요청', exact: true })).toBeDisabled();
  expect(writes).toEqual([]);
});
