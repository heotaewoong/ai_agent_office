import type { Idea, IdeaInput, IdeaSourcesInput } from "./types";
import { briefOverridesFromForm } from "./briefs.ts";

type Form = Record<string, string | boolean>;

function text(form: Form, key: string): string {
  const v = form[key];
  return typeof v === "string" ? v.trim() : "";
}

function count(form: Form, key: string, label: string): number | null | { error: string } {
  const raw = text(form, key).replace(/,/g, "");
  if (raw === "") return null;
  if (!/^\d+$/.test(raw)) return { error: `${label}은(는) 0 이상의 정수여야 합니다.` };
  const n = Number(raw);
  if (n > 1e12) return { error: `${label}은(는) 1조 이하로 입력하세요` };
  return n;
}

function ranged(form: Form, key: string, label: string, min: number, max: number): number | { error: string } {
  const raw = text(form, key);
  if (raw !== "" && !/^\d+(\.\d+)?$/.test(raw)) {
    return { error: `${label}은(는) 숫자로 입력하세요.` };
  }
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
  const brief = briefOverridesFromForm(form);
  if ("error" in brief) return brief;
  const brief_preset = text(form, "brief_preset");
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
      ...(brief_preset ? { brief_preset } : {}),
      ...(Object.keys(brief.overrides).length > 0 ? { brief: brief.overrides } : {}),
    },
  };
}

export type IdeaSourcesDraft = { text: string; baseText: string; baseHash: string; confirmed: boolean; dirty: boolean };

export function ideaSourcesDraft(idea: Idea): IdeaSourcesDraft {
  const text = (idea.source_urls ?? (idea.source_url ? [idea.source_url] : [])).join("\n");
  return { text, baseText: text, baseHash: idea.edit_hash ?? "", confirmed: false, dirty: false };
}

export function changeIdeaSourcesDraft(draft: IdeaSourcesDraft, text: string): IdeaSourcesDraft {
  return { ...draft, text, confirmed: false, dirty: text !== draft.baseText };
}

export function syncIdeaSourcesDraft(draft: IdeaSourcesDraft, idea: Idea): IdeaSourcesDraft {
  return draft.dirty ? draft : ideaSourcesDraft(idea);
}

export function ideaSourcesInput(draft: IdeaSourcesDraft): { input: IdeaSourcesInput } | { error: string } {
  if (!/^[a-f0-9]{64}$/.test(draft.baseHash)) return { error: "기획 판본을 다시 불러온 뒤 저장하세요." };
  if (!draft.confirmed) return { error: "각 출처의 본문과 기획 관련성을 직접 확인한 뒤 체크하세요." };
  const urls = draft.text.split(/\r?\n/).map((url) => url.trim()).filter(Boolean);
  if (urls.length < 1 || urls.length > 10) return { error: "공개 HTTPS 원출처 주소를 한 줄에 하나씩, 1~10개 입력하세요." };
  for (const value of urls) {
    try {
      const url = new URL(value);
      if (value.length > 2000 || url.protocol !== "https:" || !url.hostname || url.username || url.password || (url.port && url.port !== "443")) throw new Error();
    } catch {
      return { error: "출처는 계정 정보가 없는 공개 https:// 주소로 입력하세요." };
    }
  }
  return { input: { source_urls: urls, operator_verified: true, expected_hash: draft.baseHash } };
}
