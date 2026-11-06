"use client";

import { useEffect, useRef, useState, type FormEvent } from 'react';
import Link from 'next/link';
import { api } from '../lib/api';
import { benchmarkPublicUrl, filterBenchmarkIdeas, filterBenchmarkItems, groupBenchmarkSources, parseBenchmarkFields, splitBenchmarkDates, type BenchmarkItem, type BenchmarkOverview, type BenchmarkResearchPacket, type BenchmarkSource } from '../lib/benchmarks';
import styles from './benchmark-panel.module.css';

type SourceEditor = { id: string; creator_id: string; name: string; platform: string; url: string; fields: string; channel_id: string; baseHash: string };
type IdeaEditor = { item: BenchmarkItem; title: string; angle: string; targets: string[]; baseHash: string; manual?: boolean };
type Props = { onSendResearch?: (text: string) => Promise<string | void> };
const activityNames: Record<string, string> = { queued: '수집 대기', running: '수집 중', completed: '수집 완료', failed: '수집 실패', unknown: '결과 확인 필요' };
const statusNames: Record<string, string> = { ready: '아직 수집하지 않음', channel_id_required: 'YouTube 채널 ID 필요', manual: '자동 수집 미연동', ok: '수집 확인', failed: '수집 실패', stale: '이전 조건의 결과' };
function dateLabel(value: string | null | undefined): string {
  if (!value || !Number.isFinite(Date.parse(value))) return '확인 기록 없음';
  return new Date(value).toLocaleString('ko-KR', { timeZone: 'Asia/Seoul', year: 'numeric', month: '2-digit', day: '2-digit', hour: '2-digit', minute: '2-digit' }) + ' KST';
}
function OriginalLink({ url, children = '원문 열기 ↗' }: { url: string; children?: React.ReactNode }) {
  const href = benchmarkPublicUrl(url);
  return href ? <a href={href} target="_blank" rel="noopener noreferrer">{children}</a> : <span>공개 원문 주소 확인 필요</span>;
}

