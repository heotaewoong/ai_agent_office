import test from "node:test";
import assert from "node:assert/strict";
import { api } from "../lib/api.ts";

test("회차 검토는 화면에서 읽은 판본 토큰을 승인과 반려 요청에 함께 보낸다", async (t) => {
  const originalFetch = globalThis.fetch;
  const requests: { url: string; body: Record<string, unknown> }[] = [];
  t.after(() => { globalThis.fetch = originalFetch; });
  globalThis.fetch = async (input, init) => {
    if (String(input) === "/api/session") return Response.json({ csrf: "isolated-contract-token" });
    assert.equal(init?.method, "POST");
    requests.push({ url: String(input), body: JSON.parse(String(init?.body)) });
    return Response.json({ id: "issue A/1" });
  };

  const firstVersion = "a".repeat(64);
  const nextVersion = "b".repeat(64);
  await api.reviewNewsletter("issue A/1", "approve", "읽은 본문 확인", firstVersion);
  await api.reviewNewsletter("issue A/1", "reject", "새 판본 수정 요청", nextVersion);

  assert.deepEqual(requests, [
    { url: "/api/newsletters/issue%20A%2F1/review", body: { decision: "approve", note: "읽은 본문 확인", expected_hash: firstVersion } },
    { url: "/api/newsletters/issue%20A%2F1/review", body: { decision: "reject", note: "새 판본 수정 요청", expected_hash: nextVersion } },
  ]);
});

test("카드 기본 요청은 프로필을 따르고 명시적인 이미지 선택은 그대로 전달한다", async (t) => {
  const originalFetch = globalThis.fetch;
  const bodies: unknown[] = [];
  t.after(() => { globalThis.fetch = originalFetch; });
  globalThis.fetch = async (input, init) => {
    if (String(input) === "/api/session") return Response.json({ csrf: "isolated-contract-token" });
    assert.equal(String(input), "/api/jobs/job-a/cards");
    bodies.push(JSON.parse(String(init?.body)));
    return Response.json({ task_id: "isolated-task" });
  };
  await api.requestCards("job-a");
  await api.requestCards("job-a", false);
  await api.requestCards("job-a", true);
  assert.deepEqual(bodies, [{}, { images: false }, { images: true }]);
});

test("브리프 저장은 편집을 시작한 판본 토큰을 보낸다", async (t) => {
  const originalFetch = globalThis.fetch;
  t.after(() => { globalThis.fetch = originalFetch; });
  const expected = "c".repeat(64);
  globalThis.fetch = async (input, init) => {
    if (String(input) === "/api/session") return Response.json({ csrf: "isolated-contract-token" });
    assert.equal(String(input), "/api/jobs/job%20a/brief");
    assert.equal(init?.method, "PUT");
    assert.deepEqual(JSON.parse(String(init?.body)), { preset: "ai-agent", overrides: { reader: "새 독자" }, expected_brief_hash: expected });
    return Response.json({ id: "job a", brief_hash: expected });
  };
  await api.setJobBrief("job a", "ai-agent", { reader: "새 독자" }, expected);
});

test("출처 보완은 같은 기획 ID에 URL·운영자 확인·판본으로 PUT하고 선택을 호출하지 않는다", async (t) => {
  const originalFetch = globalThis.fetch;
  t.after(() => { globalThis.fetch = originalFetch; });
  const expected = "d".repeat(64);
  globalThis.fetch = async (input, init) => {
    if (String(input) === "/api/session") return Response.json({ csrf: "isolated-contract-token" });
    assert.equal(String(input), "/api/ideas/idea%20a%2F1/sources");
    assert.equal(init?.method, "PUT");
    assert.deepEqual(JSON.parse(String(init?.body)), { source_urls: ["https://example.edu/source"], operator_verified: true, expected_hash: expected });
    return Response.json({ id: "idea a/1", edit_hash: "e".repeat(64) });
  };
  const saved = await api.updateIdeaSources("idea a/1", { source_urls: ["https://example.edu/source"], operator_verified: true, expected_hash: expected });
  assert.equal(saved.id, "idea a/1");
});

test("기획 선택⓪도 화면에서 확인한 기획 판본을 보낸다", async (t) => {
  const originalFetch = globalThis.fetch;
  t.after(() => { globalThis.fetch = originalFetch; });
  const expected = "f".repeat(64);
  globalThis.fetch = async (input, init) => {
    if (String(input) === "/api/session") return Response.json({ csrf: "isolated-contract-token" });
    assert.equal(String(input), "/api/ideas/idea%20read/select");
    assert.equal(init?.method, "POST");
    assert.deepEqual(JSON.parse(String(init?.body)), { expected_hash: expected });
    return Response.json({ idea: { id: "idea read" }, job: { id: "job-one" } });
  };
  assert.equal((await api.selectIdea("idea read", expected)).job.id, "job-one");
});

