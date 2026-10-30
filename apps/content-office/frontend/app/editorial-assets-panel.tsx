"use client";
import type {Job} from "../lib/types";

export function EditorialAssetsPanel({job}:{job:Job}) {
  const drafts=(job.drafts??[]).filter(d=>d.assets?.length);
  if(!drafts.length)return null;
  return <section className="editor-panel" aria-label="새 편집 결과 검토"><h2>새 편집 결과 · 오피스 안에서 검토</h2>
    <p>원고·사진·영상의 미승인 개정본입니다. 기존 승인 제작물을 바꾸지 않습니다. 내용을 채택하려면 초안을 편집기로 불러와 저장하고 다시 검수하세요.</p>
    {drafts.map(d=><details key={d.id} open><summary>{d.title} · 검토 파일 {d.assets!.length}개</summary>
      {d.source_hash_snapshot!==job.source_hash&&<p className="notice error">이전 원고에 대한 결과입니다. 현재 원고와 대조하세요.</p>}
      <div className="cards-grid">{d.assets!.map(f=>{const url=`/api/jobs/${encodeURIComponent(job.id)}/drafts/${encodeURIComponent(d.id)}/files/${encodeURIComponent(f.name)}`;return <article key={f.name}>
        {f.media_type.startsWith('image/')?<img src={url} alt={f.name} style={{width:'100%',height:'auto',objectFit:'contain'}} loading="lazy"/>:f.media_type.startsWith('video/')?<video src={url} controls preload="metadata" style={{width:'100%',maxHeight:'70vh'}}/>:null}
        <a href={url} download>{f.name} 내려받기</a>
      </article>;})}</div>
    </details>)}
  </section>;
}
