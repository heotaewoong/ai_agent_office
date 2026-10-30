import type { LeadInput } from "./types";

export const LEAD_SOURCES = ["homepage", "youtube", "instagram", "threads", "blog", "newsletter", "other"] as const;
export type LeadForm = LeadInput & { consent_confirmed: boolean };

export function emptyLeadForm(): LeadForm {
  return { email: "", magnet_key: "", source: "other", consent_version: "", consent_text: "", consent_confirmed: false };
}

/** 화면용 이메일 형식 검사. 마스킹·저장은 서버가 합니다. */
export function validEmail(value: string): boolean {
  const v = value.trim();
  if (!v || v.length > 254) return false;
  return /^[A-Za-z0-9._%+-]+@[A-Za-z0-9-]+(\.[A-Za-z0-9-]+)+$/.test(v);
}

export function changeLeadForm(form: LeadForm, key: keyof LeadInput, value: string): LeadForm {
  if (form[key] === value) return form;
  const reset = ["email", "magnet_key", "consent_version", "consent_text"].includes(key);
  return { ...form, [key]: value, consent_confirmed: reset ? false : form.consent_confirmed };
}

export function leadInputFromForm(form: LeadForm): { input: LeadInput } | { error: string } {
  if (!validEmail(form.email)) return { error: "이메일 형식을 확인하세요." };
  if (!/^[A-Za-z0-9][A-Za-z0-9._-]{0,99}$/.test(form.magnet_key.trim())) return { error: "자료 키는 영문·숫자로 시작하는 100자 이내의 영문·숫자·점·밑줄·하이픈으로 입력하세요." };
  if (!LEAD_SOURCES.some((source) => source === form.source)) return { error: "신청 경로를 등록된 출처 중에서 고르세요." };
  const version = form.consent_version.trim(), text = form.consent_text.trim();
  if (!version || version.length > 50 || !text || text.length > 2000) return { error: "독자가 실제로 본 동의 문구(2000자 이내)와 버전(50자 이내)을 입력하세요." };
  if (form.consent_confirmed !== true) return { error: "이 독자가 해당 문구를 보고 실제로 동의했는지 먼저 확인하세요." };
  return { input: { email: form.email.trim(), magnet_key: form.magnet_key.trim(), source: form.source, consent_version: version, consent_text: text } };
}

export function leadFormAfterSave(form: LeadForm): LeadForm {
  return { ...form, email: "", consent_confirmed: false };
}

const SOURCE_LABELS: Record<string, string> = {
  homepage: "홈페이지",
  youtube: "YouTube",
  instagram: "Instagram",
  threads: "Threads",
  blog: "블로그",
  newsletter: "뉴스레터",
  other: "기타 · 직접 등록",
};

export function leadSourceLabel(source: string): string {
  return SOURCE_LABELS[source] ?? source;
}
