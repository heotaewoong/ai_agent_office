import { LEAD_SOURCES, validEmail } from "./leads.ts";

/** 서버 카탈로그(config/lead_magnets.json)의 공개 항목. 동의 문구와 버전은 서버가 정합니다. */
export type PublicMagnet = { key: string; title: string; description: string; consent_version: string; consent_text: string };
export type PublicLeadSource = (typeof LEAD_SOURCES)[number];
export type PublicLeadPayload = { email: string; magnet_key: string; source: PublicLeadSource; consent_version: string; consent_checked: true; hp: string };
export type PublicLeadForm = { email: string; consent: boolean; hp: string };
/** 운영자 화면용 GET /api/leads/public-form 응답. */
export type PublicLeadFormInfo = { public_origin: string | null; magnets: PublicMagnet[]; sources: string[] };

export const PUBLIC_LEAD_DONE = "신청을 받았어요. 자료는 운영자가 확인 후 이메일로 보내 드려요.";

/** 주소창의 src 값을 허용 목록으로 맞춥니다. 모르는 값은 other로 기록합니다. */
export function leadSourceFromQuery(value: string | string[] | undefined | null): PublicLeadSource {
  const raw = Array.isArray(value) ? value[0] : value;
  return LEAD_SOURCES.find((source) => source === raw) ?? "other";
}

export function magnetKeyFromQuery(value: string | string[] | undefined | null): string {
  const raw = (Array.isArray(value) ? value[0] : value) ?? "";
  return /^[A-Za-z0-9][A-Za-z0-9._-]{0,99}$/.test(raw) ? raw : "";
}

/** 제출 직전 검사. 동의 문구는 보내지 않고 화면에 보여 준 버전만 보냅니다. */
export function publicLeadPayload(form: PublicLeadForm, magnet: PublicMagnet, source: PublicLeadSource): { payload: PublicLeadPayload } | { error: string } {
  if (!validEmail(form.email)) return { error: "이메일 주소를 확인해 주세요." };
  if (form.consent !== true) return { error: "개인정보 수집·이용 동의에 체크해 주세요." };
  return { payload: { email: form.email.trim(), magnet_key: magnet.key, source, consent_version: magnet.consent_version, consent_checked: true, hp: form.hp } };
}

/** 운영자가 채널마다 붙일 공개 신청 링크. */
export function publicLeadLink(origin: string, magnetKey: string, source: string): string {
  const base = origin.replace(/\/+$/, "");
  return `${base}/lead?${new URLSearchParams({ m: magnetKey, src: source }).toString()}`;
}

function escapeHtml(value: string): string {
  return value.replace(/&/g, "&amp;").replace(/</g, "&lt;").replace(/>/g, "&gt;").replace(/"/g, "&quot;").replace(/'/g, "&#39;");
}

/** heobrain.kr 등에 붙일 단순 링크 버튼 HTML. iframe·스크립트 없이 신청 페이지로 이동만 합니다. */
export function publicLeadEmbed(link: string, title: string): string {
  return `<a href="${escapeHtml(link)}" rel="noopener" style="display:inline-block;padding:12px 20px;border-radius:8px;background:#e96836;color:#fff;font-weight:700;text-decoration:none">무료 자료 받기: ${escapeHtml(title)}</a>`;
}

export async function fetchPublicMagnets(): Promise<PublicMagnet[]> {
  const response = await fetch("/api/public/magnets", { cache: "no-store", headers: { Accept: "application/json" } });
  if (!response.ok) throw new Error("자료 정보를 불러오지 못했어요. 잠시 뒤 다시 열어 주세요.");
  const data = (await response.json()) as { magnets?: PublicMagnet[] };
  return Array.isArray(data.magnets) ? data.magnets : [];
}

/** 공개 신청. 운영자 세션·CSRF 없이 같은 출처에서 보냅니다. 성공 응답은 이미 신청했는지와 상관없이 같습니다. */
export async function submitPublicLead(payload: PublicLeadPayload): Promise<{ ok: true } | { ok: false; message: string }> {
  let response: Response;
  try {
    response = await fetch("/api/public/leads", {
      method: "POST",
      credentials: "omit",
      cache: "no-store",
      headers: { Accept: "application/json", "Content-Type": "application/json" },
      body: JSON.stringify(payload),
    });
  } catch {
    return { ok: false, message: "연결이 불안정해요. 잠시 뒤 다시 시도해 주세요." };
  }
  if (response.status === 202) return { ok: true };
  let detail = "";
  try {
    const data = (await response.json()) as { detail?: unknown };
    if (typeof data.detail === "string") detail = data.detail;
  } catch {
    // 본문이 없으면 기본 문구를 씁니다.
  }
  if (response.status === 429) return { ok: false, message: detail || "신청이 너무 잦아요. 잠시 뒤 다시 시도해 주세요." };
  return { ok: false, message: detail || "신청을 받지 못했어요. 잠시 뒤 다시 시도해 주세요." };
}
