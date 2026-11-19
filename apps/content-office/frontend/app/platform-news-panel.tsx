'use client';

import { useEffect, useRef, useState } from 'react';
import Link from 'next/link';
import { api } from '../lib/api';
import { benchmarkPublicUrl } from '../lib/benchmarks';
import { platformNewsLabels, type PlatformNews, type PlatformNewsItem } from '../lib/platform-news';
import type { Idea } from '../lib/types';
import styles from './platform-news.module.css';

const statuses = {
  available: '수집 완료',
  observed: '공개 화면 관측',
  waiting: '수집 대기',
  stale: '이전 수집 기록',
  error: '수집 실패',
} satisfies Record<PlatformNews['platforms'][number]['source_status'], string>;
const metrics = [
  ['views', '누적 조회수'], ['likes', '좋아요'], ['reactions', '반응'], ['comments', '댓글'], ['reposts', '리포스트'],
] as const;

const rankingSources = {
  youtube_api: 'YouTube Data API',
  public_rss: '공개 RSS',
  browser_observation: '브라우저 공개 화면',
};
const rankingMetrics = { views: '누적 조회수', likes: '좋아요 수', reactions: '반응 수' };

function displayDate(value: string | null): string {
  return value && Number.isFinite(Date.parse(value))
    ? new Intl.DateTimeFormat('ko-KR', { timeZone: 'Asia/Seoul', dateStyle: 'medium', timeStyle: 'short' }).format(new Date(value)) + ' KST'
    : '';
}

export function PlatformNewsPanel({ active, platform, onPlatformChange, onIdeaSaved }: {
  active: boolean; platform: string; onPlatformChange: (value: string) => void; onIdeaSaved?: () => void;
}) {
  const [data, setData] = useState<PlatformNews | null>(null);
  const [error, setError] = useState('');
  const [requestVersion, setRequestVersion] = useState(0);
  const platformSelect = useRef<HTMLSelectElement>(null);
  useEffect(() => {
    if (!active) return;
    let live = true;
    let reading = false;
    async function read() {
      if (document.hidden || reading) return;
      reading = true;
      try {
        const current = await api.platformNews();
        if (!Array.isArray(current.platforms)) throw new Error('Invalid platform news response');
        if (live) {
          setData(current);
          setError('');
        }
      } catch {
        if (live) setError('플랫폼 수집 기록을 불러오지 못했습니다.');
      } finally {
        reading = false;
      }
    }
    void read();
    const timer = window.setInterval(() => void read(), 60_000);
    document.addEventListener('visibilitychange', read);
    return () => {
      live = false;
      window.clearInterval(timer);
      document.removeEventListener('visibilitychange', read);
    };
  }, [active, requestVersion]);

  const platforms = data?.platforms.filter(row => platform === 'all' || platform === row.id) ?? [];
  return <section className={styles.feed} aria-labelledby="platform-news-heading">
    <header className={styles.header}>
      <div>
        <h2 id="platform-news-heading">플랫폼 소식</h2>
        <p>{data?.topic ? '수집 주제 · ' + data.topic : '플랫폼별 수집 결과와 등록 출처를 살펴보세요.'}</p>
      </div>
      <label>출처 플랫폼<select ref={platformSelect} value={platform} onChange={event => onPlatformChange(event.target.value)}>
        <option value="all">전체 플랫폼</option>
        {Object.entries(platformNewsLabels).map(([id, label]) => <option key={id} value={id}>{label}</option>)}
      </select></label>
    </header>
    <nav className={styles.jumpLinks} aria-label="플랫폼 소식 바로 이동">
      <a href="#platform-trend-research">소재 참고 조사</a>
      <a href="#creator-news">등록 출처와 아이디어</a>
    </nav>
    {error && <div className={styles.statusLine}>
      <p className={styles.muted} role="status">{error}</p>
      <button type="button" className={styles.more} onClick={() => setRequestVersion(version => version + 1)}>플랫폼 소식 다시 불러오기</button>
    </div>}
    {!data && !error && <p className={styles.muted} role="status">플랫폼 수집 기록을 불러오는 중입니다.</p>}
    {data && platforms.length === 0 && <p className={styles.muted}>이 플랫폼의 정기 수집 기록이 없습니다. 등록 출처를 확인할 수 있습니다.</p>}
    {data && platforms.length > 0 && <div className={styles.platformGrid}>
      {platforms.map(group => <section className={styles.platformGroup} key={group.id} aria-label={group.label + ' 공개 후보'}>
        <div className={styles.groupHeader}>
          <h3>{group.label}</h3>
          <span className={styles.state}>{statuses[group.source_status] ?? '상태 확인 필요'}</span>
        </div>
        {group.criteria ? <>
          <p className={styles.muted}>
            <strong>{group.criteria.kind === 'latest' ? '최신 발행일 순' : group.criteria.metric ? rankingMetrics[group.criteria.metric] + ' 순' : '반응 지표 확인 중'}</strong>
            {' · '}최근 {group.criteria.published_days}일 발행
            {group.criteria.kind === 'popularity' && ' · 최근 ' + group.criteria.observation_days + '일 지표 확인'}
          </p>
          <p className={styles.muted}>{rankingSources[group.criteria.source] || group.method}{group.criteria.scope && ' · ' + group.criteria.scope}</p>
        </> : <p className={styles.muted}>{group.ranking_basis || group.method}</p>}
        {group.source_status !== 'available' && group.message && <p className={styles.muted}>{group.message}</p>}
        {group.checked_at && <p className={styles.muted}>최근 확인 {displayDate(group.checked_at)}</p>}
        {group.items.length === 0 && (group.criteria || group.source_status === 'available') && <p className={styles.muted}>
          {group.criteria ? '발행일과 수집 기준을 충족하는 게시물이 없습니다.' : '현재 조건에 맞는 후보가 없습니다.'}
        </p>}
        {group.items.length > 0 && <ol className={styles.items}>
          {group.items.slice(0, platform === 'all' ? 3 : group.items.length).map(item =>
            <Candidate key={item.id} item={item} platform={group.id} platformLabel={group.label}
              snapshotHash={data.snapshot_hash} onIdeaSaved={onIdeaSaved} />)}
        </ol>}
        {platform === 'all' && group.items.length > 3 && <button type="button" className={styles.more}
          onClick={() => { onPlatformChange(group.id); platformSelect.current?.focus(); }}>
          {group.label} 후보 {group.items.length}건 보기
        </button>}
        {group.reference_items && group.reference_items.length > 0 && <details>
          <summary>참고 게시물 {group.reference_items.length}건</summary>
          <p className={styles.muted}>발행일 또는 지표를 확인하지 못했거나 최근 발행 범위를 지난 자료입니다.</p>
          <ul className={styles.items}>
            {group.reference_items.map(item => <Candidate key={item.id} item={item} platform={group.id} platformLabel={group.label}
              snapshotHash={data.snapshot_hash} onIdeaSaved={onIdeaSaved} reference />)}
          </ul>
        </details>}
      </section>)}
    </div>}
  </section>;
}

