"use client";
import {useId, useState} from "react";
import {api} from "../lib/api";
import type {Job} from "../lib/types";

export function ExternalMediaPanel({job, editLocked=false}:{job:Job;editLocked?:boolean}) {
  const id=useId();
  const [reviewed,setReviewed]=useState(false);
  const [busy,setBusy]=useState(false);
  const [error,setError]=useState("");
  const spec=job.source_packet?.external_media as {version?:string;draft_id?:string;scope?:string;channel_pack?:{cards?:string[];platforms?:{name:string;label:string}[]}}|undefined;
  const prepared=spec?.version==="external-media-v1" && Boolean(spec.draft_id);
  const readyDraft=(job.drafts??[]).find(d=>["short.mp4","source-original.md","captions.srt","thumbnail-01.png","description.txt"].every(name=>d.assets?.some(a=>a.name===name)));
  if(!prepared&&!readyDraft)return null;
  const sourceApproved=job.source_approval?.decision==="approved"&&job.source_approval.version===job.source_hash;
  const connected=sourceApproved&&job.manifest?.source_hash===job.source_hash;
  const base=`/api/jobs/${encodeURIComponent(job.id)}/drafts/${encodeURIComponent(spec?.draft_id??readyDraft!.id)}/files/`;
  async function run() {
    if(busy||editLocked||!job.source_hash)return;
    setBusy(true);setError("");
    try {
      if(prepared)await api.adoptExternalMedia(job.id,{version:job.source_hash,reviewed});
      else await api.prepareExternalMedia(job.id,{version:job.source_hash,draft_id:readyDraft!.id});
      window.location.assign(`/publish?job=${encodeURIComponent(job.id)}`);
    } catch(e) {setError(e instanceof Error?e.message:"파일 연결을 확인해 주세요");setBusy(false);}
  }
  return <section className="editor-panel" aria-labelledby={id}>
    <h2 id={id}>기존 완성 영상을 정식 검토로 연결</h2>
    <p>재렌더링과 새 모델 호출 없이 EC2 파일을 사용합니다. 원고①·출고②는 직접 승인하며, 공개 발행하지 않습니다.</p>
    {prepared?<>
      <p><strong>{job.source_packet?.title}</strong> · 비공개 검토용</p>
      <video src={`${base}short.mp4`} controls preload="none" style={{maxWidth:"100%",maxHeight:420}} aria-label="승인할 기존 완성 영상"/>
      <details><summary>연결된 원고 전체 확인</summary><pre style={{whiteSpace:"pre-wrap",overflowWrap:"anywhere"}}>{job.source_packet?.body}</pre></details>
      <p><a href={`${base}captions.srt`} target="_blank" rel="noopener noreferrer">전체 자막 확인</a>{" · "}<a href={`${base}description.txt`} target="_blank" rel="noopener noreferrer">영상 설명 확인</a></p>
      {spec?.channel_pack&&<section aria-label="함께 승인할 카드뉴스와 채널별 글">
        <h3>카드뉴스 8장 · 플랫폼별 원고 4종</h3>
        <p>글은 채널별로 따로 준비했습니다. 원문 사실과 할인 조건을 대조한 뒤 영상과 함께 승인하세요. 공개 발행하지 않습니다.</p>
        <div style={{display:"grid",gridTemplateColumns:"repeat(auto-fit,minmax(150px,1fr))",gap:12}}>
          {spec.channel_pack.cards?.map((name,index)=><a key={name} href={`${base}${encodeURIComponent(name)}`} target="_blank" rel="noopener noreferrer"><img src={`${base}${encodeURIComponent(name)}`} alt={`승인 대기 카드뉴스 ${index+1} / 8`} loading="lazy" style={{width:"100%",height:"auto"}}/></a>)}
        </div>
        <ul>{spec.channel_pack.platforms?.map(post=><li key={post.name}><a href={`${base}${encodeURIComponent(post.name)}`} target="_blank" rel="noopener noreferrer">{post.label} 원고 전체 읽기</a></li>)}</ul>
        <p>이 묶음은 사람이 검토하는 편집 결과입니다. 자동 카드 품질 검사를 통과했다고 표시하지 않습니다.</p>
      </section>}
      <p className="notice">모델 검수 통과 판정이 아닙니다. 음성·자막·후기 사용권과 미확정 혜택 표현을 직접 검토해 주세요. 비공개 검토용이며 공개 사용 승인과는 다릅니다.</p>
      {!connected&&<label><input type="checkbox" checked={reviewed} onChange={e=>setReviewed(e.target.checked)} disabled={busy||editLocked}/> 원문·영상·음성·자막과 첨부 카드·채널별 글을 확인했고, 후기·인물·음성을 비공개 검토에 사용할 권한과 남아 있는 검토 표시를 확인했습니다.</label>}
    </>:<p>선택한 편집본의 원문·자막·표지·영상 해시를 확인해 새 원고 검토 버전으로 연결합니다. 기존 승인은 새 판본에 재사용하지 않습니다.</p>}
    {connected?<p role="status">기존 영상이 정식 제작물에 연결됐습니다. 아래에서 표지를 선택하고 영상 확인 후 출고 승인②을 진행하세요. 아직 업로드하지 않았습니다.</p>:<button type="button" className="button" disabled={busy||editLocked||(prepared&&!reviewed)} onClick={()=>void run()}>{busy?"파일을 검증하고 연결하는 중…":prepared?(sourceApproved?"기존 파일로 제작 연결 다시 확인":"원고 승인① · 기존 파일로 제작 연결"):"이 영상으로 정식 원고 검토 준비"}</button>}
    {editLocked&&<p className="muted">저장하지 않은 변경이나 진행 중인 작업을 먼저 마쳐 주세요.</p>}
    {error&&<p role="alert">{error}</p>}
  </section>;
}
