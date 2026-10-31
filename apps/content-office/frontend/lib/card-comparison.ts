import type {ContentHistory} from './version-history';


export type ComparedCard = {number:number;name:string;url:string;sha256?:string};
export type CardVersion = {id:string;label:string;createdAt?:string;sourceHash?:string;approval:string;cards:ComparedCard[];ambiguous:number[]};

function uniqueCards(cards:ComparedCard[]) {
  const counts = new Map<number,number>();
  for (const card of cards) counts.set(card.number,(counts.get(card.number)??0)+1);
  return {cards:cards.filter(card=>counts.get(card.number)===1).sort((a,b)=>a.number-b.number),ambiguous:[...counts].filter(([,n])=>n>1).map(([number])=>number)};
}
const cardNumber=(name:string)=>{const match=name.match(/(?:^|\/)card-(\d{1,3})\.png$/i);return match&&Number(match[1])>0?Number(match[1]):null;};

export function cardVersionChoices(history:ContentHistory):CardVersion[] {
  const versions:CardVersion[] = [
    ...[...history.productions].reverse().map((p,index)=>({
      id:`production:${p.manifest.hash}`,label:`제작 결과 ${history.productions.length-index}${p.current?' · 현재':''}`,createdAt:p.created_at,sourceHash:p.manifest.source_hash,
      approval:p.approved_before?'과거 출고 승인 기록 있음 · 현재 승인과 별개':'출고 승인 기록 없음',
      ...uniqueCards(p.manifest.files.flatMap(f=>{const number=cardNumber(f.name),expected=`/api/jobs/${encodeURIComponent(history.job_id)}/history/${encodeURIComponent(p.manifest.hash)}/files/${encodeURIComponent(f.id)}`,url=f.url===expected?expected:null;return number&&url?[{number,name:f.name,url,sha256:f.sha256}]:[];})),
    })),
    ...history.drafts.map(d=>({id:`draft:${d.id}`,label:`개선 검토본 · ${d.title}`,createdAt:d.created_at,sourceHash:d.source_hash_snapshot,
      approval:'개선 검토본 · 출고 승인과 별개',
      ...uniqueCards((d.assets??[]).flatMap(f=>{const number=cardNumber(f.name);return number&&f.media_type==='image/png'?[{number,name:f.name,url:`/api/jobs/${encodeURIComponent(history.job_id)}/drafts/${encodeURIComponent(d.id)}/files/${encodeURIComponent(f.name)}`,sha256:f.sha256}]:[];})),
    })),
  ];
  return versions.filter(v=>v.cards.length>0||v.ambiguous.length>0);
}

export function comparedCardNumbers(left?:CardVersion,right?:CardVersion) {
  return [...new Set([...(left?.cards??[]),...(right?.cards??[])].map(c=>c.number))].sort((a,b)=>a-b);
}
