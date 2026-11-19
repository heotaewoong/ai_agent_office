'use client';

import { useEffect, useRef, useState } from 'react';
import { api } from '../lib/api';
import { benchmarkPublicUrl } from '../lib/benchmarks';
import { platformNewsLabels, type PlatformNews } from '../lib/platform-news';
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

function displayDate(value: string | null): string {
  return value && Number.isFinite(Date.parse(value))
    ? new Intl.DateTimeFormat('ko-KR', { timeZone: 'Asia/Seoul', dateStyle: 'medium', timeStyle: 'short' }).format(new Date(value)) + ' KST'
    : '';
}

export function PlatformNewsPanel({ active, platform, onPlatformChange }: {
  active: boolean; platform: string; onPlatformChange: (value: string) => void;
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
      <a href="#platform-trend-research">트렌드 조사</a>
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
        <p className={styles.muted}>{group.ranking_basis || group.method}</p>
        {group.source_status !== 'available' && group.message && <p className={styles.muted}>{group.message}</p>}
        {group.checked_at && <p className={styles.muted}>최근 확인 {displayDate(group.checked_at)}</p>}
        {group.items.length === 0 && group.source_status === 'available' && <p className={styles.muted}>현재 조건에 맞는 후보가 없습니다.</p>}
        {group.items.length > 0 && <ol className={styles.items}>
          {group.items.slice(0, platform === 'all' ? 3 : group.items.length).map(item => {
            const href = benchmarkPublicUrl(item.url);
            return <li key={item.id}>
              <p className={styles.muted}>{item.source || group.label}{item.published_at && ' · ' + displayDate(item.published_at)}</p>
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
              {item.observed_at && <p className={styles.muted}>관측 {displayDate(item.observed_at)}</p>}
            </li>;
          })}
        </ol>}
        {platform === 'all' && group.items.length > 3 && <button type="button" className={styles.more}
          onClick={() => { onPlatformChange(group.id); platformSelect.current?.focus(); }}>
          {group.label} 후보 {group.items.length}건 보기
        </button>}
      </section>)}
    </div>}
  </section>;
}
