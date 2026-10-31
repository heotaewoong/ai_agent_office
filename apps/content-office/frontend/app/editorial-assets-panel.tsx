"use client";
import {VideoPlatformsSummary} from "./video-platforms-panel";
import {ExternalMediaPanel} from "./external-media-panel";
import type {EditorialDraft, Job} from "../lib/types";
import {formatBytes} from "../lib/workflow";

const labels: Record<string,string> = {
  "blog-review.md":"블로그 원고", "instagram-caption-review.txt":"인스타그램 게시 문구",
  "instagram-cards-review.md":"인스타그램 카드 구성", "linkedin-review.txt":"링크드인 원고",
  "shorts-reels-script-review.md":"쇼츠·릴스 대본", "threads-review.txt":"스레드 원고",
  "youtube-script-review.md":"유튜브 대본",
};

export function EditorialAssetsPanel({job,onLoadDraft,editLocked=false}:{job:Job;onLoadDraft?:(draft:EditorialDraft)=>void;editLocked?:boolean}) {
  const drafts=(job.drafts??[]).filter(d=>d.assets?.length);
  if(!drafts.length)return null;
  return <section className="editor-panel editorial-panel" aria-label="새 편집 결과 검토">
    <VideoPlatformsSummary job={job}/><ExternalMediaPanel key={job.source_hash} job={job} editLocked={editLocked}/>
    <h2>새 편집 결과</h2>
    <p className="muted">원고·사진·영상의 미승인 검토본입니다. 현재 원고와 승인된 제작물은 그대로 보존합니다.</p>
    {drafts.map((d,index)=>{
      const base=`/api/jobs/${encodeURIComponent(job.id)}/drafts/${encodeURIComponent(d.id)}`;
      return <details className="editorial-draft" key={d.id} open={index===0}>
        <summary><strong>{d.title}</strong><span className="muted">검토 파일 {d.assets!.length}개 · 미승인</span></summary>
        {d.source_hash_snapshot!==job.source_hash&&<p className="notice">이전 원고에 대한 검토본입니다. 현재 원고와 대조하세요.</p>}
        <div className="editorial-actions">
          {onLoadDraft?<button className="button secondary" disabled={editLocked} onClick={()=>onLoadDraft(d)}>이 검토본을 편집기로 불러오기</button>:<a className="button secondary" href={`/scripts/${encodeURIComponent(job.id)}`}>원고 편집기로 이동</a>}
          <a className="button secondary" href={`${base}/preview`} target="_blank" rel="noopener noreferrer">전체 글 새 창으로 보기</a>
        </div>
        {onLoadDraft&&editLocked&&<p className="muted">저장하지 않은 수정이 있거나 처리 중입니다. 현재 편집을 마친 뒤 검토본을 불러오세요.</p>}
        <details className="editorial-preview"><summary>글 미리보기 펼치기</summary>
          <iframe title={`${d.title} · 전체 글 검토`} sandbox="" loading="lazy" src={`${base}/preview`}/>
        </details>
        <div className="editorial-files">{d.assets!.map(f=>{
          const url=`${base}/files/${encodeURIComponent(f.name)}`;
          return <article className="editorial-file" key={f.name}>
            {f.media_type.startsWith('image/')?<img src={url} alt={labels[f.name]??f.name} loading="lazy"/>:f.media_type.startsWith('video/')?<video src={url} controls preload="none" aria-label={labels[f.name]??f.name}/>:null}
            <strong>{labels[f.name]??f.name}</strong>
            <span className="muted editorial-filename">{f.name} · {formatBytes(f.size)}</span>
            <a className="button secondary small" href={url} download aria-label={`${labels[f.name]??f.name} 내려받기`}>내려받기</a>
          </article>;
        })}</div>
      </details>;
    })}
  </section>;
}
