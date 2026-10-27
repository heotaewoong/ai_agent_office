import { chromium } from "playwright";
import AxeBuilder from "@axe-core/playwright";
import { writeFile, mkdir } from "node:fs/promises";
import { resolve } from "node:path";
const destination = resolve("test-results/live");
await mkdir(destination, { recursive: true });
const browser = await chromium.launch({ headless: true });
const context = await browser.newContext({
  viewport: { width: 1440, height: 1050 },
});
const page = await context.newPage();
const errors = [];
const mutations = [];
page.on("pageerror", (error) => errors.push(error.message));
page.on("request", (request) => {
  if (
    new URL(request.url()).pathname.startsWith("/api/") &&
    request.method() !== "GET"
  )
    mutations.push({
      method: request.method(),
      path: new URL(request.url()).pathname,
    });
});
await page.goto("http://127.0.0.1:3110");
await page.getByRole("checkbox").first().waitFor();
const session = await page.evaluate(async () => {
  const response = await fetch("/api/session", { credentials: "same-origin" });
  const body = await response.json();
  return { status: response.status, hasCsrf: Boolean(body.csrf) };
});
const dashboard = await page.evaluate(async () => {
  const response = await fetch("/api/dashboard", {
    credentials: "same-origin",
  });
  return response.json();
});
const data = {
  checked_at: new Date().toISOString(),
  method:
    "Live Chromium, real API/SQLite, read-only navigation; no approval or paid request",
  session,
  articles: dashboard.articles.length,
  jobs: dashboard.jobs.map((job) => ({
    id: job.id,
    state: job.state,
    has_source: Boolean(job.source_packet),
    error: job.error,
  })),
  budget: dashboard.budget,
  feeds: dashboard.feeds.length,
  window: dashboard.window,
  views: {},
  errors,
  mutations,
};
for (const [name, button] of [
  ["news", null],
  ["studio", "콘텐츠 작업실"],
  ["activity", "운영 기록"],
  ["delivery", "제작·출고함"],
]) {
  if (button)
    await page
      .getByRole("navigation", { name: "오피스 메뉴" })
      .getByRole("button", { name: new RegExp("^" + button) })
      .click();
  if (name === "studio") {
    const readable = dashboard.jobs.find((item) => item.source_packet);
    if (readable) {
      await page
        .locator(".job-sidebar .job-item")
        .filter({ hasText: readable.title })
        .first()
        .click();
      await page.getByLabel("본문 · Markdown").waitFor();
    }
  }
  await page.waitForTimeout(200);
  const result = await new AxeBuilder({ page })
    .withTags(["wcag2a", "wcag2aa", "wcag21aa"])
    .analyze();
  data.views[name] = {
    horizontal_overflow: await page.evaluate(
      () => document.documentElement.scrollWidth > innerWidth,
    ),
    accessibility_violations: result.violations.map((item) => ({
      id: item.id,
      targets: item.nodes.map((node) => node.target),
      details: item.nodes.map((node) => node.failureSummary),
    })),
  };
  await page.screenshot({
    path: resolve(destination, `${name}-desktop.png`),
    fullPage: true,
  });
  if (name === "studio") {
    data.body_font_px = await page.getByLabel("본문 · Markdown").evaluate(element=>parseFloat(getComputedStyle(element).fontSize));
    await page.getByRole("button", { name: /근거 \d/ }).click();
    data.evidence_links = await page.getByText("근거 원문 확인").count();
    await page.screenshot({
      path: resolve(destination, "evidence-desktop.png"),
      fullPage: true,
    });
    if (
      await page.getByRole("button", { name: "영상 대본", exact: true }).count()
    ) {
      await page
        .getByRole("button", { name: "영상 대본", exact: true })
        .click();
      await page.screenshot({
        path: resolve(destination, "video-plan-desktop.png"),
        fullPage: true,
      });
    }
  }
}
await page.setViewportSize({ width: 390, height: 844 });
for (const [name, label] of [
  ["news", "오늘의 뉴스"],
  ["studio", "콘텐츠 작업실"],
  ["activity", "운영 기록"],
  ["delivery", "제작·출고함"],
]) {
  await page
    .getByRole("navigation", { name: "오피스 메뉴" })
    .getByRole("button", { name: new RegExp("^" + label) })
    .click();
  const checks = await new AxeBuilder({ page })
    .withTags(["wcag2a", "wcag2aa", "wcag21aa"])
    .analyze();
  data.views[`mobile_${name}`] = {
    horizontal_overflow: await page.evaluate(
      () => document.documentElement.scrollWidth > innerWidth,
    ),
    accessibility_violations: checks.violations.map((item) => ({
      id: item.id,
      targets: item.nodes.map((node) => node.target),
    })),
  };
  await page.screenshot({
    path: resolve(destination, `${name}-mobile.png`),
    fullPage: true,
  });
}
await page.setViewportSize({width:1440,height:1050});
await page.getByRole("button",{name:"과거 문서 검색",exact:true}).click();
const drawer=page.getByRole("dialog",{name:"과거 문서 검색"});
await drawer.getByLabel("과거 문서 검색어").fill("콘텐츠");
await drawer.getByRole("button",{name:"문서 검색",exact:true}).click();
await drawer.locator(".knowledge-result").first().waitFor();
const drawerChecks=await new AxeBuilder({page}).withTags(["wcag2a","wcag2aa","wcag21aa"]).analyze();
data.knowledge={summary:await drawer.locator(".knowledge-counts").innerText(),result_count:await drawer.locator(".knowledge-result").count(),accessibility_violations:drawerChecks.violations.map(item=>item.id)};
await page.screenshot({path:resolve(destination,"knowledge-desktop.png"),fullPage:true});
await page.keyboard.press("Escape");
await writeFile(
  resolve(destination, "verification.json"),
  JSON.stringify(data, null, 2),
);
console.log(
  JSON.stringify(
    {
      session,
      articles: data.articles,
      jobs: data.jobs.map((job) => ({
        state: job.state,
        has_source: job.has_source,
      })),
      evidence_links: data.evidence_links,
      views: data.views,
      consoleErrors: errors,
      apiMutations: mutations,
    },
    null,
    2,
  ),
);
await browser.close();
if (
  errors.length || data.body_font_px < 16 || data.knowledge?.accessibility_violations?.length ||
  mutations.length ||
  Object.values(data.views).some(
    (view) => view.horizontal_overflow || view.accessibility_violations?.length,
  )
)
  process.exitCode = 1;
