"use client";

import { useCallback, useEffect, useId, useState } from "react";
import type { FormEvent } from "react";
import { api } from "../lib/api";
import { leadSourceLabel, validEmail } from "../lib/leads";
import { formatDate } from "../lib/workflow";
import type { Action, Lead, LeadSummary } from "../lib/types";
import { Icon } from "./icons";

const SOURCES = ["homepage", "youtube", "blog", "newsletter", "manual", "other"];
const EMPTY = { email: "", magnet_key: "", source: "manual", consent_version: "v1", consent_text: "뉴스레터와 자료 안내 메일 수신에 동의합니다." };

/** 리드마그넷 동의 장부. 이메일 원문은 서버 장부에만 있고 화면에는 마스킹된 값만 옵니다. */
export function LeadsPanel({ busy, action }: { busy: boolean; action: Action }) {
  const uid = useId();
  const [leads, setLeads] = useState<Lead[]>([]);
  const [summary, setSummary] = useState<LeadSummary | null>(null);
  const [loadError, setLoadError] = useState("");
  const [form, setForm] = useState<Record<string, string>>(EMPTY);
  const [error, setError] = useState("");

  const load = useCallback(async () => {
    try {
      const [list, sum] = await Promise.all([api.leads(), api.leadSummary()]);
      setLeads(list.leads);
      setSummary(sum);
      setLoadError("");
    } catch (cause) {
      setLoadError(cause instanceof Error ? cause.message : "동의 장부를 불러오지 못했습니다.");
    }
  }, []);

  useEffect(() => {
    void load();
  }, [load]);

  async function run(label: string, execute: () => Promise<unknown>, success: string) {
    const ok = await action(label, execute, success);
    if (ok === true) await load();
  }

  async function submit(event: FormEvent) {
    event.preventDefault();
    if (!validEmail(form.email)) {
      setError("이메일 형식을 확인하세요.");
      return;
    }
    if (!form.magnet_key.trim()) {
      setError("리드마그넷 키를 입력하세요. 예: exam-d30-planner");
      return;
    }
    if (!form.consent_version.trim() || !form.consent_text.trim()) {
      setError("동의 문구와 버전을 입력하세요.");
      return;
    }
    setError("");
    const ok = await action(
      "리드 등록",
      () =>
        api.addLead({
          email: form.email.trim(),
          magnet_key: form.magnet_key.trim(),
          source: form.source,
          consent_version: form.consent_version.trim(),
          consent_text: form.consent_text.trim(),
        }),
      "리드를 동의 장부에 기록했습니다. 자료 전달은 수동이며 보낸 뒤 '전달 완료'로 표시하세요.",
    );
    if (ok === true) {
      setForm((f) => ({ ...f, email: "" }));
      await load();
    }
  }

  const set = (key: string, value: string) => {
    setError("");
    setForm((f) => ({ ...f, [key]: value }));
  };
  const emailOk = form.email.trim() === "" || validEmail(form.email);

  return (
    <section className="settings-card leads-panel" aria-label="리드마그넷 동의 장부">
      <h2>리드마그넷 동의 장부</h2>
      <p className="settings-help">
        무료 자료를 신청한 독자의 이메일과 동의 기록입니다. 이메일 원문은 서버의 장부에만 있고 화면·내보내기에는 마스킹된 값만 나옵니다. 자료 전달과 메일 발송은 오너가 직접 하며, 이 화면은 기록만 합니다. 철회는 되돌리지 않습니다.
      </p>
      {summary && (
        <dl className="budget-grid">
          <div>
            <dt>전체</dt>
            <dd>{summary.total}</dd>
          </div>
          <div>
            <dt>동의 유지</dt>
            <dd>{summary.consented}</dd>
          </div>
          <div>
            <dt>철회</dt>
            <dd>{summary.withdrawn}</dd>
          </div>
          {Object.entries(summary.by_magnet).map(([key, count]) => (
            <div key={`m-${key}`}>
              <dt>자료 {key}</dt>
              <dd>{count}</dd>
            </div>
          ))}
          {Object.entries(summary.by_source).map(([key, count]) => (
            <div key={`s-${key}`}>
              <dt>출처 {leadSourceLabel(key)}</dt>
              <dd>{count}</dd>
            </div>
          ))}
        </dl>
      )}
      {loadError && <p className="field-error">{loadError}</p>}
      <details>
        <summary>수동 등록 (오프라인·DM으로 받은 신청)</summary>
        <form onSubmit={(e) => void submit(e)}>
          <fieldset disabled={busy} style={{ border: 0, padding: 0, margin: 0 }}>
            <div className="editor-fields">
              <div>
                <label htmlFor={`${uid}-email`}>이메일</label>
                <input id={`${uid}-email`} type="email" value={form.email} aria-invalid={!emailOk} placeholder="reader@example.com" onChange={(e) => set("email", e.target.value)} />
              </div>
              <div>
                <label htmlFor={`${uid}-magnet`}>리드마그넷 키</label>
                <input id={`${uid}-magnet`} value={form.magnet_key} placeholder="exam-d30-planner" maxLength={80} onChange={(e) => set("magnet_key", e.target.value)} />
              </div>
              <div>
                <label htmlFor={`${uid}-source`}>출처</label>
                <select id={`${uid}-source`} value={form.source} onChange={(e) => set("source", e.target.value)}>
                  {SOURCES.map((s) => (
                    <option key={s} value={s}>
                      {leadSourceLabel(s)}
                    </option>
                  ))}
                </select>
              </div>
              <div>
                <label htmlFor={`${uid}-version`}>동의 문구 버전</label>
                <input id={`${uid}-version`} value={form.consent_version} maxLength={40} onChange={(e) => set("consent_version", e.target.value)} />
              </div>
              <label htmlFor={`${uid}-consent`}>동의 문구 (독자가 본 그대로)</label>
              <textarea id={`${uid}-consent`} rows={2} value={form.consent_text} maxLength={1000} onChange={(e) => set("consent_text", e.target.value)} />
            </div>
          </fieldset>
          {error && (
            <p className="notice error" role="alert">
              {error}
            </p>
          )}
          <button className="button primary" type="submit" disabled={busy || !validEmail(form.email)}>
            동의 장부에 기록
          </button>
        </form>
      </details>
      {leads.length > 0 && (
        <div className="channel-table-wrap">
          <table className="channel-table">
            <thead>
              <tr>
                <th>신청</th>
                <th>이메일(마스킹)</th>
                <th>자료</th>
                <th>출처</th>
                <th>동의</th>
                <th>전달</th>
                <th>조치</th>
              </tr>
            </thead>
            <tbody>
              {leads.map((lead) => {
                const withdrawn = Boolean(lead.consent.withdrawn_at);
                return (
                  <tr key={lead.id} className={withdrawn ? "withdrawn" : ""}>
                    <td>{formatDate(lead.created_at, true)}</td>
                    <td>
                      <code>{lead.email_masked}</code>
                    </td>
                    <td>{lead.magnet_key}</td>
                    <td>{leadSourceLabel(lead.source)}</td>
                    <td>
                      {withdrawn ? (
                        <span className="cred missing">
                          <Icon name="alert" size={13} />
                          철회 {formatDate(lead.consent.withdrawn_at ?? undefined, true)}
                        </span>
                      ) : (
                        <span className="cred ok">
                          <Icon name="check" size={13} />
                          {lead.consent.version} · {formatDate(lead.consent.granted_at, true)}
                        </span>
                      )}
                    </td>
                    <td>{lead.delivery.state === "sent_manual" ? `전달 완료 ${formatDate(lead.delivery.sent_at ?? undefined, true)}` : "대기"}</td>
                    <td>
                      <div className="derived-actions">
                        {!withdrawn && lead.delivery.state === "pending" && (
                          <button className="button secondary small" type="button" disabled={busy} onClick={() => void run("전달 완료 표시", () => api.markLeadSent(lead.id), "자료를 직접 보낸 것으로 표시했습니다.")}>
                            전달 완료
                          </button>
                        )}
                        {!withdrawn && (
                          <button
                            className="button text small"
                            type="button"
                            disabled={busy}
                            onClick={() => {
                              if (!window.confirm("동의를 철회로 기록합니다. 되돌릴 수 없습니다. 계속할까요?")) return;
                              void run("동의 철회", () => api.withdrawLead(lead.id), "동의 철회를 기록했습니다. 다음 회차부터 수신자에서 빠집니다.");
                            }}
                          >
                            철회
                          </button>
                        )}
                      </div>
                    </td>
                  </tr>
                );
              })}
            </tbody>
          </table>
        </div>
      )}
      {leads.length === 0 && !loadError && <p className="muted">기록된 리드가 없습니다.</p>}
    </section>
  );
}
