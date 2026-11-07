import test from 'node:test';
import assert from 'node:assert/strict';
import { parseBenchmarkResearchRun, parseBenchmarkResearchSubmission } from '../lib/benchmark-research.ts';

const uuid = '256a5f50-451f-4ee2-b061-18e26c534fa2';
const publicSourceUrl = 'https://www.youtube.com/watch?v=--Quy-4QTMs';
const reportSummary = `관측 범위와 반례를 구분한 최종 보고\n공개 원문: ${publicSourceUrl}`;
const receipt = { task_id: 't_real', run_id: 2, event_id: 3, report_sha256: 'a'.repeat(64), body_sha256: 'b'.repeat(64) };
const observation = { id: 'observed-one', title: '조사 시점의 원문 제목', url: 'https://example.org/source', summary: '공개 관측' };
const completed = () => ({ request_id: uuid, packet_hash: 'c'.repeat(64), registry_hash: 'd'.repeat(64), snapshot_hash: 'e'.repeat(64), item_ids: ['observed-one'], observations: [observation], created_at: '2026-11-07T00:00:00Z', budget_evidence: { cap_krw: 30000, spent_krw: 10, reserved_krw: 20, remaining_krw: 29970, native_monetary_guard: false, billing_mode: 'not_exposed_by_native_bridge' }, analysis_receipt: receipt,
  execution: { request_id: uuid, native_task_id: 't_real', board: 'heobrain-office', status: 'completed', native_status: 'done', assignee: 'lumi', title: '공개자료 조사', updated_at: '2026-11-07T00:00:00Z', current_run_id: 2, events: [{ id: 3, task_id: 't_real', run_id: 2, kind: 'completed', created_at: '2026-11-07T00:00:00Z', assignee: 'lumi' }], report: { summary: reportSummary, verified: true, task_id: 't_real', run_id: 2, event_id: 3 }, error: null } });

test('실제 완료 이벤트와 결합된 분석 영수증만 받는다', () => {
  assert.equal(parseBenchmarkResearchRun(completed(), uuid).analysis_receipt?.event_id, 3);
  assert.throws(() => parseBenchmarkResearchRun({ ...completed(), analysis_receipt: { ...receipt, event_id: 4 } }, uuid));
  assert.throws(() => parseBenchmarkResearchRun({ ...completed(), analysis_receipt: { ...receipt, report_sha256: 'wrong' } }, uuid));
  assert.throws(() => parseBenchmarkResearchRun(completed(), '00000000-0000-4000-8000-000000000000'));
});

test('공개 HTTP(S) 원문 3종을 포함한 보고서와 완료 영수증을 보존한다', () => {
  for (const reference of [publicSourceUrl, 'http://example.com/public-source', 'HTTPS://www.instagram.com/p/De6OvlsFfaA/']) {
    const row = completed();
    row.execution.report.summary = `관측과 추론을 구분한 최종 보고\n공개 원문: ${reference}`;
    const result = parseBenchmarkResearchRun(row, uuid);
    assert.ok('report' in result.execution);
    assert.equal(result.execution.report?.summary, row.execution.report.summary, reference);
    assert.deepEqual(result.analysis_receipt, receipt);
  }
});

test('공개 원문 URL이 있어도 내부 경로·인증정보·제어문자 18종을 거부한다', () => {
  for (const privateText of [
    String.raw`C:\Users\owner\private.txt`, 'D:/private/report.md',
    String.raw`prefixC:\Users\owner\private.txt`, String.raw`httpS:\Users\owner\private.txt`,
    'P:/private/report.md', 'S://private/report.md', 'file:///C:/private/report.md',
    '/home/owner/private.txt', '%2fhome%2fowner', '../private.txt', String.raw`..\private.txt`,
    'https://example.com/home/owner/private.txt', 'Bearer private-value', 'token=private-value',
    'api_key: private-value', 'sk-abcdefghijklmnopqrstuv', '\u202ereversed', '\x01control',
  ]) {
    const row = completed();
    row.execution.report.summary = `${reportSummary}\n${privateText}`;
    assert.throws(() => parseBenchmarkResearchRun(row, uuid), /비서 업무 응답을 확인할 수 없습니다/, privateText);
  }
});

test('queued 접수는 실행 완료·과금 guard로 바꾸지 않는다', () => {
  const row = { ...completed(), analysis_receipt: null, execution: { request_id: uuid, native_task_id: 't_real', board: 'heobrain-office', status: 'queued' } };
  const result = parseBenchmarkResearchRun(row, uuid);
  assert.equal(result.execution.status, 'queued');
  assert.equal(result.budget_evidence.native_monetary_guard, false);
  assert.throws(() => parseBenchmarkResearchRun({ ...row, analysis_receipt: receipt }, uuid));
  assert.throws(() => parseBenchmarkResearchRun({ ...row, execution: { ...row.execution, status: 'completed' } }, uuid));
});

test('새 수집 목록 대신 조사 시점의 관측 ID와 제목을 보존한다', () => {
  assert.equal(parseBenchmarkResearchRun(completed(), uuid).observations[0].title, '조사 시점의 원문 제목');
  assert.throws(() => parseBenchmarkResearchRun({ ...completed(), observations: [] }, uuid));
  assert.throws(() => parseBenchmarkResearchRun({ ...completed(), observations: [{ ...observation, id: 'different' }] }, uuid));
});

test('새로고침 복구는 같은 UUID와 불변 제출 항목만 사용한다', () => {
  const saved = { request_id: uuid, source_ids: ['every-ig'], fields: [], platforms: [], expected_hash: 'a'.repeat(64), snapshot_hash: 'b'.repeat(64), item_ids: ['observed-one'] };
  assert.deepEqual(parseBenchmarkResearchSubmission(saved, uuid), saved);
  assert.throws(() => parseBenchmarkResearchSubmission({ ...saved, text: '임의 원문 주입' }, uuid));
  assert.throws(() => parseBenchmarkResearchSubmission(saved, 'wrong-request'));
});
