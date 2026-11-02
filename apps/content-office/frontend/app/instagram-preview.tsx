import type { Job } from '../lib/types';
import { safeArtifactUrl } from '../lib/workflow';

/** Only show the cards bound to this production manifest, never a newer unapproved replacement. */
export function InstagramPreview({job}: {job: Job}) {
  const current = job.manifest?.source_hash === job.source_hash;
  const files = current ? job.manifest?.files ?? [] : [];
  const cards = files.filter(file => file.outputs?.includes('cards') && /^card-\d{2}\.png$/.test(file.name))
    .sort((a,b) => a.name.localeCompare(b.name));
  const caption = files.find(file => file.name === 'instagram-main-caption.txt');
  return <section aria-label="Instagram 카드뉴스 미리보기">
    <p>출고 파일에 포함된 카드 순서입니다. 캡션과 함께 검토하세요. 이 화면에서는 Instagram에 게시하지 않습니다.</p>
    {!cards.length ? <p className="notice" role="status">현재 원고의 출고 카드뉴스가 아직 없습니다. 만들기에서 카드 콘텐츠를 선택하고, 제작 완료 후 다시 확인하세요. 이전 카드로 대체하지 않습니다.</p> :
      <div className="cards-grid">{cards.map((file,index) => {
        const url = safeArtifactUrl(file.url);
        return <article className="card-slide" key={file.id}>
          <div className="card-slide-image">{url ? <img src={url} alt={`Instagram 카드뉴스 ${index+1}장`} loading="lazy"/> : <p>카드 파일 주소를 확인할 수 없습니다.</p>}</div>
          <span className="thumbnail-number">{index+1} / {cards.length}</span>
          {url && <a className="button secondary small" href={url} download={file.name}>{index+1}장 내려받기</a>}
        </article>;
      })}</div>}
    {caption ? <details><summary>함께 올릴 글 확인</summary>
      <div className="artifact-preview blog-preview"><iframe sandbox="" title={`${job.title} · Instagram 캡션`} src={`/api/jobs/${encodeURIComponent(job.id)}/blog-preview?format=instagram`}/></div>
      <a className="button secondary small" href={safeArtifactUrl(caption.url) ?? undefined} download={caption.name}>캡션 내려받기</a>
    </details> : <p className="muted">함께 올릴 캡션 파일은 아직 없습니다.</p>}
  </section>;
}
