"use client";
import {useEffect,useState} from 'react';
import {api} from '../lib/api';
import type {Job} from '../lib/types';
import {comparisonChoices,changedLineCounts,type ContentHistory} from '../lib/version-history';
import {CardVersionCompare} from './card-version-compare';

const date=(value:string)=>new Date(value).toLocaleString('ko-KR',{timeZone:'Asia/Seoul'});

export function VersionHistoryPanel({job}:{job:Job}) {
  const [data,setData]=useState<ContentHistory|null>(null);
  const [open,setOpen]=useState(false);
  const [error,setError]=useState('');
  const [left,setLeft]=useState('');
  const [right,setRight]=useState('');
  const [filter,setFilter]=useState('all');
  const [loading,setLoading]=useState(false);
  const [refresh,setRefresh]=useState(0);
  useEffect(()=>{if(!open)return;let active=true;setLoading(true);setError('');
    api.versionHistory(job.id).then(result=>{if(active)setData(result);}).catch(e=>{if(active)setError(e instanceof Error?e.message:'버전 기록을 불러오지 못했습니다.');}).finally(()=>{if(active)setLoading(false);});
    return()=>{active=false;};
  },[open,job.id,job.source_hash,job.manifest?.hash,job.drafts?.length,refresh]);
  const choices=data?comparisonChoices(data):[];
  const a=choices.find(c=>c.id===left)??choices.find(c=>c.id!==`source:${job.source_hash}`)??choices[0];
  const b=choices.find(c=>c.id===right)??choices.find(c=>c.id===`source:${job.source_hash}`)??choices.at(-1);
  const changes=a&&b?changedLineCounts(a.body,b.body):null;
  const show=(kind:string)=>filter==='all'||filter===kind;
  return <section className="editor-panel version-history" aria-label="콘텐츠 버전 보관함">
    <div className="version-heading"><div><p className="version-eyebrow">개선해도 이전 결과는 그대로</p><h2>이전 버전과 새 개선본</h2><p>현재 원고·제작물과 별도로 보관한 개선본을 구분해서 확인하세요.</p></div>
      <button className="button secondary" aria-expanded={open} onClick={()=>setOpen(!open)}>{open?'버전 보관함 접기':'버전 보관함 열기'}</button></div>
    {open&&<>
      <p className="notice">가장 최근에 만든 결과가 자동으로 채택되거나 승인되지는 않습니다. 이전 결과를 읽거나 내려받아도 현재 원고·승인은 바뀌지 않습니다.</p>
      {error&&<p className="notice error" role="alert">{error}</p>}
      <button className="button secondary" disabled={loading} onClick={()=>setRefresh(n=>n+1)}>{loading?'버전 기록을 불러오는 중…':'기록 새로 확인'}</button>
      {data&&data.job_id===job.id&&data.current_source_hash===job.source_hash&&data.current_manifest_hash===(job.manifest?.hash??null)&&<>
        <div className="version-stats"><span>원고 <strong>{data.sources.length}</strong></span><span>제작 결과 <strong>{data.productions.length}</strong></span><span>개선 검토본 <strong>{data.drafts.length}</strong></span></div>
        <CardVersionCompare key={job.id} history={data}/>
        <label>보고 싶은 기록<select value={filter} onChange={e=>setFilter(e.target.value)}><option value="all">모든 기록</option><option value="production">제작 결과</option><option value="source">원고</option><option value="draft">개선 검토본</option></select></label>
        {show('production')&&<div className="version-cards">{[...data.productions].reverse().map((p,index)=><details key={p.manifest.hash} className={p.current?'version-card current':'version-card'}><summary><span>제작 결과 {data.productions.length-index}</span><strong>{p.current?'현재 제작물':'보관된 제작물'}</strong><small>{date(p.created_at)} · {p.manifest.files.length}개 파일</small></summary>
          <p>{p.approved_before?'이 판본의 출고 승인 기록 있음 · 현재 승인과 별개':'출고 승인 기록 없음'}</p><p>연결된 원고: {data.sources.findIndex(s=>s.id===p.manifest.source_hash)>=0?`원고 ${data.sources.findIndex(s=>s.id===p.manifest.source_hash)+1}`:'보관 기록 없음'}</p>
          {p.manifest.files.filter(f=>/\.mp4$/i.test(f.name)).map(f=><video key={f.id} controls preload="none" src={f.url} aria-label={`제작 결과 ${data.productions.length-index} 영상`}/>)}
          <ul>{p.manifest.files.filter(f=>['tistory.html','tistory.md','naver.txt','short.mp4','video.mp4','captions.srt'].includes(f.name)).map(f=><li key={f.id}><a href={f.url} download>{f.name} 내려받기</a></li>)}</ul>
          <details><summary>전체 파일 {p.manifest.files.length}개 보기</summary><ul>{p.manifest.files.map(f=><li key={f.id}><a href={f.url} download>{f.name} 내려받기</a></li>)}</ul></details>
        </details>)}</div>}
        {show('source')&&<div className="version-cards">{[...data.sources].reverse().map((s,index)=><details className={s.current?'version-card current':'version-card'} key={s.id}><summary><span>원고 {data.sources.length-index}</span><strong>{s.current?'현재 원고':'이전 원고'}</strong><small>{date(s.created_at)} · {s.approved_before?'승인① 기록 있음':'승인① 기록 없음'}</small></summary><h3>{s.packet.title}</h3><pre>{s.packet.body}</pre></details>)}</div>}
        {show('draft')&&<div className="version-cards">{data.drafts.map((d,i)=><article className="version-card" key={d.id}><strong>{i===0?'가장 최근 개선 검토본 · 별도 보관':'이전 개선 검토본 · 별도 보관'}</strong><h3>{d.title}</h3><p>{d.created_at?date(d.created_at):''} · {d.assets?.length??0}개 검토 파일 · 전체 글·영상은 아래 ‘새 편집 결과’에서 확인하세요.</p><button className="button secondary" onClick={()=>{setLeft(`source:${job.source_hash}`);setRight(`draft:${d.id}`);document.getElementById(`compare-${job.id}`)?.scrollIntoView({block:'nearest'});}}>현재 원고와 비교</button></article>)}</div>}
        {data.sources.length+data.productions.length+data.drafts.length===0&&<p>아직 보관된 버전이 없습니다. 원고를 처음 저장하면 여기에서 확인할 수 있습니다.</p>}
        {choices.length>=2&&<details open id={`compare-${job.id}`} className="version-compare"><summary>두 원고를 나란히 비교하기</summary><div className="version-columns">{[{value:a,set:setLeft,label:'기준 원고'},{value:b,set:setRight,label:'비교할 원고'}].map(x=><label key={x.label}>{x.label}<select value={x.value?.id??''} onChange={e=>x.set(e.target.value)}>{choices.map(c=><option key={c.id} value={c.id}>{c.label}</option>)}</select></label>)}</div>
          {changes&&<p role="status">기준 대비 추가된 줄 {changes.added}개 · 빠진 줄 {changes.removed}개. 빈 줄은 제외하며, 줄 이동과 문장 수정은 본문에서 대조하세요.</p>}
          <div className="version-columns">{[a,b].map((c,i)=><article key={i}><h3>{i===0?'기준':'비교'} · {c?.title}</h3><pre tabIndex={0} aria-label={i===0?'기준 원고 전체 본문':'비교 원고 전체 본문'}>{c?.body}</pre></article>)}</div>
          <p>이전 원고를 다시 쓰려면 내용을 편집기에 새 버전으로 저장하고 검수·승인①을 받으세요.</p><a className="button secondary" href={`/scripts/${encodeURIComponent(job.id)}`}>현재 원고 편집기로 이동</a>
        </details>}
        <p className="muted">이전 버전의 보관을 시작하기 전에 덮어써졌거나 삭제된 파일은 자동 복구되지 않습니다.</p>
      </>}
    </>}
  </section>;
}
