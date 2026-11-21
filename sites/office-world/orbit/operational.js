const object = value => value !== null && typeof value === 'object' && !Array.isArray(value);
const numeric = value => typeof value === 'number' && Number.isFinite(value) && value >= 0 ? value : null;
const strings = value => Array.isArray(value) ? value.filter(item => typeof item === 'string').map(item => safeText(item)) : [];
const checkedTime = value => typeof value === 'string' && Number.isFinite(Date.parse(value)) ? value : null;
const badSchema = () => new Error('응답 형식을 확인하지 못했습니다. 마지막 정상 결과를 유지합니다.');
const blockedStates = new Set(['blocked', 'source_rejected', 'failed']);
const approvalStates = new Set(['source_review', 'release_review', 'partial_release_review']);
const labels = { source_review: '① 원고 검토 대기', release_review: '② 출고 검토 대기', partial_release_review: '② 일부 출력 검토 대기', research_ready: '조사 준비', source_rejected: '원고 수정 필요', source_approved: '원고 승인 기록', release_approved: '출고 승인 기록', blocked: '차단됨', failed: '실패', completed: '완료 기록', pending: '대기', queued: '대기', running: '진행 중', partial: '일부 완료', unknown: '결과 미확인' };
const sections = { overview: '오늘의 운영', tasks: '작업 현황', approvals: '내 검토 대기', reports: '협업 보고', knowledge: '자료 검색', channels: '콘텐츠 채널', costs: '예산·비용' };
const resources = { dashboard: '/api/dashboard?compact=true&task_results=false', reports: '/api/assistant/reports', knowledge: '/api/knowledge', channels: '/api/channels' };

