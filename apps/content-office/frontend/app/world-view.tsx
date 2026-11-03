"use client";

import { useCallback, useEffect, useLayoutEffect, useRef, useState } from "react";
import { api } from "../lib/api";
import { AssistantReports } from "./assistant-reports";
import { AssistantChat } from "./assistant-chat";
import { parseAssistantRequest } from "../lib/assistant-requests.ts";
import type { AssistantProfile, AssistantRequest } from "../lib/assistant-requests";
import { isDevAction, isStocksAction, matchesAssistantReportRef, parseAssistantReportResult, parseWorldMessage, routeWorldMessage } from "../lib/world-bridge";
import type { AssistantReportAction } from "../lib/world-bridge";

type View = "news" | "studio" | "delivery" | "activity" | "world";

export function WorldView({
  activeId,
  busy,
  connected,
  onOpen,
  onAction,
}: {
  activeId: string;
  busy: boolean;
  connected: boolean;
  onOpen: (view: View, itemId: string) => void;
  onAction: (action: "draft" | "produce", itemId: string) => Promise<void>;
}) {
  const frame = useRef<HTMLIFrameElement>(null);
  const fullscreenButton = useRef<HTMLButtonElement>(null);
  const [expanded, setExpanded] = useState(false);
  const [screenBusy, setScreenBusy] = useState(false);
  const [screenNotice, setScreenNotice] = useState('');
  const closeScreen = useCallback(() => {
    setExpanded(false);
    setScreenNotice('');
    fullscreenButton.current?.focus({ preventScroll: true });
  }, []);
  const toggleScreen = async () => {
    const shell = frame.current?.parentElement;
    if (!shell || screenBusy) return;
    setScreenBusy(true);
    try {
      if (expanded) {
        if (document.fullscreenElement === shell) await document.exitFullscreen();
        closeScreen();
      } else {
        setExpanded(true);
        if (!shell.requestFullscreen) throw new Error('fullscreen unavailable');
        await shell.requestFullscreen();
      }
    } catch {
      setScreenNotice(expanded ? 'Esc로 전체화면에서 나가 주세요.' : '페이지 안에서 화면을 가득 채웠습니다. 원래 크기로 돌아갈 수 있어요.');
    } finally {
      setScreenBusy(false);
      if (expanded) requestAnimationFrame(() => fullscreenButton.current?.focus({ preventScroll: true }));
    }
  };
  useEffect(() => {
    if (!expanded) return;
    const previousOverflow = document.body.style.overflow;
    document.body.style.overflow = 'hidden';
    const escape = (event: KeyboardEvent) => {
      if (event.key === 'Escape' && !document.fullscreenElement) { event.preventDefault(); event.stopPropagation(); closeScreen(); }
    };
    const exited = () => { if (!document.fullscreenElement) closeScreen(); };
    const inner = frame.current?.contentWindow;
    const listenInside = () => frame.current?.contentWindow?.addEventListener('keydown', escape, true);
    window.addEventListener('keydown', escape, true);
    document.addEventListener('fullscreenchange', exited);
    inner?.addEventListener('keydown', escape, true);
    const iframe = frame.current;
    iframe?.addEventListener('load', listenInside);
    return () => {
      document.body.style.overflow = previousOverflow;
      window.removeEventListener('keydown', escape, true);
      document.removeEventListener('fullscreenchange', exited);
      inner?.removeEventListener('keydown', escape, true);
      iframe?.contentWindow?.removeEventListener('keydown', escape, true);
      iframe?.removeEventListener('load', listenInside);
    };
  }, [expanded, closeScreen]);
  const resizeFrame = (change: number) => {
    const shell = frame.current?.parentElement;
    if (shell) shell.style.height = `${Math.max(480, Math.min(1600, shell.getBoundingClientRect().height + change))}px`;
  };
  const [chatSignal, setChatSignal] = useState(0);
  const [chatAssistant, setChatAssistant] = useState<AssistantProfile>('lumi');
  const lastAssistant = useRef<AssistantRequest | null>(null);
  const reportAction = useRef<{ action: AssistantReportAction; resolve: (message: string) => void; reject: (reason: Error) => void; timer: number } | null>(null);
  const reportChecking = useRef(false);
  const post = useCallback((message: Record<string, unknown>) => {
    frame.current?.contentWindow?.postMessage(
      { source: "content-office", ...message },
      window.location.origin,
    );
  }, []);
  const observeAssistant = useCallback((request: AssistantRequest) => {
    lastAssistant.current = request;
    post({ type: 'assistant-observation', request });
  }, [post]);
  const latest = useRef({ activeId, busy, connected, onOpen, onAction });
  useLayoutEffect(() => {
    latest.current = { activeId, busy, connected, onOpen, onAction };
  });
  const inFlight = useRef(false);
  const focusAssistantWorld = useCallback(() => {
    frame.current?.scrollIntoView({ block: 'start', behavior: 'auto' });
    frame.current?.focus({ preventScroll: true });
  }, []);

  const openAssistantReport = useCallback(async (request: AssistantRequest, action: 'visit' | 'result') => {
    const report = request.report;
    if (!report || !latest.current.connected || reportChecking.current || reportAction.current) throw new Error('작업실 연결을 확인해 주세요. 기존 보고는 보존했습니다.');
    const reference: AssistantReportAction = { type: 'assistant-report-action', action, request_id: request.request_id,
      task_id: report.task_id, run_id: report.run_id, event_id: report.event_id };
    if (!matchesAssistantReportRef(reference, lastAssistant.current)) throw new Error('현재 업무와 완료 보고가 다릅니다. 같은 요청 상태를 확인해 주세요.');
    reportChecking.current = true;
    try {
      const fresh = parseAssistantRequest(await api.assistantRequest(request.request_id), request.request_id);
      if (!latest.current.connected || !frame.current?.contentWindow || !matchesAssistantReportRef(reference, fresh)
        || !matchesAssistantReportRef(reference, lastAssistant.current)) throw new Error('최신 완료 기록이 바뀌었습니다. 기존 보고를 보존했으니 같은 요청 상태를 확인해 주세요.');
      observeAssistant(fresh);
      return await new Promise<string>((resolve, reject) => {
        const timer = window.setTimeout(() => {
          reportAction.current = null;
          reject(new Error('작업실의 응답을 확인하지 못했습니다. 기존 보고를 보존했으며 자동으로 다시 실행하지 않습니다.'));
        }, 10_000);
        reportAction.current = { action: reference, resolve, reject, timer };
        post(reference);
      });
    } finally { reportChecking.current = false; }
  }, [observeAssistant, post]);

  useEffect(() => () => {
    const pending = reportAction.current;
    if (pending) { window.clearTimeout(pending.timer); reportAction.current = null; pending.reject(new Error('화면 연결이 종료됐습니다. 기존 업무는 보존됩니다.')); }
  }, []);

  useEffect(() => {
    async function handle(event: MessageEvent) {
      if (event.origin !== window.location.origin) return;
      if (event.source !== frame.current?.contentWindow) return;
      const result = parseAssistantReportResult(event.data);
      if (result) {
        const pending = reportAction.current;
        if (!pending || result.action !== pending.action.action
          || result.request_id !== pending.action.request_id || result.task_id !== pending.action.task_id
          || result.run_id !== pending.action.run_id || result.event_id !== pending.action.event_id
          || !matchesAssistantReportRef(result, lastAssistant.current)) return;
        window.clearTimeout(pending.timer); reportAction.current = null;
        if (result.ok) pending.resolve(result.message); else pending.reject(new Error(result.message));
        return;
      }
      const message = parseWorldMessage(event.data);
      if (!message) return;
      const current = latest.current;
      const route = routeWorldMessage(message, {
        busy: current.busy,
        connected: current.connected,
        inFlight: inFlight.current,
      });
      if (route.kind === "focus") {
        post({ type: "focus", itemId: current.activeId });
        if (lastAssistant.current) post({ type: 'assistant-observation', request: lastAssistant.current });
      } else if (route.kind === 'assistant' && message.type === 'assistant-open') {
        setChatAssistant(message.assistant);
        setChatSignal(signal => signal + 1);
      } else if (route.kind === "open" && message.type === "open") {
        current.onOpen(message.view, message.itemId);
      } else if (route.kind === "reply") {
        post({ type: "result", ok: false, message: route.message });
      } else if (message.type === "action") {
        inFlight.current = true;
        try {
          if (isDevAction(message.action)) {
            const on = message.action === "auto-deploy-on";
            await api.setAutoDeploy(on);
            post({ type: "result", ok: true, message: on ? "자동 배포를 켰습니다" : "자동 배포를 껐습니다" });
          } else if (isStocksAction(message.action)) {
            const result = await api.refreshStocks();
            post({ type: "result", ok: result.started, message: result.message });
          } else {
            await current.onAction(message.action, message.itemId);
            post({ type: "result", ok: true, message: "요청했습니다" });
          }
          post({ type: "refresh" });
        } catch (cause) {
          post({
            type: "result",
            ok: false,
            message: cause instanceof Error ? cause.message : "요청을 처리하지 못했습니다.",
          });
        } finally {
          inFlight.current = false;
        }
      }
    }
    window.addEventListener("message", handle);
    return () => window.removeEventListener("message", handle);
  }, [post]);

  useEffect(() => {
    post({ type: "focus", itemId: activeId });
  }, [activeId, post]);

  return (
    <section className="world-workspace" aria-label="오피스 월드와 콘텐츠 검토">
      <div className="world-workspace-bar">
        <div>
          <strong>도시에서 살펴보고, 작업실에서 검토하세요.</strong>
          <p>3D가 느리거나 열리지 않아도 원고와 완성 파일을 확인할 수 있어요. 승인과 발행은 별도 검토가 필요합니다.</p>
        </div>
        <div className="world-workspace-links" aria-label="콘텐츠 검토 화면">
          <button className="button secondary" type="button" onClick={() => onOpen("studio", activeId)}>원고 작업실</button>
          <button className="button secondary" type="button" onClick={() => onOpen("delivery", activeId)}>완성 파일·출고함</button>
        </div>
      </div>
      <AssistantReports connected={connected} loadReports={api.assistantReports} />
      <AssistantChat connected={connected} openSignal={chatSignal} requestedAssistant={chatAssistant} createRequest={api.createAssistantRequest} loadRequest={api.assistantRequest} onObservation={observeAssistant} onReportAction={openAssistantReport} onReportOpened={focusAssistantWorld} />
      <div className={`world-frame-resizer${expanded ? ' world-frame-expanded' : ''}`}>
      <div className="world-frame-controls" role="group" aria-label="3D 화면 크기 조절">
        <button ref={fullscreenButton} type="button" onClick={toggleScreen} disabled={screenBusy} aria-pressed={expanded}>{expanded ? '원래 크기' : '전체화면'}</button>
        {!expanded && <><button type="button" onClick={() => resizeFrame(160)}>화면 길게</button>
        <button type="button" onClick={() => resizeFrame(-160)}>화면 짧게</button></>}
        <span role="status">{screenNotice || (expanded ? 'Esc로 돌아가기' : '모서리를 끌어 높이를 조절할 수도 있어요.')}</span>
      </div>
      <iframe
        ref={frame}
        className="world-frame"
        title="오피스 월드"
        src="/world/index.html?api=/api/space&embed=1"
      />
      </div>
    </section>
  );
}
