"use client";
import { useEffect, useRef, useState } from 'react';
import type { CSSProperties } from 'react';
import { api } from '../lib/api';
import { researchSourceLabels, signalLabels, type DiscoveryStatus, type ResearchConfig } from '../lib/discovery';

const controlStyle: CSSProperties = { display: 'block', width: '100%', minHeight: 44, marginTop: 6,
  padding: '10px 12px', border: '1px solid var(--line)', borderRadius: 8, background: 'var(--white)', fontSize: 16 };

export function DiscoveryPanel({ active = true, platform = 'all' }: { active?: boolean; platform?: string } = {}) {
  const [data, setData] = useState<DiscoveryStatus | null>(null);
  const [draft, setDraft] = useState<ResearchConfig | null>(null);
  const [baseHash, setBaseHash] = useState('');
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState('');
  const [message, setMessage] = useState('');
  const initialized = useRef(false);
  useEffect(() => {
    if (!active) return;
    let live = true;
    const read = async () => {
      try {
        const current = await api.discovery();
        if (!live) return;
        setData(current);
        if (!initialized.current) {
          setDraft(current.config); setBaseHash(current.config_hash); initialized.current = true;
        }
      } catch (cause) { if (live) setError(cause instanceof Error ? cause.message : '조사 상태를 읽지 못했습니다.'); }
    };
    void read();
    const timer = setInterval(() => void read(), 10000);
    return () => { live = false; clearInterval(timer); };
  }, [active]);
  async function save() {
    if (!draft || busy) return;
    setBusy(true); setError('');
    try {
      const current = await api.saveDiscovery({ ...draft, youtube_channels: draft.youtube_channels.map(c => c.trim()).filter(Boolean), expected_hash: baseHash });
      setData(current); setDraft(current.config); setBaseHash(current.config_hash);
      setMessage(current.task?.state === 'completed' ? '같은 조건의 저장된 조사 결과를 재사용합니다. 15분 후 새 조사를 요청할 수 있습니다.' : current.task?.state === 'failed' ? '이전 조사 실패가 기록돼 있습니다. 연결 상태를 확인하고 15분 뒤 다시 요청하세요.' : current.window_open ? '조사를 자동 요청했습니다. 완료되면 아래 소재 후보가 갱신됩니다.' : '설정과 조사 요청을 저장했습니다. 작업 시간이 열려야 수집할 수 있습니다.');
    } catch (cause) { setError(cause instanceof Error ? cause.message : '저장 결과를 확인하세요.'); }
    finally { setBusy(false); }
  }
  async function reload() {
    setBusy(true);
    try { const current = await api.discovery(); setData(current); setDraft(current.config); setBaseHash(current.config_hash); initialized.current = true; setError(''); }
    catch (cause) { setError(cause instanceof Error ? cause.message : '불러오지 못했습니다.'); }
    finally { setBusy(false); }
  }
  const queued = (data?.activity ?? data?.task)?.state === 'queued';
  const recommendations = data?.snapshot && Object.entries(data.snapshot.recommendations)
    .filter(([id]) => platform === 'all' || id === platform)
    .map(([id, rows]) => <details key={id}>
      <summary>{data.platforms[id]} 소재 후보 {rows.length}건</summary>
      {rows.length ? <ul>{rows.map(row => <li key={row.id} style={{ marginBlock: 16, overflowWrap: 'anywhere' }}>
        <a href={row.url} target="_blank" rel="noopener noreferrer">{row.title}</a>
        <p>{row.feed_name} · {signalLabels(row.signals).join(' · ') || '공개 지표 없음'}<br />{row.reason}</p>
        <p className="muted">{row.date_note} {row.signal_note}</p>
      </li>)}</ul> : <p>해당 조건으로 확인된 소재가 없습니다.</p>}
    </details>);
  return <section className="outline-panel" aria-labelledby="discovery-heading" style={{ fontSize: 16 }}>
    <h2 id="discovery-heading">게시할 콘텐츠의 소재 참고 조사</h2>
    <p>Google 검색·뉴스, Hacker News, 공식 발표 등에서 기획할 주제의 단서를 찾습니다. 플랫폼에서 실제로 반응을 얻은 게시물은 위의 플랫폼별 목록에서 확인할 수 있습니다.</p>
    {error && <p role="alert" className="notice error">{error}</p>}
    {!data || !draft ? <div><p role="status">조사 설정을 불러오는 중입니다.</p><button className="button secondary" disabled={busy} onClick={() => void reload()}>조사 설정 다시 불러오기</button></div> : <>
      <form onSubmit={e => { e.preventDefault(); void save(); }}>
        <fieldset disabled={busy} style={{ minWidth: 0, border: '1px solid var(--line)', borderRadius: 10, padding: 16 }}><legend>소재를 활용할 게시 대상</legend>
          <div style={{ display: 'flex', flexWrap: 'wrap', gap: '12px 20px' }}>{Object.entries(data.platforms).map(([id, label]) => <label key={id}><input type="checkbox" checked={draft.platforms.includes(id)} onChange={e => setDraft({ ...draft, platforms: e.target.checked ? [...draft.platforms, id] : draft.platforms.filter(p => p !== id) })} /> {label}</label>)}</div>
        </fieldset>
        <div style={{ display: 'grid', gap: 12, marginTop: 16 }}>
          <label>조사 주제<input style={controlStyle} value={draft.topic} maxLength={80} required disabled={busy} onChange={e => setDraft({ ...draft, topic: e.target.value })} /></label>
          <label>관심 지역<select style={controlStyle} value={draft.region} disabled={busy} onChange={e => setDraft({ ...draft, region: e.target.value })}><option value="KR">한국</option><option value="US">미국</option><option value="GB">영국</option><option value="JP">일본</option></select></label>
          <details><summary>참고할 YouTube 공개 채널 변경</summary><label>채널 ID · 한 줄에 하나, 최대 6개<textarea style={{ ...controlStyle, minHeight: 140, resize: 'vertical' }} value={draft.youtube_channels.join('\n')} disabled={busy} onChange={e => setDraft({ ...draft, youtube_channels: e.target.value.split('\n') })} /></label><p className="muted">UC로 시작하는 채널 ID를 사용합니다. 기본은 OpenAI와 Google Developers이며 계정 로그인·구독 변경은 하지 않습니다.</p></details>
        </div>
        {baseHash !== data.config_hash && <p className="notice">다른 화면에서 설정이 바뀌었습니다. 입력은 보존됩니다. 현재 설정을 다시 불러와 확인하세요.</p>}
        <div className="button-row" style={{ marginTop: 16 }}><button className="button primary" disabled={busy || !draft.platforms.length || baseHash !== data.config_hash}>조건 저장하고 조사 요청</button><button type="button" className="button secondary" disabled={busy} onClick={() => void reload()}>현재 설정 다시 불러오기 · 입력 초기화</button></div>
      </form>
      {message && <p role="status">{message}</p>}
      <p className="muted">작업 시간 {data.window_open ? '열림' : '종료'} · 같은 조건의 결과는 15분간 재사용합니다.</p>
      {data.activity && <p role="status">조사 상태: {({ queued: '대기', running: '수집 중', completed: '완료', failed: '실패', unknown: '결과 확인 필요' } as Record<string, string>)[data.activity.state] ?? data.activity.state}{data.activity.error ? ` · ${data.activity.error}` : ''}</p>}
      {data.snapshot ? <>
        <p>마지막 조사 {new Date(data.snapshot.checked_at).toLocaleString('ko-KR', { timeZone: 'Asia/Seoul' })} KST</p>
        {data.stale
          ? <details><summary>이전 조건의 소재 후보 보기</summary><p className="muted">{queued
            ? data.window_open ? '새 조건의 조사 요청이 대기 중입니다.' : '새 조건의 조사 요청이 대기 중입니다. 작업 시간이 열려야 수집할 수 있습니다.'
            : '이전 조건에서 수집한 소재입니다.'}</p>{recommendations}</details>
          : recommendations}
      </> : <p>소재를 조사한 기록이 없습니다. 조건을 저장한 뒤 작업 시간을 열어 주세요.</p>}
      <details>
        <summary>참고 출처와 수집 상태{data.snapshot && ' (' + data.snapshot.sources.length + '개)'}</summary>
        <ul>{Object.entries(data.plan).filter(([id]) => platform === 'all' || id === platform).map(([id, kinds]) =>
          <li key={id}><strong>{data.platforms[id]}</strong> · {kinds.map(k => researchSourceLabels[k] ?? k).join(' · ')}</li>)}</ul>
        {data.snapshot && <>
          <ul>{data.snapshot.sources.map(source => <li key={source.id}>
            {source.name} · {source.state === 'ok' ? ('조회 성공' + (source.count != null ? ' ' + source.count + '건' : '')) : '수집 실패'}
            {source.raw_items !== undefined && source.raw_items !== source.count && (' (조회 항목 ' + source.raw_items + ', 주제 일치 ' + (source.count ?? '미확인') + ')')}
            {source.error && ' · ' + source.error}
          </li>)}</ul>
          <p className="muted">{data.snapshot.method} · 모델 호출 {data.snapshot.paid_calls}회</p>
        </>}
        {data.unconnected.length > 0 && <details><summary>연결 준비가 필요한 참고 도구</summary><ul>{data.unconnected.map(note => <li key={note}>{note}</li>)}</ul></details>}
      </details>
    </>}
  </section>;
}
