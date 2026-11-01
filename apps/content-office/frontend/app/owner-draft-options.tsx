"use client";

import {useEffect, useState} from 'react';
import {api} from '../lib/api';
import type {Channel} from '../lib/types';

const keys = new Set(['youtube_main_ko','youtube_english','instagram_main','instagram_english','threads_main','linkedin_personal','tistory_main','naver_blog_main']);

export function OwnerDraftOptions({language, selected, onChange}: {language?: string; selected: string[]; onChange: (keys: string[]) => void}) {
  const [channels, setChannels] = useState<Channel[]>([]);
  const [error, setError] = useState('');
  useEffect(() => {let live=true; api.channels().then(data => {if(live) setChannels(data.channels.filter(c => keys.has(c.key) && c.locale===language && c.publication_enabled));}).catch(() => {if(live) setError('채널을 불러오지 못했습니다. 초안 자동 전달 없이 승인하거나 다시 확인하세요.');}); return () => {live=false;};}, [language]);
  return <fieldset className="confirm-panel"><legend>승인① 이후 비공개·임시저장할 채널</legend>
    <p>선택한 채널은 제작 후 PC 실행기로 전달합니다. 공개·예약 발행은 하지 않습니다. 로그인·지원 여부는 채널마다 확인하며, 미연결은 대기로 남습니다.</p>
    <p>이 선택은 출고 승인②가 아닙니다. 승인된 원고의 초안을 외부 플랫폼에 비공개로 전송하도록 허용합니다.</p>
    {error && <p role="alert">{error}</p>}
    {channels.map(c => <label key={c.key} className="check-label"><input type="checkbox" checked={selected.includes(c.key)} onChange={e => onChange(e.target.checked ? [...selected,c.key] : selected.filter(k => k!==c.key))}/>{c.label}{c.platform==='youtube' ? ' · 비공개 · PC 실행기 필요' : c.platform==='instagram' ? ' · Meta 계정·초안 지원 확인 필요' : ' · 웹 확장 저장·재열기 검증 필요'}</label>)}
    <p>{selected.length ? `${selected.length}개 채널 선택 · PC와 Chrome이 켜져 있어야 합니다` : '선택하지 않으면 기존 자동 제작만 진행합니다'}</p>
  </fieldset>;
}

type DraftView = {items: {id:string; channel_key:string; state:string; reason?:string}[]};
const labels:Record<string,string>={pending:'PC 연결·처리 대기',claimed:'처리 중 · 완료 확인 전',platform_private:'플랫폼 비공개 확인',platform_draft:'플랫폼 임시저장 확인',blocked:'확인 필요',unknown:'결과 불명 · 자동 재전송 안 함'};
export function OwnerDraftStatus({jobId, revision}: {jobId:string; revision?:string}) {
  const [view,setView]=useState<DraftView>();
  const [error,setError]=useState('');
  const load=()=>{api.ownerDrafts(jobId).then(setView).catch(()=>setError('초안 전달 상태를 확인하지 못했습니다.'));};
  useEffect(()=>{let live=true; api.ownerDrafts(jobId).then(v=>{if(live)setView(v);}).catch(()=>{if(live)setError('초안 전달 상태를 확인하지 못했습니다.');});return()=>{live=false;};},[jobId,revision]);
  return <section className="confirm-panel" aria-label="비공개·임시저장 진행"><h3>플랫폼 초안 전달</h3><p>플랫폼 저장 확인과 앱의 파일 준비를 구분합니다. 공개 발행은 하지 않습니다.</p>{error&&<p role="alert">{error}</p>}{view?.items.length ? <ul>{view.items.map(r=><li key={r.id}>{r.channel_key} · {labels[r.state]||'상태 확인 필요'}{r.reason ? ` · ${r.reason}`:''}</li>)}</ul>:<p>전달 요청이 없습니다. 원고 승인①에서 채널을 고르면 제작 후 자동으로 준비합니다.</p>}<button type="button" className="button secondary small" onClick={load}>전달 상태 새로고침</button></section>;
}
