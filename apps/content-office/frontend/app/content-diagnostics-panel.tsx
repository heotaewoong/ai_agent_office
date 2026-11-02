"use client";
import {useEffect,useState} from 'react';
import {api} from '../lib/api';
import type {ContentDiagnostics,DiagnosticCheck,Job} from '../lib/types';

const LABELS:Record<string,string>={threads_main:'Threads',linkedin_personal:'LinkedIn',instagram_main:'Instagram',instagram_english:'Instagram 영어',x_main:'X'};

function Checks({name,checks}:{name:string;checks:DiagnosticCheck[]}){
  return <section aria-label={`${name} 구성 항목`}><h4>{name}</h4><ul className="settings-list">{checks.map(check=><li key={check.id}><strong>{check.passed?'확인':'참고'} · {check.label}</strong><p className="muted">{check.detail}</p></li>)}</ul></section>;
}

export function ContentDiagnosticsPanel({job}:{job:Job}){
  const [view,setView]=useState<ContentDiagnostics|null>(null),[error,setError]=useState(''),[loading,setLoading]=useState(false),[attempt,setAttempt]=useState(0);
  useEffect(()=>{
    let active=true;
    setView(null);setError('');
    if(!job.source_packet?.body){setLoading(false);return;}
    setLoading(true);
    api.contentDiagnostics(job.id).then(result=>{
      if(!active)return;
      if(!job.source_hash || result.source_hash!==job.source_hash){setError('원고 판본이 바뀌었습니다. 작업을 새로 확인한 뒤 다시 조회하세요.');return;}
      setView(result);
    }).catch(cause=>{if(active)setError(cause instanceof Error?cause.message:'구성 정보를 불러오지 못했습니다.');})
      .finally(()=>{if(active)setLoading(false);});
    return ()=>{active=false;};
  },[job.id,job.source_hash,job.source_packet?.body,attempt]);
  if(!job.source_packet?.body)return null;
  return <details className="studio-disclosure" aria-label="저장된 원고 구성 점검">
    <summary>원고 구성 점검 · 무료</summary>
    <p className="muted">저장된 원고 판본 {job.source_hash?.slice(0,8)} 기준입니다. 편집 중인 미저장 문장은 포함하지 않습니다.</p>
    <p className="muted">길이·소제목·근거 ID 연결 등 표기만 확인합니다. 사실 정확성·답변 적합성·검색 순위·성과를 판정하지 않습니다. 원고와 승인은 바꾸지 않습니다.</p>
    {loading && <p role="status">구성 정보를 확인하고 있습니다.</p>}
    {error && <p role="alert" className="field-error">{error}</p>}
    <button type="button" className="button secondary small" disabled={loading} onClick={()=>setAttempt(value=>value+1)}>구성 정보 다시 조회</button>
    {view?.analysis && <><Checks name="블로그" checks={view.analysis.blog}/>{Object.entries(view.analysis.social).map(([key,checks])=><Checks key={key} name={LABELS[key]??key} checks={checks}/>)}</>}
    {!loading && !error && view && !view.analysis && <p className="muted">점검할 저장 원고가 없습니다.</p>}
  </details>;
}
