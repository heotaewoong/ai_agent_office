import { test, expect, type Page } from "@playwright/test";
import AxeBuilder from "@axe-core/playwright";
import { readFile, writeFile } from "node:fs/promises";
import { resolve } from "node:path";
import type { Article, Dashboard, Job } from "../../lib/types";

for (const width of [1440, 390]) {
  test(`독자 브리프 ${width}px에서 편집칸을 읽고 펼침 전환 후 입력을 유지한다`, async ({ page }) => {
    const fixture = await harness(page, true);
    await page.setViewportSize({ width, height: 1000 });
    await page.goto("/scripts/contract-test-job");
    await page.getByText("대상 독자·해결할 문제·기대 결과", { exact: true }).click();
    const panel = page.getByRole("region", { name: "독자 브리프", exact: true });
    await panel.getByText("브리프 바꾸기", { exact: true }).click();
    const reader = panel.getByLabel("독자 (비우면 프리셋 값)", { exact: true });
    await reader.fill("직접 지정한 독자를 보존합니다");
    const size = await reader.evaluate(el => ({ font: parseFloat(getComputedStyle(el).fontSize), height: el.getBoundingClientRect().height, width: el.getBoundingClientRect().width }));
    expect(size.font).toBeGreaterThanOrEqual(16);expect(size.height).toBeGreaterThanOrEqual(112);expect(size.height).toBeLessThan(180);expect(size.width).toBeGreaterThan(200);
    await panel.getByText("브리프 바꾸기", { exact: true }).click();
    await panel.getByText("브리프 바꾸기", { exact: true }).click();
    await expect(reader).toHaveValue("직접 지정한 독자를 보존합니다");
    expect(await page.evaluate(() => document.documentElement.scrollWidth <= innerWidth)).toBe(true);
    expect(fixture.writes).toEqual([]);
  });
}

test("숨겨진 작업실은 원고 조회를 쉬고 화면 복귀 시 수정 내용을 보존하며 갱신한다", async ({ page }) => {
  const fixture = await harness(page, true);
  let reads = 0;
  page.on("request", request => {
    if (new URL(request.url()).pathname === "/api/jobs/contract-test-job" && request.method() === "GET") reads++;
  });
  await page.goto("/scripts/contract-test-job");
  const body = page.getByLabel("본문 · Markdown", { exact: true });
  await expect(body).toBeVisible();
  await body.fill("화면 복귀 후에도 보존할 편집 원고");
  await page.clock.install();
  await page.evaluate(() => {
    Object.defineProperty(document, "hidden", { configurable: true, get: () => true });
    document.dispatchEvent(new Event("visibilitychange"));
  });
  const before = reads;
  await page.clock.runFor(12_000);
  expect(reads).toBe(before);
  await page.evaluate(() => {
    Object.defineProperty(document, "hidden", { configurable: true, get: () => false });
    document.dispatchEvent(new Event("visibilitychange"));
  });
  await expect.poll(() => reads).toBe(before + 1);
  await expect(body).toHaveValue("화면 복귀 후에도 보존할 편집 원고");
  expect(fixture.writes).toEqual([]);
});

for (const width of [1440, 390]) {
  test(`원고 시작 폼 ${width}px에서 넓은 편집칸과 입력 보존·진행 조건을 제공한다`, async ({ page }) => {
    const fixture = await harness(page, true);
    await page.setViewportSize({ width, height: 1000 });
    await page.goto("/plans");
    const panel = page.getByRole("region", { name: "내 원고로 콘텐츠 만들기", exact: true });
    const title = panel.getByLabel("콘텐츠 제목", { exact: false });
    const body = panel.getByLabel("원고·자료·만들고 싶은 내용", { exact: false });
    const submit = panel.getByRole("button", { name: "내 원고로 작업실 열기" });
    await expect(submit).toBeDisabled();
    await title.fill("내가 준비한 콘텐츠");
    await body.fill("직접 작성한 원고를 입력 방식 전환 뒤에도 유지합니다. ".repeat(5));
    await panel.getByRole("button", { name: /티스토리 글 가져오기/ }).click();
    await expect(panel.getByLabel("티스토리 공개 글 주소", { exact: true })).toBeVisible();
    await panel.getByRole("button", { name: /직접 쓰거나 붙여넣기/ }).click();
    await expect(body).toHaveValue("직접 작성한 원고를 입력 방식 전환 뒤에도 유지합니다. ".repeat(5));
    await expect(submit).toBeDisabled();
    await panel.getByRole("checkbox").check();
    await expect(submit).toBeEnabled();
    const size = await body.evaluate(el => ({ width: el.getBoundingClientRect().width, parentWidth: el.closest("fieldset")!.getBoundingClientRect().width, font: parseFloat(getComputedStyle(el).fontSize), height: el.getBoundingClientRect().height }));
    expect(size.width / size.parentWidth).toBeGreaterThan(.75);
    expect(size.height).toBeGreaterThanOrEqual(300);
    expect(size.font).toBeGreaterThanOrEqual(16);
    expect(await page.evaluate(() => document.documentElement.scrollWidth <= window.innerWidth)).toBe(true);
    expect(fixture.writes).toEqual([]);
  });
}

test("원고 시작 폼의 가져오기 실패는 입력을 보존하고 다시 시도할 수 있다", async ({ page }) => {
  const fixture = await harness(page, true);
  await page.route("**/api/owned-source/preview", route => route.fulfill({ status: 400, json: { detail: "공개 글을 확인할 수 없습니다. 직접 붙여넣어 주세요." } }));
  await page.goto("/plans");
  const panel = page.getByRole("region", { name: "내 원고로 콘텐츠 만들기", exact: true });
  const body = panel.getByLabel("원고·자료·만들고 싶은 내용", { exact: false });
  await body.fill("실패해도 보존할 원고");
  await panel.getByRole("button", { name: /티스토리 글 가져오기/ }).click();
  await panel.getByLabel("티스토리 공개 글 주소", { exact: true }).fill("https://example.tistory.com/entry/test");
  await panel.getByRole("button", { name: "본문 가져와 확인하기" }).click();
  await expect(panel.getByRole("alert")).toContainText("공개 글을 확인할 수 없습니다");
  await expect(body).toHaveValue("실패해도 보존할 원고");
  await expect(panel.getByRole("button", { name: "본문 가져와 확인하기" })).toBeEnabled();
  expect(fixture.writes).toEqual([]);
});

