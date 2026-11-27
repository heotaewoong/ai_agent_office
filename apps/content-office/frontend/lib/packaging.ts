import type { Job, PackagingBrief } from "./types";

export const TITLE_MAX = 45;
export const THUMB_TEXT_MAX = 12;
export const HOOK_MAX = 120;

export function validatePackagingBrief(brief: PackagingBrief): string[] {
  const issues: string[] = [];
  const titles = brief.titles ?? [];
  const thumbs = brief.thumbnails ?? [];
  if (titles.length !== 3) issues.push("제목은 비교용 3안이 필요합니다");
  titles.forEach((t, i) => {
    if (!(t ?? "").trim()) issues.push(`제목 ${i + 1}안이 비어 있습니다`);
    else if (t.length > TITLE_MAX) issues.push(`제목 ${i + 1}안이 ${TITLE_MAX}자를 넘습니다`);
  });
  if (thumbs.length !== 3) issues.push("썸네일은 비교용 3안이 필요합니다");
  thumbs.forEach((t, i) => {
    const tx = t.text ?? "";
    if (!tx.trim()) issues.push(`썸네일 ${i + 1}안 글자가 비어 있습니다`);
    else if (tx.length > THUMB_TEXT_MAX)
      issues.push(`썸네일 ${i + 1}안 글자가 ${THUMB_TEXT_MAX}자를 넘습니다`);
  });
  const hook = (brief.hook ?? "").trim();
  if (!(hook.length > 0 && hook.length <= HOOK_MAX)) issues.push(`훅은 1~${HOOK_MAX}자로 씁니다`);
  if (!(brief.logline ?? "").trim()) issues.push("로그라인이 없습니다");
  const reasons = (brief.reasons ?? []).length;
  if (reasons < 2 || reasons > 3) issues.push("통할 이유는 2~3개입니다");
  return issues;
}

export function packagingRequired(job: Pick<Job, "article" | "packaging">): boolean {
  return job.article?.origin === "idea" && !job.packaging;
}

// 제목 점수(0원, connect-ai-writer plan-hooks의 점수 방식을 우리 규칙에 맞춤): 100점에서 빼요. 고르는 건 사람이에요.
const OVERCLAIM = ["3일 완성", "무조건 합격", "100% 합격", "뇌과학으로 입증", "단기간에 완벽", "누구나 쉽게", "이것만 보면 끝", "최고", "최초", "평생", "보장"];
const AI_TELLS = ["알아보겠습니다", "살펴보겠습니다", "결론적으로", "정리하자면", "혁신적인", "획기적인", "게임 체인저", "극대화", "시너지"];
function scoreLine(text: string, sourceText: string, short: [number, string], long: [number, string, number]): { score: number; reasons: string[] } {
  const reasons: string[] = [];
  let score = 100;
  if (text.length < short[0]) { score -= 15; reasons.push(short[1]); }
  if (text.length > long[0]) { score -= long[2]; reasons.push(long[1]); }
  const numbers = text.match(/\d+(?:[.,]\d+)?/g) ?? [];
  const missing = numbers.filter((number) => !sourceText.includes(number));
  if (sourceText && missing.length) { score -= 40; reasons.push(`숫자 ${missing.join(", ")}: 근거에서 찾지 못했어요`); }
  for (const word of OVERCLAIM) if (text.includes(word)) { score -= 15; reasons.push(`과장 표현 '${word}'`); }
  for (const word of AI_TELLS) if (text.includes(word)) { score -= 15; reasons.push(`AI 티 나는 말 '${word}'`); }
  if (/[—–]/.test(text)) { score -= 15; reasons.push("줄표는 쓰지 않아요"); }
  return { score: Math.max(0, score), reasons };
}
export function scoreTitle(title: string, sourceText = ""): { score: number; reasons: string[] } {
  const text = (title ?? "").trim();
  if (!text) return { score: 0, reasons: ["제목이 비어 있어요"] };
  return scoreLine(text, sourceText, [12, "12자보다 짧아서 무엇을 얻는지 덜 보여요"], [40, "40자를 넘어 목록에서 잘릴 수 있어요", 10]);
}
// 첫 줄(훅) 점수: 같은 규칙에 길이 기준만 첫 줄용(스레드 첫 줄 60자 안에 요점, writer plan-hooks).
export function scoreHook(hook: string, sourceText = ""): { score: number; reasons: string[] } {
  const text = (hook ?? "").trim().split("\n")[0].trim();
  if (!text) return { score: 0, reasons: ["첫 줄이 비어 있어요"] };
  return scoreLine(text, sourceText, [10, "10자보다 짧아서 읽을 이유가 덜 보여요"], [60, "60자를 넘어 첫 줄에서 요점이 잘려요", 10]);
}
