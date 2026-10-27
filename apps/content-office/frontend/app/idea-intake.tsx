"use client";

import { useId, useState } from "react";
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
  const uid = useId();
  const set = (key: string, value: string | boolean) => {
    setMessage("");
    setForm((f) => ({ ...f, [key]: value }));
  };
  const field = (key: string, label: string, hint?: string, maxLength?: number) => (
    <div>
      <label htmlFor={`${uid}-${key}`}>{label}</label>
      <input
        id={`${uid}-${key}`}
        value={String(form[key])}
        placeholder={hint}
        maxLength={maxLength}
        onChange={(e) => set(key, e.target.value)}
      />
    </div>
  );

  async function submit(event: FormEvent) {
    event.preventDefault();
    if (busy) return;
    setMessage("");
    const parsed = ideaInputFromForm(form);
    if ("error" in parsed) {
      setError(parsed.error);
      return;
    }
    setError("");
    setBusy(true);
    let saved = false;
    try {
      const idea = await api.addIdea(parsed.input);
      setForm(EMPTY);
      setMessage(idea.blocked.length > 0 ? `저장됨 · 막힌 이유: ${idea.blocked.join(", ")}` : "저장됨");
      saved = true;
    } catch (cause) {
      setError(cause instanceof Error ? cause.message : "기획을 저장하지 못했습니다.");
    } finally {
      setBusy(false);
    }
    if (saved) onSaved();
  }

  return (
    <details>
      <summary>기획 직접 등록</summary>
      <form onSubmit={(e) => void submit(e)}>
        <fieldset disabled={busy} style={{ border: 0, padding: 0, margin: 0 }}>
        <div className="editor-fields">
          {field("title", "제목", undefined, 200)}
          {field("source_url", "출처 URL (https)", "https://", 2000)}
          {field("views", "조회수")}
          {field("channel_avg_views", "채널 평균 조회수")}
          {field("demand", "수요 (0~100)")}
          {field("primary_sources", "1차 출처 수")}
          {field("fit", "적합도 (0~1)")}
          <div>
            <input
              id={`${uid}-covered`}
              type="checkbox"
              checked={form.covered_before === true}
              onChange={(e) => set("covered_before", e.target.checked)}
            />{" "}
            <label htmlFor={`${uid}-covered`}>전에 다룸</label>
          </div>
          {field("policy_flags", "정책 플래그 (쉼표로 구분)", "no_primary_source, templated_series, ai_persona_real_person_ymyl")}
          <p className="muted">자유 입력도 가능합니다. 위 세 키나 1차 출처 0개는 ⓪ 기획 선택을 막습니다(저장은 됩니다).</p>
        </div>
        </fieldset>
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
