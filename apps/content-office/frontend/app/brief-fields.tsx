"use client";

import type { BriefPreset } from "../lib/types";
import { BRIEF_FIELDS, axisLabel } from "../lib/briefs";

export const BRIEF_FORM_EMPTY: Record<string, string> = {
  brief_preset: "",
  brief_reader: "",
  brief_problem: "",
  brief_outcome: "",
  brief_cta: "",
  brief_language: "",
};

/** 기획 등록과 작업실에서 같이 쓰는 독자 브리프 입력. 비워 둔 칸은 프리셋 값을 그대로 씁니다. */
export function BriefFields({
  uid,
  presets,
  defaultPreset,
  form,
  onChange,
  loadError,
}: {
  uid: string;
  presets: BriefPreset[];
  defaultPreset: string;
  form: Record<string, string | boolean>;
  onChange: (key: string, value: string) => void;
  loadError?: string;
}) {
  const axes = Array.from(new Set(presets.map((p) => p.axis)));
  const selectedId = String(form.brief_preset || defaultPreset);
  const selected = presets.find((p) => p.id === selectedId);
  return (
    <fieldset className="brief-fields">
      <legend>독자 브리프</legend>
      <div>
        <label htmlFor={`${uid}-brief_preset`}>프리셋</label>
        <select id={`${uid}-brief_preset`} value={String(form.brief_preset ?? "")} onChange={(e) => onChange("brief_preset", e.target.value)}>
          <option value="">기본 프리셋{defaultPreset ? ` (${presets.find((p) => p.id === defaultPreset)?.label ?? defaultPreset})` : ""}</option>
          {axes.map((axis) => (
            <optgroup key={axis} label={`${axis}축 · ${axisLabel(axis)}`}>
              {presets
                .filter((p) => p.axis === axis)
                .map((p) => (
                  <option key={p.id} value={p.id}>
                    {p.label} · {p.language === "en" ? "영어" : "한국어"}
                  </option>
                ))}
            </optgroup>
          ))}
        </select>
        {loadError && <p className="field-error">{loadError}</p>}
        {selected && (
          <p className="muted">
            독자 {selected.reader} · 문제 {selected.problem} · CTA {selected.cta}
          </p>
        )}
      </div>
      {BRIEF_FIELDS.map((f) => (
        <div key={f.key}>
          <label htmlFor={`${uid}-brief_${f.key}`}>{f.label} (비우면 프리셋 값)</label>
          <textarea
            id={`${uid}-brief_${f.key}`}
            value={String(form[`brief_${f.key}`] ?? "")}
            placeholder={selected?.[f.key] || f.hint}
            maxLength={500}
            rows={3}
            onChange={(e) => onChange(`brief_${f.key}`, e.target.value)}
          />
        </div>
      ))}
      <div>
        <label htmlFor={`${uid}-brief_language`}>언어</label>
        <select id={`${uid}-brief_language`} value={String(form.brief_language ?? "")} onChange={(e) => onChange("brief_language", e.target.value)}>
          <option value="">프리셋 값{selected ? ` (${selected.language === "en" ? "영어" : "한국어"})` : ""}</option>
          <option value="ko">한국어 (ko)</option>
          <option value="en">영어 (en)</option>
        </select>
      </div>
    </fieldset>
  );
}
