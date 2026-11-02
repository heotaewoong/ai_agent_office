import test from 'node:test';
import assert from 'node:assert/strict';

const implementation: any = await import('../lib/assistant-requests.ts').catch(() => null);
const requestId = 'aa3a151d-72e8-4abf-b09d-10d416279c41';
const accepted = () => ({ request_id: requestId, native_task_id: 't_1234abcd', board: 'heobrain-office', status: 'queued' });
const result = (patch = {}) => ({ ...accepted(), status: 'running', native_status: 'running', assignee: 'lumi', title: '근거 확인', updated_at: '2026-11-02T13:00:00Z', current_run_id: 9,
  events: [{ id: 12, task_id: 't_1234abcd', run_id: 9, kind: 'spawned', created_at: 1793624400, assignee: 'lumi' }], report: null, error: null, ...patch });

test('native request parser preserves actual IDs and rejects invented completion evidence or unsafe metadata', () => {
  assert.equal(typeof implementation?.parseAssistantRequest, 'function', 'native request parser must exist');
  assert.deepEqual(implementation.parseAssistantRequest(result(), requestId), result());
  for (const patch of [{ request_id: 'other' }, { board: 'other' }, { assignee: 'director' }, { native_task_id: '../private' }, { title: 'Bearer abcdef' },
    { events: [{ ...result().events[0], id: 1.5 }] }, { events: [result().events[0], result().events[0]] },
    { report: { summary: '완료', verified: true, task_id: 't_1234abcd', run_id: 9, event_id: 99 } }]) {
    assert.throws(() => implementation.parseAssistantRequest(result(patch), requestId));
  }
});

test('completion needs its real completed event and matching run before the report can return to the owner', () => {
  assert.equal(typeof implementation?.parseAssistantRequest, 'function');
  const report = { summary: '근거를 대조했습니다.', verified: true, task_id: 't_1234abcd', run_id: 9, event_id: 12 };
  const completed = result({ status: 'completed', native_status: 'done', events: [{ ...result().events[0], kind: 'completed' }], report });
  assert.deepEqual(implementation.parseAssistantRequest(completed, requestId), completed);
  assert.throws(() => implementation.parseAssistantRequest({ ...completed, status: 'running' }, requestId));
  assert.throws(() => implementation.parseAssistantRequest({ ...completed, report: { ...report, run_id: 8 } }, requestId));
  assert.equal(implementation.parseAssistantRequest({ ...completed, report: null }, requestId).report, null);
});

test('verified final Lumi descendant retains the stable root task and requires its own completed event', () => {
  const child = result({ status: 'completed', native_status: 'done', current_run_id: null, updated_at: 1793624400,
    events: [{ id: 15, task_id: 't_final123', run_id: 10, kind: 'completed', created_at: 1793624400, assignee: 'lumi' }],
    report: { summary: '협업 결과를 대조했습니다.', verified: true, task_id: 't_final123', run_id: 10, event_id: 15 } });
  assert.equal(implementation.parseAssistantRequest(child, requestId).native_task_id, 't_1234abcd');
  assert.throws(() => implementation.parseAssistantRequest({ ...child, events: [{ ...child.events[0], assignee: 'ada' }] }, requestId));
  assert.throws(() => implementation.parseAssistantRequest(child, 'bbbbbbbb-72e8-4abf-b09d-10d416279c41'));
});

test('unknown admission retains the exact prompt and UUID; reconciliation only reads the same request', async () => {
  assert.equal(typeof implementation?.createAssistantRequestsController, 'function', 'native request controller must exist');
  const controller = implementation.createAssistantRequestsController();
  controller.setAvailability(true, true);
  controller.setDraft('공식 근거를 확인해 주세요.');
  await controller.submit(async () => { throw { status: 502 }; }, () => requestId);
  assert.equal(controller.getSnapshot().submission.request_id, requestId);
  assert.equal(controller.getSnapshot().draft, '공식 근거를 확인해 주세요.');
  assert.match(controller.getSnapshot().error, /접수|확인/);
  let readId = '';
  await controller.refresh(async (id: string) => { readId = id; return result({ native_task_id: null, native_status: null, status: 'queued', current_run_id: null, events: [], error: { code: 'native_admission_unknown', message: '접수 여부 확인 중' } }); });
  assert.equal(readId, requestId);
  assert.equal(controller.getSnapshot().request.native_task_id, null);
  assert.equal(controller.getSnapshot().submission.text, '공식 근거를 확인해 주세요.');
});

