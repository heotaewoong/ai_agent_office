'use client';

import { useId, useLayoutEffect, useState, useSyncExternalStore } from 'react';
import { createAssistantReportsController } from '../lib/assistant-reports.ts';

/** Inject an existing authenticated GET adapter from a client parent, not a server component. */
export function AssistantReports({ connected, loadReports }: {
  connected: boolean; loadReports: () => Promise<unknown>;
}) {
  const [controller] = useState(createAssistantReportsController);
  const [open, setOpen] = useState(false);
  const contentId = useId();
  const state = useSyncExternalStore(controller.subscribe, controller.getSnapshot, controller.getSnapshot);

  useLayoutEffect(() => { controller.setAvailability(connected, open); }, [controller, connected, open]);
  useLayoutEffect(() => () => { controller.invalidate(); }, [controller]);

  function toggle() {
    const next = !open;
    controller.setAvailability(connected, next);
    setOpen(next);
    if (next && connected) void controller.refresh(loadReports);
  }

  return <section className="panel" aria-label="비서 협업 보고" style={{ minWidth: 0, maxWidth: '100%', overflowWrap: 'anywhere' }}>
    <h2>비서 협업 보고</h2>
    <p className="muted">읽기 전용 · 원고 승인①·제작·게시와 별개입니다. 회의 생성이나 명령을 실행하지 않습니다.</p>
    <button type="button" className="button secondary" aria-expanded={open} aria-controls={contentId} onClick={toggle}>
      {open ? '보고 접기' : '보고 열기'}
    </button>
    {open && <div id={contentId}>
      {!connected ? <p role="status" className="muted">연결되지 않았습니다. 보고 요청을 보내지 않습니다.</p> : <>
        <button type="button" className="button secondary" disabled={state.status === 'loading'} onClick={() => { void controller.refresh(loadReports); }}>보고 새로고침</button>
        <div aria-live="polite" aria-busy={state.status === 'loading'}>
          {state.status === 'idle' && <p className="muted">새로고침으로 보고를 조회하세요.</p>}
          {state.status === 'loading' && <p className="muted">협업 보고를 불러오는 중입니다.</p>}
          {state.status === 'error' && <p role="alert">{state.error}</p>}
          {state.status === 'success' && state.reports.length === 0 && <p className="muted">보고가 0건입니다.</p>}
        </div>
        {state.status === 'success' && state.reports.map(report => <article className="panel" key={report.id}>
          <h3>{report.title}</h3>
          <p className="muted">{report.scope === 'dm_review' ? 'DM 팀 검토 · GroupChat 회의 아님' : 'GroupChat 그룹 검토'}</p>
          <p>{report.summary}</p>
          <p>참여: {report.participants.join(' · ')}</p>
          <p>근거 기록 {report.evidence_count}개 · 근거 수는 독립 검증 완료를 뜻하지 않습니다.</p>
          <p>보고 시각: <time dateTime={report.reported_at}>{report.reported_at}</time></p>
          <h4>실제 검증 한계</h4>
          {report.limitations.length ? <ul>{report.limitations.map(item => <li key={item}>{item}</li>)}</ul> : <p className="muted">기록된 한계 없음 · 전체 검증 완료를 의미하지 않습니다.</p>}
        </article>)}
      </>}
    </div>}
  </section>;
}
