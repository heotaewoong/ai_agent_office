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

export function packagingRequired(job: Pick<Job, "article" | "packaging" | "source_packet">): boolean {
  return job.article?.origin === "idea" && !job.packaging && !job.source_packet?.body;
}
