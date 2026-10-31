"use client";
import {useEffect,useState} from 'react';
import {api} from '../lib/api';
import type {Action,Job} from '../lib/types';
type Studio={model:string;title:string;source_hash:string;manifest_hash?:string;initial_reservation_krw:number;refine_reservation_krw:number;job_cap_krw:number;ready:boolean;blockers:string[];candidates:{id:string;title:string}[];history:{parent_id?:string;feedback?:string;created_at:string}[]};
export function ThumbnailImagesPanel({job,busy,action}:{job:Job;busy:boolean;action:Action}){
 const [status,setStatus]=useState<Studio|null>(null),[error,setError]=useState('');
 const [parent,setParent]=useState(''),[feedback,setFeedback]=useState(''),[confirmed,setConfirmed]=useState(false);
 useEffect(()=>{let active=true;api.thumbnailImages(job.id).then(s=>{if(active){setStatus(s);setError('');}}).catch(()=>{if(active)setError('이미지 제작 상태를 읽지 못했습니다. 화면을 새로고침해 주세요.');});return()=>{active=false;};},[job.id,job.source_hash,job.manifest?.hash,job.updated_at]);
 const ready=Boolean(status?.ready)&&!busy&&confirmed;
 async function request(refine:boolean){
  if(!ready||!status?.manifest_hash||(refine&&(!parent||!feedback.trim())))return;
  const result=await action(refine?'선택 이미지 개선 요청':'원고 기반 이미지 3종 요청',()=>api.requestThumbnailImages(job.id,{source_hash:status.source_hash,manifest_hash:status.manifest_hash!,parent_artifact_id:refine?parent:undefined,feedback:refine?feedback.trim():'',confirm_paid:true}), '이미지 작업을 요청했습니다. 결과를 비교한 뒤 최종 썸네일은 직접 선택하세요.');
  if(result===true)setConfirmed(false);
 }
 return <section className="thumbnail-section" aria-label="원고 기반 썸네일 이미지 제작" aria-busy={busy}>
  <div className="section-heading"><div><p className="eyebrow">확정 원고 → 이미지 비교 → 선택 이미지 개선 → 직접 최종 선택</p><h3>같은 제목으로 이미지 3종을 비교해요</h3></div></div>
  <p><strong>확정 제목:</strong> {status?.title||job.source_packet?.title||job.title}</p>
  <p>제목·본문은 바꾸지 않습니다. 원고의 내용이 보이는 이미지 3장을 만들고, 마음에 드는 이미지를 기준으로 수정할 수 있어요. 생성과 최종 확정은 별도입니다.</p>
  <p className="muted">OpenAI {status?.model||'이미지 API'} · 3장 요청 예약 {status?.initial_reservation_krw??600}원 · 선택 이미지 개선 1장 예약 {status?.refine_reservation_krw??200}원 · 이 작업 썸네일 상한 {status?.job_cap_krw??2000}원. 기존 전체·작업 예산도 적용합니다. 실제 사용량·청구액은 별도 대사합니다.</p>
  {error&&<p role="alert">{error}</p>}
  {status?.blockers.map((b,i)=><p className="notice" key={i}>{b}</p>)}
  <label style={{display:'block',margin:'16px 0'}}><input type="checkbox" checked={confirmed} disabled={busy} onChange={e=>setConfirmed(e.target.checked)}/> 원고 내용과 개선 기준 이미지를 OpenAI로 보내고 위 예약 비용 범위에서 생성하는 것을 확인했습니다.</label>
  <button className="button secondary" disabled={!ready||Boolean(status?.candidates.length)} onClick={()=>void request(false)}>{status?.candidates.length?'이미지 3종 준비됨 · 아래에서 개선':'원고 기반 이미지 3종 생성'}</button>
  <fieldset disabled={busy||!status?.candidates.length} style={{minWidth:0,marginTop:20,padding:16,borderRadius:12}}>
   <legend>내가 고른 이미지를 개선하기</legend>
   <label>개선 기준 이미지<select value={parent} onChange={e=>setParent(e.target.value)} style={{width:'100%'}}><option value="">아래 실제 이미지를 보고 후보를 고르세요</option>{status?.candidates.map((c,i)=><option value={c.id} key={c.id}>후보 {i+1} · {c.id.slice(-8)}</option>)}</select></label>
   <label style={{display:'block',marginTop:12}}>바꾸고 싶은 부분<textarea value={feedback} maxLength={1500} rows={3} onChange={e=>setFeedback(e.target.value)} placeholder="예: 주요 사물은 유지하고 배경을 단순하게, 더 따뜻한 자연광으로" style={{width:'100%'}}/></label>
   <p className="muted">선택 이미지의 실제 원본을 참조해 1장을 개선합니다. 이전 이미지·수정 요청은 보존하고, 새 이미지는 자동으로 최종 선택하지 않습니다.</p>
   <button className="button secondary" disabled={!ready||!parent||!feedback.trim()} onClick={()=>void request(true)}>선택한 이미지 개선 1장 요청</button>
  </fieldset>
  {Boolean(status?.history.length)&&<details style={{marginTop:12}}><summary>이미지 생성·개선 기록 {status?.history.length}회</summary>{status?.history.map((h,i)=><p key={i}>{h.created_at} · {h.parent_id?'선택 이미지 개선':'원고 기반 3종'}{h.feedback?' · '+h.feedback:''}</p>)}</details>}
  <p className="notice">아래 실제 이미지를 크게 보고 ‘이 안으로 선택’을 눌러야 최종 확정됩니다. AI는 승자를 대신 결정하지 않습니다. 새 후보·최종 선택 변경은 원고①를 유지하고 출고②를 다시 검토합니다.</p>
 </section>;
}