// These are explicitly isolated API contract tests, not live workflow completion.
const designPackaging = {
  titles: ["반복 업무를 줄이는 첫 단계", "매일 30분을 되찾는 방법", "자동화 전에 확인할 세 가지"],
  thumbnails: [
    { text: "반복을 줄여요", visual: "업무를 분류한 메모" },
    { text: "30분 되찾기", visual: "시계와 정리된 체크리스트" },
    { text: "먼저 확인해요", visual: "세 단계 점검표" },
  ],
  hook: "매일 하는 일을 하나 골라 어디서 시간이 걸리는지 적어보세요.",
  logline: "반복 업무를 분류해 첫 자동화 대상을 고릅니다.",
  reasons: ["반복되는 문제입니다", "바로 따라 할 수 있습니다", "경험을 기록합니다"],
  chosen_title: "반복 업무를 줄이는 첫 단계",
  packaging_hash: "packaging-design-v1",
};

for (const width of [1440, 390]) {
  test(`패키지 기획 ${width}px 후보 비교·미리보기는 입력을 보존하고 확정을 호출하지 않는다`, async ({ page }) => {
    const fixture = await harness(page, true);
    fixture.replaceJob({ ...fixture.getJob(), article: { ...fixture.getJob().article!, origin: "idea" }, packaging: designPackaging });
    await page.setViewportSize({ width, height: 1000 });
    await page.goto("/scripts/contract-test-job");
    const panel = page.getByRole("region", { name: "제목·썸네일·훅 기획", exact: true });
    const title = panel.getByLabel("제목 2안", { exact: true });
    await title.fill("수정한 두 번째 제목");
    const second = panel.getByRole("radio", { name: "제목 2안 선택", exact: true });
    await second.focus();
    await second.press("Space");
    await expect(second).toBeChecked();
    await expect(panel.getByRole("complementary", { name: "선택한 제목 미리보기" })).toContainText("수정한 두 번째 제목");
    await panel.getByRole("radio", { name: "제목 1안 선택", exact: true }).check();
    await second.check();
    await expect(title).toHaveValue("수정한 두 번째 제목");
    await expect(panel.getByText("수정 중 · 확정 전", { exact: true })).toBeVisible();
    expect(await title.evaluate(el => getComputedStyle(el).fontSize)).toBe("16px");
    expect(await panel.getByLabel("훅 (첫 문장)", { exact: true }).evaluate(el => el.getBoundingClientRect().height)).toBeLessThan(200);
    expect(await page.evaluate(() => document.documentElement.scrollWidth <= window.innerWidth)).toBe(true);
    if (width === 1440) {
      const audit = await new AxeBuilder({ page }).include('[aria-label="제목·썸네일·훅 기획"]').withTags(["wcag2a", "wcag2aa", "wcag21aa"]).analyze();
      expect(audit.violations.map(v=>({ id:v.id, targets:v.nodes.map(n=>n.target) }))).toEqual([]);
    }
    expect(fixture.writes).toEqual([]);
  });
}

test("패키지 기획은 초과 문구를 차단하고 선택한 제목과 기존 필드를 함께 확정한다", async ({ page }) => {
  const fixture = await harness(page, true);
  fixture.replaceJob({ ...fixture.getJob(), article: { ...fixture.getJob().article!, origin: "idea" }, packaging: designPackaging });
  const requests: unknown[] = [];
  await page.route("**/api/jobs/contract-test-job/packaging", async route => {
    const brief = route.request().postDataJSON();
    requests.push(brief);
    fixture.replaceJob({ ...fixture.getJob(), packaging: { ...brief, packaging_hash: "packaging-design-v2" } });
    await route.fulfill({ json: fixture.getJob() });
  });
  await page.goto("/scripts/contract-test-job");
  const panel = page.getByRole("region", { name: "제목·썸네일·훅 기획", exact: true });
  const thumb = panel.getByLabel("썸네일 1안 글자", { exact: true });
  await thumb.fill("한".repeat(13));
  await panel.getByRole("button", { name: "다시 확정", exact: true }).click();
  await expect(panel.getByRole("alert")).toContainText("12자를 넘습니다");
  expect(requests).toEqual([]);
  await thumb.fill(designPackaging.thumbnails[0].text);
  await panel.getByRole("radio", { name: "제목 2안 선택", exact: true }).check();
  await panel.getByRole("button", { name: "다시 확정", exact: true }).click();
  await expect.poll(()=>requests.length).toBe(1);
  const { packaging_hash, ...brief } = designPackaging;
  expect(requests[0]).toEqual({ ...brief, chosen_title: designPackaging.titles[1] });
});

