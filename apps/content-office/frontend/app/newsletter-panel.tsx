"use client";

import { useCallback, useEffect, useId, useState } from "react";
import { api } from "../lib/api";
import { defaultIssueKey, newsletterStateLabel, validIssueKey } from "../lib/newsletter";
import { formatDate, sourceApproved } from "../lib/workflow";
import type { Action, Job, NewsletterIssue } from "../lib/types";
import { Icon } from "./icons";

const TONES: Record<string, string> = { draft: "orange", approved: "green", rejected: "red", sent_manual: "neutral" };

/** 뉴스레터 회차 ③. 이 화면은 메일을 보내지 않습니다. 승인된 회차를 내보내 오너가 메일러에서 직접 보내고, 보낸 뒤 "발송 완료"로 표시합니다. */
export function NewsletterPanel({ job, busy, action }: { job: Job; busy: boolean; action: Action }) {
  const uid = useId();
  const [issues, setIssues] = useState<NewsletterIssue[]>([]);
  const [loadError, setLoadError] = useState("");
  const [issueKey, setIssueKey] = useState(() => defaultIssueKey(new Date()));
  const [subject, setSubject] = useState(job.title ?? "");
  const [notes, setNotes] = useState<Record<string, string>>({});
  const [copied, setCopied] = useState("");
  const approved = sourceApproved(job.state);

  const load = useCallback(async () => {
    try {
      setIssues((await api.newsletters()).issues);
      setLoadError("");
    } catch (cause) {
      setLoadError(cause instanceof Error ? cause.message : "회차 목록을 불러오지 못했습니다.");
    }
  }, []);

  // ② 출고 승인 뒤 서버가 자동으로 만든 초안도 작업 새로고침에 맞춰 다시 읽습니다.
  useEffect(() => {
    void load();
  }, [load, job.updated_at, job.state, job.release_approval?.version]);
  const releaseApproved = job.release_approval?.decision === "approved";

  async function run(label: string, execute: () => Promise<unknown>, success: string) {
    const ok = await action(label, execute, success);
    if (ok === true) await load();
  }

  function build() {
    const key = issueKey.trim();
    if (!validIssueKey(key) || !subject.trim()) return;
    void run("회차 만들기", () => api.buildNewsletter(job.id, { issue_key: key, subject: subject.trim() }), `회차 ${key} 초안을 만들었습니다. 읽고 ③ 회차 승인을 결정하세요.`);
  }

  async function copyMarkdown(issue: NewsletterIssue) {
    try {
      await navigator.clipboard.writeText(issue.markdown);
      setCopied(issue.id);
    } catch {
      setCopied("");
    }
  }

  const mine = issues.filter((i) => i.job_id === job.id);
  const others = issues.length - mine.length;
  const keyValid = validIssueKey(issueKey);

  return (
    <section className="youtube-panel newsletter-panel" aria-label="뉴스레터 회차">
      <div className="youtube-head">
        <div>
          <h3>
            <Icon name="file" size={17} />
            뉴스레터 회차 · ③
          </h3>
          <p className="not-ready">이 화면은 메일을 보내지 않습니다. ③ 승인은 회차 내용의 승인이며, 발송은 오너가 메일러에서 직접 합니다. 수신자 수는 동의 장부의 동의 유지 리드만 셉니다.</p>
        </div>
      </div>
      <div className="newsletter-build">
        <label>
          회차 키
          <input id={`${uid}-key`} value={issueKey} aria-invalid={!keyValid} disabled={busy} onChange={(e) => setIssueKey(e.target.value)} />
        </label>
        <label>
          제목
          <input id={`${uid}-subject`} value={subject} maxLength={200} disabled={busy} onChange={(e) => setSubject(e.target.value)} />
        </label>
        <button className="button primary" type="button" disabled={busy || !approved || !keyValid || !subject.trim()} onClick={build}>
          이 작업으로 회차 만들기
        </button>
      </div>
      {!keyValid && <p className="field-error">회차 키는 2026-10-w5 형식입니다.</p>}
      {!approved && <p className="muted">① 원고 승인 뒤에 회차를 만들 수 있습니다.</p>}
      {loadError && <p className="field-error">{loadError}</p>}
      {mine.length === 0 && !loadError && <p className="muted">이 작업으로 만든 회차가 아직 없습니다.{others > 0 ? ` 다른 작업의 회차 ${others}개는 운영 기록에서 확인하세요.` : ""}</p>}
      {mine.length > 0 && (
        <ul className="delivery-list">
          {mine.map((issue) => {
            const reviewable = issue.state === "draft" || issue.state === "rejected";
            const note = notes[issue.id] ?? "";
            return (
              <li key={issue.id} className={`delivery-item newsletter-item state-${issue.state}`}>
                <div>
                  <span className={`badge ${TONES[issue.state] ?? "neutral"}`}>{newsletterStateLabel(issue.state)}</span>
                  {issue.state === "draft" && releaseApproved && <span className="badge neutral">② 출고 승인 뒤 만든 초안 · 읽고 ③을 결정하세요</span>}
                  <strong>
                    {issue.issue_key} · {issue.subject}
                  </strong>
                  <small>
                    수신자 {issue.recipient_count}명 · 만든 시각 {formatDate(issue.built_at, true)} · 버전 {issue.hash.slice(0, 8)} · 수신자 묶음 {issue.recipients_hash.slice(0, 8)}
                    {issue.approval ? ` · ${issue.approval.stage} ${issue.approval.decision} (${issue.approval.actor}, ${formatDate(issue.approval.at, true)})${issue.approval.note ? ` · ${issue.approval.note}` : ""}` : ""}
                    {issue.sent_at ? ` · 발송 표시 ${formatDate(issue.sent_at, true)}` : ""}
                  </small>
                  <details>
                    <summary>본문 Markdown 보기</summary>
                    <pre className="newsletter-markdown">{issue.markdown}</pre>
                  </details>
                </div>
                <div className="newsletter-actions">
                  {reviewable && (
                    <div className="newsletter-review" role="group" aria-label="③ 회차 승인">
                      <textarea rows={2} placeholder="③ 회차 승인 메모 (선택)" value={note} disabled={busy} onChange={(e) => setNotes((n) => ({ ...n, [issue.id]: e.target.value }))} />
                      <div className="derived-actions">
                        <button className="button primary small" type="button" disabled={busy} onClick={() => void run("③ 회차 승인", () => api.reviewNewsletter(issue.id, "approve", note.trim()), "③ 회차를 승인했습니다. 발송은 하지 않았습니다. 내보내서 메일러로 보내세요.")}>
                          <Icon name="check" size={13} />③ 회차 승인
                        </button>
                        <button className="button text small" type="button" disabled={busy} onClick={() => void run("③ 회차 반려", () => api.reviewNewsletter(issue.id, "reject", note.trim()), "회차를 반려했습니다.")}>
                          반려
                        </button>
                      </div>
                    </div>
                  )}
                  <div className="derived-actions">
                    {issue.state !== "sent_manual" && (
                      <button className="button secondary small" type="button" disabled={busy} onClick={() => void run("회차 다시 만들기", () => api.rebuildNewsletter(issue.id), "최신 동의 장부로 회차를 다시 만들었습니다. 다시 읽고 ③ 승인을 결정하세요.")}>
                        최신 동의로 다시 만들기
                      </button>
                    )}
                    <a className="button secondary small" href={api.newsletterExportUrl(issue.id)} download={`${issue.issue_key}.md`}>
                      <Icon name="download" size={13} />
                      내보내기
                    </a>
                    <button className="button text small" type="button" onClick={() => void copyMarkdown(issue)}>
                      {copied === issue.id ? "복사됨" : "Markdown 복사"}
                    </button>
                    {issue.state === "approved" && (
                      <button
                        className="button secondary small"
                        type="button"
                        disabled={busy}
                        onClick={() => {
                          if (!window.confirm("메일러에서 실제로 보낸 뒤에만 표시하세요. 발송 완료로 기록할까요?")) return;
                          void run("발송 완료 표시", () => api.markNewsletterSent(issue.id), "발송 완료로 표시했습니다.");
                        }}
                      >
                        발송 완료로 표시
                      </button>
                    )}
                  </div>
                </div>
              </li>
            );
          })}
        </ul>
      )}
    </section>
  );
}
