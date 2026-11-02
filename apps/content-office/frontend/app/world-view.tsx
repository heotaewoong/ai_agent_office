"use client";

import { useCallback, useEffect, useLayoutEffect, useRef, useState } from "react";
import { api } from "../lib/api";
import { AssistantReports } from "./assistant-reports";
import { AssistantChat } from "./assistant-chat";
import type { AssistantRequest } from "../lib/assistant-requests";
import { isDevAction, isStocksAction, parseWorldMessage, routeWorldMessage } from "../lib/world-bridge";

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
  const [chatSignal, setChatSignal] = useState(0);
  const lastAssistant = useRef<AssistantRequest | null>(null);
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

  useEffect(() => {
    async function handle(event: MessageEvent) {
      if (event.origin !== window.location.origin) return;
      if (event.source !== frame.current?.contentWindow) return;
      if (event.data?.source === 'office-world' && event.data?.type === 'assistant-open') {
        setChatSignal(signal => signal + 1);
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
      <AssistantChat connected={connected} openSignal={chatSignal} createRequest={api.createAssistantRequest} loadRequest={api.assistantRequest} onObservation={observeAssistant} />
      <iframe
        ref={frame}
        className="world-frame"
        title="오피스 월드"
        src="/world/index.html?api=/api/space&embed=1"
      />
    </section>
  );
}
