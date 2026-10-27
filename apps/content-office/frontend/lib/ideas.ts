import type { IdeaInput } from "./types";

type Form = Record<string, string | boolean>;

function text(form: Form, key: string): string {
  const v = form[key];
  return typeof v === "string" ? v.trim() : "";
}

function count(form: Form, key: string, label: string): number | null | { error: string } {
  const raw = text(form, key).replace(/,/g, "");
  if (raw === "") return null;
  if (!/^\d+$/.test(raw)) return { error: `${label}은(는) 0 이상의 정수여야 합니다.` };
  return Number(raw);
}

function ranged(form: Form, key: string, label: string, min: number, max: number): number | { error: string } {
  const raw = text(form, key);
  const n = raw === "" ? 0 : Number(raw);
  if (!Number.isFinite(n) || n < min || n > max) {
    return { error: `${label}은(는) ${min}~${max} 사이여야 합니다.` };
  }
  return n;
}

export function ideaInputFromForm(form: Form): { input: IdeaInput } | { error: string } {
  const title = text(form, "title");
  if (!title) return { error: "제목을 입력하세요." };
  const source_url = text(form, "source_url");
  if (!source_url.startsWith("https://")) return { error: "출처 URL은 https:// 로 시작해야 합니다." };

  const views = count(form, "views", "조회수");
  if (views !== null && typeof views === "object") return views;
  const avg = count(form, "channel_avg_views", "채널 평균 조회수");
  if (avg !== null && typeof avg === "object") return avg;
  const sources = count(form, "primary_sources", "1차 출처 수");
  if (sources !== null && typeof sources === "object") return sources;
  const demand = ranged(form, "demand", "수요", 0, 100);
  if (typeof demand === "object") return demand;
  const fit = ranged(form, "fit", "적합도", 0, 1);
  if (typeof fit === "object") return fit;

  const policy_flags = text(form, "policy_flags")
    .split(",")
    .map((s) => s.trim())
    .filter(Boolean);
  return {
    input: {
      title,
      source_url,
      views,
      channel_avg_views: avg,
      demand,
      primary_sources: sources ?? 0,
      fit,
      covered_before: form.covered_before === true,
      policy_flags,
    },
  };
}
