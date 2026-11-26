"use client";

import {useCallback, useEffect, useRef, useState} from "react";
import {api} from "../lib/api";
import {frameNote, parseAt, type FrameProvenance} from "../lib/frame-pick";
import type {Action, Job} from "../lib/types";
import styles from "./thumbnail-studio.module.css";

export type ThumbnailFormat = "landscape"|"shorts";
type Candidate = {id:string; title:string; angle:string; url:string; portrait_url?:string|null; parent_id?:string|null; instruction?:string; provenance?:FrameProvenance};
export type ThumbnailState = {revision:string; current_source_hash?:string; source_hash?:string; title?:string; stale:boolean; candidates:Candidate[]; selected_id?:string|null; finalized_id?:string|null; selected_format?:ThumbnailFormat; finalized_format?:ThumbnailFormat|null; default_format?:ThumbnailFormat; task?:{id:string; state:string; result?:{error?:string}}|null};

export function ThumbnailStudio({job, blockedReason, action}:{job:Job; blockedReason?:string; action:Action}) {
  const [data,setData]=useState<ThumbnailState|null>(null);
  const [error,setError]=useState("");
  const [busy,setBusy]=useState(false);
  const [paid,setPaid]=useState(false);
  const [reviewed,setReviewed]=useState(false);
  const [instruction,setInstruction]=useState("");
  const [format,setFormat]=useState<ThumbnailFormat>("landscape");
  const [large,setLarge]=useState<string|null>(null);
  const videos=(job.manifest?.files??[]).filter(f=>f.kind==="video");
  const [videoId,setVideoId]=useState("");
  const [at,setAt]=useState("0:03");
  const [manualX,setManualX]=useState(false);
  const [x,setX]=useState(0.7);
  const requestId=useRef(0);
  const dialog=useRef<HTMLDialogElement>(null);
  const previewOpener=useRef<HTMLButtonElement|null>(null);
  function closePreview(){dialog.current?.close();setLarge(null);previewOpener.current?.focus();}
  const load=useCallback(async()=>{const seq=++requestId.current;try {const next=await api.thumbnailStudio(job.id);if(seq===requestId.current){setData(next);setError("");}}catch(e){if(seq===requestId.current)setError(e instanceof Error?e.message:"썸네일을 불러오지 못했습니다");}},[job.id,job.source_hash]);
  useEffect(()=>{setData(null);setReviewed(false);setInstruction("");setLarge(null);void load();return()=>{requestId.current++;};},[load]);
  useEffect(()=>{if(large)dialog.current?.showModal();},[large]);
  useEffect(()=>{if(data?.selected_format)setFormat(data.selected_format);else if(data?.default_format)setFormat(data.default_format);},[data?.selected_format,data?.default_format]);
  const pending=data?.task?.state==="queued"||data?.task?.state==="running";
  useEffect(()=>{if(!pending)return;const timer=setInterval(()=>void load(),2500);return()=>clearInterval(timer);},[pending,load]);
  useEffect(()=>setReviewed(false),[data?.selected_id,data?.revision,format]);
  const picture=(c:Candidate|undefined)=>c?(format==="shorts"?c.portrait_url??undefined:c.url):undefined;
  const sameFormat=(data?.selected_format??"landscape")===format;
  const selected=sameFormat?data?.candidates.find(c=>c.id===data.selected_id):undefined;
  const before=selected?.parent_id?data?.candidates.find(c=>c.id===selected.parent_id):null;
  async function run(fn:()=>Promise<unknown>){setBusy(true);setError("");try{await fn();await load();}catch(e){setError(e instanceof Error?e.message:"요청을 완료하지 못했습니다. 자동 재시도하지 않습니다");}finally{setBusy(false);}}
  async function generate(edit=false){if(!data||!job.source_hash)return;await run(()=>api.generateThumbnails(job.id,{source_hash:job.source_hash!,revision:data.revision,confirm_paid:paid,...(edit&&selected?{edit_id:selected.id,instruction}: {})}));}
  const disabled=busy||pending||!!data?.stale;
  const seconds=parseAt(at);
  const chosenVideo=videos.find(v=>v.id===videoId)??videos[0];
  async function fromFrame(){if(!data||!job.source_hash||!chosenVideo||seconds==null)return;await run(()=>action("내 영상 장면으로 썸네일 후보 만들기",()=>api.thumbnailFrame(job.id,{source_hash:job.source_hash!,revision:data.revision,video_id:chosenVideo.id,at:seconds,...(manualX?{x}:{})}),"영상에서 가장 선명한 장면을 골라 후보에 넣었습니다. 비용은 0원이에요."));}
  return <section className={styles.root} aria-labelledby={`thumbnail-studio-${job.id}`}>
    <header><div><p className="eyebrow">원고 기반 이미지 · 최종 결정은 내가</p><h2 id={`thumbnail-studio-${job.id}`}>썸네일 3장을 비교하고 다듬으세요</h2></div><span className="count-pill">{data?.finalized_id&&!data.stale&&(data.finalized_format??"landscape")===format?"최종 확정":"검토 중"}</span></header>
    <p>같은 원고와 제목으로 서로 다른 이미지 3장을 만듭니다. 한 장을 고른 뒤 원하는 부분을 수정하고 최종 확정하세요. 원고 승인①·출고 승인②와 외부 발행은 별도입니다.</p>
    <fieldset className={styles.formats}><legend>썸네일 규격 · 글자가 잘리지 않는 원본</legend>
      <label><input type="radio" name={`thumb-format-${job.id}`} checked={format==="landscape"} onChange={()=>{setFormat("landscape");setLarge(null);}}/> YouTube 일반 영상 · 16:9 · 1280×720</label>
      <label><input type="radio" name={`thumb-format-${job.id}`} checked={format==="shorts"} disabled={!data?.candidates.length||data.candidates.some(c=>!c.portrait_url)} onChange={()=>{setFormat("shorts");setLarge(null);}}/> Shorts 세로 표지 · 9:16 · 1080×1920</label>
      <p>가로 표지를 세로로 잘라 쓰지 마세요. 쇼츠 제작은 9:16 표지를 기본 준비하며, 세로 표지는 원본 그림에 제목을 다시 배치하고 규격·제목 넘침을 검사합니다. Shorts 맞춤 표지는 계정 인증과 YouTube Studio의 지원 여부를 별도로 확인해야 합니다.</p>
    </fieldset>
    {error&&<p role="alert" className="notice">{error} <button type="button" className="button text" onClick={()=>void load()}>다시 불러오기</button></p>}
    {!data&&!error&&<p role="status">현재 원고의 썸네일을 확인하고 있어요.</p>}
    {data?.stale&&<p role="alert" className="notice">원고가 바뀌었습니다. 이전 후보는 보존했으며 새 원고로 3장을 다시 만들어야 합니다. 이전 후보는 확대해서 비교할 수 있지만, 선택·수정·최종 확정은 새 원고의 후보를 만든 뒤 가능합니다.</p>}
    {data?.task?.result?.error&&<p role="alert" className="notice">{data.task.result.error} 이미 받은 후보는 보존됩니다. 결과 불명 요청은 자동으로 반복하지 않습니다.</p>}
    {pending&&<p role="status">{data?.task?.state==="queued"?"이미지 제작 대기 중입니다. 작업 시간과 작업자 상태를 확인하세요.":"이미지를 만들고 있습니다. 완료된 후보부터 표시됩니다."}</p>}
    {!!data?.candidates.length&&<div className={styles.grid}>{data.candidates.map((c,i)=><article key={c.id} className={sameFormat&&c.id===data.selected_id?styles.selected:styles.card}>
      <button type="button" className={styles.image} onClick={e=>{previewOpener.current=e.currentTarget;setLarge(c.id);}} aria-label={`${c.parent_id?"수정본":"후보"} ${i+1} 크게 보기`}><img src={picture(c)} alt={`${c.angle} — ${c.title}`} /></button>
      <h3>{c.parent_id?"선택 이미지 수정본":`후보 ${i+1}`} · {c.angle}</h3>
      <p>{frameNote(c.provenance)??(c.provenance?.provider||"생성 이미지")}{c.parent_id&&" · 원본 보존"}</p>
      <button type="button" className="button secondary" disabled={disabled} aria-pressed={sameFormat&&c.id===data.selected_id} onClick={()=>void run(()=>action("썸네일 비교 선택",()=>api.chooseStudioThumbnail(job.id,c.id,data.revision,false,format),"이미지를 선택했습니다. 필요하면 수정본을 만든 뒤 최종 확정하세요."))}>{sameFormat&&c.id===data.selected_id?"현재 비교 선택":"이 이미지 선택"}</button>
    </article>)}</div>}
    {large&&<dialog ref={dialog} className={styles.dialog} aria-label="썸네일 크게 보기" onCancel={e=>{e.preventDefault();closePreview();}}><button type="button" className="button secondary" autoFocus onClick={closePreview}>확대 닫기</button><img src={picture(data?.candidates.find(c=>c.id===large))} alt="확대한 썸네일 후보" /></dialog>}
    {before&&selected&&<div className={styles.comparison}><figure><img src={picture(before)} alt="수정 전 선택 이미지"/><figcaption>수정 전</figcaption></figure><figure><img src={picture(selected)} alt="수정한 이미지"/><figcaption>수정 후 · {selected.instruction}</figcaption></figure></div>}
    {videos.length>0&&<fieldset className={styles.formats}><legend>내 영상 장면으로 후보 만들기 · 0원</legend>
      <p>고른 시각 앞뒤 1초 안에서 흔들림 없고 너무 어둡지 않은 장면을 고른 뒤, 얼굴을 오른쪽에 두고 잘라요. 얼굴을 못 찾으면 가운데를 지키고, 위치를 직접 정할 수도 있어요. 사진은 서버 밖으로 나가지 않아요.</p>
      {videos.length>1&&<label>영상 <select value={chosenVideo?.id??""} onChange={e=>setVideoId(e.target.value)} disabled={disabled}>{videos.map(v=><option key={v.id} value={v.id}>{v.name}</option>)}</select></label>}
      <label>시각(초 또는 분:초) <input value={at} onChange={e=>setAt(e.target.value)} inputMode="numeric" aria-invalid={seconds==null} disabled={disabled} placeholder="1:15"/></label>
      <label><input type="checkbox" checked={manualX} onChange={e=>setManualX(e.target.checked)} disabled={disabled}/> 사람 위치를 직접 정하기</label>
      {manualX&&<label>사람이 있는 가로 위치 {Math.round(x*100)}% <input type="range" min={0} max={1} step={0.01} value={x} onChange={e=>setX(Number(e.target.value))} disabled={disabled}/></label>}
      <button type="button" className="button secondary" disabled={disabled||seconds==null||!job.source_hash} onClick={()=>void fromFrame()}>이 시각 근처 장면으로 후보 만들기</button>
    </fieldset>}
    <div className={styles.controls}>
      <label><input type="checkbox" checked={paid} onChange={e=>setPaid(e.target.checked)} disabled={busy||pending}/> OpenAI 이미지 비용 확인: 새 후보 최대 3장 × 200원 예약, 수정 1회 200원 예약 · 같은 작업 합산 최대 2,000원 · 기존 예산 안에서만 호출</label>
      {blockedReason&&<p className="notice">{blockedReason} {data?.stale?"이전 후보의 확대 비교는 계속할 수 있습니다.":"비교·선택·최종 확정은 계속할 수 있습니다."}</p>}
      {(!data?.candidates.length||data.stale||data.candidates.filter(c=>!c.parent_id).length<3)&&<button type="button" className="button primary" disabled={busy||pending||!paid||!!blockedReason||!job.source_hash} onClick={()=>void generate()}>원고로 이미지 3장 만들기</button>}
      {selected&&!data?.stale&&<><label htmlFor={`thumb-edit-${job.id}`}>선택 이미지에서 바꾸고 싶은 부분</label><textarea id={`thumb-edit-${job.id}`} value={instruction} maxLength={1200} onChange={e=>setInstruction(e.target.value)} placeholder="예: 인물과 구도는 유지하고 새벽 러닝의 빛을 더 자연스럽게 해주세요." disabled={busy||pending}/><button type="button" className="button secondary" disabled={disabled||!paid||!instruction.trim()||!!blockedReason} onClick={()=>void generate(true)}>선택 이미지 수정본 만들기</button>
      <label><input type="checkbox" checked={reviewed} onChange={e=>setReviewed(e.target.checked)} disabled={disabled}/> 선택한 이미지의 제목·내용·권리를 확인했습니다.</label>
      <button type="button" className="button primary" disabled={disabled||!reviewed||data?.finalized_id===selected.id&&(data?.finalized_format??"landscape")===format} onClick={()=>void run(()=>action("썸네일 최종 확정",()=>api.chooseStudioThumbnail(job.id,selected.id,data!.revision,true,format),"이 이미지를 최종 썸네일로 확정했습니다. 출고 승인②와 외부 발행은 별도입니다."))}>이 이미지를 최종 썸네일로 확정</button></>}
    </div>
    <p className="muted">이미지는 기존 EC2에 보관합니다. 최종 확정은 현재 원고에만 유효하며, 원고가 바뀌면 재검토합니다. 미승인 편집 영상의 썸네일 확정은 정식 제작·출고 승인을 대신하지 않습니다.</p>
  </section>;
}
