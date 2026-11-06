import test from 'node:test';
import assert from 'node:assert/strict';
import { createAssistantRequestsController } from '../lib/assistant-requests.ts';

test('a prepared Sage request stays a draft until the owner explicitly submits through Lumi', async () => {
  const controller = createAssistantRequestsController();
  assert.equal(controller.prepareDraft('mybots-sage', '출처를 비교하고 확인하지 못한 항목을 구분해 주세요.'), true);
  assert.equal(controller.getSnapshot().submission, null);
  assert.equal(controller.getSnapshot().selectedAssistant, 'mybots-sage');
  const submissions: unknown[] = [];
  controller.setAvailability(true, true);
  const id = 'aa3a151d-72e8-4abf-b09d-10d416279c41';
  await controller.submit(async body => { submissions.push(body); return { request_id: id, native_task_id: 't_1234abcd', board: 'heobrain-office', status: 'queued' }; }, () => id);
  assert.equal(submissions.length, 1);
  assert.equal(controller.getSnapshot().submission?.assignee, 'lumi');
  assert.match(controller.getSnapshot().submission!.text, /mybots-sage/);
});

test('preparation preserves another draft and a restored in-flight request; oversized packets are not truncated', () => {
  const controller = createAssistantRequestsController();
  controller.setDraft('기존 업무 원문');
  assert.equal(controller.prepareDraft('mybots-sage', '새 조사'), false);
  assert.equal(controller.getSnapshot().draft, '기존 업무 원문');
  assert.equal(controller.getSnapshot().selectedAssistant, 'lumi');
  const restored = createAssistantRequestsController();
  restored.restore('aa3a151d-72e8-4abf-b09d-10d416279c41');
  assert.equal(restored.prepareDraft('mybots-sage', '새 조사'), false);
  assert.equal(restored.getSnapshot().submission?.text, '');
  const empty = createAssistantRequestsController();
  assert.equal(empty.prepareDraft('mybots-sage', '가'.repeat(4001)), false);
  assert.equal(empty.getSnapshot().draft, '');
});
