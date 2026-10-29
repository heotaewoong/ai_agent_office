import type { Brief, BriefLanguage, BriefOverrides, BriefPreset } from "./types";

type Form = Record<string, string | boolean>;

export const BRIEF_FIELDS: { key: keyof BriefOverrides; label: string; hint: string }[] = [
  { key: "reader", label: "독자", hint: "예: 편입 영어를 처음 준비하는 직장인" },
  { key: "problem", label: "문제", hint: "독자가 지금 막힌 지점" },
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

const KEYS: Exclude<keyof BriefOverrides, "language">[] = ["reader", "problem", "outcome", "cta", "topic", "prior_knowledge", "tone"];

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
  if (brief.cta) rows.push(["CTA", brief.cta]);
  if (brief.language) rows.push(["언어", LANGUAGE_LABELS[brief.language] ?? brief.language]);
  return rows;
}
