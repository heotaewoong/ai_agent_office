"use client";

import { useEffect, useId, useState } from "react";
import type { FormEvent } from "react";
import { api } from "../lib/api";
import { changeIdeaSourcesDraft, ideaSourcesDraft, ideaSourcesInput, syncIdeaSourcesDraft, type IdeaSourcesDraft } from "../lib/ideas";
import type { Idea } from "../lib/types";

/** 같은 기획 ID의 출처만 보완한다. 저장은 선택⓪나 원고 승인이 아니다. */
export function IdeaSourcesPanel({ idea, onSaved, onEditingChange, cached, onDraftChange }: {
  idea: Idea;
  onSaved: (saved: Idea) => void;
  onEditingChange?: (id: string, pending: boolean) => void;
  cached?: IdeaSourcesDraft;
  onDraftChange?: (id: string, draft: IdeaSourcesDraft | null) => void;
}) {
  const uid = useId();
  const [localDraft, setLocalDraft] = useState(() => ideaSourcesDraft(idea));
  const draft = syncIdeaSourcesDraft(onDraftChange ? cached ?? ideaSourcesDraft(idea) : localDraft, idea);
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState("");
  const [message, setMessage] = useState("");
  const candidate = idea.state === "candidate";
  const hasToken = /^[a-f0-9]{64}$/.test(idea.edit_hash ?? "");
  const conflict = draft.dirty && draft.baseHash !== idea.edit_hash;

  function changeDraft(next: IdeaSourcesDraft | null) {
    setLocalDraft(next ?? ideaSourcesDraft(idea));
    onDraftChange?.(idea.id, next?.dirty ? next : null);
  }

  useEffect(() => { onEditingChange?.(idea.id, draft.dirty || busy); }, [idea.id, draft.dirty, busy, onEditingChange]);
  useEffect(() => () => onEditingChange?.(idea.id, false), [idea.id, onEditingChange]);

  useEffect(() => {
    if (!draft.dirty) return;
    const warn = (event: BeforeUnloadEvent) => { event.preventDefault(); event.returnValue = ""; };
    window.addEventListener("beforeunload", warn);
    return () => window.removeEventListener("beforeunload", warn);
  }, [draft.dirty]);

  async function reload() {
    if (busy) return;
    setBusy(true); setError(""); setMessage("");
    try {
      const current = (await api.ideas()).ideas.find((card) => card.id === idea.id);
      if (!current) throw new Error("기획을 찾을 수 없습니다.");
      changeDraft(null);
      onSaved(current);
    } catch (cause) {
      setError(cause instanceof Error ? cause.message : "기획을 불러오지 못했습니다.");
    } finally { setBusy(false); }
  }

  async function save(event: FormEvent) {
    event.preventDefault();
    if (busy || !candidate || !hasToken || conflict) return;
    const parsed = ideaSourcesInput(draft);
    if ("error" in parsed) { setError(parsed.error); return; }
    setBusy(true); setError(""); setMessage("");
    try {
      const saved = await api.updateIdeaSources(idea.id, parsed.input);
      changeDraft(null);
      onSaved(saved);
      setMessage("출처를 보완했습니다. 다음은 기획 선택⓪입니다. 다른 차단 항목이 있으면 먼저 해결하세요.");
    } catch (cause) {
      setError(cause instanceof Error ? cause.message : "출처를 저장하지 못했습니다.");
    } finally { setBusy(false); }
  }

  return (
    <details className="idea-sources-panel">
      <summary>출처 확인·보완</summary>
      <p className="muted">운영자 확인 출처 수: {idea.operator_verified_sources ?? 0}개. URL 개수는 독립 검증 결과가 아닙니다. 서버가 이 주소의 본문을 읽었다는 뜻도 아닙니다.</p>
      <p className="muted">학교 모집 요강·공식 시험 안내·직접 작성한 경험 기록처럼 이 기획에 맞는 원출처를 직접 확인하세요. 첫 주소를 이후 원문 수집에 쓰며 나머지는 참고 목록으로 보관합니다.</p>
      {!candidate && <p className="notice">이미 선택한 기획의 출처는 여기서 바꿀 수 없습니다.</p>}
      <form onSubmit={(event) => void save(event)}>
        <fieldset disabled={busy || !candidate} className="editor-fields" style={{ border: 0, padding: 0, margin: 0, minWidth: 0 }}>
          <label htmlFor={`${uid}-urls`}>공개 HTTPS 원출처 주소 (한 줄에 하나, 최대 10개)</label>
          <textarea id={`${uid}-urls`} rows={4} maxLength={20010} value={draft.text} placeholder="직접 확인한 원출처의 https:// 주소를 붙여넣으세요." onChange={(event) => { changeDraft(changeIdeaSourcesDraft(draft, event.target.value)); setError(""); setMessage(""); }} />
          <label htmlFor={`${uid}-confirm`}><input id={`${uid}-confirm`} type="checkbox" checked={draft.confirmed} onChange={(event) => changeDraft({ ...draft, confirmed: event.target.checked, dirty: event.target.checked || draft.text !== draft.baseText })} />각 주소의 본문과 기획 관련성을 직접 확인했습니다.</label>
        </fieldset>
        {conflict && <p className="notice error" role="alert">다른 화면에서 기획이 바뀌었습니다. 입력은 보존했으며 저장을 막았습니다. 현재 기획을 다시 불러와 확인하세요.</p>}
        {!hasToken && <p className="notice error" role="alert">기획 판본을 확인하지 못했습니다. 현재 기획을 다시 불러오세요.</p>}
        {error && <p className="notice error" role="alert">{error}</p>}
        {message && <p role="status">{message}</p>}
        <div className="button-row">
          <button className="button secondary small" type="submit" disabled={busy || !candidate || !hasToken || conflict || !draft.confirmed}>{busy ? "처리 중" : "확인한 출처 저장"}</button>
          <button className="button text small" type="button" disabled={busy} onClick={() => void reload()}>현재 기획 다시 불러오기{draft.dirty ? " (입력 버리기)" : ""}</button>
        </div>
      </form>
    </details>
  );
}
