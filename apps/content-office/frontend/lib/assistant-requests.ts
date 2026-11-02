export type AssistantSubmission = { request_id: string; text: string; assignee: 'lumi' };
export type AssistantEvent = { id: number; task_id: string; run_id: number | null; kind: string; created_at: string | number; assignee: AssistantProfile };
export type AssistantNoticeRef = { request_id: string; task_id: string; run_id: number; event_id: number; terminal_state: 'completed' | 'blocked' };
export type AssistantDelivery = { slack: 'watching' | 'pending' | 'sent_unverified' | 'confirmed' | 'unknown' | 'not_attached' | 'failed' | 'privacy_review_required'; external_delivery_verified: boolean; error_code?: string | null; notice_ref?: AssistantNoticeRef | null };
export type AssistantAccepted = { request_id: string; native_task_id: string | null; board: 'heobrain-office'; status: 'queued' | 'running' | 'blocked' | 'completed' | 'failed'; delivery?: AssistantDelivery };
export type AssistantRequest = AssistantAccepted & {
  native_status: string | null; assignee: AssistantProfile; title: string; updated_at: string | number; current_run_id: number | null;
  events: AssistantEvent[];
  report: null | { summary: string; verified: boolean; task_id: string; run_id: number; event_id: number };
  error: null | { code: string; message: string };
};
export const assistantNames = { lumi: '루미', ada: '에이다', ethan: '이든', mia: '미아', noah: '노아', oliver: '올리버', sam: '샘', 'mybots-sage': '세이지', default: 'Hermes' } as const;
export type AssistantProfile = keyof typeof assistantNames;
export function isAssistantProfile(value: unknown): value is AssistantProfile {
  return typeof value === 'string' && Object.hasOwn(assistantNames, value);
}
export function assistantSubmissionText(assistant: AssistantProfile, draft: string): string {
  if (!isAssistantProfile(assistant)) return invalid();
  if (assistant === 'lumi') return draft;
  const name = assistantNames[assistant];
  return `[배정 요청: ${name} (${assistant})]\n아래 업무를 ${name}에게 배정해 주세요. 배정할 수 없으면 이유를 보고해 주세요.\n\n${draft}`;
}
export function assistantDraftLimit(assistant: AssistantProfile): number {
  return 4000 - [...assistantSubmissionText(assistant, '')].length;
}
const states = ['queued', 'running', 'blocked', 'completed', 'failed'];
const uuidPattern = /^[0-9a-f]{8}-[0-9a-f]{4}-[1-8][0-9a-f]{3}-[89ab][0-9a-f]{3}-[0-9a-f]{12}$/i;
export function initialAssistantRequestId(search: string, saved: string | null): string | null {
  const linked = new URLSearchParams(search).getAll('assistant_request');
  if (linked.length) return linked.length === 1 && uuidPattern.test(linked[0]) ? linked[0].toLowerCase() : null;
  return saved && uuidPattern.test(saved) ? saved.toLowerCase() : null;
}
const invalid = () => { throw new Error('비서 업무 응답을 확인할 수 없습니다.'); };
const object = (value: unknown): Record<string, unknown> => value && typeof value === 'object' && !Array.isArray(value) ? value as Record<string, unknown> : invalid();
function text(value: unknown, limit = 300): string {
  if (typeof value !== 'string' || !value.trim() || [...value].length > limit || /[\u0000-\u0008\u000b\u000c\u000e-\u001f\u007f\u202a-\u202e\u2066-\u2069]|(?:\/|%2f)(?:home|users|mnt|tmp|etc|root|var)(?:\/|%2f)|[a-z]:[\\/]|\.\.[\\/]|bearer\s|(?:api[_-]?key|password|secret|token)\s*[:=]|sk-[a-z0-9]{12,}/i.test(value)) return invalid();
  return value;
}
const id = (value: unknown): string => { const s = text(value, 120); return /^[a-zA-Z0-9][a-zA-Z0-9_-]*$/.test(s) ? s : invalid(); };
const integer = (value: unknown): number => typeof value === 'number' && Number.isSafeInteger(value) && value > 0 ? value : invalid();
const profile = (value: unknown): AssistantProfile => isAssistantProfile(value) ? value : invalid();
function noticeRef(value: unknown, expected: string): AssistantNoticeRef | null | undefined {
  if (value === undefined || value === null) return value;
  const row = object(value);
  if (Object.keys(row).length !== 5 || !['request_id', 'task_id', 'run_id', 'event_id', 'terminal_state'].every(key => Object.hasOwn(row, key))
    || row.request_id !== expected || (row.terminal_state !== 'completed' && row.terminal_state !== 'blocked')) return invalid();
  return { request_id: expected, task_id: id(row.task_id), run_id: integer(row.run_id), event_id: integer(row.event_id), terminal_state: row.terminal_state };
}
function delivery(value: unknown, expected: string): AssistantDelivery | undefined {
  if (value === undefined) return undefined;
  const row = object(value), slack = row.slack;
  if (!['watching', 'pending', 'sent_unverified', 'confirmed', 'unknown', 'not_attached', 'failed', 'privacy_review_required'].includes(String(slack))) return invalid();
  const verified = row.external_delivery_verified === undefined && slack === 'not_attached' ? false : row.external_delivery_verified;
  if (typeof verified !== 'boolean' || (verified && slack !== 'confirmed')) return invalid();
  if (row.error_code !== undefined && row.error_code !== null && (typeof row.error_code !== 'string' || !/^[a-z][a-z0-9_]{0,79}$/.test(row.error_code))) return invalid();
  const reference = noticeRef(row.notice_ref, expected);
  if (verified && !reference) return invalid();
  return { slack: slack as AssistantDelivery['slack'], external_delivery_verified: verified,
    ...(row.error_code === undefined ? {} : { error_code: row.error_code as string | null }),
    ...(reference === undefined ? {} : { notice_ref: reference }) };
}
function accepted(value: unknown, expected: string): AssistantAccepted {
  const row = object(value);
  if (row.request_id !== expected || !uuidPattern.test(expected) || row.board !== 'heobrain-office' || !states.includes(String(row.status))) return invalid();
  const safeDelivery = delivery(row.delivery, expected);
  if (safeDelivery?.external_delivery_verified && row.status !== 'completed' && row.status !== 'blocked') return invalid();
  return { request_id: expected, native_task_id: row.native_task_id === null ? null : id(row.native_task_id), board: 'heobrain-office', status: row.status as AssistantAccepted['status'],
    ...(safeDelivery ? { delivery: safeDelivery } : {}) };
}
export function parseAssistantRequest(value: unknown, expected: string): AssistantRequest {
  const row = object(value), receipt = accepted(row, expected);
  if (!Array.isArray(row.events) || row.events.length > 200) return invalid();
  const seen = new Set<number>();
  const events = row.events.map(raw => {
    const e = object(raw), eventId = integer(e.id);
    if (seen.has(eventId)) return invalid(); seen.add(eventId);
    if (typeof e.created_at !== 'number' && typeof e.created_at !== 'string') return invalid();
    const created = typeof e.created_at === 'number' ? integer(e.created_at) : text(e.created_at, 50);
    return { id: eventId, task_id: id(e.task_id), run_id: e.run_id === null ? null : integer(e.run_id), kind: id(e.kind), created_at: created, assignee: profile(e.assignee) };
  });
  let report: AssistantRequest['report'] = null;
  if (row.report !== null) {
    const r = object(row.report);
    if (typeof r.verified !== 'boolean') return invalid();
    report = { summary: text(r.summary, 6000), verified: r.verified, task_id: id(r.task_id), run_id: integer(r.run_id), event_id: integer(r.event_id) };
    if (report.verified && (receipt.status !== 'completed' || row.native_status !== 'done' || !events.some(e => e.id === report!.event_id && e.task_id === report!.task_id && e.run_id === report!.run_id && e.kind === 'completed' && e.assignee === 'lumi'))) return invalid();
  }
  const error = row.error === null ? null : object(row.error);
  if (receipt.delivery?.external_delivery_verified) {
    const notice = receipt.delivery.notice_ref!;
    const match = events.some(event => event.task_id === notice.task_id && event.run_id === notice.run_id && event.id === notice.event_id
      && event.kind === (notice.terminal_state === 'completed' ? 'completed' : 'blocked'));
    const current = receipt.status === 'completed' ? report?.verified && row.native_status === 'done' && notice.terminal_state === 'completed'
      && report.task_id === notice.task_id && report.run_id === notice.run_id && report.event_id === notice.event_id
      : receipt.status === 'blocked' && row.native_status === 'blocked' && notice.terminal_state === 'blocked';
    if (!match || !current) return invalid();
  }
  return { ...receipt, native_status: row.native_status === null ? null : id(row.native_status), assignee: profile(row.assignee), title: text(row.title, 160), updated_at: typeof row.updated_at === 'number' ? integer(row.updated_at) : text(row.updated_at, 50), current_run_id: row.current_run_id === null ? null : integer(row.current_run_id), events, report,
    error: error ? { code: id(error.code), message: text(error.message, 400) } : null };
}

