import type { Job } from "./types";
import { sourceApproved } from "./workflow.ts";

/** A production request is not an approval; explain the actual next step. */
export function productionNext(job: Job) {
  if (job.manifest?.files?.length) return null;
  if (["producing", "production_queued"].includes(job.state))
    return { title: "요청한 콘텐츠를 제작하고 있어요", detail: "완료한 파일부터 이 작업에 연결됩니다.", href: null };
  if (!sourceApproved(job.state) || job.source_approval?.decision !== "approved" || job.source_approval.version !== job.source_hash)
    return { title: "현재 원고의 승인①을 기다리고 있어요", detail: "현재 원고의 사람 승인이 없습니다. 원고와 영상 대본을 확인한 뒤 승인하면 선택한 제작을 이어갈 수 있습니다.", href: `/scripts/${encodeURIComponent(job.id)}` };
  return { title: "승인한 원고의 제작을 시작하세요", detail: "작업 시간을 열고 선택한 콘텐츠를 제작하세요. 기존 승인과 예산은 유지됩니다.", href: "/settings" };
}
