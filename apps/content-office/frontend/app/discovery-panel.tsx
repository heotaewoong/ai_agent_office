"use client";
import { useEffect, useState } from 'react';
import type { CSSProperties } from 'react';
import { api } from '../lib/api';
import { researchSourceLabels, signalLabels, type DiscoveryStatus, type ResearchConfig } from '../lib/discovery';

const controlStyle: CSSProperties = { display: 'block', width: '100%', minHeight: 44, marginTop: 6,
  padding: '10px 12px', border: '1px solid var(--line)', borderRadius: 8, background: 'var(--white)', fontSize: 16 };

export function DiscoveryPanel() {
  const [data, setData] = useState<DiscoveryStatus | null>(null);
  const [draft, setDraft] = useState<ResearchConfig | null>(null);
  const [baseHash, setBaseHash] = useState('');
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState('');
  const [message, setMessage] = useState('');
  useEffect(() => {
    let live = true;
    const read = async (first = false) => {
      try {
        const current = await api.discovery();
        if (!live) return;
        setData(current);
        if (first) { setDraft(current.config); setBaseHash(current.config_hash); }
      } catch (cause) { if (live) setError(cause instanceof Error ? cause.message : '조사 상태를 읽지 못했습니다.'); }
    };
    void read(true);
    const timer = setInterval(() => void read(), 10000);
    return () => { live = false; clearInterval(timer); };
  }, []);
  async function save() {
    if (!draft || busy) return;
    setBusy(true); setError('');
    try {
      const current = await api.saveDiscovery({ ...draft, youtube_channels: draft.youtube_channels.map(c => c.trim()).filter(Boolean), expected_hash: baseHash });
      setData(current); setDraft(current.config); setBaseHash(current.config_hash);
      setMessage(current.task?.state === 'completed' ? '같은 조건의 저장된 조사 결과를 재사용합니다. 15분 후 새 조사를 요청할 수 있습니다.' : current.task?.state === 'failed' ? '이전 조사 실패가 기록돼 있습니다. 연결 상태를 확인하고 15분 뒤 다시 요청하세요.' : current.window_open ? '조사를 자동 요청했습니다. 결과가 들어오면 아래 목록과 오늘의 뉴스가 갱신됩니다.' : '설정과 조사 요청을 저장했습니다. 제작 설정에서 작업 시간을 열면 자동으로 수집합니다.');
    } catch (cause) { setError(cause instanceof Error ? cause.message : '저장 결과를 확인하세요.'); }
    finally { setBusy(false); }
  }
  async function reload() {
    setBusy(true);
    try { const current = await api.discovery(); setData(current); setDraft(current.config); setBaseHash(current.config_hash); setError(''); }
    catch (cause) { setError(cause instanceof Error ? cause.message : '불러오지 못했습니다.'); }
    finally { setBusy(false); }
  }
  return <section className="outline-panel" aria-labelledby="discovery-heading" style={{ fontSize: 16 }}>
    <h2 id="discovery-heading">게시할 곳에 맞춰 소식과 트렌드 조사</h2>
    <p>공식 소식·YouTube·HN을 함께 수집하고, 게시 대상에 필요한 검색·뉴스 신호를 추가합니다. 선택 저장 후 자동 조사하며 원고·승인·게시를 시작하지 않습니다. 추가 모델 호출은 없습니다.</p>
    {error && <p role="alert" className="notice error">{error}</p>}
    {!data || !draft ? <div><p role="status">조사 설정을 불러오는 중입니다.</p><button className="button secondary" disabled={busy} onClick={() => void reload()}>조사 설정 다시 불러오기</button></div> : <>
      <form onSubmit={e => { e.preventDefault(); void save(); }}>
        <fieldset disabled={busy} style={{ minWidth: 0, border: '1px solid var(--line)', borderRadius: 10, padding: 16 }}><legend>조사할 게시 대상</legend>
          <div style={{ display: 'flex', flexWrap: 'wrap', gap: '12px 20px' }}>{Object.entries(data.platforms).map(([id, label]) => <label key={id}><input type="checkbox" checked={draft.platforms.includes(id)} onChange={e => setDraft({ ...draft, platforms: e.target.checked ? [...draft.platforms, id] : draft.platforms.filter(p => p !== id) })} /> {label}</label>)}</div>
        </fieldset>
        <div style={{ display: 'grid', gap: 12, marginTop: 16 }}>
          <label>조사 주제<input style={controlStyle} value={draft.topic} maxLength={80} required disabled={busy} onChange={e => setDraft({ ...draft, topic: e.target.value })} /></label>
          <label>관심 지역<select style={controlStyle} value={draft.region} disabled={busy} onChange={e => setDraft({ ...draft, region: e.target.value })}><option value="KR">한국</option><option value="US">미국</option><option value="GB">영국</option><option value="JP">일본</option></select></label>
          <details><summary>구독할 공개 YouTube 채널 변경</summary><label>채널 ID · 한 줄에 하나, 최대 6개<textarea style={{ ...controlStyle, minHeight: 140, resize: 'vertical' }} value={draft.youtube_channels.join('\n')} disabled={busy} onChange={e => setDraft({ ...draft, youtube_channels: e.target.value.split('\n') })} /></label><p className="muted">UC로 시작하는 채널 ID를 사용합니다. 기본은 OpenAI와 Google Developers이며 계정 로그인·구독 변경은 하지 않습니다.</p></details>
        </div>
        {baseHash !== data.config_hash && <p className="notice">다른 화면에서 설정이 바뀌었습니다. 입력은 보존됩니다. 현재 설정을 다시 불러와 확인하세요.</p>}
        <div className="button-row" style={{ marginTop: 16 }}><button className="button primary" disabled={busy || !draft.platforms.length || baseHash !== data.config_hash}>선택 저장하고 자동 조사</button><button type="button" className="button secondary" disabled={busy} onClick={() => void reload()}>현재 설정 다시 불러오기 · 입력 초기화</button></div>
      </form>
      {message && <p role="status">{message}</p>}
      <p className="muted">작업 시간 {data.window_open ? '열림' : '종료'} · 같은 조건은 15분 동안 저장된 결과를 재사용합니다. 기존 API 비용 상한과 사람 승인 단계는 유지합니다.</p>
      {data.activity && <p role="status">조사 상태: {({ queued: '대기', running: '수집 중', completed: '완료', failed: '실패', unknown: '결과 확인 필요' } as Record<string, string>)[data.activity.state] ?? data.activity.state}{data.activity.error ? ` · ${data.activity.error}` : ''}</p>}
      <div style={{ display: 'grid', gap: 12 }}>{Object.entries(data.plan).map(([id, kinds]) => <p key={id}><strong>{data.platforms[id]}</strong> → {kinds.map(k => researchSourceLabels[k] ?? k).join(' · ')}</p>)}</div>
      {data.stale && <p className="notice">아래 결과는 이전 조사 조건입니다. 새 조건의 조사 완료를 기다리고 있습니다.</p>}
      {data.snapshot ? <>
        <p>마지막 조사 {new Date(data.snapshot.checked_at).toLocaleString('ko-KR', { timeZone: 'Asia/Seoul' })} KST · 추가 모델 호출 {data.snapshot.paid_calls}회</p>
        <p className="muted">{data.snapshot.method}</p>
        <details><summary>수집 출처·실패 상태 확인 ({data.snapshot.sources.length}개)</summary><ul>{data.snapshot.sources.map(source => <li key={source.id}>{source.name} · {source.state === 'ok' ? `조회 성공 ${source.count ?? 0}건` : '수집 실패'}{source.raw_items !== undefined && source.raw_items !== source.count ? ` (조회 항목 ${source.raw_items}, 주제 일치 ${source.count})` : ''}{source.error ? ` · ${source.error}` : ''}</li>)}</ul></details>
        {Object.entries(data.snapshot.recommendations).map(([platform, rows]) => <details key={platform}><summary>{data.platforms[platform]}에 맞춰 살펴볼 후보 {rows.length}건</summary>{rows.length ? <ul>{rows.map(row => <li key={row.id} style={{ marginBlock: 16, overflowWrap: 'anywhere' }}><a href={row.url} target="_blank" rel="noopener noreferrer">{row.title}</a><p>{row.feed_name} · {signalLabels(row.signals).join(' · ') || '반응 지표 없음'}<br />{row.reason}</p><p className="muted">{row.date_note} {row.signal_note}</p></li>)}</ul> : <p>현재 주제와 기간에 맞는 후보가 없습니다. 연결 실패와 후보 없음은 다릅니다.</p>}</details>)}
      </> : <p>아직 이 조사 기능의 수집 기록이 없습니다. 조건을 저장한 뒤 작업 시간을 열어 주세요.</p>}
      <details><summary>아직 자동으로 연결되지 않은 도구</summary><ul>{data.unconnected.map(note => <li key={note}>{note}</li>)}</ul><p>개별 서비스의 자동 연동 권한·공식 제공 방식·비용을 확인하기 전에는 연결 완료로 표시하지 않습니다.</p></details>
    </>}
  </section>;
}
