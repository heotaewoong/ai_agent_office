export type ReportSummary = {
  id: string; work_id: string; title: string; summary: string;
  scope: 'dm_review' | 'group_review'; reported_at: string;
  participants: string[]; limitations: string[]; evidence_count: number;
};

export type AssistantReportsState = {
  status: 'idle' | 'loading' | 'success' | 'error'; reports: ReportSummary[]; error: string | null;
};

export function createAssistantReportsController() {
  let connected = false;
  let open = false;
  let busy = false;
  let generation = 0;
  let state: AssistantReportsState = { status: 'idle', reports: [], error: null };
  const listeners = new Set<() => void>();
  const publish = (next: AssistantReportsState) => { state = next; listeners.forEach(listener => listener()); };
  return {
    getSnapshot: () => state,
    subscribe(listener: () => void) { listeners.add(listener); return () => { listeners.delete(listener); }; },
    setAvailability(nextConnected: boolean, nextOpen: boolean) {
      if (connected === nextConnected && open === nextOpen) return;
      connected = nextConnected; open = nextOpen; generation++;
      publish({ status: 'idle', reports: [], error: null });
    },
    invalidate() {
      connected = false; open = false; generation++;
      publish({ status: 'idle', reports: [], error: null });
    },
    async refresh(load: () => Promise<unknown>) {
      if (!connected || !open || busy) return;
      busy = true;
      const requestGeneration = generation;
      const current = () => connected && open && generation === requestGeneration;
      publish({ status: 'loading', reports: [], error: null });
      try {
        const value = await load();
        if (current()) publish({ status: 'success', reports: parseAssistantReports(value), error: null });
      } catch {
        if (current()) publish({ status: 'error', reports: [], error: '협업 보고를 불러오지 못했습니다. 연결·인증 또는 서버 지원을 확인하세요.' });
      } finally { busy = false; }
    },
  };
}

const INVALID = '지원하지 않거나 안전하지 않은 협업 보고 응답입니다.';
function invalid(): never { throw new Error(INVALID); }
function record(value: unknown): Record<string, unknown> {
  if (!value || typeof value !== 'object' || Array.isArray(value)) return invalid();
  return value as Record<string, unknown>;
}
function exact(value: Record<string, unknown>, keys: string[]) {
  if (Object.keys(value).length !== keys.length || keys.some(key => !Object.hasOwn(value, key))) invalid();
}
function text(value: unknown, max: number): string {
  if (typeof value !== 'string' || value.length > max * 2 || !value.trim() || [...value].length > max ||
      /(?:\/|%2f)(?:home|users|mnt|tmp|etc|root|var)(?:\/|%2f)|\.\.[\\/]|[a-z]:[\\/]|%2f|[\u0000-\u001f\u007f\u202a-\u202e\u2066-\u2069]|(?:^|[\s("'=])(?:\/|~\/|\\\\)|(?:https?|file):|bearer\s|(?:api[_-]?key|password|secret|token)\s*[:=]|sk-[a-z0-9]{12,}/i.test(value)) invalid();
  return value;
}
function identifier(value: unknown): string {
  const result = text(value, 120);
  if (!/^[a-zA-Z0-9][a-zA-Z0-9_-]*$/.test(result)) invalid();
  return result;
}
function list(value: unknown, maxText: number, required = false): string[] {
  if (!Array.isArray(value) || value.length > 20 || (required && !value.length)) return invalid();
  const result = value.map(item => text(item, maxText));
  if (new Set(result).size !== result.length) invalid();
  return result;
}
function timestamp(value: unknown): string {
  const result = text(value, 35);
  const parts = /^(\d{4}-\d{2}-\d{2}T\d{2}:\d{2}:\d{2})(?:\.\d{1,6})?(Z|[+-](?:0\d|1[0-4]):[0-5]\d)$/.exec(result);
  if (!parts) return invalid();
  const date = new Date(result);
  const wallClock = new Date(`${parts[1]}Z`);
  if (!Number.isFinite(date.getTime()) || !Number.isFinite(wallClock.getTime()) || wallClock.toISOString().slice(0, 19) !== parts[1]) invalid();
  return result;
}

/** Only the allowlisted, server-redacted summary DTO is accepted; never raw conversations. */
export function parseAssistantReports(value: unknown): ReportSummary[] {
  const envelope = record(value);
  exact(envelope, ['reports']);
  if (!Array.isArray(envelope.reports) || envelope.reports.length > 100) return invalid();
  const ids = new Set<string>();
  return envelope.reports.map(item => {
    const row = record(item);
    exact(row, ['id', 'work_id', 'title', 'summary', 'scope', 'reported_at', 'participants', 'limitations', 'evidence_count']);
    const id = identifier(row.id);
    if (ids.has(id)) invalid();
    ids.add(id);
    if (row.scope !== 'dm_review' && row.scope !== 'group_review') invalid();
    if (typeof row.evidence_count !== 'number' || !Number.isSafeInteger(row.evidence_count) || row.evidence_count < 0 || row.evidence_count > 10000) invalid();
    return { id, work_id: identifier(row.work_id), title: text(row.title, 160), summary: text(row.summary, 1200),
      scope: row.scope, reported_at: timestamp(row.reported_at), participants: list(row.participants, 80, true),
      limitations: list(row.limitations, 400), evidence_count: row.evidence_count };
  });
}
