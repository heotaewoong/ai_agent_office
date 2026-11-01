"use client";

import { useCallback, useEffect, useState } from "react";
import { api } from "../lib/api";
import { deliveryLabel, localeLabel, validChannelId } from "../lib/channels";
import { connectBlockedReason, connectionLabel, type YoutubeOAuthStatus } from "../lib/youtube-oauth";
import type { Action, Channel } from "../lib/types";
import { Icon } from "./icons";

/** 채널 레지스트리. 공개 주소·계정 ID·발행 허용만 다루며 토큰은 화면에 오지 않습니다. */
export function ChannelsPanel({ busy, action }: { busy: boolean; action: Action }) {
  const [channels, setChannels] = useState<Channel[]>([]);
  const [loadError, setLoadError] = useState("");
  const [accounts, setAccounts] = useState<Record<string, string>>({});
  const [oauth, setOauth] = useState<YoutubeOAuthStatus | null>(null);
  const [oauthError, setOauthError] = useState("");
  const [connecting, setConnecting] = useState("");

  const load = useCallback(async () => {
    try {
      const result = await api.channels();
      setChannels(result.channels);
      setAccounts(Object.fromEntries(result.channels.map((c) => [c.key, c.external_account_id ?? ""])));
      setLoadError("");
    } catch (cause) {
      setLoadError(cause instanceof Error ? cause.message : "채널 목록을 불러오지 못했습니다.");
    }
    try {
      setOauth(await api.youtubeOAuthStatus());
    } catch {
      setOauth(null);
    }
  }, []);

  const blocked = connectBlockedReason(oauth);

  /** Google 로그인 화면으로 이동합니다. 돌아오면 첫 화면이 결과를 알립니다. 연결은 발행이 아닙니다. */
  async function connect(channel: Channel) {
    setConnecting(channel.key);
    setOauthError("");
    try {
      const { authorize_url } = await api.youtubeOAuthStart(channel.key);
      if (!authorize_url.startsWith("https://accounts.google.com/")) throw new Error("예상하지 못한 로그인 주소입니다. 연결을 중단했습니다.");
      window.location.assign(authorize_url);
    } catch (cause) {
      setOauthError(cause instanceof Error ? cause.message : "YouTube 연결을 시작하지 못했습니다.");
      setConnecting("");
    }
  }

  async function disconnect(channel: Channel) {
    const ok = await action("YouTube 연결 해제", () => api.youtubeOAuthDisconnect(channel.key), `${channel.label}의 로그인 연결 토큰을 서버 비밀 파일에서 지웠습니다. 실행 환경 파일의 토큰과 등록된 채널 ID는 그대로입니다.`);
    if (ok === true) await load();
  }

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
        오너가 준 공개 주소와 계정 ID만 적습니다. 주소 등록·로그인 연결·파일 준비·플랫폼에 실제 저장된 상태는 각각 따로 확인합니다. 비밀번호와 토큰은 이 화면에서 입력받거나 표시하지 않습니다.
      </p>
      {loadError && <p className="field-error">{loadError}</p>}
      <p className="settings-help">
        {oauth?.auth_location === "owner_pc" ? "현재는 본인 PC 전용 인증입니다. 로그인 정보는 Windows 계정으로 암호화해 PC에 보관하고, 서버에는 최근 연결 여부만 보냅니다. 연결 확인이 만료되면 PC 실행기를 다시 확인하세요. 서버 관리자가 로그인 정보를 등록하는 방식이 아닙니다." : "YouTube 연결은 채널 소유 계정으로 로그인해 서버의 분리된 비밀 파일에 토큰을 저장하는 방식입니다."}
        {" "}기존 출고 전송은 승인② 뒤 YouTube 비공개로만 진행합니다. 원고 승인①에서 별도로 고른 초안은 Windows 확장 실행기로 전달하며, 웹 채널은 실제 계정의 저장·재열기 검증 후에만 자동 처리합니다. 로그인이나 파일 준비만으로 플랫폼 저장 완료가 되지 않습니다.
        {oauth?.redirect_uri && (
          <>
            {" "}Google Cloud OAuth 클라이언트의 승인된 리디렉션 URI: <code>{oauth.redirect_uri}</code>
          </>
        )}
      </p>
      {blocked && <p className="field-error">{blocked}</p>}
      {oauthError && <p className="field-error" role="alert">{oauthError}</p>}
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
                const oauthEntry = oauth?.channels.find((entry) => entry.key === channel.key);
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
                        <div className="channel-account">
                          <span className={channel.credentials_configured ? "cred ok" : "cred missing"}>
                            <Icon name={channel.credentials_configured ? "check" : "alert"} size={13} />
                            {oauth ? connectionLabel(oauthEntry) : channel.credentials_configured ? "연결됨" : "토큰 없음"}
                          </span>
                          <button
                            className="button secondary"
                            type="button"
                            disabled={busy || Boolean(connecting) || Boolean(blocked) || oauthEntry?.source === "env"}
                            title={oauthEntry?.source === "env" ? "실행 환경 파일의 토큰이 우선합니다. 로그인 연결을 쓰려면 환경 파일에서 이 채널의 토큰을 지우세요." : (blocked ?? undefined)}
                            onClick={() => void connect(channel)}
                          >
                            {connecting === channel.key ? "Google로 이동 중…" : oauthEntry?.source === "file" ? "다시 연결" : "YouTube 연결"}
                          </button>
                          {oauthEntry?.file_stored && (
                            <button className="button text" type="button" disabled={busy || Boolean(connecting)} onClick={() => void disconnect(channel)}>
                              연결 해제
                            </button>
                          )}
                        </div>
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
