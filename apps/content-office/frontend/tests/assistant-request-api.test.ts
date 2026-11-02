import test from 'node:test';
import assert from 'node:assert/strict';
import { api } from '../lib/api.ts';

test('assistant API preserves a safe server refusal code while ignoring unsafe arbitrary codes', async () => {
  const previous = globalThis.fetch;
  let code = 'unsafe_request_body';
  globalThis.fetch = async (url: any) => String(url) === '/api/session'
    ? new Response(JSON.stringify({ csrf: 'fixture' }), { status: 200 })
    : new Response(JSON.stringify({ detail: '입력을 검토해 주세요', code }), { status: 422 });
  try {
    const body = { request_id: 'aa3a151d-72e8-4abf-b09d-10d416279c41', text: '검토', assignee: 'lumi' as const };
    await assert.rejects(api.createAssistantRequest(body), (error: any) => error.status === 422 && error.code === code);
    code = 'Bearer private';
    await assert.rejects(api.createAssistantRequest(body), (error: any) => error.code === undefined);
  } finally { globalThis.fetch = previous; }
});
