export type WorldMessage =
  | { type: "ready" }
  | { type: "open"; view: "news" | "studio" | "delivery" | "activity"; itemId: string }
  | { type: "action"; action: "draft" | "produce"; itemId: string };

const VIEWS = ["news", "studio", "delivery", "activity"];
const ACTIONS = ["draft", "produce"];

export function parseWorldMessage(data: unknown): WorldMessage | null {
  if (!data || typeof data !== "object") return null;
  const d = data as Record<string, unknown>;
  if (d.source !== "office-world") return null;
  if (d.type === "ready") return { type: "ready" };
  if (typeof d.itemId !== "string") return null;
  if (d.type === "open" && typeof d.view === "string" && VIEWS.includes(d.view))
    return { type: "open", view: d.view as "news", itemId: d.itemId };
  if (d.type === "action" && typeof d.action === "string" && ACTIONS.includes(d.action))
    return { type: "action", action: d.action as "draft", itemId: d.itemId };
  return null;
}

export type WorldRoute =
  | { kind: "focus" }
  | { kind: "open" }
  | { kind: "action" }
  | { kind: "reply"; ok: false; message: string };

export function routeWorldMessage(
  msg: WorldMessage,
  ctx: { busy: boolean; connected: boolean; inFlight: boolean },
): WorldRoute {
  if (msg.type === "ready") return { kind: "focus" };
  if (msg.type === "open") return { kind: "open" };
  if (!ctx.connected) return { kind: "reply", ok: false, message: "연결을 확인해 주세요" };
  if (ctx.busy || ctx.inFlight) return { kind: "reply", ok: false, message: "이미 처리 중입니다" };
  return { kind: "action" };
}
