"use client";

import { useCallback, useEffect, useRef, useState } from "react";
import { api } from "../lib/api";
import type { Channel, ChannelStagingSnapshot, Delivery as DeliveryRecord, Job } from "../lib/types";
import { canReconcile, studioUrl } from "../lib/settings";
import { localeLabel, youtubeChannels } from "../lib/channels";
import { deliveryRecordLabel, packetLanguage, requirePrivateDeliveryResult, requireStagingSnapshot, sourceChannelMismatch, stagingExternalLabel, stagingLocalLabel, youtubePreflight } from "../lib/delivery-readiness";
import { formatDate, safeArtifactUrl } from "../lib/workflow";
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
  const queuedDeliveryState=(job.tasks??[]).filter(t=>t.kind==='private_delivery').map(t=>t.id+':'+t.state).join('|');
  const ownerPending = records.some(record => record.state === "pending_owner");

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
    if (!ownerPending && !(job.tasks??[]).some(t=>t.kind==='private_delivery'&&['queued','running'].includes(t.state??''))) return;
    const timer=setInterval(()=>void load(),4_000);
    return ()=>clearInterval(timer);
  }, [load, job.release_approval?.version, queuedDeliveryState, ownerPending]);

  async function upload() {
    if (!readiness.ok || busy) return;
    const name = channel?.label ?? channelKey;
    if (!window.confirm(`승인된 영상을 ${name} 채널에 비공개(private)로 올립니다. 진행할까요?`)) return;
    await action("YouTube 비공개 업로드", async () => {
      const record = await api.deliverYoutube(job.id, channelKey);
      requirePrivateDeliveryResult(record, channelKey);
    }, "전달 요청을 확인했습니다. 아래 기록에서 PC 전달 대기와 실제 비공개 완료를 구분해 확인하세요.");
    await load();
  }

  async function reconcile(record: DeliveryRecord) {
    await action("업로드 대사", () => api.reconcileDelivery(job.id, record.id), "업로드 상태를 다시 확인했습니다.");
    await load();
  }

  const blocking = records.some((r) => ["created", "accepted", "unknown", "needs_review", "pending_owner"].includes(r.state));

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
              {channel.auth_location === "owner_pc" ? (channel.credentials_configured ? "본인 PC 인증 연결됨 · 로그인 정보는 PC에 보관" : "본인 PC 인증 실행기 연결 필요") : (channel.credentials_configured ? "자격 설정 있음 · 실제 OAuth 미검증" : `YOUTUBE_${channel.key.replace(/^youtube_/, "").toUpperCase()}_REFRESH_TOKEN 없음`)}
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