test("UI 목록 조회만 compact dashboard를 요청하고 상세 작업은 기존 경로를 쓴다", async (t) => {
  const originalFetch = globalThis.fetch;
  const paths: string[] = [];
  t.after(() => { globalThis.fetch = originalFetch; });
  globalThis.fetch = async (input, init) => {
    paths.push(String(input));
    assert.equal(init?.method, "GET");
    return Response.json({ id: "job-one", jobs: [{ id: "job-one", title: "편입", state: "source_review", has_source: true }] });
  };
  await api.dashboard();
  await api.job("job-one");
  assert.deepEqual(paths, ["/api/dashboard?compact=true", "/api/jobs/job-one"]);
});

test("배포대기는 GET으로 확인하고 읽은 판본만 앱 장부에 기록하며 외부 전송을 호출하지 않는다", async (t) => {
  const originalFetch = globalThis.fetch;
  const requests: { url: string; method: string; body?: unknown }[] = [];
  t.after(() => { globalThis.fetch = originalFetch; });
  const expected = "a".repeat(64);
  globalThis.fetch = async (input, init) => {
    if (String(input) === "/api/session") return Response.json({ csrf: "isolated-contract-token" });
    requests.push({ url: String(input), method: init?.method ?? "GET", ...(init?.body ? { body: JSON.parse(String(init.body)) } : {}) });
    return Response.json({ job_id: "job a/1", stage_hash: expected, channels: [] });
  };
  const snapshot = await api.channelStaging("job a/1");
  await api.recordChannelStaging("job a/1", snapshot.stage_hash);
  assert.deepEqual(requests, [
    { url: "/api/jobs/job%20a%2F1/staging", method: "GET" },
    { url: "/api/jobs/job%20a%2F1/staging", method: "POST", body: { expected_hash: expected } },
  ]);
});

test("원문 입력의 기본 요약 방식과 명시한 원문 보존 선택을 같은 판본 토큰에 묶어 보낸다", async (t) => {
  const originalFetch = globalThis.fetch;
  const requests: { url: string; body: unknown }[] = [];
  t.after(() => { globalThis.fetch = originalFetch; });
  globalThis.fetch = async (input, init) => {
    if (String(input) === "/api/session") return Response.json({ csrf: "isolated-contract-token" });
    assert.equal(init?.method, "POST");
    requests.push({ url: String(input), body: JSON.parse(String(init?.body)) });
    return Response.json({ id: "job a/1" });
  };
  const text = "# 직접 쓴 원문\n\n공백과 Markdown을 그대로 둡니다.  \n".repeat(30);
  await api.registerEvidence("job a/1", text, null);
  await api.registerEvidence("job a/1", text, "current-version", true);
  assert.deepEqual(requests, [
    { url: "/api/jobs/job%20a%2F1/evidence", body: { source_text: text, version: null, preserve_original: false } },
    { url: "/api/jobs/job%20a%2F1/evidence", body: { source_text: text, version: "current-version", preserve_original: true } },
  ]);
});

test("작업 예산은 읽기와 명시 PUT을 구분하고 읽은 설정 해시를 그대로 전달한다", async (t) => {
  const originalFetch = globalThis.fetch;
  const calls: { url: string; method: string; body?: unknown }[] = [];
  const hash = "e".repeat(64);
  t.after(() => { globalThis.fetch = originalFetch; });
  globalThis.fetch = async (input, init) => {
    if (String(input) === "/api/session") return Response.json({ csrf: "isolated-contract-token" });
    calls.push({ url: String(input), method: init?.method ?? "GET", ...(init?.body ? { body: JSON.parse(String(init.body)) } : {}) });
    return Response.json({ job_id: "job a/1", hash, cap_krw: null });
  };
  const budget = await api.jobBudget("job a/1");
  await api.setJobBudget("job a/1", 1000, budget.hash);
  assert.deepEqual(calls, [
    { url: "/api/jobs/job%20a%2F1/budget", method: "GET" },
    { url: "/api/jobs/job%20a%2F1/budget", method: "PUT", body: { cap_krw: 1000, expected_hash: hash } },
  ]);
});
