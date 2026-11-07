'use client';

import { useEffect, useRef, useState } from 'react';
import { api } from '../lib/api';
import { assistantNames, type AssistantRequest } from '../lib/assistant-requests';
import { parseBenchmarkResearchRun, parseBenchmarkResearchSubmission, type BenchmarkResearchRun, type BenchmarkResearchInputRun } from '../lib/benchmark-research';
import type { BenchmarkItem, BenchmarkResearchInput } from '../lib/benchmarks';
import styles from './benchmark-panel.module.css';

const savedKey = 'office-benchmark-research-request';
const states = { queued: '접수·역할 배정 대기', running: '실제 비서 조사 중', blocked: '조사 차단·확인 필요', failed: '조사 실패·확인 필요', completed: '최종 보고 도착' };
export function BenchmarkResearchRunPanel({ active, ready, input, items, platforms, windowOpen, onIdeaSaved }: { active: boolean; ready: boolean; input: BenchmarkResearchInput; items: BenchmarkItem[]; platforms: Record<string, string>; windowOpen: boolean; onIdeaSaved?: () => void }) {
  const [requestId, setRequestId] = useState('');
  const [run, setRun] = useState<BenchmarkResearchRun | null>(null);
  const [busy, setBusy] = useState(false), [error, setError] = useState(''), [notice, setNotice] = useState('');
  const [itemId, setItemId] = useState(''), [title, setTitle] = useState(''), [angle, setAngle] = useState(''), [targets, setTargets] = useState<string[]>([]);
  const submitted = useRef<BenchmarkResearchInputRun | null>(null);
  const pending = useRef(false), currentId = useRef('');
  useEffect(() => { try { const id = sessionStorage.getItem(savedKey); if (id && /^[0-9a-f-]{36}$/i.test(id)) { currentId.current = id; setRequestId(id); const saved = sessionStorage.getItem(savedKey + ':input'); if (saved) submitted.current = parseBenchmarkResearchSubmission(JSON.parse(saved), id); } } catch { /* Keep the UUID even if a damaged draft cannot be restored. */ } }, []);
  useEffect(() => {
    if (!active || !requestId || (run && ['completed', 'blocked', 'failed'].includes(run.execution.status))) return;
    let live = true, timer: ReturnType<typeof setTimeout>;
    async function read() {
      try { const value = parseBenchmarkResearchRun(await api.benchmarkResearch(requestId), requestId); if (live) { setRun(value); setError(''); if (['queued', 'running'].includes(value.execution.status)) timer = setTimeout(read, 5000); } }
      catch (cause) { if (live) setError(cause instanceof Error ? cause.message : '조사 기록 조회에 실패했습니다.'); }
    }
    void read();
    return () => { live = false; clearTimeout(timer); };
  }, [active, requestId, run?.execution.status]);
  async function readNow() {
    if (pending.current || !requestId) return;
    pending.current = true; setBusy(true);
    try { setRun(parseBenchmarkResearchRun(await api.benchmarkResearch(requestId), requestId)); setError(''); }
    catch (cause) { setError(cause instanceof Error ? cause.message : '조사 기록 조회에 실패했습니다.'); }
    finally { pending.current = false; setBusy(false); }
  }
  async function start() {
    if (pending.current || !windowOpen || (!submitted.current && (!ready || !input.snapshot_hash || !input.item_ids?.length))) return;
    pending.current = true; setBusy(true); setError('');
    const id = currentId.current || crypto.randomUUID(); currentId.current = id;
    submitted.current ??= { ...input, request_id: id, snapshot_hash: input.snapshot_hash!, item_ids: input.item_ids! };
    setRequestId(id); try { sessionStorage.setItem(savedKey, id); sessionStorage.setItem(savedKey + ':input', JSON.stringify(submitted.current)); } catch { /* Keep the UUID and immutable input in memory. */ }
    try { setRun(parseBenchmarkResearchRun(await api.startBenchmarkResearch(submitted.current), id)); }
    catch (cause) { setError(cause instanceof Error ? cause.message : '접수 결과를 확인하지 못했습니다. 같은 요청 번호를 유지합니다.'); }
    finally { pending.current = false; setBusy(false); }
  }
  async function saveIdea() {
    if (pending.current || !run?.analysis_receipt || !itemId || !targets.length || !title.trim() || !angle.trim()) return;
    pending.current = true; setBusy(true); setError('');
    try { await api.benchmarkResearchIdea(requestId, { item_id: itemId, title: title.trim(), angle: angle.trim(), target_platforms: targets, receipt: run.analysis_receipt }); setNotice('최종 분석 영수증과 원문 관측값을 연결해 기획 은행에 후보를 저장했습니다. 승인⓪·원고·제작은 시작하지 않았습니다.'); onIdeaSaved?.(); }
    catch (cause) { setError(cause instanceof Error ? cause.message : '아이디어 저장 결과를 확인하지 못했습니다.'); }
    finally { pending.current = false; setBusy(false); }
  }
  const execution = run?.execution, detailed = execution && 'events' in execution ? execution as AssistantRequest : null, report = detailed?.status === 'completed' && detailed.report?.verified ? detailed.report : null;
  return <section className={styles.editor} aria-label="실제 세이지 조사와 최종 보고">
    <h4>원문 수집 → 세이지 분석 → 독립 검토 → 루미 보고</h4>
    <p className={styles.hint}>선택한 실제 관측 최대 6건으로 조사합니다. 기존 비서 모델 사용량을 소비할 수 있으며 제작 예산 표는 비서의 금액 상한 장치가 아닙니다. 기존 승인·비용 예약을 바꾸거나 외부 알림을 보내지 않습니다.</p>
    {!windowOpen && <p role="status">작업 시간이 종료됐습니다. 제작 설정에서 사용자가 작업 시간을 연 뒤 조사를 시작할 수 있습니다.</p>}
    {!requestId && <button type="button" className="button primary" disabled={busy || !ready || !windowOpen || !input.item_ids?.length} onClick={() => void start()}>선택한 근거로 세이지 조사 시작</button>}
    {requestId && <><p>요청 번호 <code>{requestId}</code> · {execution ? states[execution.status] : '접수 여부 확인 중'}</p><div className={styles.actions}><button type="button" className="button secondary" disabled={busy} onClick={() => void readNow()}>실행·보고 다시 확인</button>{!run && submitted.current && <button type="button" className="button secondary" disabled={busy || !windowOpen} onClick={() => void start()}>같은 요청 번호로 접수 확인</button>}{execution && ['completed', 'blocked', 'failed'].includes(execution.status) && <button type="button" className={styles.textButton} disabled={busy} onClick={() => { currentId.current = ''; setRequestId(''); setRun(null); submitted.current = null; try { sessionStorage.removeItem(savedKey); sessionStorage.removeItem(savedKey + ':input'); } catch { /* Keep the server record. */ } }}>새 조사 준비</button>}</div></>}
    {detailed && <details className={styles.angle}><summary>실제 역할·실행 기록 {detailed.events.length}개</summary><ol>{detailed.events.slice(-30).map(event => <li key={event.id}>{assistantNames[event.assignee]} · {event.kind} · 실행 {event.run_id ?? '미배정'} · 기록 {event.id}</li>)}</ol></details>}
    {detailed?.error && <p role="alert">{detailed.error.message}</p>}
    {report && <section aria-label="세이지 조사 최종 보고"><h4>루미의 최종 보고</h4><p className={styles.summary}>{report.summary}</p><p className={styles.hint}>업무 {report.task_id} · 실행 {report.run_id} · 완료 기록 {report.event_id}</p></section>}
    {run?.analysis_receipt && <form onSubmit={event => { event.preventDefault(); void saveIdea(); }}><h4>이 분석을 내 아이디어로 연결</h4><label>분석에 사용한 근거<select required value={itemId} onChange={event => setItemId(event.target.value)}><option value="">원문 선택</option>{run.item_ids.map(id => <option key={id} value={id}>{run.observations.find(item => item.id === id)?.title ?? id}</option>)}</select></label><label>내 콘텐츠 제목<input required maxLength={200} value={title} onChange={event => setTitle(event.target.value)} /></label><label>보고에서 가져올 관점·검증할 질문<textarea required maxLength={1000} value={angle} onChange={event => setAngle(event.target.value)} /></label><fieldset><legend>게시할 대상</legend><div className={styles.checks}>{Object.entries(platforms).map(([id, label]) => <label key={id}><input type="checkbox" checked={targets.includes(id)} onChange={event => setTargets(event.target.checked ? [...targets, id] : targets.filter(target => target !== id))} />{label}</label>)}</div></fieldset><button type="submit" className="button primary" disabled={busy || !itemId || !targets.length}>분석 근거를 연결해 후보 저장</button><p className={styles.hint}>공개 반응 관측은 1차 근거 검증이나 성과 보장이 아닙니다. 원문과 최종 보고를 함께 보존합니다.</p></form>}
    {busy && <p role="status">처리 중…</p>}{error && <p className={styles.error} role="alert">{error}</p>}{notice && <p className={styles.notice} role="status">{notice}</p>}
  </section>;
}
