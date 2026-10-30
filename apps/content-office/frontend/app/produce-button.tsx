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

  useEffect(() => {
    let alive = true;
    setConfirming(false);
    api
      .productionEstimate(jobId)
      .then((result) => alive && setEstimate(result.clips))
      .catch(() => alive && setEstimate(null));
    return () => {
      alive = false;
    };
  }, [jobId]);

  const notice = paidProduceNotice(estimate);
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