export function BenchmarkPanel({ onSendResearch }: Props) {
  const [data, setData] = useState<BenchmarkOverview | null>(null);
  const [busy, setBusy] = useState('불러오기');
  const [error, setError] = useState('');
  const [notice, setNotice] = useState('');
  const [field, setField] = useState('all');
  const [platform, setPlatform] = useState('all');
  const [query, setQuery] = useState('');
  const [view, setView] = useState<'news' | 'ideas'>('news');
  const [selectedSources, setSelectedSources] = useState<string[]>([]);
  const [manageOpen, setManageOpen] = useState(false);
  const [sourceEditor, setSourceEditor] = useState<SourceEditor | null>(null);
  const [ideaEditor, setIdeaEditor] = useState<IdeaEditor | null>(null);
  const [packet, setPacket] = useState<BenchmarkResearchPacket | null>(null);
  const [packetSelection, setPacketSelection] = useState('');
  const sourceName = useRef<HTMLInputElement>(null);
  const ideaTitle = useRef<HTMLInputElement>(null);
  const packetText = useRef<HTMLTextAreaElement>(null);
  const actionPending = useRef(false);
  useEffect(() => {
    let live = true;
    void api.benchmarks().then(current => { if (live) setData(current); }).catch(cause => { if (live) setError(cause instanceof Error ? cause.message : '보드를 불러오지 못했습니다.'); }).finally(() => { if (live) setBusy(''); });
    return () => { live = false; };
  }, []);
  useEffect(() => { if (sourceEditor) sourceName.current?.focus(); }, [sourceEditor?.id]);
  useEffect(() => { if (ideaEditor) ideaTitle.current?.focus(); }, [ideaEditor?.item.id]);

  async function reload() {
    if (busy) return;
    setBusy('불러오기'); setError('');
    try { setData(await api.benchmarks()); }
    catch (cause) { setError(cause instanceof Error ? cause.message : '보드를 불러오지 못했습니다.'); }
    finally { setBusy(''); }
  }
  async function perform(label: string, operation: () => Promise<void>) {
    if (busy || actionPending.current) return;
    actionPending.current = true;
    setBusy(label); setError(''); setNotice('');
    try { await operation(); }
    catch (cause) { setError(cause instanceof Error ? cause.message : '처리 결과를 확인하지 못했습니다. 입력을 보존했습니다.'); }
    finally { actionPending.current = false; setBusy(''); }
  }
  if (!data) return <section className={styles.panel} aria-label="소식·아이디어 보드">
    <h2>소식·아이디어 보드</h2>
    {error ? <p role="alert" className={styles.error}>{error}</p> : <p role="status">등록한 출처와 수집 기록을 불러오는 중입니다.</p>}
    <button className="button secondary" type="button" disabled={Boolean(busy)} onClick={() => void reload()}>보드 다시 불러오기</button>
  </section>;

  const sources = data.registry.sources;
  const creators = groupBenchmarkSources(sources);
  const filters = { field, platform, query };
  const matches = filterBenchmarkItems(data.items, filters);
  const dates = splitBenchmarkDates(matches, Date.now());
  const ideas = filterBenchmarkIdeas(data.ideas, sources, filters);
  const fields = field === 'all' ? [] : [field];
  const platforms = platform === 'all' ? [] : [platform];
  const selectionKey = JSON.stringify({ source_ids: [...selectedSources].sort(), fields, platforms });
  const packetStale = Boolean(packet && (packet.registry_hash !== data.registry_hash || packetSelection !== selectionKey));
  const checked = data.sources_status.map(status => status.checked_at).filter((value): value is string => Boolean(value) && Number.isFinite(Date.parse(value!))).sort((left, right) => Date.parse(right) - Date.parse(left))[0];
  const selected = new Set(selectedSources);
  const sourceChanged = Boolean(sourceEditor && sourceEditor.baseHash !== data.registry_hash);
  const ideaChanged = Boolean(ideaEditor && ideaEditor.baseHash !== data.registry_hash);

  function editSource(source?: BenchmarkSource) {
    setManageOpen(true);
    setSourceEditor({ id: source?.id ?? '', creator_id: source?.creator_id ?? 'new', name: source?.name ?? '', platform: source?.platform ?? 'instagram', url: source?.url ?? '', fields: source?.fields.join(', ') ?? (field === 'all' ? '' : field), channel_id: source?.channel_id ?? '', baseHash: data!.registry_hash });
  }
  async function saveSource(event: FormEvent) {
    event.preventDefault();
    if (!sourceEditor || sourceChanged) return;
    await perform('등록 저장', async () => {
      const url = benchmarkPublicUrl(sourceEditor.url.trim());
      if (!url) throw new Error('계정 정보가 없는 공개 HTTPS 주소를 입력하세요.');
      const source: BenchmarkSource = {
        id: sourceEditor.id || `source_${crypto.randomUUID().replaceAll('-', '').slice(0, 16)}`,
        creator_id: sourceEditor.creator_id === 'new' ? `creator_${crypto.randomUUID().replaceAll('-', '').slice(0, 16)}` : sourceEditor.creator_id,
        name: sourceEditor.name.trim(), platform: sourceEditor.platform, url, fields: parseBenchmarkFields(sourceEditor.fields),
        ...(sourceEditor.platform === 'youtube' && sourceEditor.channel_id.trim() ? { channel_id: sourceEditor.channel_id.trim() } : {}),
      };
      const next = sourceEditor.id ? sources.map(row => row.id === source.id ? source : row) : [...sources, source];
      setData(await api.saveBenchmarks({ sources: next, expected_hash: sourceEditor.baseHash }));
      setSourceEditor(null); setNotice('경쟁사 등록 정보를 저장했습니다. 자동 수집과 원문 내용 확인은 별도입니다.');
    });
  }
  async function saveIdea(event: FormEvent) {
    event.preventDefault();
    if (!ideaEditor || ideaChanged) return;
    await perform('아이디어 저장', async () => {
      const url = benchmarkPublicUrl(ideaEditor.item.url.trim());
      if (!url) throw new Error('실제로 확인한 게시물의 공개 HTTPS 원문 주소를 입력하세요.');
      await api.saveBenchmarkIdea({ title: ideaEditor.title.trim(), source_url: url, source_id: ideaEditor.item.source_id, fields: ideaEditor.item.fields, target_platforms: ideaEditor.targets, angle: ideaEditor.angle.trim(), expected_hash: ideaEditor.baseHash });
      setIdeaEditor(null);
      setNotice('기획 은행에 후보 아이디어를 저장했습니다. 1차 근거 미확인 상태이며 기획⓪·원고·제작은 시작하지 않았습니다.');
      try { setData(await api.benchmarks()); }
      catch { setError('아이디어 저장은 확인했지만 목록을 다시 읽지 못했습니다. 다시 저장하지 말고 보드 다시 확인을 눌러 주세요.'); }
    });
  }
  function manualIdea(source: BenchmarkSource) {
    setIdeaEditor({ item: { id: `manual-${source.id}`, title: '', url: '', source_id: source.id, creator_id: source.creator_id, source_name: source.name, platform: source.platform, fields: source.fields, published_at: null, checked_at: '', summary: '', verification_state: 'unverified', idea_angle: '' }, title: '', angle: '', targets: [], baseHash: data!.registry_hash, manual: true });
  }
  async function preparePacket() {
    await perform('요청문 준비', async () => {
      const current = await api.benchmarkResearchPacket({ source_ids: selectedSources, fields, platforms, expected_hash: data!.registry_hash });
      setPacket(current); setPacketSelection(selectionKey); setNotice('조사 요청문을 준비했습니다. 아직 비서에게 접수하지 않았습니다.');
    });
  }
  function itemCard(item: BenchmarkItem, needsDate = false) {
    const saved = data!.ideas.some(idea => idea.source_url === item.url);
    return <article className={styles.card} key={item.id}>
      <div className={styles.cardTop}><span className={styles.platform}>{data!.platforms[item.platform] ?? item.platform}</span><span className={styles.muted}>{item.verification_state === 'stale_metadata' ? '이전 관측 · 재확인 필요' : '원문 내용 확인 필요'}</span></div>
      <p className={styles.source}>{item.source_name || '공식 소식'}{!item.source_id && <span> · 기존 공식 뉴스</span>}</p>
      <h3><OriginalLink url={item.url}>{item.title}</OriginalLink></h3>
      <div className={styles.tags}>{item.fields.map(value => <span key={value}>{value}</span>)}</div>
      <p className={styles.summary}>{item.summary || '제목과 공개 메타데이터를 확인한 후보입니다. 세부 내용은 원문을 확인하세요.'}</p>
      <dl className={styles.dates}><div><dt>발행</dt><dd>{needsDate ? '발행일 확인 필요' : dateLabel(item.published_at)}</dd></div><div><dt>확인</dt><dd>{dateLabel(item.checked_at)}</dd></div></dl>
      {item.idea_angle && <details className={styles.angle}><summary>기획 제안 살펴보기</summary><p>{item.idea_angle}</p><small>제목·메타데이터 기반 제안이며 사실 확인과 성과 예측은 별도입니다.</small></details>}
      <div className={styles.cardActions}><OriginalLink url={item.url} /><button type="button" className="button secondary" disabled={Boolean(busy) || saved} onClick={() => setIdeaEditor({ item, title: item.title, angle: item.idea_angle || '', targets: [], baseHash: data!.registry_hash })}>{saved ? '아이디어 저장됨' : '아이디어로 다듬기'}</button></div>
    </article>;
  }

  return <section className={styles.panel} aria-labelledby="benchmark-heading">
    <header className={styles.hero}>
      <div><p className={styles.eyebrow}>내 분야의 소식에서 다음 콘텐츠까지</p><h2 id="benchmark-heading">흩어진 소식을<br /><span>나만의 아이디어로.</span></h2><p>분야·플랫폼별 소식을 살펴보고, 내 콘텐츠 아이디어로 정리하세요.</p></div>
      <div className={styles.heroStats}><div><strong>{creators.length}</strong><span>등록 크리에이터</span></div><div><strong>{new Set(sources.map(source => source.platform)).size}</strong><span>등록 출처 플랫폼</span></div><div><strong>{data.items.length}</strong><span>보관된 소식</span></div></div>
    </header>

    <section className={styles.filters} aria-label="소식 필터">
      <div className={styles.filterHeading}><h3>관심 분야를 골라보세요</h3><button type="button" className={styles.textButton} onClick={() => { setField('all'); setPlatform('all'); setQuery(''); }}>필터 초기화</button></div>
      <div className={styles.chips} role="group" aria-label="분야"><button type="button" aria-pressed={field === 'all'} onClick={() => setField('all')}>전체 분야</button>{data.fields.map(value => <button type="button" key={value} aria-pressed={field === value} onClick={() => setField(value)}>{value}</button>)}</div>
      <div className={styles.filterRow}><label>출처 플랫폼<select aria-label="출처 플랫폼" value={platform} onChange={event => setPlatform(event.target.value)}><option value="all">전체 플랫폼</option>{Object.entries(data.platforms).map(([id, label]) => <option key={id} value={id}>{label}</option>)}</select></label><label className={styles.search}>소식·크리에이터 검색<input type="search" value={query} placeholder="주제나 크리에이터 이름을 입력하세요" onChange={event => setQuery(event.target.value)} /></label></div>
      <p className={styles.muted}>필터는 현재 보관된 자료만 바꿔 보여줍니다. 출처 플랫폼은 자료가 올라온 곳이며, 내가 게시할 대상과 다릅니다.</p>
    </section>

    <div className={styles.statusBar}><div><strong>최근 출처 확인 · {dateLabel(checked)}</strong><p>작업 시간 {data.window_open ? '열림' : '종료'}{data.activity ? ` · ${activityNames[data.activity.state] ?? '수집 상태 확인 필요'}` : ' · 수집 요청 기록 없음'}</p></div><div className={styles.actions}><button type="button" className="button secondary" disabled={Boolean(busy)} onClick={() => void reload()}>보드 다시 확인</button><button type="button" className="button primary" disabled={Boolean(busy) || !data.window_open} onClick={() => void perform('공개 소식 수집 요청', async () => { const result = await api.refreshBenchmarks({ expected_hash: data.registry_hash }); setNotice(result.window_open ? '공개 소식 수집을 요청했습니다. 완료 후 보드 다시 확인을 눌러 결과를 읽어 주세요.' : '작업 시간이 종료돼 수집을 시작하지 않았습니다.'); })}>공개 소식 수집 요청</button></div></div>
    {!data.window_open && <p className={styles.hint}>수집은 열린 작업 시간 안에서만 진행합니다. <Link href="/settings">제작 설정에서 작업 시간 확인</Link></p>}
    <p className={styles.hint}>YouTube 공개 RSS와 수동 원문 등록을 구분합니다. Instagram 등 자동 수집 미연동 출처의 실시간 소식·비공개 성과는 제공하지 않습니다.</p>
    {busy && <p role="status" className={styles.notice}>{busy} 중…</p>}
    {error && <p role="alert" className={styles.error}>{error}</p>}
    {notice && <p role="status" className={styles.notice}>{notice}</p>}
    {data.activity?.error && <p className={styles.error}>수집 기록: {data.activity.error}</p>}

    <div className={styles.sectionHeading}><div className={styles.viewButtons} role="group" aria-label="보드 보기"><button type="button" aria-pressed={view === 'news'} onClick={() => setView('news')}>소식 <span>{matches.length}</span></button><button type="button" aria-pressed={view === 'ideas'} onClick={() => setView('ideas')}>저장 아이디어 <span>{ideas.length}</span></button></div><button type="button" className={styles.textButton} onClick={() => editSource()}>+ 경쟁사 등록</button></div>
    {view === 'news' ? <>
      <div className={styles.sectionHeading}><h3>발행일을 확인한 소식</h3><span className={styles.muted}>최신 발행일 순 · 확인 시각과 구분</span></div>
      {dates.dated.length ? <div className={styles.cards}>{dates.dated.map(item => itemCard(item))}</div> : <div className={styles.empty}><h4>{data.items.length ? '현재 필터에 맞는 소식이 없어요' : '아직 수집한 소식이 없어요'}</h4><p>{data.items.length ? '다른 분야나 플랫폼을 고르거나 검색어를 줄여보세요. 발행일 확인이 필요한 자료는 아래에 따로 모았습니다.' : '경쟁사를 등록하고 출처별 연결 상태를 확인하세요. 작업 시간이 열려 있다면 공개 소식 수집을 요청할 수 있어요.'}</p></div>}
      {dates.undated.length > 0 && <details className={styles.undated}><summary>발행일 확인이 필요한 자료 {dates.undated.length}건</summary><p className={styles.hint}>날짜 미상·미래 날짜·잘못된 날짜는 최신 소식에 섞지 않았습니다.</p><div className={styles.cards}>{dates.undated.map(item => itemCard(item, true))}</div></details>}
    </> : <section aria-label="저장한 후보 아이디어">
      <p className={styles.hint}>후보 저장은 원출처 확인이나 기획⓪ 승인이 아닙니다. 기획 은행에서 근거를 확인한 뒤 선택하세요.</p>
      {ideas.length ? <div className={styles.cards}>{ideas.map(idea => <article className={styles.card} key={idea.id}><span className={styles.platform}>{data.platforms[idea.platform ?? sources.find(source => source.id === idea.source_id)?.platform ?? 'website'] ?? '출처 미확인'} 출처 · 후보 아이디어</span><h3>{idea.title}</h3><p className={styles.summary}>{idea.angle || '구체적인 독자 질문과 새 관점을 기획 은행에서 다듬어 주세요.'}</p><p className={styles.muted}>게시 대상: {idea.target_platforms?.map(id => data.platforms[id] ?? id).join(' · ') || '미지정'}</p>{Boolean(idea.blocked?.length) && <p className={styles.hint}>확인할 조건 {idea.blocked.length}개 · 기획 은행에서 확인</p>}<div className={styles.cardActions}>{idea.source_url && <OriginalLink url={idea.source_url} />}<Link href="/plans">기획 은행에서 검토 →</Link></div></article>)}</div> : <div className={styles.empty}><h4>조건에 맞는 저장 아이디어가 없어요</h4><p>소식의 ‘아이디어로 다듬기’에서 내 관점과 게시 대상을 정해 후보로 저장하세요.</p></div>}
    </section>}

    {ideaEditor && <section className={styles.editor} aria-labelledby="benchmark-idea-heading"><h3 id="benchmark-idea-heading">내 콘텐츠의 관점으로 다듬기</h3><p className={styles.hint}>출처: {ideaEditor.item.source_name} · 1차 근거는 미확인으로 저장합니다.</p><form onSubmit={event => void saveIdea(event)}>{ideaEditor.manual && <label>확인한 게시물의 원문 주소<input type="url" value={ideaEditor.item.url} maxLength={2048} required disabled={Boolean(busy)} placeholder="계정 홈이 아닌 실제 게시물의 https:// 주소" onChange={event => setIdeaEditor({ ...ideaEditor, item: { ...ideaEditor.item, url: event.target.value } })} /><small>직접 읽은 공개 게시물 주소를 입력하세요. 저장은 원문 검증 완료를 뜻하지 않습니다.</small></label>}<label>후보 제목<input ref={ideaTitle} value={ideaEditor.title} maxLength={200} required disabled={Boolean(busy)} onChange={event => setIdeaEditor({ ...ideaEditor, title: event.target.value })} /></label><label>내가 더할 관점<textarea value={ideaEditor.angle} maxLength={1000} required disabled={Boolean(busy)} onChange={event => setIdeaEditor({ ...ideaEditor, angle: event.target.value })} /></label><fieldset disabled={Boolean(busy)}><legend>이 아이디어를 게시할 대상</legend><div className={styles.checks}>{Object.entries(data.platforms).map(([id, label]) => <label key={id}><input type="checkbox" checked={ideaEditor.targets.includes(id)} onChange={event => setIdeaEditor({ ...ideaEditor, targets: event.target.checked ? [...ideaEditor.targets, id] : ideaEditor.targets.filter(value => value !== id) })} />{label}</label>)}</div></fieldset>{ideaChanged && <p role="alert">경쟁사 등록이 변경됐습니다. 입력을 보존했어요. 원문을 다시 확인하고 편집을 새로 시작하세요.</p>}<div className={styles.actions}><button type="submit" className="button primary" disabled={Boolean(busy) || ideaChanged || !ideaEditor.targets.length}>후보 아이디어 저장</button><button type="button" className="button secondary" disabled={Boolean(busy)} onClick={() => setIdeaEditor(null)}>편집 닫기</button></div></form></section>}

    <details className={styles.management} open={manageOpen} onToggle={event => setManageOpen(event.currentTarget.open)}><summary>경쟁사 등록·수집 상태 관리 <span>{sources.length}개 출처 · {creators.length}명</span></summary><p className={styles.hint}>같은 크리에이터의 계정은 하나로 묶고 플랫폼별 출처와 수집 상태를 따로 관리합니다. 등록만으로 자동 수집이 연결되지는 않습니다.</p>
      <div className={styles.creatorGrid}>{creators.map(creator => <section key={creator.id} className={styles.creator}><h4>{creator.name}</h4>{creator.sources.map(source => { const status = data.sources_status.find(row => row.source_id === source.id); return <div key={source.id} className={styles.sourceRow}><div><strong>{data.platforms[source.platform] ?? source.platform}</strong><p>{source.name}</p><p className={styles.muted}>{statusNames[status?.state ?? ''] ?? '수집 상태 미확인'} · {status?.method === 'youtube_rss' ? 'YouTube 공개 RSS' : status?.method === 'manual' ? '수동 원문 확인' : '수집 수단 미확인'}</p><p className={styles.muted}>확인 {dateLabel(status?.checked_at)}{status?.count !== null && status?.count !== undefined ? ` · ${status.count}건` : ' · 건수 미확인'}</p>{status?.note && <p className={styles.hint}>{status.note}</p>}{status?.error && <p className={styles.error}>{status.error}</p>}<div className={styles.tags}>{source.fields.map(value => <span key={value}>{value}</span>)}</div></div><div className={styles.sourceActions}><OriginalLink url={source.url} /><button type="button" className={styles.textButton} disabled={Boolean(busy)} onClick={() => manualIdea(source)}>원문에서 아이디어 만들기<span className={styles.srOnly}> · {source.name}</span></button><button type="button" className={styles.textButton} disabled={Boolean(busy)} onClick={() => editSource(source)}>등록 편집<span className={styles.srOnly}> · {source.name}</span></button></div></div>; })}</section>)}</div>
      <button type="button" className="button secondary" disabled={Boolean(busy) || sources.length >= 64} onClick={() => editSource()}>새 경쟁사 출처 등록</button>
      {sourceEditor && <form className={styles.editor} onSubmit={event => void saveSource(event)}><h3>{sourceEditor.id ? '경쟁사 출처 편집' : '새 경쟁사 출처'}</h3><div className={styles.formGrid}><label>크리에이터 이름<input ref={sourceName} value={sourceEditor.name} maxLength={80} required disabled={Boolean(busy)} onChange={event => setSourceEditor({ ...sourceEditor, name: event.target.value })} /></label><label>같은 크리에이터로 묶기<select value={sourceEditor.creator_id} disabled={Boolean(busy)} onChange={event => setSourceEditor({ ...sourceEditor, creator_id: event.target.value })}><option value="new">새 크리에이터로 등록</option>{creators.map(creator => <option key={creator.id} value={creator.id}>{creator.name} · {creator.sources.length}개 플랫폼 출처</option>)}</select></label><label>출처 플랫폼<select value={sourceEditor.platform} disabled={Boolean(busy)} onChange={event => setSourceEditor({ ...sourceEditor, platform: event.target.value })}>{Object.entries(data.platforms).map(([id, label]) => <option key={id} value={id}>{label}</option>)}</select></label><label>공개 계정·사이트 주소<input type="url" value={sourceEditor.url} maxLength={2048} required disabled={Boolean(busy)} placeholder="https://" onChange={event => setSourceEditor({ ...sourceEditor, url: event.target.value })} /></label></div><label>분야 · 쉼표로 구분, 최대 6개<input value={sourceEditor.fields} maxLength={240} required disabled={Boolean(busy)} placeholder="AI 활용, 업무 자동화" onChange={event => setSourceEditor({ ...sourceEditor, fields: event.target.value })} /></label>{sourceEditor.platform === 'youtube' && <label>YouTube 공개 채널 ID · 선택<input value={sourceEditor.channel_id} pattern="UC[A-Za-z0-9_-]{22}" maxLength={24} disabled={Boolean(busy)} placeholder="UC로 시작하는 24자리 ID" onChange={event => setSourceEditor({ ...sourceEditor, channel_id: event.target.value })} /><small>검증된 채널 ID가 있어야 공개 RSS 수집을 준비할 수 있어요. 계정 로그인·구독은 바꾸지 않습니다.</small></label>}{sourceChanged && <p role="alert" className={styles.error}>다른 화면에서 등록이 바뀌었습니다. 입력은 보존했습니다. 최신 목록을 확인하고 등록 편집을 새로 시작하세요.</p>}<div className={styles.actions}><button type="submit" className="button primary" disabled={Boolean(busy) || sourceChanged}>등록 정보 저장</button><button type="button" className="button secondary" disabled={Boolean(busy)} onClick={() => setSourceEditor(null)}>편집 닫기</button></div><p className={styles.hint}>저장은 출처 목록만 변경합니다. 수집·원고 생성·사람 승인을 시작하지 않습니다.</p></form>}
    </details>

    <section className={styles.research} aria-labelledby="benchmark-research-heading"><div className={styles.sectionHeading}><div><p className={styles.eyebrow}>더 알아보고 싶은 것이 있다면</p><h3 id="benchmark-research-heading">세이지에게 조사 맡기기</h3></div><span className={styles.platform}>요청문 준비 → 확인 후 접수</span></div><p>조사할 크리에이터 출처를 고르세요. 현재 분야·출처 플랫폼 조건을 담아 공개자료 조사 요청문을 준비합니다.</p><fieldset disabled={Boolean(busy)}><legend>조사할 출처 · {selectedSources.length}개 선택</legend><div className={styles.checks}>{sources.map(source => <label key={source.id}><input type="checkbox" checked={selected.has(source.id)} onChange={event => setSelectedSources(event.target.checked ? [...selectedSources, source.id] : selectedSources.filter(id => id !== source.id))} />{source.name}<span>{data.platforms[source.platform] ?? source.platform}</span></label>)}</div>{!sources.length && <p>먼저 경쟁사 출처를 등록하세요.</p>}</fieldset><div className={styles.actions}><button type="button" className="button primary" disabled={Boolean(busy) || !selectedSources.length} onClick={() => void preparePacket()}>세이지 조사 요청문 준비</button></div><p className={styles.hint}>요청문 준비는 저장·전송·모델 호출을 하지 않습니다. 실제 세이지 실행과 최종 보고는 접수 후 실행 영수증으로 확인합니다.</p>
      {packet && <div className={styles.packet}><label>준비된 세이지 조사 요청문<textarea aria-label="준비된 세이지 조사 요청문" ref={packetText} value={packet.text} readOnly rows={14} /></label>{packetStale && <p role="status" className={styles.error}>출처 또는 조사 조건이 바뀌었습니다. 요청문을 다시 준비하세요.</p>}<div className={styles.actions}><button type="button" className="button secondary" disabled={Boolean(busy) || packetStale} onClick={() => void perform('요청문 복사', async () => { if (!navigator.clipboard) { packetText.current?.focus(); packetText.current?.select(); throw new Error('요청문을 선택했습니다. 복사 단축키로 복사해 주세요.'); } await navigator.clipboard.writeText(packet.text); setNotice('요청문을 복사했습니다. 아직 비서에게 접수하지 않았습니다.'); })}>요청문 복사</button>{onSendResearch && <button type="button" className="button primary" disabled={Boolean(busy) || packetStale} onClick={() => void perform('조사 요청문 검토', async () => { const message = await onSendResearch(packet.text); setNotice(message || '기존 비서 요청 화면에서 내용을 확인한 뒤 접수하세요. 아직 전송하지 않았습니다.'); })}>세이지 조사 요청문 검토</button>}</div></div>}
    </section>
  </section>;
}
