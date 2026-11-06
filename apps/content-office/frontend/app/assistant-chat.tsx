'use client';

import { useCallback, useEffect, useId, useLayoutEffect, useRef, useState, useSyncExternalStore } from 'react';
import Link from 'next/link';
import { useRouter } from 'next/navigation';
import { assistantDraftLimit, assistantNames, createAssistantRequestsController, initialAssistantRequestId, isAssistantProfile, parseAssistantContent } from '../lib/assistant-requests.ts';
import type { AssistantContent, AssistantDelivery, AssistantProfile, AssistantRequest, AssistantSubmission } from '../lib/assistant-requests.ts';
import { matchesAssistantReportRef } from '../lib/world-bridge.ts';
import { officeHref } from '../lib/navigation.ts';
import { api } from '../lib/api.ts';

const statusText = { queued: '접수 확인·담당 배정 대기', running: '실제 비서가 처리 중', blocked: '추가 확인이 필요합니다', completed: '처리 결과 확인', failed: '처리하지 못했습니다' };
const eventText: Record<string, string> = { created: '업무 등록', claimed: '담당 접수', spawned: '비서 실행', completed: '업무 완료 기록', blocked: '확인 대기', crashed: '실행 중단', worker_result: '실행 결과 수신', dependency_wait: '앞 업무 대기' };
const storageKey = 'heobrain.assistant-request.v1';
function slackStatus(delivery: AssistantDelivery) {
  const labels = { watching: '상태 알림 등록됨 · 수신 확인 전', pending: '알림 처리 중 · 수신 확인 전', sent_unverified: '전송 기록 있음 · 수신 확인 전',
    confirmed: delivery.external_delivery_verified ? '상태 알림 수신 확인' : '수신 근거 확인 중', unknown: '전송 결과 확인 중 · 자동 재전송 없음',
    not_attached: '상태 알림 연결 전', failed: '알림 확인 필요', privacy_review_required: '전달 정보 검토 필요' };
  return labels[delivery.slack] + (delivery.error_code === 'status_sender_disabled' ? ' · 상태 알림 전송 설정이 필요합니다' : delivery.error_code ? ' · 알림 상태 검토 필요' : '');
}

function SaveAssistantContent({ busy, pending, onSave }: { busy: boolean; pending: boolean; onSave?: () => Promise<string | null> }) {
  const router = useRouter();
  return <button type="button" className="button" style={{ minHeight: 44 }} disabled={busy || !onSave} onClick={async () => {
    if (busy || !onSave) return;
    const jobId = await onSave();
    if (jobId) router.push(officeHref('studio', jobId));
  }}>{pending ? '원고 저장 확인 중…' : '원고 저장하고 작업실 열기'}</button>;
}

