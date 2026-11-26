"use client";
import { useState } from "react";
import { REJECT_REASONS, type RejectReason } from "../lib/evidence-marks";

/** 승인① 거절 버튼. 이유를 하나 이상 골라야 거절이 기록된다(2026-11-26). 고른 이유는 출력 골든셋의 재료가 된다. */
export function RejectSourceButton({ disabled, onReject }: {
  disabled: boolean;
  onReject: (reasons: RejectReason[], note: string) => void;
}) {
  const [open, setOpen] = useState(false);
  const [reasons, setReasons] = useState<RejectReason[]>([]);
  const [note, setNote] = useState("");
  if (!open) {
    return <button type="button" className="button text" disabled={disabled} onClick={() => setOpen(true)}>거절</button>;
  }
  return (
    <fieldset className="reject-reasons" aria-label="원고 거절 이유">
      <legend>거절 이유 (하나 이상 골라 주세요. 다음 시험지의 재료가 돼요)</legend>
      {REJECT_REASONS.map(({ key, label }) => (
        <label key={key}>
          <input
            type="checkbox"
            checked={reasons.includes(key)}
            onChange={(event) => setReasons(event.target.checked ? [...reasons, key] : reasons.filter((reason) => reason !== key))}
          />
          {" "}{label}
        </label>
      ))}
      <input type="text" maxLength={300} placeholder="한 줄 메모 (선택)" value={note}
        onChange={(event) => setNote(event.target.value)} aria-label="거절 메모" />
      <button type="button" className="button secondary" disabled={disabled || reasons.length === 0}
        onClick={() => { onReject(reasons, note.trim()); setOpen(false); setReasons([]); setNote(""); }}>
        거절 확정
      </button>
      <button type="button" className="button text" onClick={() => setOpen(false)}>취소</button>
    </fieldset>
  );
}
