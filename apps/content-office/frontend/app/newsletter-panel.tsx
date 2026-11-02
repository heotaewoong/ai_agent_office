"use client";

import { useCallback, useEffect, useId, useRef, useState } from "react";
import { api } from "../lib/api";
import { defaultIssueKey, newsletterStateLabel, validIssueKey } from "../lib/newsletter";
import { approvalIsCurrent, formatDate } from "../lib/workflow";
import type { Action, Job, NewsletterIssue, NewsletterEditorial, NewsletterDestination, NewsletterConnection, NewsletterInputs, NewsletterPrepared } from "../lib/types";
import { Icon } from "./icons";

const TONES: Record<string, string> = { draft: "orange", approved: "green", rejected: "red", sent_manual: "neutral" };
const TARGETS: { key: NewsletterDestination; label: string }[] = [{ key: "email", label: "구독자 이메일" }, { key: "slack", label: "Slack" }, { key: "website", label: "heobrain.kr" }];

/** 뉴스레터 회차 ③. 이 화면은 메일을 보내지 않습니다. 승인된 회차를 내보내 오너가 메일러에서 직접 보내고, 보낸 뒤 "발송 완료"로 표시합니다. */
export function NewsletterPanel({ job, busy, action }: { job: Job; busy: boolean; action: Action }) {
  const uid = useId();
  const [issues, setIssues] = useState<NewsletterIssue[]>([]);
  const [loadError, setLoadError] = useState("");
  const [issueKey, setIssueKey] = useState(() => defaultIssueKey(new Date()));
  const [subject, setSubject] = useState(job.title ?? "");
  const [notes, setNotes] = useState<Record<string, string>>({});
  const [copied, setCopied] = useState("");
  const [kind, setKind] = useState<NewsletterEditorial["kind"]>("briefing");
  const [related, setRelated] = useState<string[]>([]);
  const [targets, setTargets] = useState<NewsletterDestination[]>(["email", "slack", "website"]);
  const [inputs, setInputs] = useState<NewsletterInputs | null>(null);
  const [connections, setConnections] = useState<NewsletterConnection[]>([]);
  const [inputError, setInputError] = useState("");
  const loadInputs = useCallback(async () => {
    try {
      const [options, status] = await Promise.all([api.newsletterInputs(), api.newsletterConnections()]);
      setInputs(options); setConnections(status.destinations); setInputError("");
    } catch (error) { setInputError(error instanceof Error ? error.message : "출처·연결 설정을 불러오지 못했습니다."); }
  }, []);
  useEffect(() => { void loadInputs(); }, [loadInputs]);

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
  const releaseApproved = job.release_approval?.decision === "approved"
    && approvalIsCurrent(job.release_approval.version, job.manifest?.hash)
    && approvalIsCurrent(job.manifest?.source_hash, job.source_hash);

  async function run(label: string, execute: () => Promise<unknown>, success: string) {
    const ok = await action(label, execute, success);
    if (ok === true) await load();
  }

  function build() {
    const key = issueKey.trim();
    if (!validIssueKey(key) || !subject.trim() || !targets.length || related.length > 7) return;
    void run("회차 만들기", () => api.buildNewsletter(job.id, { issue_key: key, subject: subject.trim(), editorial: { kind, related_job_ids: related, destinations: targets } }), `회차 ${key} 초안을 만들었습니다. 읽고 ③ 회차 승인을 결정하세요.`);
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
          <p className="not-ready">여러 출고 원고로 회차를 만들고 이메일·Slack·웹사이트 초안을 함께 검토합니다. ③ 승인과 전달 준비는 실제 발송·게시를 실행하지 않습니다. 이메일 수신자는 뉴스레터 동의가 있고 철회하지 않은 주소만 중복 없이 포함하며, 자료 전달만 동의한 기록은 제외합니다.</p>
        </div>
      </div>
      <div className="newsletter-build">
        <label>
          회차 키
          <input id={`${uid}-key`} value={issueKey} aria-invalid={!keyValid} disabled={busy} onChange={(e) => setIssueKey(e.target.value)} />
        </label>
        <label>
          제목
          <input id={`${uid}-subject`} value={subject} maxLength={150} disabled={busy} onChange={(e) => setSubject(e.target.value)} />
        </label>
        <label>회차 목적<select value={kind} disabled={busy} onChange={event => setKind(event.target.value as NewsletterEditorial["kind"])}><option value="briefing">AI 빠른 소식</option><option value="analysis">AI 심층 큐레이션</option><option value="updates">HeoBrain 상품·서비스 소식</option></select></label>
        <button className="button primary" type="button" disabled={busy || !releaseApproved || !job.release_approval?.outputs?.includes("blog") || !keyValid || !subject.trim() || !targets.length || related.length > 7 || !inputs} onClick={build}>
          이 작업으로 회차 만들기
        </button>
      </div>
      <div className="newsletter-options">
        <fieldset><legend>함께 실을 출고 원고</legend><p className="muted">현재 작업을 포함해 최대 8개입니다. {inputs ? `등록된 정보원 ${inputs.sources.filter(source => source.segment === "ai").length}개에서 AI 후보를 수집합니다.` : "출처·작업 목록을 확인하고 있습니다."} <a href="/news">뉴스 후보 검토</a></p>
          {inputs?.released_jobs.filter(item => item.id !== job.id).map(item => <label className="newsletter-option" key={item.id}><input type="checkbox" aria-label={`함께 실을 원고 · ${item.title}`} checked={related.includes(item.id)} disabled={busy || (!related.includes(item.id) && related.length >= 7)} onChange={event => setRelated(previous => event.target.checked ? [...previous, item.id] : previous.filter(id => id !== item.id))} /><span>{item.title}</span></label>)}
          {inputs && !inputs.released_jobs.some(item => item.id !== job.id) && <p className="muted">추가할 블로그 출고 승인 원고가 없습니다. 현재 원고로 만들 수 있습니다.</p>}
        </fieldset>
        <fieldset><legend>전달 목적지 · 복수 선택</legend>{TARGETS.map(target => <label className="newsletter-option" key={target.key}><input type="checkbox" aria-label={`전달 목적지 · ${target.label}`} checked={targets.includes(target.key)} disabled={busy} onChange={event => setTargets(previous => event.target.checked ? TARGETS.map(item => item.key).filter(key => key === target.key || previous.includes(key)) : previous.filter(key => key !== target.key))} /><span>{target.label}</span></label>)}
          {!targets.length && <p className="field-error">전달 목적지를 하나 이상 선택하세요.</p>}
        </fieldset>
      </div>
      {inputError && <p className="field-error" role="alert">{inputError} <button type="button" className="button text small" onClick={() => void loadInputs()}>출처·연결 다시 불러오기</button></p>}
      {!!connections.length && <details><summary>이메일·Slack·웹사이트 연결 설정</summary><ul>{connections.map(row => <li key={row.key}><strong>{row.label}</strong> · {row.configured ? "설정값 있음 · 실제 연결 미검증" : `설정 필요: ${row.missing.join(" · ")}`}</li>)}</ul><p className="muted">API 키·토큰은 이 화면에 표시하거나 저장하지 않습니다. heobrain.kr 초안 수신 인터페이스가 없으면 게시 준비가 완료된 것으로 표시하지 않습니다.</p></details>}
      {!keyValid && <p className="field-error">회차 키는 2026-10-w5 형식입니다.</p>}
      {!releaseApproved && <p className="muted">② 출고 승인 뒤에 회차를 만들 수 있습니다. 제작·출고함에서 먼저 출고할 결과물을 검토하세요.</p>}
      {releaseApproved && !job.release_approval?.outputs?.includes("blog") && <p className="muted">글 회차를 만들려면 블로그 결과물의 출고 승인②가 필요합니다. 영상만 승인한 상태에서는 글을 자동 발송 대상으로 포함하지 않습니다.</p>}
      {loadError && <p className="field-error">{loadError}</p>}
      {mine.length === 0 && !loadError && <p className="muted">이 작업으로 만든 회차가 아직 없습니다.{others > 0 ? ` 다른 작업의 회차 ${others}개는 운영 기록에서 확인하세요.` : ""}</p>}
      {mine.length > 0 && (
        <ul className="delivery-list">
          {mine.map((issue) => {
            const reviewable = issue.state === "draft" || issue.state === "rejected";
            const reviewToken = /^[a-f0-9]{64}$/.test(issue.review_hash ?? "") ? issue.review_hash : "";
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
                  {issue.package && <NewsletterPackageView issue={issue} connections={connections} busy={busy} run={run} />}
                </div>
                <div className="newsletter-actions">
                  {reviewable && (
                    <div className="newsletter-review" role="group" aria-label="③ 회차 승인">
                      {!reviewToken && <p className="field-error" role="alert">검토할 회차 판본을 확인하지 못했습니다. 화면을 새로고침한 뒤 본문과 수신자 묶음을 다시 읽어 주세요.</p>}
                      <textarea rows={2} placeholder="③ 회차 승인 메모 (선택)" value={note} disabled={busy} onChange={(e) => setNotes((n) => ({ ...n, [issue.id]: e.target.value }))} />
                      <div className="derived-actions">
                        <button className="button primary small" type="button" disabled={busy || !reviewToken} onClick={() => void run("③ 회차 승인", () => api.reviewNewsletter(issue.id, "approve", note.trim(), reviewToken), "③ 회차를 승인했습니다. 발송은 하지 않았습니다. 내보내서 메일러로 보내세요.")}>
                          <Icon name="check" size={13} />③ 회차 승인
                        </button>
                        <button className="button text small" type="button" disabled={busy || !reviewToken} onClick={() => void run("③ 회차 반려", () => api.reviewNewsletter(issue.id, "reject", note.trim(), reviewToken), "회차를 반려했습니다.")}>
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
                      <>
                      {!reviewToken && <p className="field-error" role="alert">발송 표시할 회차 판본을 확인하지 못했습니다. 다시 불러온 본문과 수신자 묶음을 확인하세요.</p>}
                      <button
                        className="button secondary small"
                        type="button"
                        disabled={busy || !reviewToken}
                        onClick={() => {
                          if (busy || !reviewToken) return;
                          if (!window.confirm("메일러에서 실제로 보낸 뒤에만 표시하세요. 발송 완료로 기록할까요?")) return;
                          void run("발송 완료 표시", () => api.markNewsletterSent(issue.id, reviewToken), "발송 완료로 표시했습니다.");
                        }}
                      >
                        발송 완료로 표시
                      </button>
                      </>
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

function NewsletterPackageView({ issue, connections, busy, run }: { issue: NewsletterIssue; connections: NewsletterConnection[]; busy: boolean; run: (label: string, execute: () => Promise<unknown>, success: string) => Promise<void> }) {
  const [format, setFormat] = useState<NewsletterDestination>(issue.editorial?.destinations[0] ?? "email");
  const [prepared, setPrepared] = useState<NewsletterPrepared | null>(null);
  const [error, setError] = useState("");
  const [reload, setReload] = useState(0);
  const generation = useRef(0);
  useEffect(() => {
    const request = ++generation.current;
    setPrepared(null); setError("");
    void api.newsletterPrepared(issue.id).then(result => {
      if (generation.current === request) setPrepared(result.prepared?.review_hash === issue.review_hash ? result.prepared : null);
    }).catch(cause => {
      if (generation.current === request) { setPrepared(null); setError(cause instanceof Error ? cause.message : "준비 기록을 확인하지 못했습니다."); }
    });
    return () => { generation.current++; };
  }, [issue.id, issue.review_hash, reload]);
  const pkg = issue.package!;
  const currentPrepared = prepared?.review_hash === issue.review_hash ? prepared : null;
  return <section className="newsletter-package" aria-label="회차별 미리보기와 전달 준비">
    <p><strong>원고 {pkg.article_count}개 · 발행처 {pkg.publisher_count}곳</strong></p><p className="muted">{pkg.source_note}</p>
    <details><summary>회차의 원출처 확인</summary><ul>{pkg.sources.map(source => <li key={source.job_id}>{source.title} · {source.publisher}{source.url && <> · <a href={source.url} target="_blank" rel="noopener noreferrer">원문 읽기</a></>}</li>)}</ul></details>
    <div className="newsletter-preview-actions" role="group" aria-label="목적지별 미리보기">{issue.editorial?.destinations.map(key => <button key={key} type="button" className={`button ${format === key ? "primary" : "secondary"} small`} aria-pressed={format === key} onClick={() => setFormat(key)}>{key === "email" ? "이메일 미리보기" : key === "slack" ? "Slack 원문" : "웹사이트 초안"}</button>)}</div>
    {format === "email" && pkg.outputs.email && <><iframe title="이메일 미리보기" sandbox="" referrerPolicy="no-referrer" srcDoc={pkg.outputs.email.html} /><details><summary>이미지 없이 읽는 이메일 텍스트</summary><pre className="newsletter-markdown">{pkg.outputs.email.text}</pre></details></>}
    {format === "slack" && pkg.outputs.slack && <pre className="newsletter-markdown">{pkg.outputs.slack.text}</pre>}
    {format === "website" && pkg.outputs.website && <><p className="muted">웹사이트용 초안입니다. heobrain.kr에 게시하지 않았습니다.</p><pre className="newsletter-markdown">{pkg.outputs.website.markdown}</pre></>}
    <ul className="newsletter-connection-list">{connections.filter(row => issue.editorial?.destinations.includes(row.key)).map(row => <li key={row.key}>{row.label} · {row.configured ? "설정값 확인 · 실제 연결 미검증" : "연결 설정 필요"}</li>)}</ul>
    <button type="button" className="button secondary" disabled={busy || issue.state !== "approved" || !/^[a-f0-9]{64}$/.test(issue.review_hash ?? "")} onClick={() => {
      const request = ++generation.current;
      setPrepared(null); setError("");
      void run("뉴스레터 전달 준비", async () => {
        const result = await api.prepareNewsletter(issue.id, issue.review_hash);
        if (generation.current === request && result.review_hash === issue.review_hash) { setPrepared(result); setError(""); }
        return result;
      }, "전달 준비를 기록했습니다. 실제 발송·게시는 하지 않았습니다.");
    }}>선택한 목적지 전달 준비</button>
    {issue.state !== "approved" && <p className="muted">목적지별 원문을 확인하고 사람이 ③을 승인한 뒤 준비할 수 있습니다.</p>}
    {error && <p className="field-error" role="alert">{error} <button type="button" className="button text small" onClick={() => setReload(value => value + 1)}>준비 기록 다시 확인</button></p>}
    {currentPrepared && <div role="status"><strong>{currentPrepared.state === "connection_required" ? "전달 준비 기록 · 연결 설정 필요" : "전달 패키지 준비 · 실제 전송 전"}</strong><p>{currentPrepared.note}</p><small>준비 기록 {currentPrepared.id} · 외부 요청 {currentPrepared.external_requests}건</small></div>}
  </section>;
}