export function AssistantCompletion({ request, busy, onAction, onSaveContent, contentPending = false, contentError }: {
  request: AssistantRequest; busy: boolean; onAction: (action: 'visit' | 'result') => void;
  onSaveContent?: () => Promise<string | null>;
  contentPending?: boolean; contentError?: string | null;
}) {
  const report = request.report;
  if (!report || !matchesAssistantReportRef({ request_id: request.request_id, task_id: report.task_id, run_id: report.run_id, event_id: report.event_id }, request)) return null;
  let content: AssistantContent | undefined;
  try { if (request.content) content = parseAssistantContent(request.content, request); } catch { /* Keep an invalid optional link out of the verified report. */ }
  return <section aria-label="검증된 비서 보고">
    <h3>루미의 완료 보고</h3>
    {content && <section aria-label="콘텐츠 원고 연결">
      <h4>{content.title}</h4><p className="muted">본문 {content.body_length.toLocaleString('ko-KR')}자</p>
      {contentPending && <p role="status">현재 완료 보고의 원고 저장 결과를 확인하고 있습니다.</p>}
      {contentError && <p role="alert">{contentError}</p>}
      {content.job?.state === 'deleted' ? <p role="status">원고를 복원한 뒤 열 수 있습니다. 기존 완료 보고는 보존됩니다.</p> : content.job ? <>
        <p>원고 저장됨 · 원고 승인①·제작·출고 승인② 상태는 별도입니다.</p>
        {content.job.source_hash !== content.job.current_source_hash && <p role="status">연결 후 수정됨 · 작업실에서 현재 판본을 확인하세요.</p>}
        <div style={{ display: 'flex', gap: 8, flexWrap: 'wrap' }}>
          <Link className="button" style={{ minHeight: 44 }} href={officeHref('studio', content.job.id)} prefetch={false}>원고 작업실 열기</Link>
          <Link className="button secondary" style={{ minHeight: 44 }} href={officeHref('delivery', content.job.id)} prefetch={false}>제작·출고함 보기</Link>
        </div>
      </> : <><p className="muted">완료 보고의 원고를 승인 전 콘텐츠 작업으로 저장할 수 있습니다. 원고와 보고는 그대로 보존합니다.</p><SaveAssistantContent busy={busy} pending={contentPending} onSave={onSaveContent} /></>}
    </section>}
    <p>{report.summary}</p>
    <p className="muted">업무 {report.task_id} · 실행 {report.run_id} · 완료 기록 {report.event_id}</p>
    <div style={{ display: 'flex', gap: 8, flexWrap: 'wrap' }}>
      <button type="button" className="button" disabled={busy} onClick={() => onAction('visit')}>작업실로 이동</button>
      <button type="button" className="button secondary" disabled={busy} onClick={() => onAction('result')}>결과물 열기</button>
    </div>
    <p className="muted">생활 비서 팀의 비서 업무실과 이 업무의 완료 보고를 엽니다. 콘텐츠 파일·첨부는 연결이 확인된 경우에만 열 수 있습니다.</p>
  </section>;
}