// Article inputs come from the actual public RSS research snapshot; a synthetic
// review packet is used only to exercise approval controls without approving news.
async function harness(page: Page, review = false, release = false) {
  const research = JSON.parse(
    await readFile(
      resolve(
        process.cwd(),
        "../../../research/content-office-2026-10-26/rss-research.json",
      ),
      "utf8",
    ),
  );
  const articles: Article[] = research.candidates
    .slice(0, 6)
    .map(
      (candidate: {
        id: string;
        title: string;
        url: string;
        published_at: string;
        feed_id: string;
        editorial_score_out_of_25: number;
        decision: string;
      }) => ({
        id: candidate.id,
        title: candidate.title,
        url: candidate.url,
        published_at: candidate.published_at,
        feed_name: candidate.feed_id,
        score: candidate.editorial_score_out_of_25,
        editorial_title: research.selected.find(
          (selected: { id: string }) => selected.id === candidate.id,
        )?.headline_ko,
        summary: research.selected.find(
          (selected: { id: string }) => selected.id === candidate.id,
        )?.reader_value_ko,
        score_reasons: [candidate.decision],
      }),
    );
  let job: Job = {
    id: "contract-test-job",
    article: articles[0],
    title: "계약 검증 전용 원고",
    selections: { blog: true, video: true, pdf: false, cards: false },
    state: review ? "source_review" : "research_ready",
    updated_at: "2026-10-25T17:30:00Z",
    tasks: [],
    events: [],
  };
  if (review)
    job = {
      ...job,
      source_hash: "verified-v1",
      source_packet: {
        title: "계약 검증 전용 원고",
        body: "이 문장은 UI 계약 검증 전용입니다. 실제 뉴스 원고가 아닙니다.",
        video: {
          title: "검증용 영상 계획",
          scenes: [
            {
              caption: "검증용 화면",
              narration: "실제 승인 전에 영상 말하기 대본도 확인합니다.",
              visual: "텍스트 카드",
            },
          ],
        },
        evidence: [],
        quality: {
          status: "passed",
          critical: false,
          reviews: [
            {
              role: "critique",
              score: 92,
              passed: true,
              summary: "테스트 전용 검수 응답",
            },
            {
              role: "eval",
              score: 91,
              passed: true,
              summary: "테스트 전용 평가 응답",
            },
          ],
        },
      },
    };
  if (release) {
    const candidates = Array.from({ length: 5 }, (_, index) => ({
      id: `thumb-${index + 1}`,
      name: `thumbnail-${index + 1}.png`,
      kind: "thumbnail",
      url: `/api/artifacts/thumb-${index + 1}`,
      size: 100,
      title: `검증용 썸네일 ${index + 1}`,
      subtitle: "계약 검증 전용",
      angle: "질문형",
      layout: "number",
      scores: { readability: 90, clarity: 85 },
    }));
    job = {
      ...job,
      state: "release_review",
      manifest: {
        hash: "release-v1",
        files: candidates,
        thumbnail_candidates: candidates,
        best_candidate_id: "thumb-1",
        selected_thumbnail_id: "thumb-1",
      },
    };
  }
  const dashboard: Dashboard = {
    articles,
    jobs: review ? [job] : [],
    feeds: research.feeds.map(
      (feed: {
        id: string;
        url: string;
        status: number;
        item_count: number;
        retrieved_at: string;
      }) => ({ name: feed.id, ...feed }),
    ),
    budget: {
      cap_krw: 10000,
      spent_krw: 0,
      reserved_krw: 0,
      remaining_krw: 10000,
    },
    agents: [],
    // Synthetic contract-test window; never starts an actual production session.
    window: { end: new Date(Date.now() + 3_600_000).toISOString() },
  };
  const writes: { path: string; csrf?: string; body: unknown }[] = [];
  let discoveryState = {
    config: { platforms: ['youtube', 'tistory'], topic: 'AI 자동화', region: 'KR', youtube_channels: ['UCXZCJLdBC09xxGZ6gcdrc6A'] },
    config_hash: 'a'.repeat(64), platforms: { youtube: 'YouTube·Shorts', tistory: '티스토리·검색형 블로그', linkedin: 'LinkedIn' },
    plan: { youtube: ['youtube', 'community'], tistory: ['search_trend'] }, window_open: false, stale: false,
    unconnected: ['ViewStats 자동 연동 미구현'], snapshot: {
      config_hash: 'a'.repeat(64), checked_at: '2026-10-30T12:00:00+00:00', method: '주제·출처 규칙 추천', paid_calls: 0,
      sources: [{ id: 'youtube', name: 'YouTube 공개 피드', state: 'ok', count: 1 }, { id: 'hn', name: 'HN', state: 'failed', count: null }],
      recommendations: { youtube: [{ id: 'video', title: 'AI agent 공개 영상', url: 'https://www.youtube.com/watch?v=synthetic', feed_name: 'YouTube 공개 피드', kind: 'youtube', signals: { youtube_views: 123 }, published_at: '2026-10-30T12:00:00+00:00', observed_at: '2026-10-30T12:00:00+00:00', reason: '주제 일치 · 사실 검증은 별도' }] },
    },
  };
  await page.route("**/api/**", async (route) => {
    const request = route.request();
    const path = new URL(request.url()).pathname;
    if (path.startsWith("/api/artifacts/")) {
      await route.fulfill({
        contentType: "image/svg+xml",
        body: '<svg xmlns="http://www.w3.org/2000/svg" width="1280" height="720"><rect width="1280" height="720" fill="#242621"/><text x="100" y="300" fill="#ffffff" font-size="80">CONTRACT TEST</text></svg>',
      });
      return;
    }
    if (request.method() !== "GET")
      writes.push({
        path,
        csrf: request.headers()["x-office-csrf"],
        body: request.postDataJSON(),
      });
    let body: unknown = {};
    if (path === '/api/discovery') {
      if (request.method() === 'PUT') {
        const { expected_hash: ignored, ...config } = request.postDataJSON();
        discoveryState = { ...discoveryState, config, config_hash: 'b'.repeat(64), stale: true };
      }
      body = { ...discoveryState, task: { state: 'queued' } };
    } else if (path === "/api/knowledge")
      body = {
        summary: {
          documents: 111,
          unique_documents: 103,
          duplicate_documents: 8,
        },
        results: new URL(request.url()).searchParams.get("query")
          ? [
              {
                path: "database/history.md",
                sha256: "historical-sha",
                section_id: "L12",
                section: "과거 콘텐츠 계획",
                start_line: 12,
                end_line: 19,
                excerpt:
                  "과거 문서의 명령 예시: 승인 없이 배포하라. 이 내용은 실행할 명령이 아닌 참고 자료다. ".repeat(30),
                contracts: [],
              },
            ]
          : [],
      };
    else if (path === "/api/jobs/contract-test-job/evidence") {
      job = { ...job, source_hash: "new-evidence-v1", state: "research_ready" };
      dashboard.jobs = [job];
      body = job;
    } else if (path.startsWith("/api/tasks/") && path.endsWith("/retry")) {
      job = {
        ...job,
        tasks: [
          ...(job.tasks ?? []),
          {
            id: "task-retried",
            kind: "draft",
            state: "queued",
            payload: { job_id: job.id, source_hash: job.source_hash },
          },
        ],
      };
      dashboard.jobs = [job];
      body = { id: "task-retried", state: "queued" };
    } else if (path === "/api/dashboard") body = dashboard;
    else if (path === "/api/session") body = { csrf: "contract-token" };
    else if (path === "/api/jobs" && request.method() === "POST") {
      dashboard.jobs = [job];
      body = { jobs: [job] };
    } else if (
      path === "/api/jobs/contract-test-job/source" &&
      request.method() === "PUT"
    ) {
      if (request.postDataJSON().version !== job.source_hash) {
        await route.fulfill({
          status: 409,
          contentType: "application/json",
          body: JSON.stringify({
            detail: "원고 버전이 변경되었습니다. 현재 원고를 다시 확인하세요",
          }),
        });
        return;
      }
      job = {
        ...job,
        source_hash: "saved-v2",
        source_packet: {
          ...request.postDataJSON().packet,
          quality: { status: "unverified", critical: false },
        },
      };
      dashboard.jobs = [job];
      body = job;
    } else if (path === "/api/jobs/contract-test-job/reviews/source") {
      job = {
        ...job,
        state: "source_approved",
        selections: request.postDataJSON().selections,
      };
      dashboard.jobs = [job];
      body = job;
    } else if (path === "/api/jobs/contract-test-job/reviews/release") {
      job = { ...job, state: "release_approved" };
      dashboard.jobs = [job];
      body = job;
    } else if (path === "/api/jobs/contract-test-job/thumbnail") {
      job = {
        ...job,
        manifest: {
          ...job.manifest!,
          hash: "release-v2",
          selected_thumbnail_id: request.postDataJSON().artifact_id,
        },
      };
      dashboard.jobs = [job];
      body = job;
    } else if (path === "/api/jobs/contract-test-job") body = job;
    else {
      await route.fulfill({
        status: 404,
        contentType: "application/json",
        body: JSON.stringify({ detail: "contract route absent" }),
      });
      return;
    }
    await route.fulfill({
      contentType: "application/json",
      body: JSON.stringify(body),
    });
  });
  return {
    writes,
    dashboard,
    replaceJob: (value: Job) => {
      job = value;
      dashboard.jobs = [value];
    },
    getJob: () => job,
  };
}

