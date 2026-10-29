"use client";

import { useCallback, useEffect, useState } from "react";
import { api } from "../lib/api";
import type { Channel, Delivery as DeliveryRecord, Job } from "../lib/types";
import { canReconcile, studioUrl } from "../lib/settings";
import { localeLabel, youtubeChannels } from "../lib/channels";
import { channelHandoffStatus, deliveryRecordLabel, packetLanguage, requirePrivateUploadResult, sourceChannelMismatch, youtubePreflight } from "../lib/delivery-readiness";
import { Icon } from "./icons";

const DEFAULT_CHANNEL = "youtube_main_ko";

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
  requestBlockedReason,
}: {
  job: Job;
  youtubeConfigured: boolean;
  busy: boolean;
  action: Action;
  requestBlockedReason?: string;
}) {
  const [records, setRecords] = useState<DeliveryRecord[]>([]);
  const [loadError, setLoadError] = useState("");
  const [channels, setChannels] = useState<Channel[]>([]);
  const [channelKey, setChannelKey] = useState(DEFAULT_CHANNEL);
  const channel = channels.find((c) => c.key === channelKey);
  const sourceLanguage = packetLanguage(job);
  const readiness = youtubePreflight(job, channel, requestBlockedReason);
  const mismatch = channel ? sourceChannelMismatch(job, channel) : null;

  useEffect(() => {
    let alive = true;
    api
      .channels()
      .then((result) => {
        if (!alive) return;
        const list = youtubeChannels(result.channels);
        setChannels(list);
        if (!list.some((c) => c.key === DEFAULT_CHANNEL) && list[0]) setChannelKey(list[0].key);
      })
      .catch(() => {
        if (alive) setChannels([]);
      });
    return () => {
      alive = false;
    };
  }, []);

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
    if (!readiness.ok || busy) return;
    const name = channel?.label ?? channelKey;
    if (!window.confirm(`승인된 영상을 ${name} 채널에 비공개(private)로 올립니다. 진행할까요?`)) return;
    await action("YouTube 비공개 업로드", async () => {
      const record = await api.deliverYoutube(job.id, channelKey);
      requirePrivateUploadResult(record);
    }, `${name} 채널의 비공개 응답과 영상 ID를 확인했습니다. 영상 처리·재생 상태는 YouTube Studio에서 확인하세요.`);
    await load();
  }

  async function reconcile(record: DeliveryRecord) {
    await action("업로드 대사", () => api.reconcileDelivery(job.id, record.id), "업로드 상태를 다시 확인했습니다.");
    await load();
  }

  const blocking = records.some((r) => ["created", "accepted", "unknown", "needs_review"].includes(r.state));

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
        <button className="button primary" disabled={busy || !readiness.ok || blocking || Boolean(mismatch)} onClick={() => void upload()}>
          비공개로 올리기
        </button>
      </div>
      {channels.length > 0 && (
        <div className="channel-pick">
          <label>
            채널
            <select value={channelKey} disabled={busy} onChange={(e) => setChannelKey(e.target.value)}>
              {channels.map((c) => (
                <option key={c.key} value={c.key}>
                  {c.label} · {localeLabel(c.locale)} · {c.credentials_configured ? "자격 설정 있음" : "토큰 없음"}
                </option>
              ))}
            </select>
          </label>
          {channel && (
            <small className="muted">
              {channel.key} · {localeLabel(channel.locale)} ·{" "}
              {channel.credentials_configured ? "자격 설정 있음 · 실제 OAuth 미검증" : `YOUTUBE_${channel.key.replace(/^youtube_/, "").toUpperCase()}_REFRESH_TOKEN 없음`}
              {channel.publication_enabled ? "" : " · 제작 설정에서 발행 허용이 꺼져 있습니다"}
            </small>
          )}
        </div>
      )}
      {mismatch && <p className="field-error">{mismatch}</p>}
      <p className="muted">제작물에 연결된 원고 언어: {sourceLanguage ? localeLabel(sourceLanguage) : "미확인"} · 다음 원고용 브리프: {localeLabel(job.brief?.language)}. 브리프 변경은 기존 영상의 번역이 아닙니다.</p>
      {!channel && youtubeConfigured && <p className="muted">서버에 YouTube 자격 설정은 있으나 선택 채널을 확인하지 못해 요청을 막았습니다.</p>}
      {blocking && <p className="field-error">준비·전송 중이거나 결과 확인이 필요한 업로드가 있습니다. 아래 장부와 Studio를 확인하고 가능한 경우 대사하세요. 자동 재전송하지 않습니다.</p>}
      {loadError && <p className="field-error">{loadError}</p>}
      {records.length > 0 && (
        <ul className="delivery-list">
          {records.map((record) => {
            const link = studioUrl(record.external_id);
            return (
              <li key={record.id} className={`delivery-item state-${record.state}`}>
                <div>
                  <strong>{deliveryRecordLabel(record)}</strong>
                  <span>{record.title}</span>
                  <small>
                    {when(record.updated_at)}
                    {record.channel_key ? ` · ${record.channel_key}` : ""}
                    {record.locale ? ` (${localeLabel(record.locale)})` : ""}
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
                    <button className="button secondary" disabled={busy || Boolean(requestBlockedReason)} title={requestBlockedReason} onClick={() => void reconcile(record)}>
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

export function ChannelHandoffPanel({ job }: { job: Job }) {
  const sourceLanguage = packetLanguage(job);
  const [channels, setChannels] = useState<Channel[]>([]);
  const [error, setError] = useState("");
  useEffect(() => {
    let alive = true;
    api.channels().then((result) => {
      if (alive) { setChannels(result.channels); setError(""); }
    }).catch((cause) => {
      if (alive) setError(cause instanceof Error ? cause.message : "채널 설정을 읽지 못했습니다.");
    });
    return () => { alive = false; };
  }, []);
  return <section className="editor-panel derived-panel" aria-label="플랫폼별 출고 준비 상태">
    <div className="section-heading"><div><span className="eyebrow">작업 {job.id}</span><h2>채널별로 어디까지 준비됐나요?</h2></div></div>
    <p className="muted">앱의 출고 묶음과 외부 플랫폼의 임시저장함은 다릅니다. 아래 준비 표시는 현재 파일·출고 승인 기록만 확인하며, 실제 플랫폼 전송 성공을 뜻하지 않습니다.</p>
    <p className="muted">제작물의 원고 언어: {sourceLanguage ? localeLabel(sourceLanguage) : "미확인 · 원고 재검수 필요"} · 다음 원고용 브리프: {localeLabel(job.brief?.language)}. 채널은 제작물에 연결된 원고 언어로 확인합니다.</p>
    {error ? <p className="notice error" role="alert">{error}</p> : !channels.length ? <p className="muted" role="status">등록 채널을 확인하고 있습니다.</p> : <div style={{ overflowX: "auto" }}>
      <table className="channel-table"><thead><tr><th scope="col">채널</th><th scope="col">현재 준비 범위 · 다음 행동</th></tr></thead>
        <tbody>{channels.map((row) => <tr key={row.key}><th scope="row">{row.label} · {localeLabel(row.locale)}</th><td>{["youtube", "instagram", "threads", "linkedin", "x", "tistory", "naver_blog"].includes(row.platform) && sourceChannelMismatch(job, row) || channelHandoffStatus(job, row.platform, row.key)}</td></tr>)}</tbody>
      </table>
    </div>}
    <p className="muted">YouTube만 현재 출고 승인② 뒤 별도 요청으로 비공개 업로드할 수 있습니다. 네이버·티스토리·Instagram·Threads·LinkedIn 등의 플랫폼 임시저장·예약·공개 게시 연동은 아직 없습니다. 메일·홍보 발송은 동의와 회차 승인③이 별도로 필요합니다.</p>
  </section>;
}