type NoAdmissionCode = 'native_preflight_failed' | 'assistant_not_configured' | 'unsafe_request_body';
const noAdmissionCode = (error: unknown): NoAdmissionCode | null => {
  const code = (error as { code?: unknown })?.code;
  return code === 'native_preflight_failed' || code === 'assistant_not_configured' || code === 'unsafe_request_body' ? code : null;
};
type State = { draft: string; selectedAssistant: AssistantProfile; submission: AssistantSubmission | null; receipt: AssistantAccepted | null; request: AssistantRequest | null; pending: boolean; error: string | null; noAdmissionCode: NoAdmissionCode | null };
export function createAssistantRequestsController() {
  let state: State = { draft: '', selectedAssistant: 'lumi', submission: null, receipt: null, request: null, pending: false, error: null, noAdmissionCode: null };
  let connected = false, open = false, generation = 0, busy = false;
  const listeners = new Set<() => void>();
  const publish = (patch: Partial<State>) => { state = { ...state, ...patch }; listeners.forEach(fn => fn()); };
  const failure = (error: unknown) => (error as { status?: number })?.status === 503 ? '비서 연결 설정이 필요합니다. 입력은 보존했습니다. 연결 후 같은 요청의 접수 여부를 확인하세요.' : '요청의 접수 여부를 확인하지 못했습니다. 입력을 보존했으며 같은 요청 번호로 확인합니다.';
  const send = async (create: (input: AssistantSubmission) => Promise<unknown>, submission: AssistantSubmission) => {
    busy = true; const currentGeneration = generation;
    publish({ submission, pending: true, request: null, error: null, noAdmissionCode: null });
    try { const receipt = accepted(await create(submission), submission.request_id); if (generation === currentGeneration) publish({ receipt }); }
    catch (error) { if (generation === currentGeneration) publish({ error: failure(error), noAdmissionCode: noAdmissionCode(error) }); }
    finally { busy = false; publish({ pending: false }); }
  };
  return {
    getSnapshot: () => state,
    subscribe(fn: () => void) { listeners.add(fn); return () => { listeners.delete(fn); }; },
    setDraft(draft: string) { if (!state.submission) publish({ draft }); },
    selectAssistant(assistant: unknown) {
      if (!isAssistantProfile(assistant) || busy || state.pending || state.submission) return false;
      publish({ selectedAssistant: assistant });
      return true;
    },
    setAvailability(nextConnected: boolean, nextOpen: boolean) { if (connected !== nextConnected) generation++; connected = nextConnected; open = nextOpen; },
    restore(requestId: string) { if (!uuidPattern.test(requestId)) return invalid(); if (!state.submission && !state.draft) publish({ submission: { request_id: requestId, text: '', assignee: 'lumi' } }); },
    newRequest() {
      if (busy || (state.submission && !state.noAdmissionCode && !['blocked', 'failed', 'completed'].includes(state.request?.status || ''))) return false;
      publish({ draft: '', selectedAssistant: 'lumi', submission: null, receipt: null, request: null, error: null, noAdmissionCode: null });
      return true;
    },
    editRejectedRequest() {
      if (busy || !state.noAdmissionCode || !state.submission) return false;
      publish({ submission: null, receipt: null, request: null, error: null, noAdmissionCode: null });
      return true;
    },
    async submit(create: (input: AssistantSubmission) => Promise<unknown>, uuid: () => string) {
      if (!connected || !open || busy || state.submission || !state.draft.trim() || [...state.draft].length > assistantDraftLimit(state.selectedAssistant)) return;
      const submission: AssistantSubmission = { request_id: uuid(), text: assistantSubmissionText(state.selectedAssistant, state.draft), assignee: 'lumi' };
      await send(create, submission);
    },
    async retrySubmission(create: (input: AssistantSubmission) => Promise<unknown>) {
      if (!connected || !open || busy || !state.noAdmissionCode || !state.submission?.text) return;
      await send(create, state.submission);
    },
    async refresh(read: (id: string) => Promise<unknown>) {
      if (!connected || busy || !state.submission) return;
      busy = true; const currentGeneration = generation, requestId = state.submission.request_id;
      publish({ pending: true });
      try {
        const request = parseAssistantRequest(await read(requestId), requestId);
        if (generation === currentGeneration) publish({ request, error: null,
          noAdmissionCode: request.native_status === 'not_submitted' ? noAdmissionCode(request.error) : null });
      }
      catch (error) { if (generation === currentGeneration) publish({ error: failure(error) }); }
      finally { busy = false; publish({ pending: false }); }
    },
  };
}