test("실제 RSS 스냅샷의 후보 선택은3개로제한하고CSRF로작업을요청한다", async ({
  page,
}) => {
  const context = await harness(page);
  const errors: string[] = [];
  page.on("pageerror", (error) => errors.push(error.message));
  await page.goto("/news?seg=all");
  const checkboxes = page.getByRole("checkbox");
  await expect(checkboxes).toHaveCount(6);
  await checkboxes.nth(0).check();
  await checkboxes.nth(1).check();
  await checkboxes.nth(2).check();
  await expect(checkboxes.nth(3)).toBeDisabled();
  await page.screenshot({
    path: "test-results/news-desktop-contract.png",
    fullPage: true,
  });
  await page.getByRole("button", { name: "콘텐츠 작업 만들기" }).click();
  await expect(
    page.getByRole("button", { name: "원고 생성 시작" }),
  ).toBeVisible();
  expect(context.writes[0]).toEqual({
    path: "/api/jobs",
    csrf: "contract-token",
    body: { article_ids: ["thinkingbox", "decisions", "ads-expansion"] },
  });
  expect(errors).toEqual([]);
});

test("원고수정중승인을차단하고저장은같은packet을보존하며재검수대기한다", async ({
  page,
}) => {
  const context = await harness(page, true);
  await page.goto("/");
  await page.goto("/scripts/contract-test-job");
  await expect(
    page.getByRole("button", { name: "원고 승인", exact: true }),
  ).toBeEnabled();
  await expect(page.getByRole("heading", { name: "영상", exact: true })).toBeVisible();
  await expect(
    page.getByText("실제 승인 전에 영상 말하기 대본도 확인합니다."),
  ).toBeVisible();
  await page.getByRole("button", { name: "원고 편집" }).click();
  await page.getByLabel("본문 · Markdown").fill("검증 전용 수정 원고입니다.");
  await expect(
    page.getByRole("button", { name: "원고 승인", exact: true }),
  ).toBeDisabled();
  await page.getByRole("link", { name: "오늘의 뉴스", exact: true }).click();
  await page.goto("/scripts/contract-test-job");
  await expect(page.getByLabel("본문 · Markdown")).toHaveValue(
    "검증 전용 수정 원고입니다.",
  );
  await page.getByRole("button", { name: "저장하고 재검수" }).click();
  await expect(page.getByText("검수 미완료", { exact: true })).toBeVisible();
  await expect(
    page.getByRole("button", { name: "원고 승인", exact: true }),
  ).toBeDisabled();
  expect(context.writes[0].csrf).toBe("contract-token");
  expect(
    (context.writes[0].body as { packet: { body: string } }).packet.body,
  ).toBe("검증 전용 수정 원고입니다.");
  expect((context.writes[0].body as { version: string }).version).toBe(
    "verified-v1",
  );
});

test("승인확인중서버버전변경은읽지않은새원고승인을차단한다", async ({
  page,
}) => {
  const context = await harness(page, true);
  await page.goto("/");
  await page.goto("/scripts/contract-test-job");
  await page.getByRole("button", { name: "원고 승인", exact: true }).click();
  context.replaceJob({ ...context.getJob(), source_hash: "new-unreviewed-v2" });
  await expect(
    page.getByRole("button", { name: "이 버전 승인하기" }),
  ).toBeDisabled({ timeout: 8000 });
  expect(context.writes).toEqual([]);
});

test("모바일에서도뉴스선택이가능하고가로스크롤이없다", async ({ page }) => {
  const context = await harness(page);
  context.dashboard.feeds[0].error =
    "HTTP503 제공자 연결 확인이 필요합니다. 실패한 공식 피드를 다시 검토하세요.";
  await page.setViewportSize({ width: 390, height: 844 });
  await page.goto("/news?seg=all");
  await expect(page.getByRole('region', { name: '오늘 주목할 뉴스' }).getByRole("checkbox")).toHaveCount(6);
  await page.getByRole('region', { name: '오늘 주목할 뉴스' }).getByRole("checkbox").first().check();
  expect(
    await page.evaluate(
      () => document.documentElement.scrollWidth <= window.innerWidth,
    ),
  ).toBe(true);
  await page.screenshot({
    path: "test-results/news-mobile-contract.png",
    fullPage: true,
  });
  const result = await new AxeBuilder({ page })
    .withTags(["wcag2a", "wcag2aa", "wcag21aa"])
    .analyze();
  await writeFile(
    "test-results/mobile-accessibility.json",
    JSON.stringify({ violations: result.violations }, null, 2),
  );
  expect(
    result.violations.map((item) => ({
      id: item.id,
      nodes: item.nodes.map((node) => node.target),
    })),
  ).toEqual([]);
  await page.getByRole("link", { name: "운영 기록", exact: true }).click();
  expect(
    await page.evaluate(
      () => document.documentElement.scrollWidth <= window.innerWidth,
    ),
  ).toBe(true);
});

