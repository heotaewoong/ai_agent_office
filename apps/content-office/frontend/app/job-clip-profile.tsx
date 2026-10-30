"use client";
import {useEffect,useState} from "react";
import {api} from "../lib/api";
import type {Action,Job} from "../lib/types";

export function JobClipProfile({job,busy,action}:{job:Job;busy:boolean;action:Action}) {
  const [data,setData]=useState<Awaited<ReturnType<typeof api.jobClipProfile>>|null>(null);
  const [error,setError]=useState("");
  useEffect(()=>{let live=true;api.jobClipProfile(job.id).then(d=>{if(live){setData(d);setError("");}}).catch(e=>{if(live)setError(String(e));});return()=>{live=false;};},[job.id,job.source_hash,job.clip_profile_override?.selected_at]);
  const choose=(profile:"none"|"global")=>{
    if(!data||!job.source_hash)return;
    void action("이 작업의 영상 설정",()=>api.setJobClipProfile(job.id,{source_hash:job.source_hash!,override_hash:data.override_hash,profile}),"이 작업의 다음 제작 설정을 저장했습니다. 다른 작업·기존 제작물·원고 승인은 바뀌지 않았습니다.");
  };
  return <section className="editor-panel job-clip-panel" aria-label="작업별 유료 영상 설정"><h3>이 작업의 추가 영상 클립</h3>
    <p>{job.clip_profile_override?.id==="none"?"이 작업은 추가 유료 클립 없이 배경·음성·자막으로 영상을 만듭니다.":"전역 영상 설정을 따릅니다. 제작 전에 유료 클립 예상 비용을 확인하세요."} 음성 등 다른 API 비용에는 기존 작업 상한을 적용합니다.</p>
    {error&&<p className="notice error" role="alert">{error}</p>}
    <button className="button secondary" disabled={busy||!data||data.source_hash!==job.source_hash||job.clip_profile_override?.id==="none"} onClick={()=>choose("none")}>이 작업만 추가 유료 클립 없이 제작</button>
    {job.clip_profile_override?.id==="none"&&<button className="button secondary" disabled={busy||!data||data.source_hash!==job.source_hash} onClick={()=>choose("global")}>전역 설정 다시 따르기</button>}
  </section>;
}
