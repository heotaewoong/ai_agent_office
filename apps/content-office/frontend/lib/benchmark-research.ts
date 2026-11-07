import { parseAssistantRequest, type AssistantAccepted, type AssistantRequest, type AssistantContentSubmission } from './assistant-requests.ts';
import { benchmarkPublicUrl, type BenchmarkItem, type BenchmarkResearchInput } from './benchmarks.ts';

export type BenchmarkResearchInputRun = BenchmarkResearchInput & { request_id: string; item_ids: string[]; snapshot_hash: string };
export type BenchmarkResearchRun = {
  request_id: string; packet_hash: string; registry_hash: string; snapshot_hash: string; item_ids: string[]; observations: BenchmarkItem[]; created_at: string;
  execution: AssistantAccepted | AssistantRequest; analysis_receipt: AssistantContentSubmission | null;
  budget_evidence: { cap_krw: number; spent_krw: number; reserved_krw: number; remaining_krw: number; native_monetary_guard: false; billing_mode: string };
};
export type BenchmarkResearchIdea = { item_id: string; title: string; angle: string; target_platforms: string[]; receipt: AssistantContentSubmission };
export function parseBenchmarkResearchSubmission(raw: unknown, expected: string): BenchmarkResearchInputRun {
  const invalid = () => { throw new Error('보존한 조사 입력이 올바르지 않습니다. 요청 번호는 유지하고 실행 기록을 확인하세요.'); };
  if (!raw || typeof raw !== 'object') return invalid();
  const row = raw as BenchmarkResearchInputRun;
  if (Object.keys(row).sort().join(',') !== 'expected_hash,fields,item_ids,platforms,request_id,snapshot_hash,source_ids'
    || row.request_id !== expected || !/^[0-9a-f]{8}-[0-9a-f]{4}-[1-8][0-9a-f]{3}-[89ab][0-9a-f]{3}-[0-9a-f]{12}$/i.test(expected)
    || [row.expected_hash, row.snapshot_hash].some(hash => !/^[a-f0-9]{64}$/.test(hash))
    || [row.source_ids, row.fields, row.platforms, row.item_ids].some(values => !Array.isArray(values) || values.length > 64 || values.some(value => typeof value !== 'string' || value.length > 100))
    || !row.item_ids.length || row.item_ids.length > 6) return invalid();
  return row;
}
export function parseBenchmarkResearchRun(raw: unknown, expected: string): BenchmarkResearchRun {
  const bad = (): never => { throw new Error('조사 실행 기록을 확인하지 못했습니다. 같은 요청 번호로 다시 확인하세요.'); };
  if (!raw || typeof raw !== 'object') return bad();
  const row = raw as BenchmarkResearchRun;
  if (row.request_id !== expected || !/^[0-9a-f]{8}-[0-9a-f]{4}-[1-8][0-9a-f]{3}-[89ab][0-9a-f]{3}-[0-9a-f]{12}$/i.test(expected)
    || [row.packet_hash, row.registry_hash, row.snapshot_hash].some(hash => typeof hash !== 'string' || !/^[a-f0-9]{64}$/.test(hash))
    || !Array.isArray(row.item_ids) || !row.item_ids.length || row.item_ids.length > 6 || row.item_ids.some(id => typeof id !== 'string' || !/^[a-zA-Z0-9_-]{1,100}$/.test(id))
    || new Set(row.item_ids).size !== row.item_ids.length || !Number.isFinite(Date.parse(row.created_at))) return bad();
  if (!Array.isArray(row.observations) || row.observations.length !== row.item_ids.length
    || row.observations.some((item, index) => !item || item.id !== row.item_ids[index] || typeof item.title !== 'string' || item.title.length > 200 || !benchmarkPublicUrl(item.url))) return bad();
  const b = row.budget_evidence;
  if (!b || b.native_monetary_guard !== false || typeof b.billing_mode !== 'string' || [b.cap_krw, b.spent_krw, b.reserved_krw, b.remaining_krw].some(n => typeof n !== 'number' || !Number.isFinite(n))) return bad();
  const e = row.execution;
  if (!e || e.request_id !== expected || e.board !== 'heobrain-office' || !['queued', 'running', 'blocked', 'completed', 'failed'].includes(e.status)
    || (e.native_task_id !== null && !/^t_[a-zA-Z0-9_-]{1,80}$/.test(e.native_task_id))) return bad();
  const execution = 'events' in e ? parseAssistantRequest(e, expected) : e;
  if (!('events' in e) && e.status !== 'queued') return bad();
  const r = row.analysis_receipt;
  const report = 'events' in execution ? (execution as AssistantRequest).report : null;
  if (r) {
    if (execution.status !== 'completed' || !report?.verified
      || report.task_id !== r.task_id || report.run_id !== r.run_id || report.event_id !== r.event_id
      || [r.report_sha256, r.body_sha256].some(hash => typeof hash !== 'string' || !/^[a-f0-9]{64}$/.test(hash))) return bad();
  }
  return { ...row, execution };
}
