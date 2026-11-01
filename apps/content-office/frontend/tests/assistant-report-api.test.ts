import test from "node:test";
import assert from "node:assert/strict";
import { api } from "../lib/api.ts";

test("비서 보고는 기존 API 클라이언트의 읽기 전용 요청을 사용한다", async () => {
  const previous = globalThis.fetch;
  const calls: Array<{ input: unknown; init: RequestInit | undefined }> = [];
  globalThis.fetch = async (input, init) => {
    calls.push({ input, init });
    return new Response(JSON.stringify({ reports: [] }), { status: 200 });
  };
  try {
    const result = await api.assistantReports();
    assert.deepEqual(result, { reports: [] });
    assert.equal(calls.length, 1);
    assert.equal(calls[0].input, "/api/assistant/reports");
    assert.equal(calls[0].init?.method, "GET");
    assert.equal(calls[0].init?.credentials, "same-origin");
    assert.equal(calls[0].init?.cache, "no-store");
    assert.equal(calls[0].init?.body, undefined);
  } finally {
    globalThis.fetch = previous;
  }
});
