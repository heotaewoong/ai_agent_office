"use client";

import { useCallback, useEffect, useId, useState } from "react";
import type { FormEvent } from "react";
import { api } from "../lib/api";
import { formatDate } from "../lib/workflow";
import type { BriefPresets, Channel, QuestionGroup, QuestionSource, ReaderQuestion } from "../lib/types";

const SOURCES: { id: QuestionSource; label: string }[] = [
  { id: "homepage", label: "홈페이지" },
  { id: "comment", label: "댓글" },
  { id: "dm", label: "DM" },
  { id: "email", label: "이메일" },
  { id: "other", label: "기타" },
];

export function questionSourceLabel(source: string): string {
  return SOURCES.find((s) => s.id === source)?.label ?? source;
}

/** 독자 질문 수집. 홈페이지·댓글·DM에서 받은 질문을 모으고, 묶음 단위로 ⓪ 기획 은행에 보냅니다. */
export function QuestionsPanel({ onConverted }: { onConverted: () => void }) {
  const uid = useId();
  const [questions, setQuestions] = useState<ReaderQuestion[]>([]);
  const [groups, setGroups] = useState<QuestionGroup[]>([]);
  const [channels, setChannels] = useState<Channel[]>([]);
  const [presets, setPresets] = useState<BriefPresets>({ default: "", presets: [] });
  const [loadError, setLoadError] = useState("");
  const [error, setError] = useState("");
  const [message, setMessage] = useState("");
  const [busy, setBusy] = useState(false);
  const [source, setSource] = useState<QuestionSource>("homepage");
  const [text, setText] = useState("");
  const [channelKey, setChannelKey] = useState("");
  const [converting, setConverting] = useState<string | null>(null);
  const [preset, setPreset] = useState("");
  const [title, setTitle] = useState("");

  const load = useCallback(async () => {
    try {
      const result = await api.questions();
      setQuestions(result.questions);
      setGroups(result.groups);
      setLoadError("");
    } catch (cause) {
      setLoadError(cause instanceof Error ? cause.message : "독자 질문을 불러오지 못했습니다.");
    }
  }, []);

  useEffect(() => {
    void load();
    let alive = true;
    api
      .channels()
      .then((r) => alive && setChannels(r.channels))
      .catch(() => alive && setChannels([]));
    api
      .briefs()
      .then((r) => alive && setPresets(r))
      .catch(() => alive && setPresets({ default: "", presets: [] }));
    return () => {
      alive = false;
    };
  }, [load]);

  async function submit(event: FormEvent) {
    event.preventDefault();
    if (busy) return;
    const value = text.trim();
    if (!value) {
      setError("질문 내용을 입력하세요.");
      return;
    }
    setError("");
    setMessage("");
    setBusy(true);
    try {
      const result = await api.addQuestion({ source, text: value, channel_key: channelKey || null });
      setText("");
      setMessage(result.question.count > 1 ? `저장됨 · 같은 질문 ${result.question.count}건으로 묶였습니다.` : "저장됨");
      await load();
    } catch (cause) {
      setError(cause instanceof Error ? cause.message : "질문을 저장하지 못했습니다.");
    } finally {
      setBusy(false);
    }
  }

  async function convert(group: QuestionGroup) {
    const id = group.question_ids[0];
    if (!id || busy) return;
    setBusy(true);
    setError("");
    try {
      const result = await api.questionToIdea(id, { brief_preset: preset || null, title: title.trim() || null });
      setConverting(null);
      setTitle("");
      setMessage(`기획 은행에 보냈습니다: ${result.idea.title}`);
      await load();
      onConverted();
    } catch (cause) {
      setError(cause instanceof Error ? cause.message : "기획으로 보내지 못했습니다.");
    } finally {
      setBusy(false);
    }
  }

  const byId = new Map(questions.map((q) => [q.id, q]));
  const groupConverted = (group: QuestionGroup) => group.question_ids.length > 0 && group.question_ids.every((id) => byId.get(id)?.state === "converted");

  return (
    <section className="news-section questions-panel" aria-labelledby="questions-heading">
      <div className="section-heading">
        <div className="section-title">
          <h2 id="questions-heading">독자 질문</h2>
          <span className="count-pill">{questions.length}</span>
        </div>
        <span className="section-meta">같은 질문은 묶어서 세고, 묶음을 ⓪ 기획 은행으로 보냅니다</span>
      </div>
      <details>
        <summary>질문 등록</summary>
        <form onSubmit={(e) => void submit(e)}>
          <fieldset disabled={busy} style={{ border: 0, padding: 0, margin: 0 }}>
            <div className="editor-fields">
              <div>
                <label htmlFor={`${uid}-source`}>받은 곳</label>
                <select id={`${uid}-source`} value={source} onChange={(e) => setSource(e.target.value as QuestionSource)}>
                  {SOURCES.map((s) => (
                    <option key={s.id} value={s.id}>
                      {s.label}
                    </option>
                  ))}
                </select>
              </div>
              <div>
                <label htmlFor={`${uid}-channel`}>채널</label>
                <select id={`${uid}-channel`} value={channelKey} onChange={(e) => setChannelKey(e.target.value)}>
                  <option value="">채널 없음</option>
                  {channels.map((c) => (
                    <option key={c.key} value={c.key}>
                      {c.label} ({c.key})
                    </option>
                  ))}
                </select>
              </div>
              <label htmlFor={`${uid}-text`}>질문</label>
              <textarea id={`${uid}-text`} rows={3} maxLength={2000} value={text} placeholder="독자가 한 말을 그대로 적어요. 이름·이메일 같은 개인정보는 빼 주세요." onChange={(e) => setText(e.target.value)} />
            </div>
          </fieldset>
          {error && (
            <p className="notice error" role="alert">
              {error}
            </p>
          )}
          {message && <p className="muted">{message}</p>}
          <button className="button primary" type="submit" disabled={busy}>
            {busy ? "저장 중" : "질문 저장"}
          </button>
        </form>
      </details>
      {loadError && <p className="field-error">{loadError}</p>}
      {groups.length === 0 && !loadError && <p className="muted">아직 모은 질문이 없습니다.</p>}
      {groups.length > 0 && (
        <ul className="question-groups">
          {groups.map((group) => {
            const first = byId.get(group.question_ids[0] ?? "");
            const done = groupConverted(group);
            return (
              <li key={group.group_key} className={done ? "converted" : ""}>
                <div>
                  <strong>{group.sample_text}</strong>
                  <small>
                    {group.count}건
                    {first ? ` · ${questionSourceLabel(first.source)}` : ""}
                    {first?.channel_key ? ` · ${first.channel_key}` : ""}
                    {first?.created_at ? ` · ${formatDate(first.created_at, true)}` : ""}
                    {done ? " · 기획 전환됨" : ""}
                  </small>
                </div>
                {!done &&
                  (converting === group.group_key ? (
                    <div className="question-convert">
                      <select aria-label="독자 브리프 프리셋" value={preset} disabled={busy} onChange={(e) => setPreset(e.target.value)}>
                        <option value="">프리셋 기본값{presets.default ? ` (${presets.default})` : ""}</option>
                        {presets.presets.map((p) => (
                          <option key={p.id} value={p.id}>
                            {p.label}
                          </option>
                        ))}
                      </select>
                      <input aria-label="기획 제목(비우면 질문으로)" placeholder="기획 제목 (비우면 질문 문장)" maxLength={200} value={title} disabled={busy} onChange={(e) => setTitle(e.target.value)} />
                      <button className="button primary small" type="button" disabled={busy} onClick={() => void convert(group)}>
                        보내기
                      </button>
                      <button className="button text small" type="button" disabled={busy} onClick={() => setConverting(null)}>
                        취소
                      </button>
                    </div>
                  ) : (
                    <button className="button secondary small" type="button" disabled={busy} onClick={() => setConverting(group.group_key)}>
                      기획으로 보내기
                    </button>
                  ))}
              </li>
            );
          })}
        </ul>
      )}
    </section>
  );
}
