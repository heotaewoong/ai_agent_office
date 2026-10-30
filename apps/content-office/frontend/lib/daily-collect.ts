// 매일 아침 뉴스 자동 수집 설정. 서버 office/daily_collect.py의 범위·상태값과 맞춘다.
// 설정 저장은 작업 시간을 열지 않는다. 실행은 서버 cron(scripts/daily_collect.py)이 하며 수집·요약만 한다.

export type DailyCollectSettings = {
  enabled: boolean;
  time_kst: string;
  minutes: number;
  max_krw: number;
  updated_by?: string;
  updated_at?: string;
};

export type DailyCollectRun = {
  date: string;
  status: string;
  reason?: string;
  articles?: number;
  new_articles?: number;
  spent_krw?: number;
  max_krw?: number;
  started_at?: string;
  finished_at?: string;
  error_type?: string;
};

export type DailyCollectStatus = {
  settings: DailyCollectSettings;
  last_run: DailyCollectRun | null;
  runs: DailyCollectRun[];
  slot_minutes: number;
  source: string;
};

export type DailyCollectPatch = Pick<DailyCollectSettings, "enabled" | "time_kst" | "minutes" | "max_krw">;

export const COLLECT_MINUTES = [5, 30] as const;
export const COLLECT_MAX_KRW = [10, 1000] as const;

export function validTimeKst(value: string): string | null {
  const text = value.trim();
  return /^([01]\d|2[0-3]):[0-5]\d$/.test(text) ? text : null;
}

function integerIn(value: string, [low, high]: readonly [number, number]): number | null {
  const text = value.trim();
  if (!/^\d+$/.test(text)) return null;
  const number = Number(text);
  return number >= low && number <= high ? number : null;
}

export function validCollectMinutes(value: string): number | null {
  return integerIn(value, COLLECT_MINUTES);
}

export function validCollectMaxKrw(value: string): number | null {
  return integerIn(value, COLLECT_MAX_KRW);
}

export function parseDailyCollectForm(form: { enabled: boolean; time: string; minutes: string; maxKrw: string }):
  | { ok: true; patch: DailyCollectPatch }
  | { ok: false; errors: string[] } {
  const time = validTimeKst(form.time);
  const minutes = validCollectMinutes(form.minutes);
  const maxKrw = validCollectMaxKrw(form.maxKrw);
  const errors: string[] = [];
  if (time == null) errors.push("수집 시각은 HH:MM(예: 07:00)으로 입력하세요.");
  if (minutes == null) errors.push(`작업 시간은 ${COLLECT_MINUTES[0]}~${COLLECT_MINUTES[1]}분의 정수로 입력하세요.`);
  if (maxKrw == null) errors.push(`1회 비용 상한은 ${COLLECT_MAX_KRW[0]}~${COLLECT_MAX_KRW[1]}원의 정수로 입력하세요.`);
  if (time == null || minutes == null || maxKrw == null) return { ok: false, errors };
  return { ok: true, patch: { enabled: form.enabled, time_kst: time, minutes, max_krw: maxKrw } };
}

const STATUS_LABELS: Record<string, string> = {
  running: "실행 중",
  completed: "완료",
  stopped_cost_cap: "비용 상한에 닿아 요약 일부를 멈춤",
  timeout: "작업 시간이 끝나 중단",
  failed: "실패",
  interrupted: "중단됨",
};

const SKIP_REASONS: Record<string, string> = {
  operator_window_open: "운영자 작업 시간이 열려 있어 건너뜀",
  window_unavailable: "작업자·배포가 실행 중이어서 작업 시간을 열지 못해 건너뜀",
  services_running: "작업자 또는 감시가 실행 중이어서 건너뜀",
};

export function runSummary(run: DailyCollectRun | null | undefined): string {
  if (!run) return "아직 자동 수집 기록이 없습니다.";
  if (run.status === "skipped") return `${run.date} · ${SKIP_REASONS[run.reason ?? ""] ?? `건너뜀(${run.reason ?? "이유 없음"})`}`;
  const label = STATUS_LABELS[run.status] ?? run.status;
  const parts = [`${run.date} · ${label}`];
  if (run.articles != null) parts.push(`기사 ${run.articles}건 중 새 기사 ${run.new_articles ?? 0}건`);
  if (run.spent_krw != null) parts.push(`비용 ${run.spent_krw}원${run.max_krw != null ? ` / 상한 ${run.max_krw}원` : ""}`);
  if (run.error_type) parts.push(`오류 ${run.error_type}`);
  return parts.join(" · ");
}
