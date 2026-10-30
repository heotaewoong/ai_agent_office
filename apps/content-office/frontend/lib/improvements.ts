export const QUALITY_LABELS = { accuracy: "근거 정확성", clarity: "설명·가독성", actionability: "따라 할 수 있음", voice: "독자·브랜드 맥락", visual: "시각적 설명력" };
import type {Job} from "./types";
export function reviewBinding(job: Pick<Job,"source_hash"|"manifest"|"drafts"|"quiz">) {
  return JSON.stringify([job.source_hash, job.manifest?.hash, job.quiz?.version, job.quiz?.generated_at, (job.drafts??[]).map(d=>[d.id,d.source_hash_snapshot,(d.assets??[]).map(a=>a.sha256)])]);
}
export const REJECTION_LABELS = { fact: "사실", explanation: "설명", style: "문체", design: "디자인", rights: "권리", format: "출력 규격" };
export type ImprovementRecord = {id:string;source_hash?:string;created_at:string;title?:string;note?:string;critical?:boolean;scores?:Record<string,number>;quality_passed?:boolean;question_id?:string;concept_id?:string;attempts?:number;correct?:number;channel_id?:string;paid_revenue_krw?:number;free_orders?:number;views?:number;confirmed?:boolean;use_in_content?:boolean;facts?:string;evidence_note?:string;record_hash?:string};
export type LearningItem = {id:string;question:string;concept_id:string;learning_objective:string;misconception_candidates:string[]};
export type ImprovementWorkspace = {
  job_id:string;source_hash:string|null;note:string;
  candidates:{id:string;hash:string;label:string}[];
  reviews:ImprovementRecord[];experiences:ImprovementRecord[];outcomes:ImprovementRecord[];learning_observations:ImprovementRecord[];
  storyboard:{note:string;scenes:{index:number;kind:string;caption:string;narration:string;steps:string[];comparison:string[];key_phrases:string[];evidence_ids:string[];estimated_read_seconds:number;checks:string[]}[]};
  learning:{status:string;note:string;quiz_hash?:string;items:LearningItem[]};
  casebook:{id:string;axis:string;topic:string;status:string;split:string}[];
};
/** A stale form is preserved for review; it must not submit against a new source. */
export function workspaceIsCurrent(data: ImprovementWorkspace | null, jobId: string, sourceHash?: string | null) {
  return Boolean(data && data.job_id === jobId && data.source_hash && data.source_hash === sourceHash);
}