test('double submission, disconnected input and late responses do not create duplicate work or lose a draft', async () => {
  const controller = implementation.createAssistantRequestsController();
  controller.setDraft('기존 요청');
  let calls = 0, resolve!: (value: unknown) => void;
  const send = () => { calls++; return new Promise(yes => { resolve = yes; }); };
  await controller.submit(send, () => requestId);
  assert.equal(calls, 0);
  controller.setAvailability(true, true);
  const first = controller.submit(send, () => requestId);
  await controller.submit(send, () => 'b'.repeat(36));
  assert.equal(calls, 1);
  controller.setAvailability(false, false);
  resolve(accepted()); await first;
  assert.equal(controller.getSnapshot().draft, '기존 요청');
  assert.equal(controller.getSnapshot().request, null);
  controller.setAvailability(true, true);
  await controller.refresh(async () => result());
  assert.equal(controller.getSnapshot().request.native_task_id, 't_1234abcd');
  await controller.submit(send, () => requestId);
  assert.equal(calls, 1, 'an admitted or uncertain request must only be refreshed');
});

test('closing the input keeps native reads active while reload restoration only resumes the existing UUID', async () => {
  const controller = implementation.createAssistantRequestsController();
  controller.restore(requestId);
  controller.setAvailability(true, false);
  await controller.refresh(async (id: string) => { assert.equal(id, requestId); return result(); });
  assert.equal(controller.getSnapshot().request.status, 'running');
  assert.equal(controller.getSnapshot().submission.text, '', 'reload must not reconstruct or persist a private prompt');
  let writes = 0;
  await controller.submit(async () => { writes++; return accepted(); }, () => requestId);
  assert.equal(writes, 0);
  assert.throws(() => implementation.createAssistantRequestsController().restore('../private'));
});

test('disabled backend and blocked native work expose actionable states without simulated replies', async () => {
  const controller = implementation.createAssistantRequestsController();
  controller.setAvailability(true, true); controller.setDraft('요청 보존');
  await controller.submit(async () => { throw { status: 503, message: '/home/private token=secret' }; }, () => requestId);
  assert.match(controller.getSnapshot().error, /연결 설정/);
  assert.doesNotMatch(controller.getSnapshot().error, /home|secret/);
  await controller.refresh(async () => result({ status: 'blocked', native_status: 'blocked', error: { code: 'needs_input', message: '확인할 대상이 필요합니다.' } }));
  assert.equal(controller.getSnapshot().request.status, 'blocked');
  assert.equal(controller.getSnapshot().draft, '요청 보존');
});

test('known pre-admission failure permits only explicit same-UUID retry and no automatic POST', async () => {
  const controller = implementation.createAssistantRequestsController();
  assert.equal(typeof controller.retrySubmission, 'function');
  controller.setAvailability(true, true); controller.setDraft('원래 요청 보존');
  let writes = 0;
  await controller.submit(async () => { writes++; throw { status: 502, code: 'native_preflight_failed' }; }, () => requestId);
  assert.equal(controller.getSnapshot().noAdmissionCode, 'native_preflight_failed');
  assert.equal(writes, 1);
  controller.setAvailability(true, false);
  await controller.retrySubmission(async () => { writes++; return accepted(); });
  assert.equal(writes, 1, 'closed input must not submit');
  controller.setAvailability(true, true);
  await controller.retrySubmission(async (input: any) => {
    writes++;
    assert.deepEqual(input, { request_id: requestId, text: '원래 요청 보존', assignee: 'lumi' });
    return accepted();
  });
  assert.equal(writes, 2);
  assert.equal(controller.getSnapshot().noAdmissionCode, null);
  await controller.retrySubmission(async () => { writes++; return accepted(); });
  assert.equal(writes, 2, 'accepted requests never retry POST');
});

