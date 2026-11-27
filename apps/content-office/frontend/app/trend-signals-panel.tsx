'use client';

import { useCallback, useEffect, useState } from 'react';
import { api } from '../lib/api';
import { parseSeeds, trendLine, type TrendSource, type TrendStatus } from '../lib/trend-signals';

const SOURCES: TrendSource[] = ['google', 'youtube', 'naver', 'wikipedia'];

function message(error: unknown) {
  return error instanceof Error ? error.message : '요청을 처리하지 못했어요';
}

/** 트렌드 신호(0원): 씨앗 단어마다 자동완성 세 곳과 위키백과 조회수. 아침 수집 때 같이 모으거나 지금 모으기로 줄을 세운다. */
export function TrendSignalsPanel({ active = true, onIdeaSaved }: { active?: boolean; onIdeaSaved?: () => void }) {
  const [data, setData] = useState<TrendStatus | null>(null);
  const [seeds, setSeeds] = useState('');
  const [busy, setBusy] = useState(false);
  const [note, setNote] = useState('');
  const [error, setError] = useState('');

  const load = useCallback(async () => {
    try {
      const current = await api.trendSignals();
      setData(current); setSeeds(current.settings.seeds.join('\n')); setError('');
    } catch (err) { setError(message(err)); }
  }, []);
  useEffect(() => { if (active) void load(); }, [active, load]);

  async function run(label: string, work: () => Promise<unknown>, done: string) {
    setBusy(true); setNote(''); setError('');
    try { await work(); setNote(done); } catch (err) { setError(`${label}: ${message(err)}`); } finally { setBusy(false); }
  }

  if (!data) return <section className="outline-panel" aria-labelledby="trend-signals-heading"><h2 id="trend-signals-heading">트렌드 신호</h2>
    {error ? <p role="alert" className="notice error">{error}</p> : <p role="status">불러오는 중이에요.</p>}</section>;

  const settings = data.settings;
  const save = (patch: Partial<typeof settings>) => run('설정 저장', async () => setData(await api.saveTrendSignals({ ...settings, ...patch })), '설정을 저장했어요.');
  const rows = data.report?.rows ?? [];
  const bySeed = new Map<string, typeof rows>();
  for (const row of rows) bySeed.set(row.seed, [...(bySeed.get(row.seed) ?? []), row]);

  return <section className="outline-panel" aria-labelledby="trend-signals-heading" style={{ fontSize: 16 }}>
    <h2 id="trend-signals-heading">트렌드 신호(0원)</h2>
    <p>씨앗 단어마다 구글, 유튜브, 네이버 자동완성과 위키백과 조회수를 모아요. 순위나 예측이 아니라 읽은 그대로이고, 막힌 곳은 비워 둬요.</p>
    {error && <p role="alert" className="notice error">{error}</p>}
    <fieldset disabled={busy} style={{ border: '1px solid var(--line)', borderRadius: 10, padding: 16, minWidth: 0 }}>
      <legend>모으는 방법</legend>
      <label><input type="checkbox" checked={settings.enabled} onChange={e => void save({ enabled: e.target.checked })} /> 아침 수집 때 같이 모으기</label>
      <div style={{ display: 'flex', flexWrap: 'wrap', gap: '8px 16px', marginTop: 8 }}>
        {SOURCES.map(source => <label key={source}><input type="checkbox" checked={settings.sources.includes(source)}
          onChange={e => void save({ sources: e.target.checked ? [...settings.sources, source] : settings.sources.filter(s => s !== source) })} /> {data.labels[source]}</label>)}
      </div>
      <label style={{ display: 'block', marginTop: 12 }}>씨앗 단어(한 줄에 하나, {data.limits.max_seeds}개까지)
        <textarea value={seeds} rows={4} onChange={e => setSeeds(e.target.value)} style={{ display: 'block', width: '100%', boxSizing: 'border-box' }} />
      </label>
      <div className="button-row" style={{ marginTop: 12 }}>
        <button type="button" className="button secondary" onClick={() => void save({ seeds: parseSeeds(seeds, data.limits.max_seeds) })}>씨앗 저장</button>
        <button type="button" className="button primary" onClick={() => void run('모으기 요청', async () => {
          const task = await api.refreshTrendSignals();
          // 같은 15분 안에는 같은 작업을 돌려줘요. 끝난 작업이면 새로 줄 서지 않았다고 정직하게 알려요.
          if (task.state === 'completed') { await load(); throw new Error('15분 안에 이미 모았어요. 아래 표가 그 결과예요'); }
          if (task.state === 'failed') throw new Error('이번 15분 안의 모으기가 실패했어요. 15분 뒤 다시 눌러 주세요');
        }, '모으기를 줄 세웠어요. 작업 시간이 열려 있으면 작업자가 모아요.')}>지금 모으기</button>
        <button type="button" className="button secondary" onClick={() => void load()}>다시 읽기</button>
      </div>
    </fieldset>
    {note && <p role="status">{note}</p>}
    {data.report ? <>
      <p className="muted">마지막으로 모은 때 {new Date(data.report.checked_at).toLocaleString('ko-KR', { timeZone: 'Asia/Seoul' })} · 모델 호출 {data.report.paid_calls}회</p>
      <div className="table-scroll"><table>
        <thead><tr><th>씨앗</th><th>어디서</th><th>읽은 것</th><th>기획</th></tr></thead>
        <tbody>{[...bySeed.entries()].flatMap(([seed, list]) => list.map((row, index) => <tr key={seed + row.source}>
          {index === 0 && <th scope="rowgroup" rowSpan={list.length}>{seed}</th>}
          <td>{row.url ? <a href={row.url} target="_blank" rel="noopener noreferrer">{row.label}</a> : row.label}</td>
          <td>{trendLine(row)}</td>
          <td>{row.items.length > 0 && <select aria-label={`${seed} ${row.label} 기획 은행에 등록`} defaultValue="" disabled={busy}
            onChange={e => { const title = e.target.value; e.target.value = ''; if (title) void run('기획 등록', async () => { await api.addIdea({ title, source_url: row.url ?? '', demand: 0, primary_sources: 0, fit: 0, covered_before: false, policy_flags: [] }); onIdeaSaved?.(); }, `'${title}'을 기획 은행에 넣었어요.`); }}>
            <option value="">기획 은행에 넣기</option>{row.items.map(item => <option key={item.text} value={item.text}>{item.text}</option>)}</select>}</td>
        </tr>))}</tbody>
      </table></div>
      <p className="muted">{data.report.method}</p>
    </> : <p>아직 모은 기록이 없어요. 씨앗을 저장하고 지금 모으기를 누르거나 아침 수집에 같이 켜 두세요.</p>}
    <details><summary>아직 연결 안 된 신호</summary><ul>{data.not_connected.map(item => <li key={item}>{item}</li>)}</ul></details>
  </section>;
}
