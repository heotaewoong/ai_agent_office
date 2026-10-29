"use client";

import { useEffect, useId, useState } from "react";
import { api } from "../lib/api";
import { briefDraftFromBrief, briefOverridesFromForm, briefSummary, changeBriefDraft, syncBriefDraft, type BriefDraft, type BriefDraftUpdate } from "../lib/briefs";
import type { Action, BriefPresets, Job } from "../lib/types";
import { BriefFields } from "./brief-fields";

/** 작업실의 독자 브리프 카드. 현재 브리프를 보여주고 프리셋·덮어쓰기를 바꿉니다. 바꾸면 다음 원고 생성부터 적용됩니다. */
export function BriefPanel({ job, busy, action, cached, onDraftChange }: {
  job: Job;
  busy: boolean;
  action: Action;
  cached?: BriefDraft;
  onDraftChange: (job: Job, update: BriefDraftUpdate) => void;
}) {
  const uid = useId();
  const [presets, setPresets] = useState<BriefPresets>({ default: "", presets: [] });
  const [presetError, setPresetError] = useState("");
  const draft = syncBriefDraft(cached ?? briefDraftFromBrief(job.brief, job.brief_hash), job.brief, job.brief_hash);
  const [error, setError] = useState("");
  const rows = briefSummary(job.brief);
  const hasToken = /^[a-f0-9]{64}$/.test(job.brief_hash ?? "");
  const conflict = draft.dirty && hasToken && draft.baseHash !== job.brief_hash;

  useEffect(() => {
    let alive = true;
    api
      .briefs()
      .then((value) => {
        if (alive) setPresets(value);
      })
      .catch((cause) => {
        if (alive) setPresetError(cause instanceof Error ? cause.message : "브리프 프리셋을 불러오지 못했습니다.");
      });
    return () => {
      alive = false;
    };
  }, []);

  async function save() {
    if (busy || !hasToken || draft.baseHash !== job.brief_hash) return;
    const parsed = briefOverridesFromForm(draft.form);
    if ("error" in parsed) {
      setError(parsed.error);
      return;
    }
    setError("");
    const preset = String(draft.form.brief_preset || presets.default || job.brief?.preset || "");
    const submitted = draft;
    let saved: Job | undefined;
    const result = await action(
      "독자 브리프 변경",
      async () => {
        saved = await api.setJobBrief(job.id, preset, parsed.overrides, submitted.baseHash);
        return saved;
      },
      "독자 브리프를 바꿨습니다. 다음 원고 생성·검수부터 적용됩니다.",
    );
    if (result === true && saved) {
      const updated = saved;
      onDraftChange(job, (current) => current === submitted ? briefDraftFromBrief(updated.brief, updated.brief_hash) : current);
    } else if (typeof result === "string") setError(result);
  }

  return (
    <section className="editor-panel brief-panel" aria-label="독자 브리프">
      <div className="section-heading">
        <div>
          <span className="eyebrow">독자 브리프</span>
          <h2>누구에게, 어떤 문제를, 어떤 결과로</h2>
        </div>
        {job.brief?.preset && <span className="muted">프리셋 {job.brief.preset}</span>}
      </div>
      {rows.length > 0 ? (
        <dl className="brief-rows">
          {rows.map(([k, v]) => (
            <div key={k}>
              <dt>{k}</dt>
              <dd>{v}</dd>
            </div>
          ))}
        </dl>
      ) : (
        <p className="muted">아직 브리프가 없습니다. 원고 생성 때 기본 프리셋이 적용됩니다.</p>
      )}
      {draft.dirty && <p className="notice" role="status">저장하지 않은 브리프가 있습니다. 다른 작업이나 화면으로 이동해도 입력을 보존합니다. 다음 원고에 적용하려면 먼저 저장하세요.</p>}
      <details>
        <summary>브리프 바꾸기</summary>
        <fieldset className="editor-fields" aria-label="브리프 수정" disabled={busy} style={{ border: 0, margin: 0, minWidth: 0 }}>
          <BriefFields
            uid={uid}
            presets={presets.presets}
            defaultPreset={presets.default}
            form={draft.form}
            onChange={(key, value) => {
              setError("");
              onDraftChange(job, (current) => changeBriefDraft(current, key, value));
            }}
            loadError={presetError}
          />
          <p className="muted">비운 칸은 프리셋 값을 씁니다. 원고 생성·비평·평가·수정이 모두 같은 브리프를 읽습니다.</p>
        </fieldset>
        {conflict && <p className="notice error" role="alert">다른 화면에서 브리프가 변경되었습니다. 입력 중인 내용은 보존했습니다. 현재 브리프를 확인한 뒤 다시 불러와 편집하세요.</p>}
        {!hasToken && <p className="notice error" role="alert">브리프 판본을 확인하지 못했습니다. 최신 작업을 다시 불러온 뒤 저장하세요.</p>}
        {draft.dirty && <button className="button text" type="button" disabled={busy || !hasToken} onClick={() => { onDraftChange(job, () => briefDraftFromBrief(job.brief, job.brief_hash)); setError(""); }}>최신 브리프로 다시 불러오기 (현재 입력 버리기)</button>}
        {error && (
          <p className="notice error" role="alert">
            {error}
          </p>
        )}
        <button className="button secondary" type="button" disabled={busy || !hasToken || draft.baseHash !== job.brief_hash} onClick={() => void save()}>
          브리프 저장
        </button>
      </details>
    </section>
  );
}
