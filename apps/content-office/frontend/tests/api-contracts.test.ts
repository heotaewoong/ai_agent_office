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