export function ChannelHandoffPanel({ job, busy, action }: { job: Job; busy: boolean; action: Action }) {
  const sourceLanguage = packetLanguage(job);
  const revision = JSON.stringify([job.id, job.source_hash, job.manifest?.hash, job.release_approval, job.offer_hash, job.updated_at, job.events?.[0]?.id, job.events?.at(-1)?.id]);
  const activeRevision = useRef(revision);
  activeRevision.current = revision;
  const [snapshot, setSnapshot] = useState<{ revision: string; data: ChannelStagingSnapshot }>();
  const [error, setError] = useState("");
  const [loading, setLoading] = useState(false);
  const alive = useRef(true);
  const ticket = useRef(0);
  const writing = useRef(false);
  const current = snapshot?.revision === revision ? snapshot.data : null;
  const load = useCallback(async () => {
    if (!alive.current || activeRevision.current !== revision) return;
    const request = ++ticket.current;
    setLoading(true);
    setError("");
    try {
      const data = await api.channelStaging(job.id);
      requireStagingSnapshot(data, job.id);
      if (alive.current && activeRevision.current === revision && request === ticket.current) setSnapshot({ revision, data });
    } catch (cause) {
      if (alive.current && activeRevision.current === revision && request === ticket.current) setError(cause instanceof Error ? cause.message : "배포대기 상태를 읽지 못했습니다.");
    } finally {
      if (alive.current && activeRevision.current === revision && request === ticket.current) setLoading(false);
    }
  }, [job.id, revision]);
  useEffect(() => {
    alive.current = true;
    setSnapshot(undefined);
    void load();
    return () => { alive.current = false; ticket.current++; };
  }, [load]);
  const canRecord = Boolean(current?.current_release && !current.recorded_current && !current.blockers.length && current.channels.some((row) => row.local_ready) && /^[a-f0-9]{64}$/.test(current.stage_hash));
  async function record() {
    if (busy || loading || writing.current || error || !current || !canRecord) return;
    writing.current = true;
    ticket.current++;
    try {
      await action("앱 배포대기 기록", async () => {
        const saved = await api.recordChannelStaging(job.id, current.stage_hash);
        requireStagingSnapshot(saved, job.id);
        if (!saved.recorded_current || !saved.recorded_at || saved.job_id !== job.id || saved.stage_hash !== current.stage_hash)
          throw new Error("앱 배포대기 기록의 판본·저장 결과를 확인하지 못했습니다. 상태를 다시 조회하세요.");
        return saved;
      }, "승인된 파일 판본의 배포대기 목록을 앱 장부에 기록했습니다. 외부 플랫폼에는 전송하지 않았습니다.");
      if (alive.current) await load();
    } finally {
      writing.current = false;
    }
  }
  return <section className="editor-panel derived-panel" aria-label="플랫폼별 출고 준비 상태">
    <div className="section-heading"><div><span className="eyebrow">작업 {job.id}</span><h2>채널별로 어디까지 준비됐나요?</h2></div></div>
    <p className="muted">앱의 배포대기 장부와 외부 플랫폼의 임시저장함은 다릅니다. 목록 기록은 승인된 파일·언어·출고 판본을 앱에 보존하며, 실제 전송·임시저장·공개 게시를 시작하지 않습니다. X는 요청에 따라 보류합니다.</p>
    <p className="muted">제작물의 원고 언어: {sourceLanguage ? localeLabel(sourceLanguage) : "미확인 · 원고 재검수 필요"} · 다음 원고용 브리프: {localeLabel(job.brief?.language)}. 채널은 제작물에 연결된 원고 언어로 확인합니다.</p>
    <div className="derived-actions">
      <button className="button secondary" type="button" disabled={busy || loading || !canRecord || Boolean(error)} onClick={() => void record()}>앱 배포대기 장부에 기록</button>
      <button className="button text" type="button" disabled={busy || loading} onClick={() => void load()}>상태 다시 확인</button>
    </div>
    {error && <p className="notice error" role="alert">{error}</p>}
    {loading && <p className="muted" role="status">현재 출고 판본·파일·채널 조건을 확인하고 있습니다.</p>}
    {current && <>
      <p className="muted">{current.recorded_current ? `현재 판본의 앱 장부 기록 있음 · ${formatDate(current.recorded_at ?? undefined, true)}` : "현재 판본의 앱 배포대기 기록은 아직 없습니다."} · 출고 판본 {current.manifest_hash?.slice(0, 12) ?? "없음"}</p>
      {current.blockers.length > 0 && <ul className="derived-issues">{current.blockers.map((reason) => <li key={reason}>{reason}</li>)}</ul>}
      <div style={{ overflowX: "auto", maxWidth: "100%", minWidth: 0 }} tabIndex={0} role="region" aria-label="채널별 배포대기 상태, 작은 화면에서는 채널별 카드로 표시합니다">
        <table className="channel-table staging-table" role="table" aria-label="채널별 준비와 실제 플랫폼 기록"><thead role="rowgroup"><tr role="row"><th scope="col" role="columnheader">채널</th><th scope="col" role="columnheader">앱 내부 준비</th><th scope="col" role="columnheader">실제 플랫폼 기록</th></tr></thead>
          <tbody role="rowgroup">{current.channels.map((row) => <tr key={row.channel_key} role="row">
            <th scope="row" role="rowheader">{row.label} · {localeLabel(row.locale)}</th>
            <td role="cell"><span className="staging-field-label" aria-hidden="true">앱 내부 준비</span><strong>{stagingLocalLabel(row)}</strong>
              {row.blockers.length > 0 && <ul>{row.blockers.map((reason) => <li key={reason}>{reason}</li>)}</ul>}
              <details><summary>필수·확인 파일 {row.files.length}개</summary>
                <p>필요: {row.required_files.join(", ") || "없음"}</p>
                <ul>{row.files.map((file) => {
                  const url = file.url && safeArtifactUrl(file.url);
                  return <li key={`${file.name}-${file.sha256}`} style={{ overflowWrap: "anywhere" }}>{url ? <a href={url} target="_blank" rel="noopener noreferrer">{file.name}</a> : file.name} · 해시 {file.sha256.slice(0, 12)}</li>;
                })}</ul>
              </details>
            </td>
            <td role="cell"><span className="staging-field-label" aria-hidden="true">실제 플랫폼 기록</span><strong>{stagingExternalLabel(row)}</strong>
              {row.external_id && <p style={{ overflowWrap: "anywhere" }}>외부 ID: {row.external_id}</p>}
              {row.platform === "youtube" && row.external_id && <p>업로드 상태: {row.upload_status || "미확인"} · 영상 처리: {row.processing_status || "미확인"}. 비공개 확인 기록은 재생 완료를 뜻하지 않습니다.</p>}
              {row.platform === "youtube" && studioUrl(row.external_id) && <a href={studioUrl(row.external_id)!} target="_blank" rel="noopener noreferrer">Studio에서 실제 상태 확인 ↗</a>}
              {row.can_upload_private && <p>아래 YouTube 영역에서 비공개 업로드를 별도로 요청할 수 있습니다.</p>}
            </td>
          </tr>)}</tbody>
        </table>
      </div>
      {current.notes.map((note) => <p className="muted" key={note}>{note}</p>)}
    </>}
    <p className="muted">YouTube만 현재 출고 승인② 뒤 별도 요청으로 비공개 업로드할 수 있습니다. 네이버·티스토리·Instagram·Threads·LinkedIn 등의 플랫폼 임시저장·예약·공개 게시 연동은 아직 없습니다. 메일·홍보 발송은 동의와 회차 승인③이 별도로 필요합니다.</p>
  </section>;
}
