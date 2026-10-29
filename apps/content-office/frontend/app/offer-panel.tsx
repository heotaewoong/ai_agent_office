"use client";

import { useId, useState } from "react";
import { api } from "../lib/api";
import { offerFromForm } from "../lib/offer";
import { formatDate, formatMoney } from "../lib/workflow";
import type { Action, Job } from "../lib/types";

/** 오퍼 스냅샷. 오너가 적은 상품·가격·URL을 작업에 기록만 하며, 스토어의 가격·쿠폰을 바꾸지 않습니다. */
export function OfferPanel({ job, busy, action }: { job: Job; busy: boolean; action: Action }) {
  const uid = useId();
  const offer = job.offer ?? null;
  const [form, setForm] = useState<Record<string, string>>({
    product: offer?.product ?? "",
    price_krw: offer ? String(offer.price_krw) : "",
    url: offer?.url ?? "",
    note: offer?.note ?? "",
  });
  const [error, setError] = useState("");
  const set = (key: string, value: string) => {
    setError("");
    setForm((f) => ({ ...f, [key]: value }));
  };

  function save() {
    const parsed = offerFromForm(form);
    if ("error" in parsed) {
      setError(parsed.error);
      return;
    }
    void action("오퍼 저장", () => api.setOffer(job.id, parsed.offer), "오퍼 스냅샷을 저장했습니다. 원고의 CTA가 이 상품을 가리킵니다.");
  }

  function remove() {
    if (!window.confirm("이 작업의 오퍼 스냅샷을 지울까요? 스토어의 상품은 바뀌지 않습니다.")) return;
    void action("오퍼 삭제", () => api.deleteOffer(job.id), "오퍼 스냅샷을 지웠습니다.");
  }

  const field = (key: string, label: string, hint?: string, inputMode?: "numeric") => (
    <div>
      <label htmlFor={`${uid}-${key}`}>{label}</label>
      <input id={`${uid}-${key}`} value={form[key]} placeholder={hint} inputMode={inputMode} disabled={busy} onChange={(e) => set(key, e.target.value)} />
    </div>
  );

  return (
    <section className="editor-panel derived-panel offer-panel" aria-label="오퍼 스냅샷">
      <div className="section-heading">
        <div>
          <span className="eyebrow">오퍼 스냅샷</span>
          <h2>이 콘텐츠가 가리키는 상품</h2>
        </div>
        {offer && (
          <span className="muted">
            기록 {formatDate(offer.captured_at, true)} · {offer.actor}
          </span>
        )}
      </div>
      {offer ? (
        <p className="muted">
          <strong>{offer.product}</strong> · {formatMoney(offer.price_krw)}원 ·{" "}
          <a href={offer.url} target="_blank" rel="noopener noreferrer">
            {offer.url}
          </a>
          {offer.note ? ` · ${offer.note}` : ""}
        </p>
      ) : (
        <p className="muted">아직 오퍼가 없습니다. 기록은 작업에만 남고 스토어 가격·쿠폰·다운로드 권한은 바꾸지 않습니다.</p>
      )}
      <details>
        <summary>{offer ? "오퍼 바꾸기" : "오퍼 적기"}</summary>
        <div className="editor-fields">
          {field("product", "상품", "예: 7일 복습 플래너")}
          {field("price_krw", "가격(원)", "0", "numeric")}
          {field("url", "상품 URL (https)", "https://")}
          {field("note", "메모")}
        </div>
        {error && (
          <p className="notice error" role="alert">
            {error}
          </p>
        )}
        <div className="derived-actions">
          <button className="button secondary small" type="button" disabled={busy} onClick={save}>
            오퍼 저장
          </button>
          {offer && (
            <button className="button text small" type="button" disabled={busy} onClick={remove}>
              오퍼 삭제
            </button>
          )}
        </div>
      </details>
    </section>
  );
}
