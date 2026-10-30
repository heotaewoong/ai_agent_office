import type {Artifact, EditorialDraft, SourcePacket} from './types';

export type ContentHistory = {
  job_id:string;
  current_source_hash?:string;
  current_manifest_hash?:string|null;
  sources:{id:string; packet:SourcePacket; created_at:string; current:boolean; approved_before:boolean}[];
  productions:{manifest:{hash:string;source_hash?:string;files:Artifact[]};created_at:string;current:boolean;approved_before:boolean}[];
  drafts:EditorialDraft[];
};

export function comparisonChoices(history:ContentHistory) {
  return [
    ...history.sources.map((s,i)=>({id:`source:${s.id}`,label:`원고 ${i+1}${s.current?' · 현재 원고':''}`,body:s.packet.body,title:s.packet.title})),
    ...history.drafts.map(d=>({id:`draft:${d.id}`,label:`개선 검토본 · ${d.title}`,body:d.body,title:d.title})),
  ];
}

export function changedLineCounts(before:string,after:string) {
  const counts=(text:string)=>{const m=new Map<string,number>();for(const line of text.split(/\r?\n/)){if(line.trim())m.set(line,(m.get(line)??0)+1);}return m;};
  const a=counts(before),b=counts(after);
  return {added:[...b].reduce((n,[line,c])=>n+Math.max(0,c-(a.get(line)??0)),0),removed:[...a].reduce((n,[line,c])=>n+Math.max(0,c-(b.get(line)??0)),0)};
}
