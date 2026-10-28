"use client";

import { useCallback, useEffect, useState } from "react";
import { api } from "../lib/api";
import type { Delivery as DeliveryRecord, Job } from "../lib/types";
import { canReconcile, deliveryStateLabel, studioUrl, uploadReadiness } from "../lib/settings";
import { Icon } from "./icons";

type Action = (label: string, execute: () => Promise<unknown>, success: string) => Promise<true | string>;

function when(value?: string) {
  if (!value) return "";
  const date = new Date(value);
  return Number.isNaN(date.getTime())
    ? ""
    : new Intl.DateTimeFormat("ko-KR", { timeZone: "Asia/Seoul", month: "2-digit", day: "2-digit", hour: "2-digit", minute: "2-digit" }).format(date);
}

export function YoutubePanel({
  job,
  youtubeConfigured,
  busy,
  action,
}: {
  job: Job;
  youtubeConfigured: boolean;
  busy: boolean;
  action: Action;
}) {
  const [records, setRecords] = useState<DeliveryRecord[]>([]);
  const [loadError, setLoadError] = useState("");
  const readiness = uploadReadiness(job, youtubeConfigured);

  const load = useCallback(async () => {
    try {
      setRecords((await api.deliveries(job.id)).deliveries);
      setLoadError("");
    } catch (cause) {
      setLoadError(cause instanceof Error ? cause.message : "업로드 기록을 불러오지 못했습니다");
    }
  }, [job.id]);

  useEffect(() => {
    void load();
  }, [load, job.release_approval?.version]);

  async function upload() {
    if (!window.confirm("승인된 영상을 소유 YouTube 채널에 비공개(private)로 올립니다. 진행할까요?")) return;
    await action("YouTube 비공개 업로드", () => api.deliverYoutube(job.id), "YouTube에 비공개로 올렸습니다. 공개 여부는 YouTube Studio에서 정하세요.");
    await load();
  }

  async function reconcile(record: DeliveryRecord) {
    await action("업로드 대사", () => api.reconcileDelivery(job.id, record.id), "업로드 상태를 다시 확인했습니다.");
    await load();
  }

  const blocking = records.some((r) => r.state === "accepted" || r.state === "unknown");

  return (
    <section className="youtube-panel" aria-label="YouTube 비공개 업로드">
      <div className="youtube-head">
        <div>
          <h3>
            <Icon name="play" size={17} />
            YouTube 비공개 업로드
          </h3>
          <p className={readiness.ok ? "ready" : "not-ready"}>{readiness.reason}</p>
        </div>
        <button className="button primary" disabled={busy || !readiness.ok || blocking} onClick={() => void upload()}>
          비공개로 올리기
        </button>
      </div>
      {blocking && <p className="field-error">결과가 불명인 업로드가 있습니다. 아래에서 대사한 뒤 다시 올릴지 결정하세요.</p>}
      {loadError && <p className="field-error">{loadError}</p>}
      {records.length > 0 && (
        <ul className="delivery-list">
          {records.map((record) => {
            const link = studioUrl(record.external_id);
            return (
              <li key={record.id} className={`delivery-item state-${record.state}`}>
                <div>
                  <strong>{deliveryStateLabel(record.state)}</strong>
                  <span>{record.title}</span>
                  <small>
                    {when(record.updated_at)}
                    {record.processing_status ? ` · 처리 ${record.processing_status}` : ""}
                    {record.privacy_status ? ` · 공개 범위 ${record.privacy_status}` : ""}
                    {record.reason ? ` · ${record.reason}` : ""}
                  </small>
                </div>
                <div className="delivery-actions">
                  {link && (
                    <a className="button secondary" href={link} target="_blank" rel="noopener noreferrer">
                      Studio에서 열기 <Icon name="external" size={14} />
                    </a>
                  )}
                  {canReconcile(record) && (
                    <button className="button secondary" disabled={busy} onClick={() => void reconcile(record)}>
                      상태 대사
                    </button>
                  )}
                </div>
              </li>
            );
          })}
        </ul>
      )}
    </section>
  );
}
