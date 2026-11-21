const views = new Set(['news', 'studio', 'delivery', 'activity']);
const profiles = new Set(['lumi', 'ada', 'ethan', 'mia', 'noah', 'oliver', 'sam', 'mybots-sage', 'default']);
const refKeys = ['request_id', 'task_id', 'run_id', 'event_id'];

export function parseReportAction(value) {
  if (!value || typeof value !== 'object' || Array.isArray(value)) return null;
  const keys = ['source', 'type', 'action', ...refKeys];
  if (Object.keys(value).length !== keys.length || keys.some(key => !Object.hasOwn(value, key))
    || value.source !== 'content-office' || value.type !== 'assistant-report-action'
    || !['visit', 'result'].includes(value.action)
    || typeof value.request_id !== 'string' || !/^[0-9a-f]{8}-[0-9a-f]{4}-[1-8][0-9a-f]{3}-[89ab][0-9a-f]{3}-[0-9a-f]{12}$/i.test(value.request_id)
    || typeof value.task_id !== 'string' || !/^t_[a-zA-Z0-9_-]{1,80}$/.test(value.task_id)
    || !Number.isSafeInteger(value.run_id) || value.run_id <= 0
    || !Number.isSafeInteger(value.event_id) || value.event_id <= 0) return null;
  return value;
}

export function matchesCompletedReport(action, request) {
  const ref = parseReportAction(action), report = request?.report;
  return Boolean(ref && request?.board === 'heobrain-office' && request.status === 'completed'
    && request.native_status === 'done' && report?.verified === true
    && request.request_id === ref.request_id && report.task_id === ref.task_id
    && report.run_id === ref.run_id && report.event_id === ref.event_id
    && typeof report.summary === 'string' && report.summary.trim()
    && Array.isArray(request.events) && request.events.some(event => event?.task_id === ref.task_id
      && event.run_id === ref.run_id && event.id === ref.event_id && event.kind === 'completed' && event.assignee === 'lumi'));
}

/** Only navigation and matching report receipts cross this bridge. No execution requests. */
export function createOfficeBridge({ onFocus, onRefresh, onObservation, onReportAction, onToast } = {}) {
  let observed = null;
  let previousFocus = null;
  const dialog = document.createElement('dialog');
  dialog.className = 'shell-dialog native-report-dialog';
  dialog.setAttribute('aria-labelledby', 'native-report-title');
  const heading = document.createElement('h2');
  heading.id = 'native-report-title';
  heading.textContent = '루미 완료 보고';
  const close = document.createElement('button');
  close.type = 'button'; close.className = 'native-report-close'; close.textContent = '닫기';
  close.setAttribute('aria-label', '루미 완료 보고 닫기');
  const title = document.createElement('p');
  const body = document.createElement('pre');
  body.className = 'native-report-body';
  const note = document.createElement('p');
  note.textContent = '같은 요청·실행·완료 이벤트가 확인된 보고입니다. 공개·출고 승인과는 별개입니다.';
  dialog.append(heading, close, title, body, note);
  document.body.append(dialog);
  close.addEventListener('click', () => dialog.close());
  dialog.addEventListener('close', () => { if (previousFocus?.isConnected) previousFocus.focus(); });

  const send = message => {
    if (window.parent === window) { onToast?.('기존 오피스 화면 안에서 사용할 수 있습니다.'); return false; }
    window.parent.postMessage({ source: 'office-world', ...message }, window.location.origin);
    return true;
  };
  const receive = event => {
    if (event.origin !== window.location.origin || event.source !== window.parent || event.data?.source !== 'content-office') return;
    const value = event.data;
    if (value.type === 'focus' && typeof value.itemId === 'string') onFocus?.({ itemId: value.itemId });
    else if (value.type === 'refresh') onRefresh?.();
    else if (value.type === 'assistant-observation') {
      // Do not poll a request here: the existing request endpoint can attach delivery watches.
      observed = value.request ?? null;
      onObservation?.({ status: observed?.status ?? 'unknown' });
    } else if (value.type === 'assistant-report-action') {
      const action = parseReportAction(value);
      if (!action) return;
      let ok = false;
      if (matchesCompletedReport(action, observed)) {
        try {
          title.textContent = typeof observed.title === 'string' ? observed.title : '완료 보고';
          body.textContent = observed.report.summary;
          previousFocus = document.activeElement;
          if (!dialog.open) dialog.showModal();
          ok = dialog.open && body.textContent === observed.report.summary;
        } catch { ok = false; }
      }
      const ref = Object.fromEntries(refKeys.map(key => [key, action[key]]));
      send({ type: 'assistant-report-result', action: action.action, ...ref, ok,
        message: ok ? '같은 실행의 완료 보고를 열었습니다.' : '현재 요청과 완료 근거가 일치하지 않아 보고를 열지 않았습니다.' });
      if (ok) onReportAction?.({ action: action.action });
    }
  };
  window.addEventListener('message', receive);
  send({ type: 'ready' });
  return {
    open(view, itemId = '') { return views.has(view) && typeof itemId === 'string' ? send({ type: 'open', view, itemId }) : false; },
    openAssistant(assistant = 'lumi') { return profiles.has(assistant) ? send({ type: 'assistant-open', assistant }) : false; },
    destroy() { window.removeEventListener('message', receive); if (dialog.open) dialog.close(); dialog.remove(); observed = null; }
  };
}