test('HTTP status alone, unknown admission and reload restoration cannot enable POST retry or new intent', async () => {
  for (const error of [{ status: 503 }, { status: 502, code: 'native_admission_unknown' }, new Error('timeout')]) {
    const controller = implementation.createAssistantRequestsController();
    controller.setAvailability(true, true); controller.setDraft('보존');
    await controller.submit(async () => { throw error; }, () => requestId);
    assert.equal(controller.getSnapshot().noAdmissionCode, null);
    let writes = 0;
    await controller.retrySubmission(async () => { writes++; return accepted(); });
    controller.newRequest();
    assert.equal(controller.getSnapshot().submission.request_id, requestId);
    assert.equal(writes, 0);
  }
  const restored = implementation.createAssistantRequestsController();
  restored.restore(requestId); restored.setAvailability(true, true);
  let writes = 0;
  await restored.retrySubmission(async () => { writes++; return accepted(); });
  assert.equal(writes, 0);
});

test('definitely rejected credentials can be explicitly edited as a new intent without an automatic send', async () => {
  const controller = implementation.createAssistantRequestsController();
  assert.equal(typeof controller.editRejectedRequest, 'function');
  controller.setAvailability(true, true); controller.setDraft('검토할 원래 입력');
  await controller.submit(async () => { throw { status: 422, code: 'unsafe_request_body' }; }, () => requestId);
  controller.editRejectedRequest();
  assert.equal(controller.getSnapshot().submission, null);
  assert.equal(controller.getSnapshot().draft, '검토할 원래 입력');
  controller.setDraft('수정한 입력');
  const nextId = 'bbbbbbbb-72e8-4abf-b09d-10d416279c41';
  await controller.submit(async (input: any) => {
    assert.equal(input.request_id, nextId); assert.equal(input.text, '수정한 입력');
    return { ...accepted(), request_id: nextId };
  }, () => nextId);
});

test('Slack delivery metadata is bounded and separate from native completion evidence', () => {
  const delivery = { slack: 'sent_unverified', external_delivery_verified: false, error_code: 'status_sender_disabled' };
  assert.deepEqual(implementation.parseAssistantRequest(result({ delivery }), requestId).delivery, delivery);
  const notice = { request_id: requestId, task_id: 't_1234abcd', run_id: 9, event_id: 12, terminal_state: 'completed' };
  const confirmed = { slack: 'confirmed', external_delivery_verified: true, notice_ref: notice };
  const complete = result({ status: 'completed', native_status: 'done', events: [{ ...result().events[0], kind: 'completed' }],
    report: { summary: '검토 완료', verified: true, task_id: 't_1234abcd', run_id: 9, event_id: 12 }, delivery: confirmed });
  assert.deepEqual(implementation.parseAssistantRequest(complete, requestId).delivery, confirmed);
  for (const unsafe of [
    { slack: 'pending', external_delivery_verified: true },
    { slack: 'confirmed', external_delivery_verified: 'true' },
    { slack: 'invented', external_delivery_verified: false },
    { ...delivery, error_code: '/home/private/token' },
    { ...delivery, error_code: 'a'.repeat(81) },
  ]) assert.throws(() => implementation.parseAssistantRequest(result({ delivery: unsafe }), requestId));
  for (const patch of [{ task_id: 't_other' }, { run_id: 8 }, { event_id: 11 }, { terminal_state: 'blocked' },
    { request_id: 'bbbbbbbb-72e8-4abf-b09d-10d416279c41' }, { run_id: '9' }, { body: 'private' }]) {
    assert.throws(() => implementation.parseAssistantRequest({ ...complete, delivery: { ...confirmed, notice_ref: { ...notice, ...patch } } }, requestId));
  }
});

