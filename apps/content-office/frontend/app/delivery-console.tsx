"use client";
import {useEffect,useId,useState} from 'react';
import {api} from '../lib/api';
import type {Channel,ChannelStagingSnapshot,Job} from '../lib/types';
import {choiceReadiness,platformChoices,platformNames,type DeliveryMode} from '../lib/delivery-console';
import {requireStagingSnapshot,stagingExternalLabel,stagingLocalLabel} from '../lib/delivery-readiness';
import {ChannelHandoffPanel,YoutubePanel} from './youtube-panel';

type ConsoleAction=Parameters<typeof YoutubePanel>[0]["action"];
type DraftItem={id:string;channel_key:string;state:string;reason?:string};
const draftLabels:Record<string,string>={pending:'PC 처리 대기',claimed:'처리 중 · 저장 확인 전',platform_draft:'실제 플랫폼 임시저장 확인',platform_private:'실제 비공개 저장 확인',blocked:'차단',unknown:'결과 불명 · 자동 재전송 금지'};
export function DeliveryConsole({job,busy,action,youtubeConfigured,requestBlockedReason}:{job:Job;busy:boolean;action:ConsoleAction;youtubeConfigured:boolean;requestBlockedReason?:string}){
 const uid=useId();
 const [channels,setChannels]=useState<Channel[]>([]),[platform,setPlatform]=useState('youtube'),[account,setAccount]=useState(''),[mode,setMode]=useState<DeliveryMode>('office');
 const [snapshot,setSnapshot]=useState<ChannelStagingSnapshot>(),[items,setItems]=useState<DraftItem[]>([]),[error,setError]=useState(''),[loading,setLoading]=useState(true);
 const revision=JSON.stringify([job.id,job.source_hash,job.manifest?.hash,job.release_approval]);
 useEffect(()=>{let live=true;setLoading(true);setSnapshot(undefined);setItems([]);setError('');
 Promise.all([api.channels(),api.channelStaging(job.id),api.ownerDrafts(job.id)]).then(([c,s,d])=>{requireStagingSnapshot(s,job.id);if(live){setChannels(c.channels);setSnapshot(s);setItems(d.items);}}).catch(e=>{if(live){setChannels([]);setError(e instanceof Error?e.message:'준비 상태를 읽지 못했습니다');}}).finally(()=>{if(live)setLoading(false);});return()=>{live=false;};},[revision,job.id]);
 const accounts=channels.filter(c=>c.platform===platform);
 const channel=accounts.find(c=>c.key===account)??accounts.find(c=>c.locale===job.source_packet?.audience?.language)??accounts[0];
 const row=snapshot?.channels.find(c=>c.channel_key===channel?.key);
 const rows=items.filter(i=>i.channel_key===channel?.key);
 const active=rows.some(i=>['pending','claimed','unknown','platform_draft','platform_private'].includes(i.state));
 const readiness=choiceReadiness(job,channel,mode,requestBlockedReason);
 async function requestDraft(){if(!channel||!job.manifest?.hash||!readiness.ok||busy||loading||error||active)return;
 if(!window.confirm(`${channel.label} 계정에 승인된 원고를 임시저장하도록 PC 실행기에 요청합니다. 공개 게시하지 않습니다. 계속할까요?`))return;
 await action('플랫폼 임시저장 요청',async()=>{const result=await api.requestReleasedDraft(job.id,job.manifest!.hash,channel.key,{key:channel.key,platform:channel.platform,locale:channel.locale,public_url:channel.public_url,external_account_id:channel.external_account_id,publication_enabled:channel.publication_enabled});setItems(result.items);},'PC 실행기 요청을 저장했습니다. 실제 플랫폼 저장 완료는 영수증을 확인하세요.');}
 return <section className="editor-panel" aria-label="플랫폼·계정·전달 방식 선택"><h3>어디에 어떤 방식으로 전달할까요?</h3>
 <p>선택만으로 승인·로그인 정보는 바뀌지 않습니다. 공개 게시와 예약 활성화는 제공하지 않습니다.</p>
 <div style={{display:'grid',gridTemplateColumns:'repeat(auto-fit,minmax(180px,1fr))',gap:12,minWidth:0}}>
 <div><label htmlFor={`${uid}-platform`}>플랫폼</label><select id={`${uid}-platform`} value={platform} disabled={busy} onChange={e=>{setPlatform(e.target.value);setAccount('');setMode('office');}}>{platformChoices.map(p=><option key={p} value={p}>{platformNames[p]}</option>)}</select></div>
 <div><label htmlFor={`${uid}-account`}>계정</label><select id={`${uid}-account`} value={channel?.key??''} disabled={busy||loading||!accounts.length} onChange={e=>setAccount(e.target.value)}>{!accounts.length&&<option value="">등록된 계정 없음</option>}{accounts.map(c=><option key={c.key} value={c.key}>{c.label} · {c.locale==='en'?'영어':'한국어'}</option>)}</select></div>
 <div><label htmlFor={`${uid}-mode`}>전달 방식</label><select id={`${uid}-mode`} value={mode} disabled={busy} onChange={e=>setMode(e.target.value as DeliveryMode)}><option value="office">오피스 보관 · 전송 없음</option><option value="private" disabled={platform!=='youtube'}>YouTube 비공개 업로드</option><option value="draft" disabled={!['linkedin','threads','tistory','naver_blog'].includes(platform)}>플랫폼 임시저장 · 원고</option></select></div></div>
 {loading?<p role="status">현재 승인·계정·파일 상태를 확인하고 있습니다.</p>:error?<p role="alert">{error} · 상태를 확인하기 전에는 전송하지 않습니다.</p>:<>
 <p style={{overflowWrap:'anywhere'}}>대상: {channel?.public_url||'계정 주소 미등록'} · 현재 파일 {job.manifest?.hash?.slice(0,12)||'없음'}</p>
 <p role="status"><strong>{readiness.ok?'준비 상태':'차단 이유'}</strong> · {readiness.reason}</p>
 {platform==='instagram'&&<p>현재 Instagram 릴스의 외부 임시저장 지원은 확인되지 않았습니다. 캡션·영상 준비와 플랫폼 저장은 별개이며 오피스 보관으로 유지합니다.</p>}
 {platform==='tiktok'&&<p>TikTok 계정·임시저장 실행기는 연결되지 않았습니다. 지원하는 것처럼 요청하지 않습니다.</p>}
 {row&&<details><summary>승인 파일 준비·기존 플랫폼 기록</summary><p>{stagingLocalLabel(row)} / {stagingExternalLabel(row)}</p>{row.blockers.length>0&&<ul>{row.blockers.map(r=><li key={r}>{r}</li>)}</ul>}</details>}
 {rows.length>0&&<ul aria-label="이 계정의 실제 초안 전달 기록">{rows.map(i=><li key={i.id}>{draftLabels[i.state]||'상태 확인 필요'}{i.reason?` · ${i.reason}`:''}</li>)}</ul>}
 {mode==='draft'&&<button type="button" className="button" disabled={busy||!readiness.ok||active} onClick={()=>void requestDraft()}>{active?'기존 전달 기록 확인 · 재전송 안 함':'선택 계정에 임시저장 요청'}</button>}
 {mode==='private'&&channel?.platform==='youtube'&&<YoutubePanel key={channel.key} job={job} busy={busy} action={action} youtubeConfigured={youtubeConfigured} preferredChannelKey={channel.key} requestBlockedReason={requestBlockedReason}/>}
 </>}
 <details><summary>전체 채널의 파일 준비·전송 이력</summary><ChannelHandoffPanel job={job} busy={busy} action={action}/></details></section>;
}
