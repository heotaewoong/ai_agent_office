"use client";

import { useEffect, useId, useState } from "react";
import { api } from "../lib/api";
import { briefOverridesFromForm, briefSummary } from "../lib/briefs";
import type { Action, BriefPresets, Job } from "../lib/types";
import { BRIEF_FORM_EMPTY, BriefFields } from "./brief-fields";

/** 작업실의 독자 브리프 카드. 현재 브리프를 보여주고 프리셋·덮어쓰기를 바꿉니다. 바꾸면 다음 원고 생성부터 적용됩니다. */
export function BriefPanel({ job, busy, action }: { job: Job; busy: boolean; action: Action }) {
  const uid = useId();
  const [presets, setPresets] = useState<BriefPresets>({ default: "", presets: [] });
  const [presetError, setPresetError] = useState("");
  const [form, setForm] = useState<Record<string, string | boolean>>({ ...BRIEF_FORM_EMPTY, brief_preset: job.brief?.preset ?? "" });
  const [error, setError] = useState("");
  const rows = briefSummary(job.brief);

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

  function save() {
    const parsed = briefOverridesFromForm(form);
    if ("error" in parsed) {
      setError(parsed.error);
      return;
    }
    setError("");
    const preset = String(form.brief_preset || job.brief?.preset || presets.default);
    void action(
      "독자 브리프 변경",
      () => api.setJobBrief(job.id, preset, parsed.overrides),
      "독자 브리프를 바꿨습니다. 다음 원고 생성·검수부터 적용됩니다.",
    );
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
      <details>
        <summary>브리프 바꾸기</summary>
        <div className="editor-fields">
          <BriefFields
            uid={uid}
            presets={presets.presets}
            defaultPreset={presets.default}
            form={form}
            onChange={(key, value) => {
              setError("");
              setForm((f) => ({ ...f, [key]: value }));
            }}
            loadError={presetError}
          />
          <p className="muted">비운 칸은 프리셋 값을 씁니다. 원고 생성·비평·평가·수정이 모두 같은 브리프를 읽습니다.</p>
        </div>
        {error && (
          <p className="notice error" role="alert">
            {error}
          </p>
        )}
        <button className="button secondary" type="button" disabled={busy} onClick={save}>
          브리프 저장
        </button>
      </details>
    </section>
  );
}
