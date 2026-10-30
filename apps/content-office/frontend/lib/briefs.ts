import type { Brief, BriefLanguage, BriefOverrides, BriefPreset, Job } from "./types";

type Form = Record<string, string | boolean>;

export const BRIEF_FIELDS: { key: keyof BriefOverrides; label: string; hint: string }[] = [
  { key: "reader", label: "독자", hint: "예: 편입 영어를 처음 준비하는 직장인" },
  { key: "problem", label: "문제", hint: "독자가 지금 막힌 지점" },
  { key: "current_solution", label: "지금 쓰는 해결책", hint: "예: 검색 결과를 따라 하다가 연결 상태에서 막힘" },
  { key: "goal", label: "이번 콘텐츠의 목표", hint: "예: 두 상태를 구분하고 시험 노트 전달을 확인하기" },
  { key: "outcome", label: "약속한 결과", hint: "읽고 나면 할 수 있는 한 가지" },
  { key: "cta", label: "CTA", hint: "예: 무료 체크리스트 받기" },
];

export const AXIS_LABELS: Record<string, string> = { A: "시험·편입", B: "AI·자동화" };
export const LANGUAGE_LABELS: Record<string, string> = { ko: "한국어", en: "영어" };

export function axisLabel(axis: string): string {
  return AXIS_LABELS[axis] ?? axis;
}

export function presetLabel(presets: Pick<BriefPreset, "id" | "label">[], id: string): string {
  return presets.find((p) => p.id === id)?.label ?? id;
}

function text(form: Form, key: string): string {
  const v = form[key];
  return typeof v === "string" ? v.trim() : "";
}

const KEYS: Exclude<keyof BriefOverrides, "language">[] = ["reader", "problem", "current_solution", "goal", "outcome", "cta", "topic", "prior_knowledge", "tone"];

/** 기존 작업을 편집할 때 표시하지 않는 설정까지 보존합니다. */
export function briefFormFromBrief(brief: Brief | null | undefined): Form {
  const form: Form = { brief_preset: brief?.preset ?? "" };
  for (const key of [...KEYS, "language"] as const) form[`brief_${key}`] = brief?.[key] ?? "";
  return form;
}

export type BriefDraft = { form: Form; baseHash: string; dirty: boolean };
export type BriefDraftUpdate = (current: BriefDraft) => BriefDraft;
type BriefJob = Pick<Job, "id" | "brief" | "brief_hash">;

export function briefDraftFromBrief(brief: Brief | null | undefined, hash?: string): BriefDraft {
  return { form: briefFormFromBrief(brief), baseHash: hash ?? "", dirty: false };
}

/** 편집 중에는 외부 브리프로 입력을 덮지 않습니다. */
export function syncBriefDraft(draft: BriefDraft, brief: Brief | null | undefined, hash?: string): BriefDraft {
  return !hash || draft.dirty || draft.baseHash === hash ? draft : briefDraftFromBrief(brief, hash);
}

export function changeBriefDraft(draft: BriefDraft, key: string, value: string): BriefDraft {
  const form = key === "brief_preset" ? { ...briefFormFromBrief(undefined), brief_preset: value } : { ...draft.form, [key]: value };
  return { ...draft, form, dirty: true };
}

export function briefDraftForJob(drafts: Record<string, BriefDraft>, job: BriefJob): BriefDraft {
  return syncBriefDraft(drafts[job.id] ?? briefDraftFromBrief(job.brief, job.brief_hash), job.brief, job.brief_hash);
}

/** 화면을 닫아도 작업별 미저장 입력을 보존하고, 저장·명시적 초기화 때만 비웁니다. */
export function updateBriefDrafts(drafts: Record<string, BriefDraft>, job: BriefJob, update: BriefDraftUpdate): Record<string, BriefDraft> {
  const next = update(briefDraftForJob(drafts, job));
  if (next.dirty) return drafts[job.id] === next ? drafts : { ...drafts, [job.id]: next };
  if (!drafts[job.id]) return drafts;
  const result = { ...drafts };
  delete result[job.id];
  return result;
}

/** 폼의 brief_* 값을 서버 덮어쓰기 객체로 바꿉니다. 빈 값은 프리셋 값을 그대로 쓰므로 보내지 않습니다. */
export function briefOverridesFromForm(form: Form): { overrides: BriefOverrides } | { error: string } {
  const overrides: BriefOverrides = {};
  for (const key of KEYS) {
    const value = text(form, `brief_${key}`);
    if (value) overrides[key] = value;
  }
  const language = text(form, "brief_language");
  if (language) {
    if (language !== "ko" && language !== "en") return { error: "언어는 ko 또는 en만 고를 수 있습니다." };
    overrides.language = language as BriefLanguage;
  }
  return { overrides };
}

export function briefSummary(brief: Brief | null | undefined): [string, string][] {
  if (!brief) return [];
  const rows: [string, string][] = [["프리셋", [brief.label || brief.preset, axisLabel(brief.axis)].filter(Boolean).join(" · ")]];
  if (brief.reader) rows.push(["독자", brief.reader]);
  if (brief.problem) rows.push(["문제", brief.problem]);
  if (brief.current_solution) rows.push(["현재 해결책", brief.current_solution]);
  if (brief.goal) rows.push(["콘텐츠 목표", brief.goal]);
  if (brief.cta) rows.push(["CTA", brief.cta]);
  if (brief.language) rows.push(["언어", LANGUAGE_LABELS[brief.language] ?? brief.language]);
  return rows;
}
