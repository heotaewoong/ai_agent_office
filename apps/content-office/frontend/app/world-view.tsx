"use client";

import { useCallback, useEffect, useRef } from "react";
import { parseWorldMessage } from "../lib/world-bridge";

type View = "news" | "studio" | "delivery" | "activity" | "world";

export function WorldView({
  activeId,
  busy,
  onOpen,
  onAction,
}: {
  activeId: string;
  busy: boolean;
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
  const latest = useRef({ activeId, busy, onOpen, onAction });
  latest.current = { activeId, busy, onOpen, onAction };

  useEffect(() => {
    async function handle(event: MessageEvent) {
      if (event.origin !== window.location.origin) return;
      const message = parseWorldMessage(event.data);
      if (!message) return;
      const current = latest.current;
      if (message.type === "ready") {
        post({ type: "focus", itemId: current.activeId });
      } else if (message.type === "open") {
        current.onOpen(message.view, message.itemId);
      } else if (current.busy) {
        post({ type: "result", ok: false, message: "이미 처리 중입니다" });
      } else {
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
