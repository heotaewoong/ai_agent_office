"use client";

import { useState } from "react";
import type { FormEvent } from "react";
import { api } from "../lib/api";
import { ideaInputFromForm } from "../lib/ideas";

const EMPTY: Record<string, string | boolean> = {
  title: "",
  source_url: "",
  views: "",
  channel_avg_views: "",
  demand: "0",
  primary_sources: "0",
  fit: "0",
  covered_before: false,
  policy_flags: "",
};

export function IdeaIntake({ onSaved }: { onSaved: () => void }) {
  const [form, setForm] = useState<Record<string, string | boolean>>(EMPTY);
  const [error, setError] = useState("");
  const [message, setMessage] = useState("");
  const [busy, setBusy] = useState(false);
  const set = (key: string, value: string | boolean) => setForm((f) => ({ ...f, [key]: value }));
  const field = (key: string, label: string, hint?: string) => (
    <label>
      {label}
      <input value={String(form[key])} placeholder={hint} onChange={(e) => set(key, e.target.value)} />
    </label>
  );

  async function submit(event: FormEvent) {
    event.preventDefault();
    setMessage("");
    const parsed = ideaInputFromForm(form);
    if ("error" in parsed) {
      setError(parsed.error);
      return;
    }
    setError("");
    setBusy(true);
    try {
      const idea = await api.addIdea(parsed.input);
      setForm(EMPTY);
      setMessage(idea.blocked.length > 0 ? `저장됨 · 막힌 이유: ${idea.blocked.join(", ")}` : "저장됨");
      onSaved();
    } catch (cause) {
      setError(cause instanceof Error ? cause.message : "기획을 저장하지 못했습니다.");
    } finally {
      setBusy(false);
    }
  }

  return (
    <details>
      <summary>기획 직접 등록</summary>
      <form onSubmit={(e) => void submit(e)}>
        <div className="editor-fields">
          {field("title", "제목")}
          {field("source_url", "출처 URL (https)", "https://")}
          {field("views", "조회수")}
          {field("channel_avg_views", "채널 평균 조회수")}
          {field("demand", "수요 (0~100)")}
          {field("primary_sources", "1차 출처 수")}
          {field("fit", "적합도 (0~1)")}
          <label>
            <input
              type="checkbox"
              checked={form.covered_before === true}
              onChange={(e) => set("covered_before", e.target.checked)}
            />{" "}
            전에 다룸
          </label>
          {field("policy_flags", "정책 플래그 (쉼표로 구분)")}
        </div>
        {error && (
          <p className="notice error" role="alert">
            {error}
          </p>
        )}
        {message && <p className="muted">{message}</p>}
        <button className="button primary" type="submit" disabled={busy}>
          {busy ? "저장 중" : "기획 등록"}
        </button>
      </form>
    </details>
  );
}
