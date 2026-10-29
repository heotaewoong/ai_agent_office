"use client";

import { useCallback, useEffect, useLayoutEffect, useRef } from "react";
import { parseWorldMessage, routeWorldMessage } from "../lib/world-bridge";

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
  const post = useCallback((message: Record<string, unknown>) => {
    frame.current?.contentWindow?.postMessage(
      { source: "content-office", ...message },
      window.location.origin,
    );
  }, []);
  const latest = useRef({ activeId, busy, connected, onOpen, onAction });
  useLayoutEffect(() => {
    latest.current = { activeId, busy, connected, onOpen, onAction };
  });
  const inFlight = useRef(false);

  useEffect(() => {
    async function handle(event: MessageEvent) {
      if (event.origin !== window.location.origin) return;
      if (event.source !== frame.current?.contentWindow) return;
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
      } else if (route.kind === "open" && message.type === "open") {
        current.onOpen(message.view, message.itemId);
      } else if (route.kind === "reply") {
        post({ type: "result", ok: false, message: route.message });
      } else if (message.type === "action") {
        inFlight.current = true;
        try {
          await current.onAction(message.action, message.itemId);
          post({ type: "result", ok: true, message: "요청했습니다" });
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
      <iframe
        ref={frame}
        className="world-frame"
        title="오피스 월드"
        src="/world/index.html?api=/api/space&embed=1"
      />
    </section>
  );
}
