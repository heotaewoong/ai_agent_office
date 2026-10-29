"use client";

import { useCallback, useEffect, useState } from "react";
import { api } from "../lib/api";
import { deliveryLabel, localeLabel, validChannelId } from "../lib/channels";
import type { Action, Channel } from "../lib/types";
import { Icon } from "./icons";

/** 채널 레지스트리. 공개 주소·계정 ID·발행 허용만 다루며 토큰은 화면에 오지 않습니다. */
export function ChannelsPanel({ busy, action }: { busy: boolean; action: Action }) {
  const [channels, setChannels] = useState<Channel[]>([]);
  const [loadError, setLoadError] = useState("");
  const [accounts, setAccounts] = useState<Record<string, string>>({});

  const load = useCallback(async () => {
    try {
      const result = await api.channels();
      setChannels(result.channels);
      setAccounts(Object.fromEntries(result.channels.map((c) => [c.key, c.external_account_id ?? ""])));
      setLoadError("");
    } catch (cause) {
      setLoadError(cause instanceof Error ? cause.message : "채널 목록을 불러오지 못했습니다.");
    }
  }, []);

  useEffect(() => {
    void load();
  }, [load]);

  async function saveAccount(channel: Channel) {
    const value = (accounts[channel.key] ?? "").trim();
    if (!validChannelId(value)) return;
    const ok = await action("채널 ID 저장", () => api.updateChannel(channel.key, { external_account_id: value }), `${channel.label}의 채널 ID를 저장했습니다.`);
    if (ok === true) await load();
  }

  async function toggle(channel: Channel, enabled: boolean) {
    const ok = await action(
      enabled ? "발행 허용" : "발행 중지",
      () => api.updateChannel(channel.key, { publication_enabled: enabled }),
      enabled ? `${channel.label} 발행을 허용했습니다. 실제 업로드는 출고 승인② 뒤 운영자가 요청할 때만 일어납니다.` : `${channel.label} 발행을 껐습니다.`,
    );
    if (ok === true) await load();
  }

  return (
    <section className="settings-card" aria-label="채널">
      <h2>채널</h2>
      <p className="settings-help">
        오너가 준 공개 주소와 계정 ID만 적습니다. 주소 존재·소유권·발행 권한·실제 게시 성공은 각각 별개이며, 토큰은 서버 환경 파일에만 있고 화면에 표시하거나 입력받지 않습니다. 발행 허용은 기본으로 꺼져 있습니다.
      </p>
      {loadError && <p className="field-error">{loadError}</p>}
      {channels.length > 0 && (
        <div className="channel-table-wrap">
          <table className="channel-table">
            <thead>
              <tr>
                <th>채널</th>
                <th>플랫폼</th>
                <th>언어</th>
                <th>전달</th>
                <th>공개 주소</th>
                <th>계정 ID</th>
                <th>발행 허용</th>
                <th>자격</th>
              </tr>
            </thead>
            <tbody>
              {channels.map((channel) => {
                const draft = accounts[channel.key] ?? "";
                const valid = validChannelId(draft);
                const changed = draft.trim() !== (channel.external_account_id ?? "");
                const editable = channel.platform === "youtube";
                return (
                  <tr key={channel.key}>
                    <td>
                      <strong>{channel.label}</strong>
                      <small>{channel.key}</small>
                    </td>
                    <td>{channel.platform}</td>
                    <td>{localeLabel(channel.locale)}</td>
                    <td>{deliveryLabel(channel.delivery)}</td>
                    <td>
                      {channel.public_url ? (
                        <a href={channel.public_url} target="_blank" rel="noopener noreferrer">
                          열기 <Icon name="external" size={12} />
                        </a>
                      ) : (
                        <span className="muted">미등록</span>
                      )}
                    </td>
                    <td>
                      {editable ? (
                        <div className="channel-account">
                          <input
                            aria-label={`${channel.label} 채널 ID`}
                            value={draft}
                            placeholder="UC로 시작하는 24자"
                            aria-invalid={!valid}
                            disabled={busy}
                            onChange={(e) => setAccounts((a) => ({ ...a, [channel.key]: e.target.value }))}
                          />
                          <button className="button secondary" type="button" disabled={busy || !valid || !changed} onClick={() => void saveAccount(channel)}>
                            저장
                          </button>
                          {!valid && <span className="field-error">UC로 시작하고 영문·숫자·-·_ 22자가 이어지는 형식이어야 합니다.</span>}
                        </div>
                      ) : (
                        <span className="muted">{channel.external_account_id || "-"}</span>
                      )}
                    </td>
                    <td>
                      <label className="channel-toggle">
                        <input type="checkbox" checked={channel.publication_enabled} disabled={busy} onChange={(e) => void toggle(channel, e.target.checked)} />
                        {channel.publication_enabled ? "허용" : "꺼짐"}
                      </label>
                    </td>
                    <td>
                      {channel.delivery === "youtube_api" ? (
                        <span className={channel.credentials_configured ? "cred ok" : "cred missing"}>
                          <Icon name={channel.credentials_configured ? "check" : "alert"} size={13} />
                          {channel.credentials_configured ? "연결됨" : "토큰 없음"}
                        </span>
                      ) : (
                        <span className="muted">해당 없음</span>
                      )}
                    </td>
                  </tr>
                );
              })}
            </tbody>
          </table>
        </div>
      )}
    </section>
  );
}
