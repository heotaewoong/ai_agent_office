'use client';

import {useCallback, useEffect, useId, useRef, useState} from 'react';
import Link from 'next/link';
import {api} from '../lib/api';
import {libraryBytes, libraryVisible, type LibraryAction, type LibraryInventory, type LibraryItem, type LibraryQuote} from '../lib/artifact-library';
import styles from './artifact-library.module.css';

const labels = {video: '영상', cards: '카드뉴스', thumbnail: '썸네일', document: '글 · PDF'};
const states = {available: '보관 중', trash: '휴지통', attention: '확인 필요'};
type Review = {ids: string[]; action: LibraryAction; quote: LibraryQuote; names: string[]};

export default function ArtifactLibrary({active}: {active: boolean}) {
  const [inventory, setInventory] = useState<LibraryInventory>();
  const [view, setView] = useState<'available' | 'trash'>('available');
  const [kind, setKind] = useState('all'), [query, setQuery] = useState(''), [sort, setSort] = useState('recent');
  const [limit, setLimit] = useState(24), [selected, setSelected] = useState<string[]>([]);
  const [loading, setLoading] = useState(false), [busy, setBusy] = useState(false);
  const [error, setError] = useState(''), [notice, setNotice] = useState('');
  const [review, setReview] = useState<Review>(), [preview, setPreview] = useState<LibraryItem>();
  const dialog = useRef<HTMLDialogElement>(null), previewDialog = useRef<HTMLDialogElement>(null);
  const trigger = useRef<HTMLElement | null>(null), alive = useRef(true), headingRef = useRef<HTMLHeadingElement>(null);
  const heading = useId(), previewHeading = useId();
  useEffect(() => {alive.current = true; return () => {alive.current = false;};}, []);
  const load = useCallback(async () => {
    setLoading(true); setError('');
    try {
      const data = await api.artifactLibrary();
      if (alive.current) {setInventory(data); setSelected(current => current.filter(id => data.items.some(i => i.id === id)));}
    } catch (cause) {if (alive.current) setError(cause instanceof Error ? cause.message : '산출물을 불러오지 못했습니다.');}
    finally {if (alive.current) setLoading(false);}
  }, []);
  useEffect(() => {if (active) void load();}, [active, load]);
  const items = inventory?.items ?? [];
  const visible = libraryVisible(items, view, kind, query, sort);
  const shown = visible.slice(0, limit);
  const eligible = shown.filter(item => !item.protected_reason && item.state !== 'attention');
  const chosen = items.filter(item => selected.includes(item.id));
  function switchView(next: 'available' | 'trash') {setView(next); setSelected([]); setLimit(24); setError('');}
  function close(which: 'review' | 'preview') {
    if (busy) return;
    (which === 'review' ? dialog : previewDialog).current?.close();
    trigger.current?.focus();
  }
  async function openReview(action: LibraryAction, button: HTMLElement) {
    if (!chosen.length || busy) return;
    trigger.current = button; setBusy(true); setError('');
    const ids = chosen.map(item => item.id);
    try {
      const quote = await api.artifactLibraryQuote(ids, action);
      if (!alive.current) return;
      setReview({ids, action, quote, names: chosen.map(item => `${item.title} · ${item.name}`)});
      dialog.current?.showModal();
    } catch (cause) {if (alive.current) setError(cause instanceof Error ? cause.message : '확인 정보를 불러오지 못했습니다.');}
    finally {if (alive.current) setBusy(false);}
  }
  async function commit() {
    if (!review || busy) return;
    setBusy(true); setError('');
    let saved = false;
    try {
      const result = await api.artifactLibraryChange(review.ids, review.action, review.quote.token, crypto.randomUUID());
      saved = true;
      if (!alive.current) return;
      dialog.current?.close(); setReview(undefined); setSelected([]);
      setNotice(result.state === 'partial' ? result.message : review.action === 'trash' ? '휴지통으로 옮겼습니다. 파일은 보존되며 복원할 수 있습니다.' : review.action === 'restore' ? '산출물을 복원했습니다.' : '선택한 파일을 영구삭제했습니다. 원고·승인 기록은 보존했습니다.');
      await load(); headingRef.current?.focus();
    } catch (cause) {
      if (alive.current) setError(saved ? '처리는 완료됐지만 목록 확인이 필요합니다. 다시 실행하지 말고 새로고침하세요.' : cause instanceof Error ? cause.message : '요청 결과를 확인하지 못했습니다. 다시 실행하지 말고 목록을 새로 확인하세요.');
    } finally {if (alive.current) setBusy(false);}
  }
  function toggle(item: LibraryItem) {
    if (busy || item.protected_reason || item.state === 'attention') return;
    setSelected(old => old.includes(item.id) ? old.filter(id => id !== item.id) : old.length < 100 ? [...old, item.id] : old);
  }
  function showPreview(item: LibraryItem, button: HTMLElement) {trigger.current = button; setPreview(item); previewDialog.current?.showModal();}
  return <section className={styles.library} aria-label="산출물 보관함">
    <header className={styles.top}><div><h2 ref={headingRef} tabIndex={-1}>만든 결과물을 한눈에</h2><p>미리 보고, 필요한 것만 남기세요. 원고·승인 기록은 유지됩니다.</p></div><div className={styles.topActions}><Link href="/publish?mode=jobs" className="button secondary">작업별 출고 승인</Link><button className="button secondary" disabled={busy || loading} onClick={() => void load()}>새로고침</button></div></header>
    {inventory && <section className={styles.storage} aria-label="저장공간"><div><strong>EC2 저장공간</strong><span>{libraryBytes(inventory.storage.used_bytes)} / {libraryBytes(inventory.storage.total_bytes)} 사용</span><meter min={0} max={inventory.storage.total_bytes} value={inventory.storage.used_bytes} aria-label="디스크 사용량" /></div><div><strong>{libraryBytes(inventory.storage.free_bytes)} 여유</strong><span>휴지통 이동은 공간을 줄이지 않습니다.</span></div><p>파일을 영구삭제하면 여유 공간을 확보합니다. EBS 할당 용량의 월요금은 별도입니다.</p></section>}
    <div className={styles.tabs} role="tablist" aria-label="산출물 위치"><button role="tab" aria-selected={view === 'available'} disabled={busy} onClick={() => switchView('available')}>보관함 <span>{items.filter(i => i.state === 'available').length}</span></button><button role="tab" aria-selected={view === 'trash'} disabled={busy} onClick={() => switchView('trash')}>휴지통 <span>{items.filter(i => i.state !== 'available').length}</span></button></div>
    {view === 'trash' && <p className={styles.info}>휴지통의 파일은 복원할 수 있습니다. 영구삭제 전 실제 확보 용량과 사용 상태를 다시 확인합니다.</p>}
    <div className={styles.toolbar}><div className={styles.filters} role="group" aria-label="산출물 종류">{[['all', '전체'], ...Object.entries(labels)].map(([key, label]) => <button key={key} disabled={busy} aria-pressed={kind === key} onClick={() => {setKind(key); setSelected([]); setLimit(24);}}>{label}</button>)}</div><label className={styles.search}><span className="sr-only">산출물 검색</span><input type="search" value={query} disabled={busy} onChange={e => {setQuery(e.target.value); setSelected([]); setLimit(24);}} placeholder="제목 또는 파일 이름 검색" /></label></div>
    {error && <div className={styles.error} role="alert">{error}<button type="button" className="button text" disabled={busy} onClick={() => {dialog.current?.close(); void load();}}>목록 다시 확인</button></div>}
    {notice && <p className={styles.info} role="status">{notice}</p>}
    <div className={styles.meta}><label><input type="checkbox" aria-label="현재 목록 선택" disabled={busy || !eligible.length} checked={!!eligible.length && eligible.every(i => selected.includes(i.id))} onChange={e => setSelected(e.target.checked ? eligible.slice(0, 100).map(i => i.id) : [])} />현재 목록 선택</label><span>{visible.length}개 <select aria-label="산출물 정렬" value={sort} disabled={busy} onChange={e => setSort(e.target.value)}><option value="recent">최근 제작순</option><option value="size">용량 큰 순</option></select></span></div>
    {loading && !inventory ? <p className={styles.empty} role="status">산출물과 저장공간을 확인하고 있습니다.</p> : !shown.length ? <div className={styles.empty}><h3>{items.length ? '조건에 맞는 산출물이 없습니다.' : '아직 보관된 산출물이 없습니다.'}</h3><p>영상·카드뉴스·썸네일을 제작하면 여기에 표시됩니다.</p></div> : <div className={styles.grid}>{shown.map(item => <article key={item.id} className={`${styles.card} ${selected.includes(item.id) ? styles.selected : ''}`}>
      <div className={styles.visual}><button type="button" className={styles.previewButton} onClick={e => showPreview(item, e.currentTarget)} aria-label={`${item.title} ${item.name} 미리보기`}>
        {item.preview_url && (item.kind === 'cards' || item.kind === 'thumbnail') ? <img src={item.preview_url} alt={`${item.title} ${labels[item.kind]}`} loading="lazy" /> : <span className={styles.placeholder} aria-hidden="true">{item.kind === 'video' ? '▷' : '▤'}<small>{labels[item.kind]}</small></span>}
      </button><label className={styles.checkbox} title={item.protected_reason || '선택'}><input type="checkbox" aria-label={`${item.title} ${item.name} 선택`} checked={selected.includes(item.id)} disabled={busy || !!item.protected_reason || item.state === 'attention'} onChange={() => toggle(item)} /></label><span className={styles.type}>{labels[item.kind]}{item.kind === 'cards' ? ` · ${item.file_count}장` : ''}</span></div>
      <div className={styles.body}><div className={styles.badges}><span>{item.protected_reason ? '보호됨' : states[item.state]}</span>{item.shared && <span>공유 파일</span>}</div><h3 title={item.title}>{item.title}</h3><p title={item.name}>{item.name}</p><time dateTime={item.modified_at}>{new Date(item.modified_at).toLocaleDateString('ko-KR')}</time>{item.protected_reason && <p className={styles.reason}>{item.protected_reason}</p>}<footer><strong>{libraryBytes(item.size_bytes)}</strong><button type="button" onClick={e => showPreview(item, e.currentTarget)}>미리보기 ↗</button></footer>{item.job_id && <Link className={styles.jobLink} href={`/publish?job=${encodeURIComponent(item.job_id)}`}>이 작업의 출고 화면 →</Link>}</div>
    </article>)}</div>}
    {visible.length > limit && <button className={`button secondary ${styles.more}`} onClick={() => setLimit(n => n + 24)}>24개 더 보기 · {visible.length - limit}개 남음</button>}
    <p className={styles.footnote}>입력 원본과 배포 보관본은 이 목록의 정리 대상이 아닙니다. 현재 제작물·진행 중인 작업은 보호됩니다. 한 번에 최대 100개를 선택할 수 있습니다.</p>
    {chosen.length > 0 && <section className={styles.actionbar} aria-label="선택한 산출물 작업"><div><strong>{chosen.length}개 선택</strong><small>파일 합계 {libraryBytes(chosen.reduce((sum, i) => sum + i.size_bytes, 0))}</small></div><div><button className="button text" disabled={busy} onClick={() => setSelected([])}>선택 해제</button>{view === 'trash' && <button className="button secondary" disabled={busy} onClick={e => void openReview('restore', e.currentTarget)}>복원</button>}<button className={`button ${view === 'trash' ? 'secondary' : 'primary'}`} disabled={busy} onClick={e => void openReview(view === 'trash' ? 'purge' : 'trash', e.currentTarget)}>{busy ? '확인 중…' : view === 'trash' ? '영구삭제 확인' : '휴지통으로'}</button></div></section>}
    <dialog ref={dialog} className={styles.dialog} aria-labelledby={heading} onCancel={e => {if (busy) e.preventDefault();}} onClose={() => {if (!busy) trigger.current?.focus();}}><div className={styles.dialogBody}><h2 id={heading}>{review?.action === 'purge' ? '선택한 파일을 영구삭제할까요?' : review?.action === 'restore' ? '선택한 산출물을 복원할까요?' : '휴지통으로 옮길까요?'}</h2><p>{review?.action === 'purge' ? '삭제한 파일은 복구할 수 없습니다. 원고·승인 기록과 외부 게시물은 그대로 남습니다.' : review?.action === 'restore' ? '자동 제작이나 전송을 시작하지 않고 보관함으로 복원합니다.' : '보관함에서 숨깁니다. 파일은 보존되며 휴지통에서 복원할 수 있습니다.'}</p><ul>{review?.names.map((name, index) => <li key={index}>{name}</li>)}</ul>{review?.action === 'purge' && <div className={styles.reclaim}><span>실제 확보 예상 용량<small>공유 파일의 중복을 제외했습니다.</small></span><strong>{libraryBytes(review.quote.reclaimable_bytes)}</strong></div>}{error && <p role="alert" className={styles.error}>{error}</p>}<p className={styles.footnote}>확인 정보는 5분간 유효합니다. 파일이나 사용 상태가 바뀌면 다시 확인해야 합니다.</p></div><footer className={styles.dialogActions}><button className="button secondary" disabled={busy} onClick={() => close('review')}>취소</button><button className={`button ${review?.action === 'purge' ? 'danger' : 'primary'}`} disabled={busy || !review} onClick={() => void commit()}>{busy ? '처리 중…' : review?.action === 'purge' ? '선택 파일 영구삭제' : review?.action === 'restore' ? '복원하기' : '휴지통으로 이동'}</button></footer></dialog>
    <dialog ref={previewDialog} className={styles.dialog} aria-labelledby={previewHeading} onClose={() => trigger.current?.focus()}><div className={styles.dialogBody}><h2 id={previewHeading}>{preview?.title}</h2><p>{preview?.name}</p>{preview?.preview_url && (preview.kind === 'video' ? <video className={styles.player} src={preview.preview_url} controls playsInline preload="metadata" /> : preview.kind === 'document' ? <iframe className={styles.reader} src={preview.preview_url} sandbox="" title={preview.title} /> : <div className={styles.gallery}>{Array.from({length: Math.min(preview.file_count, 60)}, (_, index) => <img key={index} src={preview.preview_url!.replace(/\/0$/, `/${index}`)} alt={`${preview.title} ${index + 1}`} loading="lazy" />)}</div>)}</div><footer className={styles.dialogActions}><button className="button secondary" onClick={() => close('preview')}>닫기</button></footer></dialog>
  </section>;
}
