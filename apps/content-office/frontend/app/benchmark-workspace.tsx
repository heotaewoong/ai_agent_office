'use client';

import { useState } from 'react';
import Link from 'next/link';
import { useRouter } from 'next/navigation';
import { api } from '../lib/api';
import { BenchmarkPanel } from './benchmark-panel';
import { AssistantChat } from './assistant-chat';

export function BenchmarkWorkspace({ connected }: { connected: boolean }) {
  const router = useRouter();
  const [preparedDraft, setPreparedDraft] = useState('');
  const [openSignal, setOpenSignal] = useState(0);
  return <>
    <BenchmarkPanel onSendResearch={async text => {
      setPreparedDraft(text);
      setOpenSignal(value => value + 1);
      return '기존 비서 요청 화면을 열었습니다. 요청문을 확인한 뒤 직접 보내 주세요. 아직 접수하지 않았습니다.';
    }} />
    {openSignal > 0 && <AssistantChat connected={connected} openSignal={openSignal} requestedAssistant="mybots-sage" preparedDraft={preparedDraft}
      createRequest={api.createAssistantRequest} loadRequest={api.assistantRequest} onObservation={() => {}}
      onReportAction={async request => {
        router.push(`/office3d?assistant_request=${encodeURIComponent(request.request_id)}`);
        return '기존 비서 업무실에서 검증된 완료 보고를 확인합니다.';
      }} />}
    <p className="muted">세이지 조사 배정을 루미에게 요청합니다. 접수·실행·검토 완료는 실제 업무 기록으로 구분합니다. <Link href="/office3d" prefetch={false}>비서 업무실 열기</Link></p>
  </>;
}