test('selecting an actual Hermes profile preserves the draft and never changes the native Lumi assignee', async () => {
  const controller = implementation.createAssistantRequestsController();
  assert.equal(typeof controller.selectAssistant, 'function');
  assert.equal(controller.getSnapshot().selectedAssistant, 'lumi');
  controller.setDraft('원본 업무\n내용');
  for (const profile of ['director', '__proto__', '../ada', '', null, {}]) assert.equal(controller.selectAssistant(profile), false);
  assert.equal(controller.selectAssistant('ada'), true);
  assert.equal(controller.getSnapshot().draft, '원본 업무\n내용');
  controller.setAvailability(true, true);
  let sent: any;
  await controller.submit(async (input: any) => { sent = input; return accepted(); }, () => requestId);
  assert.equal(sent.assignee, 'lumi');
  assert.equal(sent.text, '[배정 요청: 에이다 (ada)]\n아래 업무를 에이다에게 배정해 주세요. 배정할 수 없으면 이유를 보고해 주세요.\n\n원본 업무\n내용');
  assert.equal(sent.text.includes('\n'), true);
  assert.equal(sent.text.includes('\\n'), false);
  assert.equal(controller.getSnapshot().draft, '원본 업무\n내용');
  assert.equal(controller.selectAssistant('ethan'), false, 'an admitted UUID cannot change its recipient');
});

test('a selected recipient is locked while pending and exact rejected text retries once without prefix duplication', async () => {
  const controller = implementation.createAssistantRequestsController();
  assert.equal(typeof controller.selectAssistant, 'function');
  controller.setAvailability(true, true); controller.setDraft('확인할 업무'); controller.selectAssistant('ethan');
  let reject!: (error: unknown) => void, sent: any;
  const pending = controller.submit(async (input: any) => { sent = input; return new Promise((_yes, no) => { reject = no; }); }, () => requestId);
  assert.equal(controller.selectAssistant('ada'), false);
  reject({ code: 'native_preflight_failed' }); await pending;
  const original = { ...sent };
  await controller.retrySubmission(async (input: any) => { assert.deepEqual(input, original); return accepted(); });
  assert.equal(controller.getSnapshot().selectedAssistant, 'ethan');
  assert.equal(controller.getSnapshot().draft, '확인할 업무');
});

test('explicitly editing a rejected assignment restores the raw draft and recipient, and new work resets the recipient', async () => {
  const controller = implementation.createAssistantRequestsController();
  assert.equal(typeof controller.selectAssistant, 'function');
  controller.setAvailability(true, true); controller.setDraft('보존할 원문'); controller.selectAssistant('ada');
  await controller.submit(async () => { throw { code: 'unsafe_request_body' }; }, () => requestId);
  assert.equal(controller.editRejectedRequest(), true);
  assert.equal(controller.getSnapshot().draft, '보존할 원문');
  assert.equal(controller.getSnapshot().selectedAssistant, 'ada');
  await controller.submit(async (input: any) => {
    assert.equal(input.text, implementation.assistantSubmissionText('ada', '보존할 원문'));
    assert.equal(input.text.match(/\[배정 요청:/g).length, 1);
    throw { code: 'native_preflight_failed' };
  }, () => requestId);
  assert.equal(controller.newRequest(), true);
  assert.equal(controller.getSnapshot().selectedAssistant, 'lumi');
  assert.equal(controller.getSnapshot().draft, '');
});

test('assignment prefix counts toward the existing 4000 character limit without truncating the draft', async () => {
  assert.equal(typeof implementation?.assistantDraftLimit, 'function');
  assert.equal(implementation.assistantDraftLimit('lumi'), 4000);
  const limit = implementation.assistantDraftLimit('ada');
  assert(limit > 0 && limit < 4000);
  assert.equal([...implementation.assistantSubmissionText('ada', '가'.repeat(limit))].length, 4000);
  const controller = implementation.createAssistantRequestsController();
  controller.setAvailability(true, true); controller.selectAssistant('ada'); controller.setDraft('가'.repeat(limit + 1));
  let writes = 0;
  await controller.submit(async () => { writes++; return accepted(); }, () => requestId);
  assert.equal(writes, 0); assert.equal(controller.getSnapshot().draft, '가'.repeat(limit + 1));
  assert.equal(controller.getSnapshot().submission, null);
  controller.setDraft('가'.repeat(limit));
  await controller.submit(async (input: any) => { writes++; assert.equal([...input.text].length, 4000); return accepted(); }, () => requestId);
  assert.equal(writes, 1);
});