export function AssistantChat({ connected, openSignal, requestedAssistant = 'lumi', preparedDraft = '', createRequest, loadRequest, onObservation, onReportAction, onReportOpened }: {
  connected: boolean; openSignal: number;
  requestedAssistant?: AssistantProfile;
  preparedDraft?: string;
  createRequest: (body: AssistantSubmission) => Promise<unknown>;
  loadRequest: (id: string) => Promise<unknown>;
  onObservation: (request: AssistantRequest) => void;
  onReportAction?: (request: AssistantRequest, action: 'visit' | 'result') => Promise<string>;
  onReportOpened?: () => void;
}) {
  const [controller] = useState(createAssistantRequestsController);
  const state = useSyncExternalStore(controller.subscribe, controller.getSnapshot, controller.getSnapshot);
  const [open, setOpen] = useState(false);
  const [targetNotice, setTargetNotice] = useState<string | null>(null);
  const [reportBusy, setReportBusy] = useState(false), [reportNotice, setReportNotice] = useState<string | null>(null);
  const dialog = useRef<HTMLDialogElement>(null), trigger = useRef<HTMLButtonElement>(null), input = useRef<HTMLTextAreaElement>(null);
  const previousFocus = useRef<HTMLElement | null>(null), lastSignal = useRef(0), latestObservation = useRef(onObservation);
  const desiredAssistant = useRef<AssistantProfile>('lumi');
  const closingForReport = useRef(false);
  const readReport = useRef<string | null>(null), latestReport = useRef<string | null>(null);
  const reportKey = state.request?.report?.verified ? `${state.request.request_id}:${state.request.report.task_id}:${state.request.report.run_id}:${state.request.report.event_id}` : null;
  const heading = useId(), inputId = useId(), help = useId();
  useLayoutEffect(() => {
    controller.setAvailability(connected, open); latestObservation.current = onObservation; latestReport.current = reportKey;
    if (open && reportKey) readReport.current = reportKey;
  }, [controller, connected, open, onObservation, reportKey]);
  useEffect(() => () => { controller.setAvailability(false, false); }, [controller]);
  useEffect(() => {
    let saved: string | null = null;
    try { saved = sessionStorage.getItem(storageKey); } catch { /* 저장소 없이도 명시된 요청을 조회할 수 있다. */ }
    const requestId = initialAssistantRequestId(window.location?.search || '', saved);
    if (!requestId) return;
    controller.restore(requestId);
    if (controller.getSnapshot().submission?.request_id === requestId && saved !== requestId) {
      try { sessionStorage.setItem(storageKey, requestId); } catch { /* 요청 UUID만 현재 화면에 유지한다. */ }
    }
  }, [controller]);
  const show = useCallback(() => {
    previousFocus.current = document.activeElement instanceof HTMLElement ? document.activeElement : null;
    dialog.current?.showModal(); readReport.current = latestReport.current; setOpen(true); input.current?.focus();
  }, []);
  const requestChat = useCallback((assistant: AssistantProfile) => {
    desiredAssistant.current = assistant;
    const selected = controller.selectAssistant(assistant);
    setTargetNotice(!selected && assistant !== controller.getSnapshot().selectedAssistant
      ? `${assistantNames[assistant]}에게 말걸기를 선택했습니다. 기존 업무와 입력을 보존했으니, 확인 후 ‘새 업무 작성’을 누르면 이 비서에게 요청할 수 있습니다.` : null);
    if (!dialog.current?.open) show();
  }, [controller, show]);
  useEffect(() => {
    if (openSignal <= lastSignal.current) return;
    lastSignal.current = openSignal;
    if (preparedDraft) {
      desiredAssistant.current = requestedAssistant;
      setTargetNotice(controller.prepareDraft(requestedAssistant, preparedDraft) ? null
        : '기존 업무와 입력·배정 대상을 보존했습니다. 기존 업무를 확인한 뒤 새 업무를 작성하거나, 조사 화면에서 요청문을 복사해 주세요. 자동으로 접수하지 않습니다.');
      if (!dialog.current?.open) show();
    } else requestChat(requestedAssistant);
  }, [openSignal, requestedAssistant, preparedDraft, controller, requestChat, show]);
  useEffect(() => { if (state.request && connected) latestObservation.current(state.request); }, [state.request, connected]);
  const requestId = state.submission?.request_id;
  const delivery = state.request?.delivery || state.receipt?.delivery;
  const waitingForSlack = delivery && (['watching', 'pending', 'sent_unverified', 'unknown'].includes(delivery.slack) || (delivery.slack === 'confirmed' && !delivery.external_delivery_verified));
  const settled = Boolean(state.noAdmissionCode) || state.request?.native_status === 'archived' || (state.request?.report?.verified === true && !waitingForSlack);
  const pollDelay = state.request?.report?.verified || state.request?.status === 'blocked' || state.request?.status === 'failed' ? 30_000 : 2500;
  const draftLimit = assistantDraftLimit(state.selectedAssistant);
  async function openReport(action: 'visit' | 'result') {
    if (reportBusy || !state.request) return;
    setReportBusy(true); setReportNotice(null);
    try {
      if (!onReportAction) throw new Error('작업실 연결을 확인할 수 없습니다. 기존 보고는 보존했습니다.');
      await onReportAction(state.request, action);
      if (dialog.current?.open) { closingForReport.current = true; dialog.current.close(); }
      else onReportOpened?.();
    } catch (cause) {
      setReportNotice(cause instanceof Error ? cause.message : '작업실을 열지 못했습니다. 기존 보고는 보존했습니다.');
    } finally { setReportBusy(false); }
  }
  async function saveContent() {
    const saved = await controller.saveContent(api.saveAssistantContentJob);
    if (!saved?.job || !dialog.current?.open) return null;
    dialog.current.close();
    return saved.job.id;
  }
  useEffect(() => {
    if (!connected || !requestId || settled) return;
    const refresh = () => { if (!document.hidden) void controller.refresh(loadRequest); };
    const timer = window.setInterval(refresh, pollDelay);
    refresh(); document.addEventListener('visibilitychange', refresh);
    return () => { window.clearInterval(timer); document.removeEventListener('visibilitychange', refresh); };
  }, [controller, connected, requestId, settled, pollDelay, loadRequest]);
  const request = state.request;
  return <section className="panel" aria-label="실제 비서에게 업무 맡기기" style={{ minWidth: 0, overflowWrap: 'anywhere' }}>
    <h2>루미에게 업무 맡기기</h2>
    <p className="muted">요청을 보내면 실제 업무판에서 접수·협업·결과를 확인합니다. 아래 콘텐츠 역할 9개와 별도의 비서입니다.</p>
    <button ref={trigger} type="button" className="button" onClick={() => requestChat('lumi')}>루미와 대화하기</button>
    <div aria-live="polite">{request?.report?.verified && reportKey !== readReport.current && !open ? <p>루미의 완료 보고가 도착했습니다. <button type="button" className="button secondary" onClick={show}>보고 열기</button></p> : request && <p className="muted">{statusText[request.status]} · {assistantNames[request.assignee]}</p>}{delivery && <p className="muted">Slack 알림: {slackStatus(delivery)}</p>}</div>
    <dialog ref={dialog} className="job-trash-dialog" aria-labelledby={heading} style={{ width: 'min(42rem, calc(100vw - 2rem))', maxHeight: '85dvh', overflowY: 'auto', boxSizing: 'border-box' }}
      onClose={() => {
        controller.setAvailability(connected, false);
        setOpen(false); const reportOpened = closingForReport.current; closingForReport.current = false;
        requestAnimationFrame(() => {
          if (dialog.current?.open) return;
          if (reportOpened) onReportOpened?.();
          else (previousFocus.current?.isConnected ? previousFocus.current : trigger.current)?.focus();
        });
      }}>
      <div style={{ display: 'flex', flexWrap: 'wrap', justifyContent: 'space-between', gap: 12 }}>
        <h2 id={heading}>{state.selectedAssistant === 'lumi' ? '루미와 대화' : `${assistantNames[state.selectedAssistant]}에게 업무 요청`}</h2>
        <button type="button" className="button secondary" onClick={() => dialog.current?.close()}>닫기</button>
      </div>
      <p id={help} className="muted">무엇을 확인하고 어떤 결과를 받을지 적어 주세요. 루미가 실제 비서 업무판에 접수합니다. 콘텐츠 원고 승인①·출고②와 유료 제작·게시에는 기존 검토가 필요합니다.</p>
      {state.selectedAssistant !== 'lumi' && <p className="muted">{assistantNames[state.selectedAssistant]}에게 배정을 요청합니다. 루미가 접수·배정을 조율하며 실제 담당과 결과는 협업 기록으로 확인합니다.</p>}
      {targetNotice && <p role="status">{targetNotice}</p>}
      <form onSubmit={event => { event.preventDefault(); void controller.submit(createRequest, () => { const uuid = crypto.randomUUID(); try { sessionStorage.setItem(storageKey, uuid); } catch { /* 현재 화면의 요청 ID는 유지한다. */ } return uuid; }); }}>
        <label htmlFor={inputId}>맡길 업무</label>
        <textarea id={inputId} ref={input} value={state.draft} maxLength={draftLimit} rows={5} readOnly={Boolean(state.submission)} aria-describedby={help}
          style={{ width: '100%', minHeight: 140, fontSize: 16, boxSizing: 'border-box' }} onChange={event => controller.setDraft(event.target.value)} placeholder="예: 오늘 확인할 자료를 정리하고, 출처와 확인하지 못한 부분을 알려 주세요." />
        <p className="muted">{[...state.draft].length} / {draftLimit.toLocaleString('ko-KR')}자{state.selectedAssistant !== 'lumi' ? ' · 비서 배정 안내를 포함해 총 4,000자까지' : ''}</p>
        {[...state.draft].length > draftLimit && <p role="alert">선택한 비서의 배정 안내를 포함하면 4,000자를 넘습니다. 입력을 줄여 주세요. 자동으로 잘라 보내지 않습니다.</p>}
        {state.submission && !state.submission.text && <p className="muted">기존 요청의 상태를 복원했습니다. 새로고침 전 입력 원문은 브라우저에 저장하지 않습니다.</p>}
        <button className="button" type="submit" disabled={!connected || state.pending || Boolean(state.submission) || !state.draft.trim() || [...state.draft].length > draftLimit}>실제 비서에게 보내기</button>
      </form>
      {!connected && <p role="status">오피스 연결을 확인해 주세요. 입력은 보존되며 요청을 보내지 않습니다.</p>}
      <div aria-live="polite" aria-busy={state.pending} style={{ whiteSpace: 'pre-wrap', overflowWrap: 'anywhere' }}>
        {state.pending && <p role="status">{requestId ? '접수·업무 상태를 확인하고 있습니다.' : '요청을 보내고 있습니다.'}</p>}
        {state.error && <p role="alert">{state.error}</p>}
        {state.noAdmissionCode && <div>
          <p role="status">이번 요청은 비서에게 접수되지 않았습니다. 입력을 보존했으며 자동으로 다시 보내지 않습니다.</p>
          {state.submission?.text && <button type="button" className="button secondary" disabled={!connected || state.pending} onClick={() => { void controller.retrySubmission(createRequest); }}>같은 요청 번호로 다시 보내기</button>}
          <button type="button" className="button secondary" disabled={state.pending} onClick={() => {
            if (controller.editRejectedRequest()) { try { sessionStorage.removeItem(storageKey); } catch { /* 입력 원문은 현재 화면에만 보존한다. */ } requestAnimationFrame(() => input.current?.focus()); }
          }}>입력 고치기</button>
        </div>}
        {state.submission && <p className="muted">요청 번호: {state.submission.request_id}</p>}
        {delivery && <p className="muted">Slack 알림: {slackStatus(delivery)}</p>}
        {request && <>
          <h3>{statusText[request.status]}</h3>
          <p>{isAssistantProfile(request.assignee) ? assistantNames[request.assignee] : 'Hermes'} · {request.title}</p>
          <p className="muted">업무 번호: {request.native_task_id || '접수 여부 확인 중'} · 실제 상태: {request.native_status || '확인 중'}</p>
          {request.error && <p role="status">{request.error.code === 'native_admission_unknown' ? '접수 여부를 확인하고 있습니다. 같은 요청을 새로 보내지 않습니다.' : request.error.message}</p>}
          {request.status === 'blocked' && <p>아래 사유와 기존 업무 번호를 확인한 뒤 필요한 내용을 보완하세요. 자동으로 다시 실행하지 않습니다.</p>}
          {request.status === 'failed' && <p>기존 요청과 입력을 보존했습니다. 실제 업무판의 오류를 확인한 뒤 다음 요청을 결정하세요.</p>}
          {request.events.length > 0 && <details><summary>실제 협업 기록 {request.events.length}개</summary><ol>{request.events.slice(-30).map(event => <li key={event.id}>{assistantNames[event.assignee]} · {eventText[event.kind] || '업무 상태 변경'} · {event.task_id} · 기록 {event.id}</li>)}</ol></details>}
          {request.report?.verified ? <AssistantCompletion request={request} busy={reportBusy || state.contentPending || !connected} onAction={action => { void openReport(action); }} onSaveContent={saveContent} contentPending={state.contentPending} contentError={state.contentError} /> : request.status === 'completed' ? <p>완료 근거를 확인하는 중입니다. 확인 전에는 완료 보고로 표시하지 않습니다.</p> : null}
          {reportBusy && <p role="status">최신 완료 기록과 작업실 연결을 확인하고 있습니다.</p>}
          {reportNotice && <p role="alert">{reportNotice}</p>}
        </>}
      </div>
      {requestId && <button type="button" className="button secondary" disabled={!connected || state.pending} onClick={() => { void controller.refresh(loadRequest); }}>같은 요청 상태 확인</button>}
      {settled && !state.noAdmissionCode && <button type="button" className="button secondary" disabled={state.pending || reportBusy} onClick={() => { if (controller.newRequest()) { controller.selectAssistant(desiredAssistant.current); if (preparedDraft) controller.prepareDraft(desiredAssistant.current, preparedDraft); setTargetNotice(null); setReportNotice(null); try { sessionStorage.removeItem(storageKey); } catch { /* 현재 화면은 새 요청을 작성한다. */ } input.current?.focus(); } }}>새 업무 작성</button>}
    </dialog>
  </section>;
}
