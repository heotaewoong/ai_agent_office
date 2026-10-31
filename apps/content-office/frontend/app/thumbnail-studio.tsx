"use client";

import {useCallback, useEffect, useRef, useState} from "react";
import {api} from "../lib/api";
import type {Action, Job} from "../lib/types";
import styles from "./thumbnail-studio.module.css";

type Candidate = {id:string; title:string; angle:string; url:string; parent_id?:string|null; instruction?:string; provenance?:{provider?:string; model?:string}};
export type ThumbnailState = {revision:string; current_source_hash?:string; source_hash?:string; title?:string; stale:boolean; candidates:Candidate[]; selected_id?:string|null; finalized_id?:string|null; task?:{id:string; state:string; result?:{error?:string}}|null};

export function ThumbnailStudio({job, blockedReason, action}:{job:Job; blockedReason?:string; action:Action}) {
  const [data,setData]=useState<ThumbnailState|null>(null);
  const [error,setError]=useState("");
  const [busy,setBusy]=useState(false);
  const [paid,setPaid]=useState(false);
  const [reviewed,setReviewed]=useState(false);
  const [instruction,setInstruction]=useState("");
  const [large,setLarge]=useState<string|null>(null);
  const requestId=useRef(0);
  const dialog=useRef<HTMLDialogElement>(null);
  const load=useCallback(async()=>{const seq=++requestId.current;try {const next=await api.thumbnailStudio(job.id);if(seq===requestId.current){setData(next);setError("");}}catch(e){if(seq===requestId.current)setError(e instanceof Error?e.message:"썸네일을 불러오지 못했습니다");}},[job.id,job.source_hash]);
  useEffect(()=>{setData(null);setReviewed(false);setInstruction("");setLarge(null);void load();return()=>{requestId.current++;};},[load]);
  useEffect(()=>{if(large)dialog.current?.showModal();},[large]);
  const pending=data?.task?.state==="queued"||data?.task?.state==="running";
  useEffect(()=>{if(!pending)return;const timer=setInterval(()=>void load(),2500);return()=>clearInterval(timer);},[pending,load]);
  useEffect(()=>setReviewed(false),[data?.selected_id,data?.revision]);
  const selected=data?.candidates.find(c=>c.id===data.selected_id);
  const before=selected?.parent_id?data?.candidates.find(c=>c.id===selected.parent_id):null;
  async function run(fn:()=>Promise<unknown>){setBusy(true);setError("");try{await fn();await load();}catch(e){setError(e instanceof Error?e.message:"요청을 완료하지 못했습니다. 자동 재시도하지 않습니다");}finally{setBusy(false);}}
  async function generate(edit=false){if(!data||!job.source_hash)return;await run(()=>api.generateThumbnails(job.id,{source_hash:job.source_hash!,revision:data.revision,confirm_paid:paid,...(edit&&selected?{edit_id:selected.id,instruction}: {})}));}
  const disabled=busy||pending||!!data?.stale;
  return <section className={styles.root} aria-labelledby={`thumbnail-studio-${job.id}`}>
    <header><div><p className="eyebrow">원고 기반 이미지 · 최종 결정은 내가</p><h2 id={`thumbnail-studio-${job.id}`}>썸네일 3장을 비교하고 다듬으세요</h2></div><span className="count-pill">{data?.finalized_id&&!data.stale?"최종 확정":"검토 중"}</span></header>
    <p>같은 원고와 제목으로 서로 다른 이미지 3장을 만듭니다. 한 장을 고른 뒤 원하는 부분을 수정하고 최종 확정하세요. 원고 승인①·출고 승인②와 외부 발행은 별도입니다.</p>
    {error&&<p role="alert" className="notice">{error} <button type="button" className="button text" onClick={()=>void load()}>다시 불러오기</button></p>}
    {!data&&!error&&<p role="status">현재 원고의 썸네일을 확인하고 있어요.</p>}
    {data?.stale&&<p role="alert" className="notice">원고가 바뀌었습니다. 이전 후보는 보존했으며 새 원고로 3장을 다시 만들어야 합니다.</p>}
    {data?.task?.result?.error&&<p role="alert" className="notice">{data.task.result.error} 이미 받은 후보는 보존됩니다. 결과 불명 요청은 자동으로 반복하지 않습니다.</p>}
    {pending&&<p role="status">{data?.task?.state==="queued"?"이미지 제작 대기 중입니다. 작업 시간과 작업자 상태를 확인하세요.":"이미지를 만들고 있습니다. 완료된 후보부터 표시됩니다."}</p>}
    {!!data?.candidates.length&&<div className={styles.grid}>{data.candidates.map((c,i)=><article key={c.id} className={c.id===data.selected_id?styles.selected:styles.card}>
      <button type="button" className={styles.image} onClick={()=>setLarge(c.id)} aria-label={`${c.parent_id?"수정본":"후보"} ${i+1} 크게 보기`}><img src={c.url} alt={`${c.angle} — ${c.title}`} /></button>
      <h3>{c.parent_id?"선택 이미지 수정본":`후보 ${i+1}`} · {c.angle}</h3>
      <p>{c.provenance?.provider||"생성 이미지"}{c.parent_id&&" · 원본 보존"}</p>
      <button type="button" className="button secondary" disabled={disabled} aria-pressed={c.id===data.selected_id} onClick={()=>void run(()=>action("썸네일 비교 선택",()=>api.chooseStudioThumbnail(job.id,c.id,data.revision,false),"이미지를 선택했습니다. 필요하면 수정본을 만든 뒤 최종 확정하세요."))}>{c.id===data.selected_id?"현재 비교 선택":"이 이미지 선택"}</button>
    </article>)}</div>}
    {large&&<dialog ref={dialog} className={styles.dialog} aria-label="썸네일 크게 보기" onCancel={()=>setLarge(null)}><button type="button" className="button secondary" autoFocus onClick={()=>setLarge(null)}>확대 닫기</button><img src={data?.candidates.find(c=>c.id===large)?.url} alt="확대한 썸네일 후보" /></dialog>}
    {before&&selected&&<div className={styles.comparison}><figure><img src={before.url} alt="수정 전 선택 이미지"/><figcaption>수정 전</figcaption></figure><figure><img src={selected.url} alt="수정한 이미지"/><figcaption>수정 후 · {selected.instruction}</figcaption></figure></div>}
    <div className={styles.controls}>
      <label><input type="checkbox" checked={paid} onChange={e=>setPaid(e.target.checked)} disabled={busy||pending}/> OpenAI 이미지 비용 확인: 새 후보 최대 3장 × 200원 예약, 수정 1회 200원 예약 · 같은 작업 합산 최대 2,000원 · 기존 예산 안에서만 호출</label>
      {blockedReason&&<p className="notice">{blockedReason} 비교·선택·최종 확정은 계속할 수 있습니다.</p>}
      {(!data?.candidates.length||data.stale||data.candidates.filter(c=>!c.parent_id).length<3)&&<button type="button" className="button primary" disabled={busy||pending||!paid||!!blockedReason||!job.source_hash} onClick={()=>void generate()}>원고로 이미지 3장 만들기</button>}
      {selected&&!data?.stale&&<><label htmlFor={`thumb-edit-${job.id}`}>선택 이미지에서 바꾸고 싶은 부분</label><textarea id={`thumb-edit-${job.id}`} value={instruction} maxLength={1200} onChange={e=>setInstruction(e.target.value)} placeholder="예: 인물과 구도는 유지하고 새벽 러닝의 빛을 더 자연스럽게 해주세요." disabled={busy||pending}/><button type="button" className="button secondary" disabled={disabled||!paid||!instruction.trim()||!!blockedReason} onClick={()=>void generate(true)}>선택 이미지 수정본 만들기</button>
      <label><input type="checkbox" checked={reviewed} onChange={e=>setReviewed(e.target.checked)} disabled={disabled}/> 선택한 이미지의 제목·내용·권리를 확인했습니다.</label>
      <button type="button" className="button primary" disabled={disabled||!reviewed||data?.finalized_id===selected.id} onClick={()=>void run(()=>action("썸네일 최종 확정",()=>api.chooseStudioThumbnail(job.id,selected.id,data!.revision,true),"이 이미지를 최종 썸네일로 확정했습니다. 출고 승인②와 외부 발행은 별도입니다."))}>이 이미지를 최종 썸네일로 확정</button></>}
    </div>
    <p className="muted">이미지는 기존 EC2에 보관합니다. 최종 확정은 현재 원고에만 유효하며, 원고가 바뀌면 재검토합니다. 미승인 편집 영상의 썸네일 확정은 정식 제작·출고 승인을 대신하지 않습니다.</p>
  </section>;
}