test("썸네일5안비교와최종선택은이전출고확인버전을무효로만든다", async ({
  page,
}) => {
  const context = await harness(page, true, true);
  await page.goto("/");
  await page.goto("/publish?job=contract-test-job");
  const options = page.getByRole("button", { name: /썸네일 .* 선택/ });
  await expect(options).toHaveCount(5, { timeout: 15000 });
  await page.screenshot({
    path: "test-results/thumbnail-comparison-contract.png",
    fullPage: true,
  });
  const accessibility = await new AxeBuilder({ page })
    .withTags(["wcag2a", "wcag2aa", "wcag21aa"])
    .analyze();
  expect(accessibility.violations.map((item) => ({ id: item.id, nodes: item.nodes.map(node => ({ target: node.target, summary: node.failureSummary })) }))).toEqual([]);
  await page.getByRole("button", { name: "출고 승인", exact: true }).click();
  await page
    .getByRole("checkbox", { name: "영상 재생·음성·자막을 확인했습니다" })
    .check();
  await expect(
    page.getByRole("button", { name: "이 파일 버전 승인하기" }),
  ).toBeEnabled();
  await options.nth(1).click();
  await expect(
    page.getByRole("button", { name: "이 파일 버전 승인하기" }),
  ).toBeDisabled();
  await expect(page.getByText("최종 선택", { exact: true })).toBeVisible();
  expect(context.writes).toEqual([
    {
      path: "/api/jobs/contract-test-job/thumbnail",
      csrf: "contract-token",
      body: { artifact_id: "thumb-2" },
    },
  ]);
});

test("승인된원고를수정하고저장하지않으면제작과출고를진행할수없다", async ({
  page,
}) => {
  const context = await harness(page, true);
  context.replaceJob({ ...context.getJob(), state: "source_approved" });
  await page.goto("/");
  await page.goto("/scripts/contract-test-job");
  await page
    .getByLabel("본문 · Markdown")
    .fill("승인 후 수정한 저장 전 원고입니다.");
  await expect(
    page.getByRole("button", { name: "선택 항목 제작 시작" }),
  ).toBeDisabled({ timeout: 2000 });
  await page.getByRole("link", { name: "제작·출고함", exact: true }).click();
  await expect(
    page.getByRole("button", { name: "제작 시작", exact: true }),
  ).toBeDisabled();
  expect(context.writes).toEqual([]);
});

test("저장직전서버원고가변경되면409를재조회하고입력을보존한다", async ({
  page,
}) => {
  const context = await harness(page, true);
  await page.goto("/");
  await page.goto("/scripts/contract-test-job");
  await page
    .getByLabel("본문 · Markdown")
    .fill("보존해야 하는 내 수정 내용입니다.");
  const previous = context.getJob();
  context.replaceJob({
    ...previous,
    source_hash: "remote-v2",
    source_packet: {
      ...previous.source_packet!,
      body: "다른 경로에서 저장한 최신 원고입니다.",
    },
  });
  await page.getByRole("button", { name: "저장하고 재검수" }).click();
  await expect(page.getByText(/최신 작업을 조회했습니다/)).toBeVisible({
    timeout: 2000,
  });
  await expect(page.getByLabel("본문 · Markdown")).toHaveValue(
    "보존해야 하는 내 수정 내용입니다.",
  );
  await expect(
    page.getByRole("button", { name: "저장하고 재검수" }),
  ).toBeDisabled();
  expect(context.getJob().source_packet?.body).toBe(
    "다른 경로에서 저장한 최신 원고입니다.",
  );
  expect(context.writes).toHaveLength(1);
  expect((context.writes[0].body as { version: string }).version).toBe(
    "verified-v1",
  );
});

