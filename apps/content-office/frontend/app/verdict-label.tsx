"use client";

import { useEffect, useId, useState } from "react";
import { api } from "../lib/api";
import { verdictLabels, verdictMeanings, type VerdictLabel, type VerdictLabelState } from "../lib/source-library";

type Props = {
  ideaId: string;
  /** 부모가 들고 있는 값. 기획 선택⓪을 누를 때 부모가 이 값을 저장합니다. */
  value?: VerdictLabel;
  onChange: (label: VerdictLabel) => void;
};

/**
 * 기획 선택⓪ 바로 위에서, 자동 조사가 붙인 자료 창고 판정(맞음, 애매, 틀림)이 맞았는지 사람이 매기는 칸.
 * 맞음과 틀림은 판정 채점에 쓰고 연습은 채점에서 뺍니다. 서버가 미리 골라 둔 값은 제안일 뿐이고, 승인⓪을 만들거나 바꾸지 않습니다.
 */
export function VerdictLabelPicker({ ideaId, value, onChange }: Props) {
  const [state, setState] = useState<VerdictLabelState | null>(null);
  const name = useId();

  // 자동 조사가 끝나야 판정이 생기므로, 판정이 아직 없으면 몇 번만 다시 묻습니다.
  useEffect(() => {
    let alive = true;
    let timer: ReturnType<typeof setTimeout> | undefined;
    const ask = (left: number) => {
      api.researchLabel(ideaId).then((found) => {
        if (!alive) return;
        setState(found);
        if (!found.verdict && left > 0) timer = setTimeout(() => ask(left - 1), 8000);
      }).catch(() => undefined);
    };
    ask(4);
    return () => { alive = false; if (timer) clearTimeout(timer); };
  }, [ideaId]);

  // 저장된 답이 있으면 그 답을, 없으면 서버가 미리 골라 둔 값을 부모에게 한 번 알려 둡니다.
  const first = state?.verdict ? state.label ?? state.suggested : null;
  useEffect(() => {
    if (first && !value) onChange(first);
  }, [first]);

  if (!state?.verdict) return null;
  const picked = value ?? first ?? undefined;
  return (
    <fieldset className="idea-public-evidence" style={{ margin: "12px 0" }}>
      <legend>자료 창고 판정이 맞았는지 알려 주세요</legend>
      <p className="muted" style={{ margin: "4px 0 8px" }}>
        시스템이 이 기획에 맞는 근거가 자료 창고에 있는지 먼저 보고, 셋 중 하나로 판정해요. 지금 판정은 굵게 표시돼요.
      </p>
      <ul style={{ listStyle: "none", padding: 0, margin: "0 0 10px", display: "grid", gap: 4 }}>
        {verdictMeanings.map((item) => {
          const now = item.id === state.verdict;
          return (
            <li key={item.id} aria-current={now ? "true" : undefined}
                style={{ padding: "6px 10px", borderRadius: 8, border: `1px solid ${now ? "var(--primary)" : "var(--line)"}`, background: now ? "var(--primary-soft)" : "transparent", fontWeight: now ? 700 : 400 }}>
              {now ? "지금 판정: " : ""}<strong>{item.label}</strong> {item.meaning} {item.action}
              {now && state.top_score != null ? <span className="muted"> (창고 최고 점수 {state.top_score.toFixed(2)})</span> : null}
            </li>
          );
        })}
      </ul>
      <p className="muted" style={{ margin: "0 0 6px" }}>
        아래 자료 창고 근거를 보고 판정이 맞았는지 골라 주세요. {state.label ? "저장해 둔 답이에요." : "미리 골라 둔 값이에요."} 기획을 선택할 때 함께 저장되고, 쌓이면 판정 기준을 고치는 데 써요.
      </p>
      {verdictLabels.map((choice) => (
        <label key={choice.id} style={{ display: "inline-flex", gap: 6, marginRight: 16, alignItems: "center" }}>
          <input type="radio" name={name} checked={picked === choice.id} onChange={() => onChange(choice.id)} />
          <span><strong>{choice.label}</strong> <span className="muted">{choice.help}</span></span>
        </label>
      ))}
    </fieldset>
  );
}
