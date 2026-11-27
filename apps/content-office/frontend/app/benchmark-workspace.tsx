'use client';

import { useEffect, useState } from 'react';
import Link from 'next/link';
import { useRouter } from 'next/navigation';
import { api } from '../lib/api';
import { BenchmarkPanel } from './benchmark-panel';
import { AssistantChat } from './assistant-chat';
import { DiscoveryPanel } from './discovery-panel';
import { TrendSignalsPanel } from './trend-signals-panel';
import { PlatformNewsPanel } from './platform-news-panel';
import styles from './platform-news.module.css';

export function BenchmarkWorkspace({ connected, active, manageSources, officialUrls, onIdeaSaved }: {
  connected: boolean; active: boolean; manageSources: boolean; officialUrls?: string[]; onIdeaSaved?: () => void;
}) {
  const router = useRouter();
  const [platform, setPlatform] = useState('all');
  const [discoveryOpen, setDiscoveryOpen] = useState(false);
  const [trendsOpen, setTrendsOpen] = useState(false);
  const [preparedDraft, setPreparedDraft] = useState('');
  const [openSignal, setOpenSignal] = useState(0);
  const [closeSignal, setCloseSignal] = useState(0);
  useEffect(() => { if (!active) setCloseSignal(value => value + 1); }, [active]);

  return <div id="competitors" className={"outline-target " + styles.workspace} hidden={!active}>
    <PlatformNewsPanel active={active} platform={platform} onPlatformChange={setPlatform} onIdeaSaved={onIdeaSaved} />
    <details id="platform-trend-research" className={styles.discovery} onToggle={event => setDiscoveryOpen(event.currentTarget.open)}>
      <summary>소재 참고 조사 · 설정과 결과</summary>
      <DiscoveryPanel active={active && discoveryOpen} platform={platform} />
    </details>
    <details id="trend-signals" className={styles.discovery} onToggle={event => setTrendsOpen(event.currentTarget.open)}>
      <summary>트렌드 신호(0원) · 자동완성과 위키백과 조회수</summary>
      <TrendSignalsPanel active={active && trendsOpen} onIdeaSaved={onIdeaSaved} />
    </details>
    <BenchmarkPanel active={active} platform={platform} onResetPlatform={() => setPlatform('all')} manageSources={manageSources}
      officialUrls={officialUrls} onIdeaSaved={onIdeaSaved}
      onSendResearch={async text => {
        if (!active) return '플랫폼 소식에서 조사 요청문을 검토하세요.';
        setPreparedDraft(text);
        setOpenSignal(value => value + 1);
        return '기존 비서 요청 화면을 열었습니다. 요청문을 확인한 뒤 직접 보내 주세요. 아직 접수하지 않았습니다.';
      }} />
    {openSignal > 0 && <AssistantChat connected={connected && active} openSignal={openSignal} closeSignal={closeSignal} requestedAssistant="mybots-sage" preparedDraft={preparedDraft}
      createRequest={api.createAssistantRequest} loadRequest={api.assistantRequest} onObservation={() => {}}
      onReportAction={async request => {
        router.push('/office3d?assistant_request=' + encodeURIComponent(request.request_id));
        return '기존 비서 업무실에서 검증된 완료 보고를 확인합니다.';
      }} />}
    <p className="muted">세이지 조사 요청과 완료 보고는 <Link href="/office3d" prefetch={false}>비서 업무실</Link>에서 확인할 수 있습니다.</p>
  </div>;
}