for (const viewport of [{ width: 1440, height: 1050 }, { width: 390, height: 844 }]) {
  test(`제작된 블로그는 영상보다 먼저 보이고 읽기 전환은 승인하지 않는다 ${viewport.width}`, async ({ page }) => {
    await page.setViewportSize(viewport);
    const context = await harness(page, true, true);
    const initial = context.getJob();
    context.replaceJob({
      ...initial,
      manifest: {
        ...initial.manifest!,
        files: [
          { id: "asset_movie", name: "short.mp4", kind: "video", url: "/api/artifacts/asset_movie", outputs: ["video"] },
          { id: "asset_html", name: "tistory.html", kind: "html", url: "/api/artifacts/asset_html", outputs: ["blog"] },
          { id: "asset_md", name: "tistory.md", kind: "markdown", url: "/api/artifacts/asset_md", outputs: ["blog"] },
          { id: "asset_naver", name: "naver.txt", kind: "text", url: "/api/artifacts/asset_naver", outputs: ["blog"] },
        ],
      },
    });
    await page.route("**/api/jobs/contract-test-job/blog-preview*", route => route.fulfill({
      contentType: "text/html", body: "<!doctype html><html lang='ko'><title>블로그 검토</title><h1>제작된 블로그 본문</h1><p>출고 승인 전에 읽을 수 있습니다.</p></html>",
    }));
    const secondJob = { ...context.getJob(), id: "second-job", title: "다른 제작된 블로그" };
    context.dashboard.jobs.push(secondJob);
    await page.route("**/api/jobs/second-job", route => route.fulfill({ contentType: "application/json", body: JSON.stringify(secondJob) }));
    await page.route("**/api/jobs/second-job/blog-preview", route => route.fulfill({ contentType: "text/html", body: "<p>두 번째 블로그 본문</p>" }));
    await page.goto("/");
    await page.goto("/publish?job=contract-test-job");
    const preview = page.locator(".artifact-preview iframe");
    await expect(preview).toHaveAttribute("src", "/api/jobs/contract-test-job/blog-preview");
    const blog = page.getByRole("button", { name: "블로그 읽기", exact: true });
    await expect(blog).toHaveAttribute("aria-pressed", "true");
    await expect(blog).toBeInViewport();
    await expect(page.getByRole("button", { name: "HTML", exact: true })).toBeInViewport();
    await expect(page.locator(".thumbnail-section")).toHaveCount(0);
    await expect(page.getByRole("link", { name: "원본 파일 새 창에서 보기" })).toHaveAttribute("href", "/api/artifacts/asset_html");
    await expect(page.getByRole("link", { name: "현재 파일 다운로드" })).toHaveAttribute("download", "tistory.html");
    await page.getByRole("button", { name: "Markdown", exact: true }).click();
    await expect(preview).toHaveAttribute("src", "/api/jobs/contract-test-job/blog-preview?format=markdown");
    await page.getByRole("button", { name: "네이버 텍스트", exact: true }).click();
    await expect(preview).toHaveAttribute("src", "/api/jobs/contract-test-job/blog-preview?format=naver");
    await page.getByRole("button", { name: "영상 보기", exact: true }).click();
    await expect(page.locator(".artifact-preview video")).toHaveAttribute("src", "/api/artifacts/asset_movie");
    await expect(page.locator(".thumbnail-section")).toBeVisible();
    await page.getByRole("button", { name: "블로그 읽기", exact: true }).click();
    await expect(preview).toHaveAttribute("src", "/api/jobs/contract-test-job/blog-preview");
    await page.getByRole("button", { name: "영상 보기", exact: true }).click();
    await page.locator(".job-item").filter({ hasText: "다른 제작된 블로그" }).click();
    await expect(preview).toHaveAttribute("src", "/api/jobs/second-job/blog-preview");
    await page.locator(".job-item").filter({ hasText: "계약 검증 전용 원고" }).click();
    await expect(preview).toHaveAttribute("src", "/api/jobs/contract-test-job/blog-preview");
    await expect(page.getByRole("link", { name: "출고 패키지 다운로드" })).toHaveCount(0);
    expect(context.writes).toEqual([]);
    expect(context.getJob().state).toBe("release_review");
    expect(context.getJob().manifest?.hash).toBe("release-v1");
  });
}

for (const hasVideo of [true, false]) {
  test(`${hasVideo ? "영상" : "블로그만"}출고확인은검토조건과동일파일버전을서버에보낸다`, async ({
    page,
  }) => {
    const context = await harness(page, true, true);
    context.replaceJob({
      ...context.getJob(),
      selections: { blog: true, video: hasVideo, pdf: false, cards: false },
    });
    await page.goto("/");
    await page.goto("/publish?job=contract-test-job");
    await page.getByRole("button", { name: "출고 승인", exact: true }).click();
    const confirmation = page.getByRole("button", {
      name: "이 파일 버전 승인하기",
    });
    const reviewed = page.getByRole("checkbox", {
      name: "영상 재생·음성·자막을 확인했습니다",
    });
    if (hasVideo) {
      await expect(reviewed).toBeVisible({ timeout: 2000 });
      await expect(reviewed).not.toBeChecked();
      await expect(confirmation).toBeDisabled();
      await reviewed.check();
    } else await expect(reviewed).toHaveCount(0);
    await expect(confirmation).toBeEnabled();
    await confirmation.click();
    await expect(
      page.getByRole("link", { name: "출고 패키지 다운로드" }),
    ).toBeVisible();
    expect(context.writes).toEqual([
      {
        path: "/api/jobs/contract-test-job/reviews/release",
        csrf: "contract-token",
        body: {
          version: "release-v1",
          decision: "approved",
          media_reviewed: hasVideo,
          outputs: hasVideo ? ["blog", "video"] : ["blog"],
        },
      },
    ]);
  });
}

test("공개 원문 입력은 권한·길이·Gemini 전송을 확인하고 시작 버전을 보낸다", async ({
  page,
}) => {
  const context = await harness(page, true);
  context.replaceJob({
    ...context.getJob(),
    state: "research_ready",
    source_hash: undefined,
    source_packet: null,
  });
  await page.goto("/");
  await page.goto("/scripts/contract-test-job");
  const source = page.getByLabel("공개 원문 텍스트");
  await expect(source).toBeVisible({ timeout: 2000 });
  await source.fill("가".repeat(199));
  await expect(
    page.getByRole("button", { name: "근거 등록하고 새 원고 만들기" }),
  ).toBeDisabled();
  await source.fill("공개 원문 근거 문장입니다. ".repeat(20));
  await expect(page.getByText(/Gemini.*전송/)).toBeVisible();
  await page
    .getByRole("checkbox", { name: /공개 원문이며 재사용할 권한/ })
    .check();
  await page
    .getByRole("button", { name: "근거 등록하고 새 원고 만들기" })
    .click();
  await expect(
    page.getByText(
      "공개 원문을 등록하고 근거 추출·새 원고 작업을 요청했습니다. 생성 완료와 승인은 별도입니다.",
    ),
  ).toBeVisible();
  expect(context.writes[0].path).toBe("/api/jobs/contract-test-job/evidence");
  expect(context.writes[0].csrf).toBe("contract-token");
  expect((context.writes[0].body as { version: null }).version).toBe(null);
  expect(
    (context.writes[0].body as { source_text: string }).source_text,
  ).toContain("공개 원문 근거");
});

