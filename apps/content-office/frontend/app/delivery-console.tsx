"use client";
import {useEffect,useId,useState} from 'react';
import {api} from '../lib/api';
import type {Channel,ChannelStagingSnapshot,Job} from '../lib/types';
import {choiceReadiness,destinationFormat,platformChoices,platformNames} from '../lib/delivery-console';
import {requireStagingSnapshot,stagingExternalLabel,stagingLocalLabel} from '../lib/delivery-readiness';
import {ChannelHandoffPanel,YoutubePanel} from './youtube-panel';

type ConsoleAction=Parameters<typeof YoutubePanel>[0]["action"];
type DraftItem={id:string;channel_key:string;state:string;reason?:string};
const draftLabels:Record<string,string>={office_held:'오피스 게시 대기 · 플랫폼 저장 전',pending:'PC 처리 대기',claimed:'처리 중 · 저장 확인 전',platform_draft:'실제 플랫폼 임시저장 확인',platform_private:'실제 비공개 저장 확인',blocked:'차단',unknown:'결과 불명 · 자동 재전송 금지'};
const holdsDelivery=(item:DraftItem)=>['pending','office_held','claimed','unknown','platform_draft','platform_private'].includes(item.state);

export function DeliveryConsole({job,busy,action,youtubeConfigured,requestBlockedReason}:{job:Job;busy:boolean;action:ConsoleAction;youtubeConfigured:boolean;requestBlockedReason?:string}){
 const uid=useId();
 const [channels,setChannels]=useState<Channel[]>([]);
 const [selection,setSelection]=useState<{revision:string;keys:string[]}>({revision:'',keys:[]});
 const [snapshot,setSnapshot]=useState<ChannelStagingSnapshot>();
 const [items,setItems]=useState<DraftItem[]>([]),[error,setError]=useState(''),[loading,setLoading]=useState(true);
 const revision=JSON.stringify([job.id,job.source_hash,job.manifest?.hash,job.release_approval]);
 const selected=selection.revision===revision?selection.keys:[];
 useEffect(()=>{let live=true;setLoading(true);setSnapshot(undefined);setItems([]);setError('');
 Promise.all([api.channels(),api.channelStaging(job.id),api.ownerDrafts(job.id)]).then(([c,s,d])=>{requireStagingSnapshot(s,job.id);if(live){setChannels(c.channels);setSnapshot(s);setItems(d.items);}}).catch(e=>{if(live){setChannels([]);setError(e instanceof Error?e.message:'준비 상태를 읽지 못했습니다');}}).finally(()=>{if(live)setLoading(false);});return()=>{live=false;};},[revision,job.id]);
 function toggle(key:string,checked:boolean){setSelection({revision,keys:checked?[...selected.filter(k=>k!==key),key]:selected.filter(k=>k!==key)});}
 async function requestDraft(channel:Channel){
  const readiness=choiceReadiness(job,channel,'draft',requestBlockedReason);
  if(!job.manifest?.hash||!readiness.ok||busy||loading||error||items.some(i=>i.channel_key===channel.key&&holdsDelivery(i)))return;
  if(!window.confirm(`${channel.label} 계정에 승인된 원고를 임시저장하도록 PC 실행기에 요청합니다. 공개 게시하지 않습니다. 계속할까요?`))return;
  await action('플랫폼 임시저장 요청',async()=>{const result=await api.requestReleasedDraft(job.id,job.manifest!.hash,channel.key,{key:channel.key,platform:channel.platform,locale:channel.locale,public_url:channel.public_url,external_account_id:channel.external_account_id,publication_enabled:channel.publication_enabled});setItems(result.items);},'PC 실행기 요청을 저장했습니다. 실제 플랫폼 저장 완료는 영수증을 확인하세요.');
 }
 return <section className="editor-panel" aria-label="멀티플랫폼 전달 선택">
  <h3>어디에 어떤 콘텐츠를 전달할까요?</h3>
  <p>플랫폼·계정을 여러 개 선택해 준비 상태를 함께 확인하세요. 선택만으로 전송하거나 승인·로그인 정보를 바꾸지 않습니다.</p>
  <p className="muted">영상은 YouTube 비공개, 글은 지원 플랫폼의 임시저장 경로를 사용합니다. 선택한 계정마다 내용을 확인하고 별도로 요청하세요. 공개·예약 발행은 하지 않습니다.</p>
  {loading?<p role="status">현재 승인·계정·파일 상태를 확인하고 있습니다.</p>:error?<p role="alert">{error} · 상태를 확인하기 전에는 전송하지 않습니다.</p>:<>
   <fieldset className="delivery-destinations"><legend>전달할 플랫폼·계정 · 복수 선택</legend>
    {platformChoices.map(platform=>{const accounts=channels.filter(c=>c.platform===platform);return <div key={platform} className="delivery-platform"><h4>{platformNames[platform]}</h4><small>{destinationFormat(platform).label}</small>
     {!accounts.length?<p className="muted">등록된 계정 없음 · 제작 설정에서 확인하세요.</p>:accounts.map(channel=><label className="delivery-account" htmlFor={`${uid}-${channel.key}`} key={channel.key}>
      <input id={`${uid}-${channel.key}`} type="checkbox" value={channel.key} checked={selected.includes(channel.key)} disabled={busy} onChange={e=>toggle(channel.key,e.target.checked)}/>
      <span>{channel.label} · {channel.locale==='en'?'영어':channel.locale==='ko'?'한국어':channel.locale}</span>
     </label>)}
    </div>;})}
   </fieldset>
   <p role="status">선택한 계정 {selected.length}개 · 현재 출고 판본 {job.manifest?.hash?.slice(0,12)||'없음'}</p>
   {!selected.length&&<p>위에서 계정을 선택하면 해당 영상·글의 준비 상태와 다음 행동이 나타납니다.</p>}
   {channels.filter(c=>selected.includes(c.key)).map(channel=>{
    const format=destinationFormat(channel.platform),readiness=choiceReadiness(job,channel,format.mode,requestBlockedReason);
    const row=snapshot?.channels.find(c=>c.channel_key===channel.key),rows=items.filter(i=>i.channel_key===channel.key),active=rows.some(holdsDelivery);
    return <section className="delivery-target" key={channel.key} aria-label={`${channel.label} 전달 준비`}>
     <h4>{channel.label} · {channel.locale==='en'?'영어':channel.locale==='ko'?'한국어':channel.locale}</h4>
     <p><strong>{format.label}</strong> · {format.note}</p>
     <p className="muted">대상: {channel.public_url||'계정 주소 미등록'}</p>
     <p><strong>{readiness.ok?'준비 상태':'차단 이유'}</strong> · {readiness.reason}</p>
     {row&&<details><summary>승인 파일·기존 플랫폼 기록</summary><p>{stagingLocalLabel(row)} / {stagingExternalLabel(row)}</p>{row.blockers.length>0&&<ul>{row.blockers.map(r=><li key={r}>{r}</li>)}</ul>}</details>}
     {rows.length>0&&<ul aria-label={`${channel.label} 초안 전달 기록`}>{rows.map(i=><li key={i.id}>{draftLabels[i.state]||'상태 확인 필요'}{i.reason?` · ${i.reason}`:''}</li>)}</ul>}
     {format.mode==='draft'&&<button type="button" className="button" disabled={busy||!readiness.ok||active} onClick={()=>void requestDraft(channel)}>{active?'기존 전달 기록 확인 · 재전송 안 함':`${channel.label}에 원고 임시저장 요청`}</button>}
     {format.mode==='private'&&<YoutubePanel job={job} busy={busy} action={action} youtubeConfigured={youtubeConfigured} preferredChannelKey={channel.key} requestBlockedReason={requestBlockedReason}/>}
    </section>;
   })}
  </>}
  <details><summary>전체 채널의 파일 준비·전송 이력</summary><ChannelHandoffPanel job={job} busy={busy} action={action}/></details>
 </section>;
}
