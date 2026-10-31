"use client";

import { useEffect, useState, type ReactNode } from "react";
import { api } from "../lib/api";
import { paidProduceNotice } from "../lib/settings";
import type { ClipEstimate } from "../lib/types";

// Produce / re-produce with the paid items shown first. Paid clips need a second, in-page click
// (no window.confirm: some viewers block it). The server refuses unconfirmed paid production too.
export function ProduceButton({
  jobId,
  className,
  disabled,
  children,
  onProduce,
}: {
  jobId: string;
  className: string;
  disabled: boolean;
  children: ReactNode;
  onProduce: (confirmPaidClips: boolean) => Promise<unknown> | void;
}) {
  const [estimate, setEstimate] = useState<ClipEstimate | null>(null);
  const [confirming, setConfirming] = useState(false);
  const [thumbnails,setThumbnails]=useState(false);

  useEffect(() => {
    let alive = true;
    setConfirming(false);
    api
      .productionEstimate(jobId)
      .then((result) => {if(alive){setEstimate(result.clips);setThumbnails(!!result.thumbnail_artwork);}})
      .catch(() => alive && setEstimate(null));
    return () => {
      alive = false;
    };
  }, [jobId]);

  const notice = [paidProduceNotice(estimate),thumbnails?"원고 기반 썸네일 이미지 3장 자동 생성 · 최대 600원 예약 · 기존 후보 재사용":""].filter(Boolean).join(" · ");
  if (!notice)
    return (
      <button className={className} disabled={disabled} onClick={() => void onProduce(false)}>
        {children}
      </button>
    );
  return (
    <span className="produce-confirm" role="group" aria-label="유료 제작 확인">
      <small className="paid-notice">
        {notice}
        {estimate?.daily_cap != null && ` · 오늘 ${estimate.used_today ?? 0}/${estimate.daily_cap}개 사용`}
      </small>
      {confirming ? (
        <>
          <button
            className={className}
            disabled={disabled}
            onClick={() => {
              setConfirming(false);
              void onProduce(true);
            }}
          >
            유료 포함 제작 확인
          </button>
          <button className="button text" disabled={disabled} onClick={() => setConfirming(false)}>
            취소
          </button>
        </>
      ) : (
        <button className={className} disabled={disabled} onClick={() => setConfirming(true)}>
          {children}
        </button>
      )}
    </span>
  );
}