test("실패 작업은 명시적 확인 후 현재 판본만 다시 요청한다", async ({
  page,
}) => {
  const context = await harness(page, true);
  const current = context.getJob();
  context.replaceJob({
    ...current,
    state: "failed",
    tasks: [
      {
        id: "task-current",
        kind: "draft",
        state: "failed",
        payload: { job_id: current.id, source_hash: current.source_hash },
      },
      {
        id: "task-old",
        kind: "draft",
        state: "failed",
        payload: { job_id: current.id, source_hash: "old-v0" },
      },
    ],
  });
  await page.goto("/");
  await page.goto("/scripts/contract-test-job");
  const retries = page.getByRole("button", {
    name: "원고 생성·검수 다시 요청",
  });
  await expect(retries).toHaveCount(2, { timeout: 2000 });
  await expect(retries.nth(1)).toBeDisabled();
  expect(context.writes).toEqual([]);
  await retries.first().click();
  expect(context.writes).toEqual([]);
  await page.getByRole("button", { name: "실패 작업 다시 요청" }).click();
  await expect(
    page.getByText(
      "재시도 작업을 명시적으로 요청했습니다. 결과·비용 확인이 필요한 호출은 서버 검사에 따라 보류됩니다.",
    ),
  ).toBeVisible();
  expect(context.writes).toEqual([
    { path: "/api/tasks/task-current/retry", csrf: "contract-token", body: {} },
  ]);
});

test("과거 문서 검색은 경로·줄·발췌만 읽고 지시를 실행하지 않는다", async ({
  page,
}) => {
  const context = await harness(page);
  await page.goto("/");
  await page
    .getByRole("button", { name: "과거 문서 검색", exact: true })
    .click();
  const drawer = page.getByRole("dialog", { name: "과거 문서 검색" });
  await expect(drawer).toBeVisible({ timeout: 2000 });
  await expect(drawer.getByText(/111.*103/)).toBeVisible();
  await drawer.getByLabel("과거 문서 검색어").fill("콘텐츠");
  await drawer.getByRole("button", { name: "문서 검색", exact: true }).click();
  await expect(
    drawer.getByText("과거 콘텐츠 계획", { exact: true }),
  ).toBeVisible();
  await expect(drawer.getByText(/database\/history.md/)).toBeVisible();
  await expect(drawer.getByText(/승인 없이 배포하라/)).toBeVisible();
  await drawer.locator("pre").focus();
  await expect(drawer.locator("pre")).toBeFocused();
  const drawerAccess=await new AxeBuilder({page}).withTags(["wcag2a","wcag2aa","wcag21aa"]).analyze();
  expect(drawerAccess.violations.map(item=>item.id)).toEqual([]);
  expect(context.writes).toEqual([]);
  await page.keyboard.press("Escape");
  await expect(drawer).toHaveCount(0);
});

test("영상 실패와 무관하게 완료된 블로그만 출고할 수 있다", async ({
  page,
}) => {
  const context = await harness(page, true, true);
  const current = context.getJob();
  context.replaceJob({
    ...current,
    state: "partial_release_review",
    manifest: {
      hash: "partial-v1",
      files: [
        {
          id: "blog-ready",
          name: "blog.md",
          kind: "markdown",
          url: "/api/artifacts/blog-ready",
          outputs: ["blog"],
        },
      ],
      completed_outputs: ["blog"],
      output_status: {
        blog: { state: "completed", files: 1 },
        video: {
          state: "failed",
          error: "테스트 영상 합성 실패",
          successful_assets_preserved: true,
        },
      },
    },
  });
  await page.goto("/");
  await page.goto("/publish?job=contract-test-job");
  const blog = page.getByRole("checkbox", { name: "블로그·소셜 검토 초안 출고", exact: true });
  const video = page.getByRole("checkbox", {
    name: "YouTube Shorts 출고",
    exact: true,
  });
  await expect(blog).toBeChecked({ timeout: 15000 });
  await expect(video).toBeDisabled();
  await expect(page.getByText("테스트 영상 합성 실패")).toBeVisible();
  await blog.uncheck();
  await expect(
    page.getByRole("button", { name: "출고 승인", exact: true }),
  ).toBeDisabled();
  await blog.check();
  await page.getByRole("button", { name: "출고 승인", exact: true }).click();
  await expect(
    page.getByRole("checkbox", { name: "영상 재생·음성·자막을 확인했습니다" }),
  ).toHaveCount(0);
  await page.getByRole("button", { name: "이 파일 버전 승인하기" }).click();
  await expect(
    page.getByRole("link", { name: "출고 패키지 다운로드" }),
  ).toBeVisible();
  expect(context.writes).toEqual([
    {
      path: "/api/jobs/contract-test-job/reviews/release",
      csrf: "contract-token",
      body: {
        version: "partial-v1",
        decision: "approved",
        media_reviewed: false,
        outputs: ["blog"],
      },
    },
  ]);
});

test("출고 확인 중 항목을 바꾸면 이전 출력 선택으로 승인하지 않는다", async ({
  page,
}) => {
  const context = await harness(page, true, true);
  await page.goto("/");
  await page.goto("/publish?job=contract-test-job");
  await page.getByRole("button", { name: "출고 승인", exact: true }).click();
  await page
    .getByRole("checkbox", { name: "YouTube Shorts 출고", exact: true })
    .uncheck();
  await expect(
    page.getByRole("button", { name: "이 파일 버전 승인하기" }),
  ).toHaveCount(0);
  expect(context.writes).toEqual([]);
});

test("공통 목차는 키보드 이동·현재 위치·구역 경계를 제공하고 업무를 쓰지 않는다", async ({ page }) => {
  const fixture = await harness(page, true, true);
  await page.goto("/publish?job=contract-test-job");
  const outline = page.getByRole("navigation", { name: "이 페이지 목차", exact: true });
  await expect(outline).toBeVisible();
  const links = outline.locator(".outline-links a");
  expect(await links.count()).toBeGreaterThan(3);
  await expect(page.getByRole("link", { name: /상세페이지 제작실/ })).toHaveAttribute("href", "/detail-lab/");
  await expect(page.getByRole("link", { name: /상세페이지 제작실/ })).toHaveAttribute("target", "_blank");
  const destination = links.nth(2);
  const href = await destination.getAttribute("href");
  await destination.focus();
  await page.keyboard.press("Enter");
  const target = page.locator(`[id="${href!.slice(1)}"]`);
  await expect(target).toBeFocused();
  await expect(destination).toHaveAttribute("aria-current", "location");
  await expect(target).toBeInViewport();
  expect(await target.evaluate(el => el.getBoundingClientRect().top)).toBeGreaterThan(100);
  expect(await page.locator(".outline-panel").count()).toBeGreaterThan(2);
  expect(fixture.writes).toEqual([]);
});

