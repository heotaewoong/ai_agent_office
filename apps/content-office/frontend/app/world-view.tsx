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
    <iframe
      ref={frame}
      className="world-frame"
      title="오피스 월드"
      src="/world/index.html?api=/api/space&embed=1"
    />
  );
}
