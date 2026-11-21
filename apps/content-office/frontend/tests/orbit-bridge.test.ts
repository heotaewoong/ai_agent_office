import assert from 'node:assert/strict';
import test from 'node:test';
// Static browser module has no dependencies and performs no work until explicitly initialized.
// @ts-expect-error plain browser JavaScript module
import { parseReportAction, matchesCompletedReport } from '../../../../sites/office-world/orbit/bridge.js';

const action = { source: 'content-office', type: 'assistant-report-action', action: 'result',
  request_id: 'aaaaaaaa-aaaa-4aaa-8aaa-aaaaaaaaaaaa', task_id: 't_final', run_id: 7, event_id: 31 };
const request = { board: 'heobrain-office', request_id: action.request_id, status: 'completed', native_status: 'done',
  report: { verified: true, summary: '검증된 보고', task_id: 't_final', run_id: 7, event_id: 31 },
  events: [{ task_id: 't_final', run_id: 7, id: 31, kind: 'completed', assignee: 'lumi' }] };
test('Orbit accepts only the exact completed run and receipt', () => {
  assert.equal(matchesCompletedReport(action, request), true);
  for (const [key, value] of Object.entries({ task_id: 't_other', run_id: 8, event_id: 32,
    request_id: 'bbbbbbbb-bbbb-4bbb-8bbb-bbbbbbbbbbbb' })) {
    assert.equal(matchesCompletedReport({ ...action, [key]: value }, request), false);
  }
  for (const patch of [{ board: 'other' }, { status: 'running' }, { native_status: 'running' }, { events: [] },
    { report: { ...request.report, verified: false } }, { report: { ...request.report, summary: '' } }]) {
    assert.equal(matchesCompletedReport(action, { ...request, ...patch }), false);
  }
});
test('Orbit rejects forged or malformed report actions', () => {
  for (const patch of [{ source: 'other' }, { action: 'publish' }, { run_id: -1 }, { event_id: 0 },
    { task_id: '../file' }, { token: 'extra-field' }, { request_id: 'invalid' }]) {
    assert.equal(parseReportAction({ ...action, ...patch }), null);
  }
  assert.equal(matchesCompletedReport(action, null), false);
  assert.equal(matchesCompletedReport(action, { ...request, events: [null] }), false);
});
