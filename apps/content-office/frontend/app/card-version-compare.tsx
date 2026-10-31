"use client";
import {useState} from 'react';
import type {ContentHistory} from '../lib/version-history';
import {cardVersionChoices,comparedCardNumbers,type ComparedCard,type CardVersion} from '../lib/card-comparison';
import {formatDate} from '../lib/workflow';

function CardImage({card,label}:{card:ComparedCard;label:string}) {
  const [failed,setFailed]=useState(false);
  return <div className="card-compare-media">{failed?<p role="status">이미지를 불러오지 못했습니다. 파일이 남아 있는지 확인하거나 기록을 새로 불러오세요.</p>:<img src={card.url} alt={`${label} · ${card.number}장`} loading="lazy" onError={()=>setFailed(true)}/>}</div>;
}

function VersionImage({version,number,side}:{version:CardVersion;number:number;side:string}) {
  const card=version.cards.find(c=>c.number===number);
  return <article className="card-compare-version"><div className="card-compare-heading"><span>{side}</span><h4>{version.label}</h4><p>{formatDate(version.createdAt,true)} · {version.cards.length}장</p><p>{version.approval}</p></div>
    {card?<CardImage key={`${card.url}:${card.sha256}`} card={card} label={side}/>:<p className="card-compare-missing">이 판본에는 {number}장 파일이 없습니다. 없는 이미지를 새로 만들거나 복원하지 않았습니다.</p>}
    {!!version.ambiguous.length&&<p className="notice">{version.ambiguous.join(', ')}장 파일이 중복돼 해당 번호는 비교에서 제외했습니다.</p>}
    <details className="card-compare-evidence"><summary>판본·파일 기록</summary><dl><dt>판본 ID</dt><dd>{version.id}</dd><dt>연결 원고 해시</dt><dd>{version.sourceHash||'기록 없음'}</dd><dt>이미지 해시</dt><dd>{card?.sha256||'기록 없음'}</dd></dl>{card&&<a href={card.url} target="_blank" rel="noopener noreferrer">원본 이미지 열기 ↗</a>}</details>
  </article>;
}

export function CardVersionCompare({history}:{history:ContentHistory}) {
  const versions=cardVersionChoices(history);
  const [open,setOpen]=useState(false),[left,setLeft]=useState(''),[right,setRight]=useState(''),[number,setNumber]=useState(1);
  const a=versions.find(v=>v.id===left)??versions[0];
  const b=versions.find(v=>v.id===right&&v.id!==a?.id)??versions.find(v=>v.id!==a?.id);
  const numbers=comparedCardNumbers(a,b),selected=numbers.includes(number)?number:numbers[0];
  return <section className="card-version-compare" aria-label="보관 카드 이미지 비교"><h3>카드 이미지로 달라진 점 확인하기</h3><p>실제로 보관된 제작물·검토본의 같은 장 번호를 비교합니다. 현재 원고·출고 판본·승인은 바뀌지 않습니다.</p>
    {versions.length<2?<p className="notice">비교할 카드 이미지 판본이 {versions.length}개입니다. 카드 파일이 있는 판본이 두 개 이상 필요합니다. 별도 재생성 때 보관되지 않은 과거 카드는 복구하지 않습니다.</p>:<>
      <button type="button" className="button secondary" aria-expanded={open} onClick={()=>setOpen(!open)}>{open?'카드 이미지 비교 접기':'카드 이미지 비교 열기'}</button>
      {open&&a&&b&&<><div className="card-compare-controls"><label>기준 카드 판본<select value={a.id} onChange={e=>setLeft(e.target.value)}>{versions.map(v=><option key={v.id} value={v.id}>{v.label}</option>)}</select></label><label>비교할 카드 판본<select value={b.id} onChange={e=>setRight(e.target.value)}>{versions.map(v=><option key={v.id} value={v.id} disabled={v.id===a.id}>{v.label}</option>)}</select></label><label>비교할 장<select value={selected??''} onChange={e=>setNumber(Number(e.target.value))}>{numbers.map(n=><option key={n} value={n}>{n}장</option>)}</select></label></div>
        <p role="status" aria-live="polite">{selected?`${selected}장 비교 · 두 판본의 보관 장 번호 ${numbers.length}개`:'비교할 장 번호가 없습니다. 중복 파일 기록을 확인하세요.'}</p>
        {selected&&<div className="card-compare-columns"><VersionImage version={a} number={selected} side="기준"/><VersionImage version={b} number={selected} side="비교"/></div>}
      </>}
    </>}
  </section>;
}
