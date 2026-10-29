"use client";

import { useEffect, useId, useState } from "react";
import { api } from "../lib/api";
import { changeOfferDraft, estimatedCouponPrice, offerDraftFromJob, offerFromForm, syncOfferDraft, type OfferDraft, type OfferDraftUpdate } from "../lib/offer";
import { formatDate, formatMoney } from "../lib/workflow";
import type { Action, Job } from "../lib/types";

/** 오퍼 기록은 실제 쿠폰 발급·결제 검증·콘텐츠 승인을 대신하지 않는다. */
export function OfferPanel({ job, busy, action, cached, onDraftChange }: { job: Job; busy: boolean; action: Action; cached?: OfferDraft; onDraftChange?: (job: Job, update: OfferDraftUpdate) => void }) {
  const uid = useId();
  const offer = job.offer ?? null;
  const [localDraft, setLocalDraft] = useState(() => offerDraftFromJob(job));
  const draft = syncOfferDraft(cached ?? localDraft, job);
  const { form, baseHash, dirty } = draft;
  const [error, setError] = useState("");
  const conflict = dirty && baseHash !== (job.offer_hash ?? null);
  const update = (change: OfferDraftUpdate) => {
    if (onDraftChange) onDraftChange(job, change);
    else setLocalDraft((current) => change(syncOfferDraft(current, job)));
  };
  useEffect(() => {
    if (!dirty || onDraftChange) return;
    const beforeUnload = (event: BeforeUnloadEvent) => { event.preventDefault(); event.returnValue = ""; };
    window.addEventListener("beforeunload", beforeUnload);
    return () => window.removeEventListener("beforeunload", beforeUnload);
  }, [dirty, onDraftChange]);
  const set = (key: string, value: string) => {
    setError("");
    update((current) => changeOfferDraft(current, key, value));
  };

  async function save() {
    if (busy || conflict) return;
    const parsed = offerFromForm(form);
    if ("error" in parsed) {
      setError(parsed.error);
      return;
    }
    const submitted = draft;
    let saved: Job | undefined;
    const result = await action("캠페인 오퍼 저장", async () => { saved = await api.setOffer(job.id, { ...parsed.offer, expected_offer_hash: baseHash }); return saved; }, "캠페인 오퍼를 기록했습니다. 새 원고·CTA를 확인하고 원고 승인①부터 다시 진행하세요.");
    if (result === true && saved) {
      const updated = saved;
      update((current) => current === submitted ? offerDraftFromJob(updated) : current);
    } else if (typeof result === "string") setError(result);
  }

  async function remove() {
    if (busy || conflict) return;
    if (!window.confirm("이 작업의 오퍼를 지울까요? 관련 승인·현재 제작물은 무효화되며 새 원고 검수가 필요합니다. 실제 스토어 상품·쿠폰은 바뀌지 않습니다.")) return;
    const submitted = draft;
    let saved: Job | undefined;
    const result = await action("오퍼 삭제", async () => { saved = await api.deleteOffer(job.id, baseHash); return saved; }, "오퍼 기록을 지웠습니다. 새 원고와 승인을 확인하세요.");
    if (result === true && saved) {
      const updated = saved;
      update((current) => current === submitted ? offerDraftFromJob(updated) : current);
    } else if (typeof result === "string") setError(result);
  }

  const field = (key: string, label: string, hint?: string, inputMode?: "numeric") => (
    <div>
      <label htmlFor={`${uid}-${key}`}>{label}</label>
      <input id={`${uid}-${key}`} value={form[key]} placeholder={hint} inputMode={inputMode} disabled={busy} onChange={(e) => set(key, e.target.value)} />
    </div>
  );

  return (
    <section className="editor-panel derived-panel offer-panel" aria-label="캠페인과 쿠폰 기록">
      <div className="section-heading">
        <div>
          <span className="eyebrow">EC2 작업에 남는 캠페인 기록</span>
          <h2>구매 링크와 쿠폰을 원고에 연결하기</h2>
        </div>
        {offer && (
          <span className="muted">
            기록 {formatDate(offer.captured_at, true)} · {offer.actor}
          </span>
        )}
      </div>
      {offer ? (
        <p className="muted">
          <strong>{offer.product}</strong> · 기준 가격 {formatMoney(offer.price_krw)}원 ·{" "}
          <a href={offer.url} target="_blank" rel="noopener noreferrer">
            {offer.url}
          </a>
          {offer.note ? ` · ${offer.note}` : ""}
        </p>
      ) : (
        <p className="muted">아직 오퍼가 없습니다. 기록은 작업에만 남고 스토어 가격·쿠폰·다운로드 권한은 바꾸지 않습니다.</p>
      )}
      {offer?.coupon && (
        <p className={offer.coupon.verified ? "notice" : "notice error"} role="status">
          쿠폰 {offer.coupon.verified ? "운영자가 조건 확인을 기록함" : "미확정 · 실제 발급/적용 확인 필요"}
          {offer.coupon.discount_percent != null ? ` · ${offer.coupon.discount_percent}% 할인 · 예상 ${formatMoney(estimatedCouponPrice(offer.price_krw, offer.coupon.discount_percent))}원` : ""}
          {offer.coupon.expires_at ? ` · 만료 ${formatDate(offer.coupon.expires_at, true)}` : " · 만료 미정"}
          <br />스토어 실시간 조회나 결제 성공 증빙이 아닙니다. 최종 가격은 실제 결제 화면에서 확인하세요.
        </p>
      )}
      <p className="muted">상품·쿠폰을 바꾸면 기존 승인①②와 현재 제작물이 무효화됩니다. 새 원고의 구매 안내·영상 마지막 장면을 읽고 재검수한 뒤 승인하세요. 이 화면은 스토어 쿠폰을 발급하지 않습니다.</p>
      <details>
        <summary>{offer ? "오퍼 바꾸기" : "오퍼 적기"}</summary>
        <div className="editor-fields">
          {field("product", "상품", "예: 7일 복습 플래너")}
          {field("price_krw", "할인 전 기준 가격(원)", "예: 9,900", "numeric")}
          {field("url", "실제 상품 URL (https)", "https://www.heobrain.kr/")}
          {field("note", "메모")}
        </div>
        <label className="media-review-check">
          <input type="checkbox" checked={form.coupon_enabled === "yes"} disabled={busy} onChange={(e) => set("coupon_enabled", e.target.checked ? "yes" : "no")} />
          이 캠페인에서 쿠폰을 안내합니다
        </label>
        {form.coupon_enabled === "yes" && <>
          <div className="editor-fields">
            {field("coupon_code", "쿠폰 코드", "발급 전이면 비워 두세요")}
            {field("discount_percent", "할인율(%)", "50", "numeric")}
            <div>
              <label htmlFor={`${uid}-expires_at`}>만료 시각(한국 시간)</label>
              <input id={`${uid}-expires_at`} type="datetime-local" value={form.expires_at} disabled={busy} onChange={(e) => set("expires_at", e.target.value)} />
            </div>
            {field("coupon_terms", "적용 상품·사용 한도 등 조건", "예: 해당 상품만, 1인 1회, 전체 사용 한도")}
          </div>
          <label className="media-review-check">
            <input type="checkbox" checked={form.coupon_verified === "yes"} disabled={busy} onChange={(e) => set("coupon_verified", e.target.checked ? "yes" : "no")} />
            스토어에서 실제 발급·적용 조건을 직접 확인했고 위 내용과 일치합니다
          </label>
          <p className="muted">미확정 상태도 기획으로 저장할 수 있지만 원고·제작은 차단됩니다. 확인 표시를 해도 앱이 스토어에 쿠폰을 만들거나 실제 결제를 시험하지 않습니다. 조건을 고치면 확인 표시가 해제됩니다.</p>
        </>}
        {dirty && <p className="muted" role="status">저장하지 않은 캠페인 입력이 있습니다. {onDraftChange ? "작업·화면을 바꿔도 이 탭에서 보존합니다. 새로고침 전에 저장하세요." : "다른 화면으로 이동하기 전에 저장하세요."} 입력만으로 현재 원고·승인·제작물이 바뀌지는 않습니다.</p>}
        {conflict && <div className="notice error" role="alert">
          다른 작업에서 캠페인 기록이 바뀌었습니다. 현재 입력은 보존했으며 덮어쓰기를 막았습니다.
        </div>}
        {error && (
          <p className="notice error" role="alert">
            {error}
          </p>
        )}
        <div className="derived-actions">
          {dirty && <button type="button" className="button text small" disabled={busy} onClick={() => { update(() => offerDraftFromJob(job)); setError(""); }}>입력을 버리고 현재 기록 다시 읽기</button>}
          <button className="button secondary small" type="button" disabled={busy || conflict} onClick={() => void save()}>
            오퍼 저장
          </button>
          {offer && (
            <button className="button text small" type="button" disabled={busy || conflict} onClick={() => void remove()}>
              오퍼 삭제
            </button>
          )}
        </div>
      </details>
    </section>
  );
}