function Candidate({ item, platform, platformLabel, snapshotHash, onIdeaSaved, reference = false }: {
  item: PlatformNewsItem; platform: string; platformLabel: string; snapshotHash?: string | null;
  onIdeaSaved?: () => void; reference?: boolean;
}) {
  const href = benchmarkPublicUrl(item.url);
  const published = displayDate(item.published_at);
  const observed = displayDate(item.observed_at);
  const sending = useRef(false);
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState('');
  const [saved, setSaved] = useState<Idea>();
  const discoveryStatus = saved?.public_discovery?.status;
  async function save() {
    if (sending.current || (saved && discoveryStatus !== 'unavailable') || !snapshotHash || !href) return;
    sending.current = true;
    setBusy(true);
    setError('');
    try {
      const { idea } = await api.savePlatformNewsIdea({ platform, url: item.url, expected_hash: snapshotHash });
      setSaved(idea);
      onIdeaSaved?.();
    } catch (cause) {
      setError(cause instanceof Error ? cause.message : '기획 후보를 저장하지 못했습니다.');
    } finally {
      sending.current = false;
      setBusy(false);
    }
  }
  return <li>
    <p className={styles.muted}>{item.source || platformLabel}{published && ' · 발행 ' + published}</p>
    <strong>{href ? <a href={href} target="_blank" rel="noopener noreferrer">{item.title}</a> : item.title}</strong>
    {item.summary && <p>{item.summary}</p>}
    <ul className={styles.metrics}>
      {metrics.map(([key, label]) => {
        const value = item.metrics?.[key];
        return typeof value === 'number' && Number.isFinite(value) && value >= 0
          ? <li key={key}>{label} {item.metric_precision?.[key] === 'approximate' && '약 '}{value.toLocaleString('ko-KR')}</li>
          : null;
      })}
    </ul>
    {observed && <p className={styles.muted}>지표 확인 {observed}</p>}
    {reference && item.reference_reason && <p className={styles.muted}>{item.reference_reason}</p>}
    {saved && <div className={styles.statusLine}>
      <p role="status">기획 후보에 저장됨
        {discoveryStatus === 'ready' && ' · 공개 원문 확인 가능'}
        {discoveryStatus === 'insufficient' && ' · 원문 근거 보완 필요'}
        {discoveryStatus === 'unavailable' && ' · 공개 원문 조회 일시 지연'}
      </p>
      <Link className={styles.more} href={'/plans#' + encodeURIComponent(saved.id)} prefetch={false}>저장한 후보에서 근거 검토</Link>
    </div>}
    {(!saved || discoveryStatus === 'unavailable') && href && /^[a-f0-9]{64}$/.test(snapshotHash ?? '') && <button type="button" className={styles.more}
      aria-label={`${item.title} ${saved ? '공개 원문 다시 찾기' : '기획 후보로 저장'}`} disabled={busy} onClick={() => void save()}>
      {busy ? '공개 원문 찾는 중…' : saved ? '공개 원문 다시 찾기' : '기획 후보로 저장'}
    </button>}
    {error && <p role="alert">{error}</p>}
  </li>;
}