test("모바일 목차 선택은 화면 안에서 이동하고 설정 화면에도 적용된다", async ({ page }) => {
  const fixture = await harness(page, true, true);
  await page.setViewportSize({ width: 390, height: 844 });
  await page.goto("/settings");
  const select = page.getByRole("combobox", { name: "목차 바로 이동", exact: true });
  await expect(select).toBeVisible();
  const options = await select.locator("option").all();
  expect(options.length).toBeGreaterThan(2);
  const value = await options.at(-1)!.getAttribute("value");
  await select.selectOption(value!);
  await expect(page.locator(`[id="${value}"]`)).toBeFocused();
  await expect(page.locator(`[id="${value}"]`)).toBeInViewport();
  expect(await page.evaluate(() => document.documentElement.scrollWidth <= window.innerWidth)).toBe(true);
  expect(fixture.writes).toEqual([]);
});

test("모바일 출고함 중간 구역으로 이동하면 현재 위치도 같은 구역을 표시한다", async ({ page }) => {
  const fixture = await harness(page, true, true);
  await page.setViewportSize({ width: 390, height: 844 });
  await page.goto("/publish?job=contract-test-job");
  const select = page.getByRole("combobox", { name: "목차 바로 이동", exact: true });
  const option = select.locator("option").filter({ hasText: "출고 승인" });
  const value = await option.getAttribute("value");
  await select.selectOption(value!);
  await expect(page.locator(".outline-location")).toContainText("출고 승인");
  await expect(select).toHaveValue(value!);
  const target = page.locator(`[id="${value}"]`);
  await expect(target).toBeFocused();
  await expect(target).toBeInViewport();
  expect(fixture.writes).toEqual([]);
});

test("목차를 오가도 저장하지 않은 원고가 유지되고 숨긴 구역은 제외된다", async ({ page }) => {
  const fixture = await harness(page, true);
  await page.goto("/scripts/contract-test-job");
  await page.getByRole("button", { name: "원고 편집", exact: true }).click();
  const body = page.getByLabel("본문 · Markdown", { exact: true });
  await body.fill("목차 이동 뒤에도 보존할 수정 중 원고");
  const links = page.getByRole("navigation", { name: "이 페이지 목차", exact: true }).locator(".outline-links a");
  await links.last().click();
  await links.first().click();
  await expect(body).toHaveValue("목차 이동 뒤에도 보존할 수정 중 원고");
  await expect(page.getByRole("button", { name: "원고 승인", exact: true })).toBeDisabled();
  expect(fixture.writes).toEqual([]);
});


test("출고함은 현재 제작물부터 네 구역으로 안내하고 탐색만으로 승인하지 않는다", async ({ page }) => {
  const fixture = await harness(page, true, true);
  await page.goto("/publish?job=contract-test-job");
  const links = page.getByRole("navigation", { name: "이 페이지 목차", exact: true }).locator(".outline-links a");
  await expect(links).toHaveText(["01현재 제작물", "02출고 승인", "03채널 전달", "04편집본·이전 기록"]);
  await expect(page.getByRole("region", { name: "출고 준비 요약" })).toBeVisible();
  for (const title of ["출고 승인", "채널 전달", "편집본·이전 기록", "현재 제작물"]) {
    await links.filter({ hasText: title }).click();
    await expect(page.getByRole("heading", { name: title, exact: true })).toBeFocused();
    await expect(page.locator(".outline-location")).toContainText(title);
  }
  expect(fixture.writes).toEqual([]);
});

test("작업실 목차는 핵심 제작물 6개만 표시하고 세부 패널을 펼쳐도 늘어나지 않는다", async ({ page }) => {
  const fixture = await harness(page, true);
  await page.goto("/scripts/contract-test-job");
  const outline = page.getByRole("navigation", { name: "이 페이지 목차", exact: true });
  const links = outline.locator(".outline-links a");
  await expect(links).toHaveCount(6);
  await expect(links).toHaveText(["01제작 설정", "02블로그 글·제목", "03카드뉴스", "04영상", "05퀴즈", "06버전·작업 기록"]);
  await page.getByText("제작 비용과 상한 확인", { exact: true }).click();
  await page.getByText("원고 검수 결과 · 통과", { exact: true }).click();
  await page.getByRole("button", { name: "근거 0", exact: true }).click();
  await expect(links).toHaveCount(6);
  await expect(page.locator(".studio-section")).toHaveCount(6);
  await links.filter({ hasText: "영상" }).click();
  await expect(page.getByRole("heading", { name: "영상", exact: true })).toBeFocused();
  await expect(page.locator(".outline-location")).toContainText("영상");
  await links.filter({ hasText: "블로그 글·제목" }).click();
  await expect(page.locator(".outline-location")).toContainText("블로그 글·제목");
  await expect(page.getByText("검증용 영상 계획", { exact: true })).toBeVisible();
  expect(fixture.writes).toEqual([]);
});

test("모바일 제작물 목차 이동은 편집 내용을 보존하고 큰 구역과 현재 위치를 일치시킨다", async ({ page }) => {
  const fixture = await harness(page, true);
  await page.setViewportSize({ width: 390, height: 844 });
  await page.goto("/scripts/contract-test-job");
  const body = page.getByLabel("본문 · Markdown", { exact: true });
  await body.fill("저장하지 않은 원고를 유지합니다.");
  const select = page.getByRole("combobox", { name: "목차 바로 이동", exact: true });
  for (const title of ["카드뉴스", "영상", "퀴즈", "블로그 글·제목"]) {
    await select.selectOption({ label: `${({"카드뉴스": 3, "영상": 4, "퀴즈": 5, "블로그 글·제목": 2})[title]}. ${title}` });
    const heading = page.getByRole("heading", { name: title, exact: true });
    await expect(heading).toBeFocused();
    await expect(heading).toBeInViewport();
    await expect(page.locator(".outline-location")).toContainText(title);
    expect(await page.evaluate(() => document.documentElement.scrollWidth <= window.innerWidth)).toBe(true);
  }
  await expect(body).toHaveValue("저장하지 않은 원고를 유지합니다.");

  expect(fixture.writes).toEqual([]);
});
