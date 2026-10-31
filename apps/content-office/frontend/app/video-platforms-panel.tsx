"use client";
import {useEffect, useId, useState} from "react";
import {api} from "../lib/api";
import type {Action, Job} from "../lib/types";
const OPTIONS=[{id:"youtube_shorts",label:"YouTube Shorts",note:"설명·표지 준비 / 연결·출고 승인 후 비공개 전송"},{id:"instagram_reels",label:"Instagram Reels",note:"릴스 캡션·영상 준비 / 외부 임시저장·게시 미연결"}] as const;
type Platform=typeof OPTIONS[number]["id"];
export function VideoPlatformsPanel({job,enabled,busy,action,onSaved,onDirtyChange}:{job:Job;enabled:boolean;busy:boolean;action:Action;onSaved:(job:Job)=>void;onDirtyChange?:(dirty:boolean)=>void}){
 const uid=useId();
 const saved:Platform[]=job.source_packet?.video_platforms??["youtube_shorts"];
 const [selected,setSelected]=useState<Platform[]>(saved);
 const dirty=OPTIONS.some(o=>selected.includes(o.id)!==saved.includes(o.id));
 useEffect(()=>{onDirtyChange?.(dirty);},[dirty,onDirtyChange]);
 const disabled=busy||!enabled;
 async function save(){
  if(disabled||!dirty||!selected.length||!job.source_hash)return;
  await action("영상 목적지 저장",async()=>{const updated=await api.setVideoPlatforms(job.id,selected,job.source_hash!);onSaved(updated);},"영상 목적지를 저장했습니다. 기존 원고①·출고②는 새 판본에서 다시 확인하세요. 생성·업로드는 시작하지 않았습니다.");
 }
 return <fieldset disabled={disabled} style={{minWidth:0,marginTop:20,padding:16,borderRadius:12}} aria-label="영상 플랫폼 선택">
  <legend>영상은 어디에 준비할까요?</legend>
  <p>한 개 또는 둘 다 선택하세요. 같은 세로 영상 원본을 재사용하고, 플랫폼별 설명·출고 상태를 나눕니다.</p>
  <div style={{display:"grid",gridTemplateColumns:"repeat(auto-fit,minmax(200px,1fr))",gap:12}}>{OPTIONS.map(o=><label key={o.id} htmlFor={`${uid}-${o.id}`} style={{display:"block",padding:12,border:"1px solid #cbd5c1",borderRadius:8,overflowWrap:"anywhere"}}><input id={`${uid}-${o.id}`} type="checkbox" checked={selected.includes(o.id)} onChange={e=>setSelected(current=>e.target.checked?[...current,o.id]:current.filter(k=>k!==o.id))}/> <strong>{o.label}</strong><small style={{display:"block",marginTop:6}}>{o.note}</small></label>)}</div>
  <p className="muted">선택 저장은 무료이며 원문·영상 파일을 바꾸거나 외부 발행하지 않습니다. 영상의 댓글·설명·프로필 링크 안내와 자막 위치는 플랫폼별로 검토하세요. 목적지를 변경하면 기존 승인①②와 정식 제작 연결을 다시 확인해야 합니다. 기존 영상·이전 기록은 보존합니다.</p>
  {!enabled&&<p>위에서 ‘세로 영상’을 선택하면 목적지를 고를 수 있습니다.</p>}
  {!selected.length&&<p role="alert">영상 플랫폼을 하나 이상 선택하세요.</p>}
  <button type="button" className="button secondary small" disabled={disabled||!dirty||!selected.length} onClick={()=>void save()}>영상 플랫폼 저장</button>
 </fieldset>;
}
export function VideoPlatformsSummary({job}:{job:Job}){
 const selected=job.source_packet?.video_platforms??["youtube_shorts"];
 if(!job.selections?.video)return null;
 return <p className="notice" aria-label="이번 영상 목적지">영상 목적지: {OPTIONS.filter(o=>selected.includes(o.id)).map(o=>o.label).join(" · ")}. 선택은 외부 업로드 완료를 뜻하지 않습니다.</p>;
}