export function safeText(value, limit = 800) {
  if (typeof value !== 'string') return '';
  return value.slice(0, limit).replace(/[\u0000-\u0008\u000b\u000c\u000e-\u001f\u007f\u202a-\u202e\u2066-\u2069]/g, '')
    .replace(/\bBearer\s+\S+|\b(?:sk-[A-Za-z0-9_-]{12,}|xox[baprs]-[A-Za-z0-9-]+)\b/gi, '[비밀값 가림]')
    .replace(/(?:api[_-]?key|access[_-]?token|password|secret)\s*[:=]\s*\S+/gi, '[비밀값 가림]')
    .replace(/[A-Z0-9._%+-]+@[A-Z0-9.-]+\.[A-Z]{2,}/gi, '[이메일 가림]');
}
const escape = value => safeText(String(value ?? ''), 5000).replace(/[&<>"']/g, char => ({ '&': '&amp;', '<': '&lt;', '>': '&gt;', '"': '&quot;', "'": '&#39;' })[char]);
const status = value => labels[value] || `상태 확인 필요 (${safeText(value, 80) || '미제공'})`;
const time = value => checkedTime(value) ? new Date(value).toLocaleString('ko-KR', { timeZone: 'Asia/Seoul', hour12: false }) + ' KST' : '시각 미확인';
const amount = value => numeric(value) === null ? '미확인' : value.toLocaleString('ko-KR') + '원';
const button = (action, text, extra = '') => `<button type="button" data-oper-action="${action}" ${extra}>${escape(text)}</button>`;
const empty = text => `<p class="oper-empty">${escape(text)}</p>`;

export function projectDashboard(value) {
  if (!object(value) || !Array.isArray(value.jobs)) throw badSchema();
  const seen = new Set();
  const jobs = value.jobs.map(job => {
    if (!object(job) || typeof job.id !== 'string' || !job.id || typeof job.state !== 'string' || !job.state || seen.has(job.id)) throw badSchema();
    seen.add(job.id);
    return { id: job.id, title: safeText(job.title, 250) || '제목 미제공', state: safeText(job.state, 80), updatedAt: checkedTime(job.updated_at), outputKinds: strings(job.output_kinds) };
  });
  let tasks = null;
  if (Array.isArray(value.tasks) && value.tasks.every(task => object(task) && typeof task.id === 'string' && typeof task.state === 'string')) {
    tasks = value.tasks.map(task => ({ id: task.id, kind: safeText(task.kind, 100) || '작업 종류 미제공', state: safeText(task.state, 80), jobId: object(task.payload) && typeof task.payload.job_id === 'string' ? task.payload.job_id : null, updatedAt: checkedTime(task.updated_at) }));
  }
  const budget = {};
  for (const key of ['cap_krw', 'spent_krw', 'reserved_krw', 'remaining_krw', 'overrun_krw']) budget[key] = numeric(value.budget?.[key]);
  budget.costStatus = safeText(value.budget?.cost_status, 150);
  budget.pricingAsOf = safeText(value.budget?.pricing_as_of, 100);
  budget.fxNote = safeText(value.budget?.fx_note, 300);
  const windowStatus = typeof value.window?.status === 'string' ? value.window.status.toUpperCase() : null;
  return { jobs, tasks, budget, blockedCount: jobs.filter(job => blockedStates.has(job.state)).length,
    approvalCount: jobs.filter(job => approvalStates.has(job.state)).length,
    windowClosed: windowStatus === 'CLOSED' ? true : windowStatus === 'OPEN' ? false : null,
    newsletterDrafts: numeric(value.newsletters?.draft), workerState: safeText(value.worker?.state, 100) || '미확인',
    workerHeartbeat: checkedTime(value.worker?.heartbeat) };
}

function projectResource(key, value) {
  if (key === 'dashboard') return projectDashboard(value);
  if (!object(value)) throw badSchema();
  if (key === 'reports') {
    if (!Array.isArray(value.reports) || !value.reports.every(row => object(row) && typeof row.id === 'string' && typeof row.title === 'string')) throw badSchema();
    return value.reports.map(row => ({ id: row.id, title: safeText(row.title, 250), summary: safeText(row.summary, 3000), scope: safeText(row.scope, 80), reportedAt: checkedTime(row.reported_at), participants: strings(row.participants), limitations: strings(row.limitations), evidenceCount: numeric(row.evidence_count) }));
  }
  if (key === 'channels') {
    if (!Array.isArray(value.channels) || !value.channels.every(row => object(row) && typeof row.key === 'string')) throw badSchema();
    return value.channels.map(row => ({ key: row.key, label: safeText(row.label, 150), platform: safeText(row.platform, 80), locale: safeText(row.locale, 50), delivery: safeText(row.delivery, 120), publicationEnabled: typeof row.publication_enabled === 'boolean' ? row.publication_enabled : null, credentialsConfigured: typeof row.credentials_configured === 'boolean' ? row.credentials_configured : null }));
  }
  if (!Array.isArray(value.results) || !object(value.summary) || !value.results.every(row => object(row) && typeof row.excerpt === 'string')) throw badSchema();
  return { documents: numeric(value.summary.documents), results: value.results.map(row => ({ title: safeText(row.section, 200) || strings(row.heading_path).join(' / ') || '저장 문서', excerpt: safeText(row.excerpt, 2000), startLine: numeric(row.start_line), endLine: numeric(row.end_line), spacing: row.match_mode === 'spacing' })) };
}

/** Fixed, read-only routes. No session creation, subscriptions, model calls, or mutation adapters. */
export function createOperationalStore(fetcher = (...args) => globalThis.fetch(...args)) {
  const records = new Map();
  const listeners = new Set();
  const pending = new Map();
  let destroyed = false;
  const get = key => records.get(key) || { state: 'idle', data: null, fetchedAt: null, message: '', query: '' };
  const notify = key => { for (const listener of listeners) listener(key, get(key)); };
  async function refresh(key, query = '') {
    if (!Object.hasOwn(resources, key)) throw new Error('허용되지 않은 조회입니다.');
    if (destroyed) return;
    pending.get(key)?.abort();
    const controller = new AbortController();
    pending.set(key, controller);
    const previous = get(key);
    records.set(key, { ...previous, state: 'loading', message: '' });
    notify(key);
    const timeout = setTimeout(() => controller.abort(), 15000);
    try {
      const url = key === 'knowledge' ? `${resources[key]}?query=${encodeURIComponent(query.trim().slice(0, 200))}&limit=10` : resources[key];
      const response = await fetcher(url, { method: 'GET', credentials: 'same-origin', cache: 'no-store', redirect: 'error', signal: controller.signal, headers: { Accept: 'application/json' } });
      if (!response.ok) throw new Error('read_failed');
      const data = projectResource(key, await response.json());
      if (destroyed || pending.get(key) !== controller) return;
      if (controller.signal.aborted) throw new Error('read_timeout');
      records.set(key, { state: 'ready', data, fetchedAt: new Date().toISOString(), message: '', query: key === 'knowledge' ? query.trim().slice(0, 200) : '' });
    } catch {
      if (destroyed || pending.get(key) !== controller) return;
      records.set(key, { ...previous, state: previous.data !== null ? 'stale' : 'error', message: previous.data !== null ? '최신 조회에 실패했습니다. 아래는 마지막 정상 결과입니다.' : '연결 또는 응답 형식을 확인하지 못했습니다. 아직 확인된 결과가 없습니다.' });
    } finally {
      clearTimeout(timeout);
      if (!destroyed && pending.get(key) === controller) { pending.delete(key); notify(key); }
    }
  }
  return { get, refresh, subscribe(listener) { listeners.add(listener); return () => listeners.delete(listener); },
    cancel() { for (const controller of pending.values()) controller.abort(); pending.clear(); for (const [key, record] of records) if (record.state === 'loading') records.set(key, { ...record, state: record.data === null ? 'idle' : 'stale', message: '조회가 중단되었습니다. 다시 조회할 수 있습니다.' }); },
    destroy() { destroyed = true; this.cancel(); listeners.clear(); } };
}

export function createOperationalPanel(host, { onNavigate = () => {}, onAssistant = () => {}, onToast = () => {}, onSummary = () => {} } = {}) {
  const store = createOperationalStore();
  let section = 'overview';
  let shown = false;
  let disposed = false;
  let restoreFocus = null;
  let query = '';
  let taskFilter = 'all';
  const doc = host.ownerDocument;
  host.classList.add('oper-host');
  host.hidden = true;
  const resourceForSection = () => ['reports', 'knowledge', 'channels'].includes(section) ? section : 'dashboard';
  function publishSummary() {
    const state = store.get('dashboard');
    const data = state.data;
    onSummary({ state: state.state === 'idle' ? 'loading' : state.state, fetchedAt: state.fetchedAt,
      jobCount: data?.jobs.length ?? null, blockedCount: data?.blockedCount ?? null, approvalCount: data?.approvalCount ?? null,
      windowClosed: data?.windowClosed ?? null, message: state.message, jobs: data?.jobs.length ?? null,
      blocked: data?.blockedCount ?? null, updatedAt: state.fetchedAt, stale: state.state === 'stale', error: state.message || null });
  }
  const unsubscribe = store.subscribe(key => { if (key === 'dashboard') publishSummary(); if (shown) render(); });
  const jobLink = job => button('job', '작업 열기 ↗', `data-job-id="${escape(job.id)}"`);
  function jobList(jobs) {
    return jobs.length ? `<div class="oper-job-list">${jobs.map(job => `<article class="oper-row"><div><span class="oper-badge ${blockedStates.has(job.state) ? 'warn' : ''}">${escape(status(job.state))}</span><h3>${escape(job.title)}</h3><p>${escape(time(job.updatedAt))}</p></div>${jobLink(job)}</article>`).join('')}</div>` : empty('이 범위에 기록된 작업이 없습니다.');
  }
  function metrics(data) {
    return `<div class="oper-metrics"><div><span>콘텐츠 업무</span><strong>${data.jobs.length}</strong></div><div><span>차단·수정 필요</span><strong>${data.blockedCount}</strong></div><div><span>①·② 검토 대기</span><strong>${data.approvalCount}</strong></div><div><span>자동 제작 시간</span><strong class="oper-word">${data.windowClosed === true ? '닫힘' : data.windowClosed === false ? '열림' : '미확인'}</strong></div></div>`;
  }
  function overview(data) {
    const attention = data.jobs.filter(job => approvalStates.has(job.state) || blockedStates.has(job.state));
    return `${metrics(data)}<div class="oper-toolbar">${button('assistant', '루미 대화 열기')}${button('section', '협업 보고 보기', 'data-section="reports"')}</div><h3 class="oper-subtitle">지금 확인할 작업</h3><p class="oper-note">원고·출고의 검토 대기와 차단된 콘텐츠 업무입니다. 작업을 열면 기존 검토 화면으로 이동합니다.</p>${jobList(attention)}<p class="oper-note">Hermes 프로필·칸반 전체 개수와 별도인 콘텐츠 오피스 기록입니다. 확인되지 않은 자동 실행을 완료로 표시하지 않습니다.</p>`;
  }
  function tasks(data) {
    const jobs = taskFilter === 'blocked' ? data.jobs.filter(job => blockedStates.has(job.state)) : taskFilter === 'review' ? data.jobs.filter(job => approvalStates.has(job.state)) : data.jobs;
    return `<div class="oper-toolbar"><label>업무 보기 <select data-oper-filter aria-label="작업 상태 필터"><option value="all" ${taskFilter === 'all' ? 'selected' : ''}>전체 콘텐츠 업무</option><option value="blocked" ${taskFilter === 'blocked' ? 'selected' : ''}>차단·수정 필요</option><option value="review" ${taskFilter === 'review' ? 'selected' : ''}>①·② 검토 대기</option></select></label></div>${jobList(jobs)}<details class="oper-details"><summary>콘텐츠 실행 기록 ${data.tasks === null ? '미확인' : data.tasks.length + '건'}</summary><p class="oper-note">한 업무에 실행 기록이 여러 건 생깁니다. 아래 수치는 Hermes 칸반 카드 수가 아닙니다.</p>${data.tasks === null ? empty('실행 기록의 형식 또는 제공 여부를 확인하지 못했습니다.') : `<div class="oper-table-wrap"><table><caption>최근 갱신순 콘텐츠 실행 기록</caption><thead><tr><th>종류</th><th>상태</th><th>최근 갱신</th></tr></thead><tbody>${[...data.tasks].sort((a, b) => (b.updatedAt || '').localeCompare(a.updatedAt || '')).map(task => `<tr><td>${escape(task.kind)}</td><td>${escape(status(task.state))}</td><td>${escape(time(task.updatedAt))}</td></tr>`).join('')}</tbody></table></div>`}</details>`;
  }
  function approvals(data) {
    return `<div class="oper-approval-steps"><div><strong>⓪ 기획 선택</strong><a href="/plans" target="_top">기존 기획 화면에서 확인 ↗</a></div><div><strong>① 원고</strong><span>${data.jobs.filter(job => job.state === 'source_review').length}건 검토 대기</span></div><div><strong>② 출고</strong><span>${data.jobs.filter(job => ['release_review', 'partial_release_review'].includes(job.state)).length}건 검토 대기</span></div><div><strong>③ 회차</strong><a href="/runs" target="_top">뉴스레터 초안 ${data.newsletterDrafts === null ? '미확인' : data.newsletterDrafts + '건'} ↗</a></div></div><p class="oper-note">검토 대기는 승인이 아닙니다. ③ 초안 건수도 발송 승인 건수와 다릅니다. 기존 화면에서 판본과 근거를 보고 직접 결정합니다.</p>${jobList(data.jobs.filter(job => approvalStates.has(job.state)))}`;
  }
  function reports(rows) {
    return rows.length ? rows.map(report => `<article class="oper-report"><span class="oper-badge">${report.scope === 'dm_review' ? 'DM 팀 검토' : report.scope === 'group_review' ? 'GroupChat 그룹 검토' : '협업 보고 기록'}</span><h3>${escape(report.title)}</h3><p class="oper-prose">${escape(report.summary)}</p><p class="oper-note">참여: ${escape(report.participants.join(' · ') || '기록 미제공')} · 근거 ${report.evidenceCount === null ? '미확인' : report.evidenceCount + '개'} · ${escape(time(report.reportedAt))}</p><details><summary>이 보고서의 확인 범위</summary>${report.limitations.length ? `<ul>${report.limitations.map(item => `<li>${escape(item)}</li>`).join('')}</ul>` : '<p>별도 한계가 기록되어 있지 않습니다. 전체 실행 검증을 뜻하지 않습니다.</p>'}</details></article>`).join('') : empty('저장된 협업 보고가 없습니다. 새 회의나 모델 실행은 시작하지 않았습니다.');
  }
  function knowledge(data, state) {
    return `<form class="oper-search" data-oper-search><label for="oper-query">저장 문서에서 찾기</label><div><input id="oper-query" name="query" maxlength="200" value="${escape(query)}" placeholder="예: 오픽, 승인 기준, EC2" autocomplete="off"><button type="submit">검색</button></div></form><p class="oper-note">기존에 색인된 문서만 검색합니다. Hermes 전체 기억이나 학습된 모델을 조회하는 기능은 아닙니다.</p>${data === null ? '' : `${data.documents === null ? '' : `<p class="oper-note">색인 문서 ${data.documents}개</p>`}${state.query !== query ? `<p class="oper-note">표시 중인 마지막 검색어: ${escape(state.query || '(입력 전)')}</p>` : ''}${!state.query ? empty('검색어를 입력하면 저장된 근거를 확인할 수 있습니다.') : data.results.length ? data.results.map(row => `<article class="oper-report"><h3>${escape(row.title)}</h3><p class="oper-prose">${escape(row.excerpt)}</p><small>근거 ${row.startLine ?? '?'}–${row.endLine ?? '?'}행${row.spacing ? ' · 띄어쓰기 보완 검색' : ''}</small></article>`).join('') : empty('이 검색어로 확인된 저장 문서가 없습니다.')}`}`;
  }
  function channels(rows) {
    return `<p class="oper-note">연결 설정과 실제 게시 성공은 다릅니다. 이 화면에서는 로그인·게시·발송을 시작하지 않습니다.</p><div class="oper-channel-grid">${rows.map(row => `<article class="oper-report"><span class="oper-badge">${escape(row.platform)} · ${escape(row.locale)}</span><h3>${escape(row.label || row.key)}</h3><dl><div><dt>전달 방식</dt><dd>${escape(row.delivery || '미확인')}</dd></div><div><dt>인증 설정</dt><dd>${row.credentialsConfigured === null ? '미확인' : row.credentialsConfigured ? '등록됨 · 실제 유효성 별도' : '서버에 등록되지 않음'}</dd></div><div><dt>게시 설정</dt><dd>${row.publicationEnabled === null ? '미확인' : row.publicationEnabled ? '허용 설정 · 승인별도' : '비활성'}</dd></div></dl></article>`).join('') || empty('등록된 채널이 없습니다.')}</div>`;
  }
  function costs(data) {
    const names = { cap_krw: '앱 예산 한도', spent_krw: '장부 사용액', reserved_krw: '예약 금액', remaining_krw: '잔여 예산', overrun_krw: '초과 기록' };
    return `<p class="oper-note">콘텐츠 오피스의 비용 장부입니다. AWS 전체 비용·구독 잔여량·카드 청구액을 합산한 값은 아닙니다.</p><dl class="oper-costs">${Object.entries(names).map(([key, label]) => `<div><dt>${label}</dt><dd>${amount(data.budget[key])}</dd></div>`).join('')}</dl><p>${escape(data.budget.costStatus || '비용 대사 상태 미제공')}</p>${data.budget.fxNote ? `<p class="oper-note">${escape(data.budget.fxNote)}</p>` : ''}<p class="oper-note">단가 기준: ${escape(data.budget.pricingAsOf || '미확인')} · 작업 시간: ${data.windowClosed === true ? '닫힘' : data.windowClosed === false ? '열림' : '미확인'}<br>작업자 상태: ${escape(data.workerState)} · 확인 기록: ${escape(time(data.workerHeartbeat))}</p>`;
  }
  function render() {
    if (!shown || disposed) return;
    const focused = doc.activeElement;
    const focusedInside = host.contains(focused);
    const focusedAction = focused?.dataset?.operAction;
    const focusedSection = focused?.dataset?.section;
    const focusedJob = focused?.dataset?.jobId;
    const input = host.querySelector('#oper-query');
    if (section === 'knowledge' && input) query = input.value.slice(0, 200);
    const state = store.get(resourceForSection());
    const data = state.data;
    let content = '';
    if (section === 'knowledge') content = knowledge(data, state);
    else if (data !== null) content = ({ overview, tasks, approvals, reports, channels, costs })[section](data);
    else content = empty(state.state === 'loading' ? '기존 운영 기록을 조회하고 있습니다.' : '아직 확인된 데이터가 없습니다. 다시 조회해 주세요.');
    const focusQuery = doc.activeElement?.id === 'oper-query';
    host.innerHTML = `<section class="oper-panel" role="dialog" aria-modal="true" aria-labelledby="oper-title" tabindex="-1"><header><div><span class="oper-eyebrow">HEOBRAIN · 운영 기록</span><h2 id="oper-title">${sections[section]}</h2><p>기존 EC2 콘텐츠 업무를 읽기 전용으로 확인합니다.</p></div>${button('close', '닫기 ×', 'aria-label="운영 패널 닫기"')}</header><nav aria-label="운영 기록 메뉴">${Object.entries(sections).map(([key, title]) => button('section', title, `data-section="${key}" aria-current="${key === section ? 'page' : 'false'}"`)).join('')}</nav><div class="oper-status ${state.state === 'stale' || state.state === 'error' ? 'warn' : ''}" role="status" aria-live="polite"><span>${state.state === 'loading' ? '조회 중' : state.state === 'ready' ? '운영 기록 확인됨' : state.state === 'stale' ? '이전 결과 표시 중' : '확인 필요'} · 마지막 정상 조회: ${escape(time(state.fetchedAt))}</span>${button('refresh', '다시 조회', state.state === 'loading' ? 'disabled' : '')}</div>${state.message ? `<p class="oper-error" role="alert">${escape(state.message)}</p>` : ''}<div class="oper-body" aria-busy="${state.state === 'loading'}">${content}</div><footer>상태 확인과 기존 작업 열기만 수행합니다. 승인·실행·게시·메일은 각 운영 화면의 절차를 따릅니다.</footer></section>`;
    if (focusQuery) host.querySelector('#oper-query')?.focus();
    else if (focusedAction) {
      const replacement = [...host.querySelectorAll('[data-oper-action]')].find(element => element.dataset.operAction === focusedAction && element.dataset.section === focusedSection && element.dataset.jobId === focusedJob);
      (replacement || host.querySelector('.oper-panel'))?.focus();
    } else if (focusedInside) host.querySelector('.oper-panel')?.focus();
  }
  async function refresh() {
    const key = resourceForSection();
    const jobs = [store.refresh('dashboard')];
    if (shown && key !== 'dashboard') jobs.push(store.refresh(key, query));
    await Promise.allSettled(jobs);
  }
  function open(next = 'overview') {
    if (disposed) return;
    if (!Object.hasOwn(sections, next)) { onToast('이 메뉴는 아직 연결되지 않았습니다.'); return; }
    if (!shown) restoreFocus = doc.activeElement;
    shown = true; section = next; host.hidden = false; render();
    host.querySelector('.oper-panel')?.focus();
    host.dispatchEvent(new CustomEvent('workspace-open', { bubbles: true, detail: { section } }));
    void refresh();
  }
  function close() {
    const wasShown = shown;
    shown = false; host.hidden = true; store.cancel(); publishSummary();
    if (wasShown && restoreFocus?.isConnected) restoreFocus.focus();
    if (wasShown) host.dispatchEvent(new CustomEvent('workspace-close', { bubbles: true }));
  }
  function click(event) {
    if (event.target === host) { close(); return; }
    const target = event.target.closest?.('[data-oper-action]');
    if (!target || !host.contains(target)) return;
    const action = target.dataset.operAction;
    if (action === 'close') close();
    if (action === 'refresh') void refresh();
    if (action === 'section') open(target.dataset.section);
    if (action === 'assistant') { close(); onAssistant('lumi'); }
    if (action === 'job') {
      const job = store.get('dashboard').data?.jobs.find(row => row.id === target.dataset.jobId);
      if (job) { close(); onNavigate(['release_review', 'partial_release_review', 'release_approved'].includes(job.state) ? 'delivery' : 'studio', job.id); }
    }
  }
  function submit(event) {
    if (!event.target.matches('[data-oper-search]')) return;
    event.preventDefault(); query = event.target.querySelector('input').value.trim().slice(0, 200);
    void store.refresh('knowledge', query);
  }
  function change(event) { if (event.target.matches('[data-oper-filter]')) { taskFilter = event.target.value; render(); host.querySelector('[data-oper-filter]')?.focus(); } }
  function keydown(event) {
    if (!shown) return;
    if (event.key === 'Escape') { event.preventDefault(); event.stopPropagation(); close(); }
    if (event.key === 'Tab') {
      const elements = [...host.querySelectorAll('button:not([disabled]),input,select,a[href],summary')];
      const first = elements[0], last = elements.at(-1);
      if (event.shiftKey && (doc.activeElement === first || !elements.includes(doc.activeElement))) { event.preventDefault(); last?.focus(); }
      else if (!event.shiftKey && doc.activeElement === last) { event.preventDefault(); first?.focus(); }
    }
  }
  host.addEventListener('click', click); host.addEventListener('submit', submit); host.addEventListener('change', change); host.addEventListener('keydown', keydown);
  return { open, close, refresh, destroy() { disposed = true; close(); unsubscribe(); store.destroy(); host.removeEventListener('click', click); host.removeEventListener('submit', submit); host.removeEventListener('change', change); host.removeEventListener('keydown', keydown); host.replaceChildren(); } };
}
