import { isAssistantProfile } from './assistant-requests.ts';
import type { AssistantProfile, AssistantRequest } from './assistant-requests.ts';

export type WorldMessage =
  | { type: "ready" }
  | { type: "assistant-open"; assistant: AssistantProfile }
  | { type: "open"; view: "news" | "studio" | "delivery" | "activity"; itemId: string }
  | { type: "action"; action: WorldAction; itemId: string };

export type WorldAction = "draft" | "produce" | "auto-deploy-on" | "auto-deploy-off" | "stocks-refresh";
const VIEWS = ["news", "studio", "delivery", "activity"];
const ACTIONS: WorldAction[] = ["draft", "produce", "auto-deploy-on", "auto-deploy-off", "stocks-refresh"];

/** 개발 팀 스위치는 콘텐츠 작업이 아니므로 작업 선택·진행 중 상태와 무관하게 처리한다. */
export function isDevAction(action: WorldAction): action is "auto-deploy-on" | "auto-deploy-off" {
  return action === "auto-deploy-on" || action === "auto-deploy-off";
}

/** 주식 팀 시세 확인은 무료 공개 시세 읽기다. 매매·보유 내역 변경·콘텐츠 승인과 무관하다. */
export function isStocksAction(action: WorldAction): action is "stocks-refresh" {
  return action === "stocks-refresh";
}

export function parseWorldMessage(data: unknown): WorldMessage | null {
  if (!data || typeof data !== "object") return null;
  const d = data as Record<string, unknown>;
  if (d.source !== "office-world") return null;
  if (d.type === "ready") return { type: "ready" };
  if (d.type === "assistant-open") {
    if (Object.keys(d).some(key => !['source', 'type', 'assistant'].includes(key))) return null;
    const assistant = Object.hasOwn(d, 'assistant') ? d.assistant : 'lumi';
    return isAssistantProfile(assistant) ? { type: 'assistant-open', assistant } : null;
  }
  if (typeof d.itemId !== "string") return null;
  if (d.type === "open" && typeof d.view === "string" && VIEWS.includes(d.view))
    return { type: "open", view: d.view as "news", itemId: d.itemId };
  if (d.type === "action" && typeof d.action === "string" && (ACTIONS as string[]).includes(d.action))
    return { type: "action", action: d.action as WorldAction, itemId: d.itemId };
  return null;
}

export type WorldRoute =
  | { kind: "focus" }
  | { kind: "assistant" }
  | { kind: "open" }
  | { kind: "action" }
  | { kind: "reply"; ok: false; message: string };

export function routeWorldMessage(
  msg: WorldMessage,
  ctx: { busy: boolean; connected: boolean; inFlight: boolean },
): WorldRoute {
  if (msg.type === "ready") return { kind: "focus" };
  if (msg.type === "assistant-open") return { kind: "assistant" };
  if (msg.type === "open") return { kind: "open" };
  if (!ctx.connected) return { kind: "reply", ok: false, message: "연결을 확인해 주세요" };
  if (ctx.busy || ctx.inFlight) return { kind: "reply", ok: false, message: "이미 처리 중입니다" };
  return { kind: "action" };
}

export type AssistantReportRef = { request_id: string; task_id: string; run_id: number; event_id: number };
export type AssistantReportAction = AssistantReportRef & { type: 'assistant-report-action'; action: 'visit' | 'result' };
export type AssistantReportResult = AssistantReportRef & { type: 'assistant-report-result'; action: 'visit' | 'result'; ok: boolean; message: string };
const reportKeys = ['request_id', 'task_id', 'run_id', 'event_id'];
function reportRef(value: unknown): AssistantReportRef | null {
  if (!value || typeof value !== 'object' || Array.isArray(value)) return null;
  const row = value as Record<string, unknown>;
  if (typeof row.request_id !== 'string' || !/^[0-9a-f]{8}-[0-9a-f]{4}-[1-8][0-9a-f]{3}-[89ab][0-9a-f]{3}-[0-9a-f]{12}$/i.test(row.request_id)
    || typeof row.task_id !== 'string' || !/^t_[a-zA-Z0-9_-]{1,80}$/.test(row.task_id)
    || typeof row.run_id !== 'number' || !Number.isSafeInteger(row.run_id) || row.run_id <= 0
    || typeof row.event_id !== 'number' || !Number.isSafeInteger(row.event_id) || row.event_id <= 0) return null;
  return { request_id: row.request_id, task_id: row.task_id, run_id: row.run_id, event_id: row.event_id };
}
export function parseAssistantReportAction(value: unknown): AssistantReportAction | null {
  const reference = reportRef(value);
  if (!reference) return null;
  const row = value as Record<string, unknown>;
  const keys = ['source', 'type', 'action', ...reportKeys];
  if (Object.keys(row).length !== keys.length || keys.some(key => !Object.hasOwn(row, key)) || row.source !== 'content-office'
    || row.type !== 'assistant-report-action' || (row.action !== 'visit' && row.action !== 'result')) return null;
  return { type: 'assistant-report-action', action: row.action, ...reference };
}
export function parseAssistantReportResult(value: unknown): AssistantReportResult | null {
  const reference = reportRef(value);
  if (!reference) return null;
  const row = value as Record<string, unknown>;
  const keys = ['source', 'type', 'action', ...reportKeys, 'ok', 'message'];
  if (Object.keys(row).length !== keys.length || keys.some(key => !Object.hasOwn(row, key)) || row.source !== 'office-world'
    || row.type !== 'assistant-report-result' || (row.action !== 'visit' && row.action !== 'result') || typeof row.ok !== 'boolean'
    || typeof row.message !== 'string' || !row.message.trim() || [...row.message].length > 400
    || /[\u0000-\u001f\u007f\u202a-\u202e\u2066-\u2069]|(?:\/|%2f)(?:home|users|mnt|tmp|etc|root|var)(?:\/|%2f)|[a-z]:[\\/]|\.\.[\\/]|bearer\s|(?:api[_-]?key|password|secret|token)\s*[:=]|sk-[a-z0-9]{12,}|xox[baprs]-[a-z0-9-]+/i.test(row.message)) return null;
  return { type: 'assistant-report-result', action: row.action, ...reference, ok: row.ok, message: row.message };
}
export function matchesAssistantReportRef(value: AssistantReportRef, request: AssistantRequest | null): boolean {
  const reference = reportRef(value), report = request?.report;
  return Boolean(reference && request?.board === 'heobrain-office' && request.status === 'completed' && request.native_status === 'done'
    && report?.verified && request.request_id === reference.request_id && report.task_id === reference.task_id
    && report.run_id === reference.run_id && report.event_id === reference.event_id
    && request.events.some(event => event.task_id === reference.task_id && event.run_id === reference.run_id
      && event.id === reference.event_id && event.kind === 'completed' && event.assignee === 'lumi'));
}
