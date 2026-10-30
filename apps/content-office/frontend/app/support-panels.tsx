"use client";

import { useCallback, useEffect, useRef, useState } from "react";
import { api } from "../lib/api";
import type { Action, Idea, Job, JobBudget, JobMetadata, KnowledgeSearch, Task, OutputKind } from "../lib/types";
import {
  completedOutputs,
  evidenceInputAllowed,
  retryBlockedReason,
  formatDate,
  formatMoney,
} from "../lib/workflow";
import { calendarSourceUrl, calendarTimeliness, dDayLabel, isVerifiedExam, timelinessPercent } from "../lib/calendar";
import { Icon } from "./icons";
import { IdeaIntake } from "./idea-intake";
import { IdeaSourcesPanel } from "./idea-sources-panel";
import type { IdeaSourcesDraft } from "../lib/ideas";
import { packagingRequired } from "../lib/packaging";

export type IntakeDraft = {
  text: string;
  version: string | null;
  acknowledged: boolean;
  preserveOriginal?: boolean;
};

export function JobBudgetPanel({ jobId, globalCap, refreshKey, busy }: { jobId: string; globalCap?: number; refreshKey?: string; busy: boolean }) {
  const [budget, setBudget] = useState<JobBudget>();
  const [input, setInput] = useState("1000");
  const [error, setError] = useState("");
  const [notice, setNotice] = useState("");
  const [loading, setLoading] = useState(false);
  const [saving, setSaving] = useState(false);
  const alive = useRef(true), sequence = useRef(0), writing = useRef(false), activeJob = useRef(jobId);
  activeJob.current = jobId;
  const current = budget?.job_id === jobId ? budget : undefined;
  function requireBudget(value: JobBudget) {
    if (!value || value.job_id !== jobId || typeof value.hash !== "string" || !/^[a-f0-9]{64}$/.test(value.hash)
      || (value.cap_krw !== null && (!Number.isSafeInteger(value.cap_krw) || value.cap_krw <= 0))
      || ![value.spent_krw, value.reserved_krw, value.overrun_krw].every((number) => Number.isSafeInteger(number) && number >= 0)
      || (value.remaining_krw !== null && !Number.isSafeInteger(value.remaining_krw))
      || (value.cap_krw === null) !== (value.remaining_krw === null))
      throw new Error("이 작업의 예산 숫자와 판본을 확인하지 못했습니다. 다시 조회하세요.");
  }
  const load = useCallback(async () => {
    if (writing.current) return;
    const ticket = ++sequence.current;
    setLoading(true); setError(""); setNotice(""); setBudget(undefined);
    try {
      const value = await api.jobBudget(jobId);
      requireBudget(value);
      if (alive.current && activeJob.current === jobId && ticket === sequence.current) setBudget(value);
    } catch (cause) {
      if (alive.current && activeJob.current === jobId && ticket === sequence.current) setError(cause instanceof Error ? cause.message : "작업별 예산을 읽지 못했습니다.");
    } finally {
      if (alive.current && activeJob.current === jobId && ticket === sequence.current) setLoading(false);
    }
  }, [jobId]);
  useEffect(() => {
    alive.current = true;
    return () => { alive.current = false; sequence.current++; };
  }, [jobId]);
  useEffect(() => { void load(); }, [load, refreshKey]);
  const cap = /^\d+$/.test(input) ? Number(input) : NaN;
  const validCap = Number.isSafeInteger(cap) && cap > 0 && (globalCap === undefined || cap <= globalCap);
  async function save() {
    if (busy || loading || writing.current || !current || error || !validCap) return;
    const ticket = ++sequence.current;
    writing.current = true; setSaving(true); setNotice("");
    try {
      const value = await api.setJobBudget(jobId, cap, current.hash);
      requireBudget(value);
      if (value.cap_krw !== cap) throw new Error("요청한 작업 상한의 저장 결과를 확인하지 못했습니다. 다시 조회하세요.");
      if (alive.current && activeJob.current === jobId && ticket === sequence.current) {
        setBudget(value); setNotice(`이 작업의 상한을 ${formatMoney(cap)}원으로 기록했습니다. 비용·예약·승인은 유지하며 모델을 호출하지 않았습니다.`);
      }
    } catch (cause) {
      if (alive.current && activeJob.current === jobId && ticket === sequence.current) { setBudget(undefined); setError(cause instanceof Error ? cause.message : "작업 상한을 기록하지 못했습니다."); }
    } finally {
      writing.current = false;
      if (alive.current && activeJob.current === jobId) setSaving(false);
    }
  }
  return <section className="editor-panel derived-panel" aria-label="이 작업의 제작 비용 상한">
    <h3>이 작업의 제작 비용</h3>
    <p className="muted">전체 상한: {typeof globalCap === "number" && Number.isSafeInteger(globalCap) && globalCap > 0 ? `${formatMoney(globalCap)}원` : "미확인"} · 기존 비용과 예약은 초기화하지 않습니다. 작업 상한이 없으면 전체 예산 제한을 따릅니다.</p>
    {loading && <p role="status">작업 예산을 확인하고 있습니다.</p>}
    {error && <p className="notice error" role="alert">{error} 사용량을 0원으로 간주하지 않았습니다. 다시 조회한 뒤 설정하세요.</p>}
    {notice && <p className="notice" role="status">{notice}</p>}
    {current && <dl className="brief-rows">
      <div><dt>이 작업 상한</dt><dd>{current.cap_krw === null ? "미설정 · 전체 제한 적용" : `${formatMoney(current.cap_krw)}원`}</dd></div>
      <div><dt>쓴 금액(추정)</dt><dd>{formatMoney(current.spent_krw)}원</dd></div>
      <div><dt>예약·결과 불명</dt><dd>{formatMoney(current.reserved_krw)}원</dd></div>
      <div><dt>작업 상한에서 남음</dt><dd>{current.remaining_krw === null ? "별도 상한 미설정" : `${formatMoney(current.remaining_krw)}원`}</dd></div>
      {current.overrun_krw > 0 && <div><dt>작업 상한 초과</dt><dd>{formatMoney(current.overrun_krw)}원</dd></div>}
    </dl>}
    <div className="newsletter-build">
      <label htmlFor={`job-budget-${jobId}`}>이 작업 상한(원)<input id={`job-budget-${jobId}`} inputMode="numeric" pattern="[0-9]*" value={input} disabled={busy || saving} onChange={(event) => setInput(event.target.value)} /></label>
      <button className="button secondary" type="button" disabled={busy || loading || saving || !current || Boolean(error) || !validCap} onClick={() => void save()}>작업 상한 설정</button>
      <button className="button text" type="button" disabled={busy || loading || saving} onClick={() => void load()}>예산 다시 조회</button>
    </div>
    <p className="muted">첫 1편은 1,000원 상한을 권장합니다. 실제 예약액은 남은 작업 예산과 전체 예산 안에서만 허용하며, 설정 자체는 제작이나 승인을 시작하지 않습니다.</p>
    {!validCap && <p className="field-error">{input === "" ? "이 작업의 상한을 입력하세요. 빈 입력은 0원이 아닙니다." : "전체 상한 이하의 양의 정수를 입력하세요."}</p>}
  </section>;
}

export function EvidenceIntake({
  job,
  busy,
  dirty,
  model,
  requestBlockedReason,
  draft,
  onChange,
  onPackaging,
  action,
}: {
  job: Job;
  busy: boolean;
  dirty: boolean;
  model?: string;
  requestBlockedReason?: string;
  draft?: IntakeDraft;
  onChange: (value: IntakeDraft | null) => void;
  onPackaging: () => void;
  action: Action;
}) {
  const text = draft?.text ?? "";
  const version = draft ? draft.version : (job.source_hash ?? null);
  const preserveOriginal = (draft?.preserveOriginal ?? job.article?.preserve_original) === true;
  const stale = Boolean(text && version !== (job.source_hash ?? null));
  if (!evidenceInputAllowed(job)) return null;
  const needsPackaging = packagingRequired(job);
  const locked =
    busy ||
    dirty ||
    [
      "drafting",
      "production_queued",
      "producing",
      "needs_reconciliation",
    ].includes(job.state);
  const valid =
    text.trim().length >= 200 &&
    text.length <= 20000 &&
    draft?.acknowledged &&
    !stale;
  return (
    <section className="source-intake">
      <details open={!job.article?.evidence?.length}>
        <summary>
          공개 원문으로 근거 보완하기
          <Icon name="source" size={16} />
        </summary>
        <div className="intake-body">
          <p>
            이 출처에서 직접 확인한 공개 원문만 입력하세요. 등록하면 현재 승인과
            파생 파일을 해제하고 근거 추출·새 원고·검수를 요청합니다.
          </p>
          <a
            className="intake-provenance"
            href={job.article?.url}
            target="_blank"
            rel="noopener noreferrer"
          >
            원출처: {job.article?.url}
            <Icon name="external" size={12} />
          </a>
          <p className="intake-disclosure">
            입력한 텍스트는 현재 설정된 원고 모델{model ? ` (${model})` : ""}로
            전송됩니다. 개인 문서나 비공개 자료는 붙여넣지 마세요.
          </p>
          <label htmlFor={`source-${job.id}`}>공개 원문 텍스트</label>
          <textarea
            id={`source-${job.id}`}
            value={text}
            maxLength={20000}
            minLength={200}
            disabled={locked}
            placeholder="원문에서 사용 권한을 확인한 공개 텍스트를 200~20,000자로 붙여넣으세요."
            onChange={(event) => onChange({ text: event.target.value, version, acknowledged: false, preserveOriginal })}
          />
          <div className="intake-meta">
            <span>
              {text.length.toLocaleString("ko-KR")} / 20,000자 · 최소 200자
            </span>
            <span>시작 버전 {version?.slice(0, 10) || "원고 없음"}</span>
          </div>
          <label className="intake-consent">
            <input
              type="checkbox"
              checked={draft?.acknowledged ?? false}
              disabled={locked || !text}
              onChange={(event) =>
                onChange({ text, version, acknowledged: event.target.checked, preserveOriginal })
              }
            />
            <span>이 출처의 공개 원문이며 재사용할 권한을 확인했습니다.</span>
          </label>
          <label className="intake-consent">
            <input
              type="checkbox"
              checked={preserveOriginal}
              disabled={locked}
              onChange={(event) => onChange({ text, version, acknowledged: draft?.acknowledged ?? false, preserveOriginal: event.target.checked })}
            />
            <span>원문 전체를 보존하고 영상만 파생</span>
          </label>
          <p className="intake-disclosure">본인이 쓴 글이나 원문 전체를 재사용하도록 허락받은 글에만 선택하세요. 선택하면 Markdown 본문을 요약·재작성하지 않고 영상 대본과 검수를 따로 요청합니다. 원고 승인①과 출고 승인②는 사람이 합니다. 선택하지 않으면 기존 요약·재작성 방식을 사용합니다.</p>
          <p className="intake-meta">등록할 방식: {preserveOriginal ? "원문 보존 · 영상 파생" : "요약·재작성"} · 입력 원문 {text.length.toLocaleString("ko-KR")}자</p>
          {stale && (
            <p className="intake-error" role="alert">
              입력 중 원고 버전이 바뀌었습니다. 입력을 복사한 뒤 현재 작업을
              다시 확인하세요.
            </p>
          )}
          {dirty && (
            <p className="intake-error">
              편집 중인 원고를 먼저 저장하거나 정리하세요.
            </p>
          )}
          {needsPackaging && (
            <div className="notice" id={`source-packaging-${job.id}`}>
              <p>제목·썸네일·후크를 먼저 확정하세요. 입력한 원문과 동의는 그대로 유지됩니다.</p>
              <button type="button" className="button text" onClick={onPackaging}>
                제목·썸네일·후크 정하러 가기
              </button>
            </div>
          )}
          <button
            className="button secondary"
            disabled={locked || !valid || needsPackaging || Boolean(requestBlockedReason)}
            aria-describedby={needsPackaging ? `source-packaging-${job.id}` : undefined}
            onClick={() => {
              if (locked || !valid || needsPackaging || requestBlockedReason) return;
              void action(
                "공개 원문 근거 등록",
                async () => {
                  await api.registerEvidence(job.id, text, version, preserveOriginal);
                  onChange(null);
                },
                preserveOriginal
                  ? `원문 ${text.length.toLocaleString("ko-KR")}자를 보존 모드로 등록하고 영상 대본·검수를 요청했습니다. 생성 완료와 승인은 별도입니다.`
                  : "공개 원문을 등록하고 근거 추출·새 원고 작업을 요청했습니다. 생성 완료와 승인은 별도입니다.",
              );
            }}
          >
            {preserveOriginal ? "근거 등록하고 영상 대본 만들기" : "근거 등록하고 새 원고 만들기"}
            <Icon name="arrow" size={16} />
          </button>
        </div>
      </details>
    </section>
  );
}

const taskNames: Record<string, string> = {
  draft: "원고 생성·검수",
  evaluate: "독립 재검수",
  produce: "콘텐츠 제작",
  refresh: "RSS 수집",
};
const taskStates: Record<string, string> = {
  queued: "대기",
  running: "실행 중",
  completed: "완료",
  partial: "일부 완료",
  failed: "실패",
  unknown: "결과 확인 필요",
};
export function TaskHistory({
  tasks,
  jobs,
  busy,
  requestBlockedReason,
  action,
}: {
  tasks: Task[];
  jobs: JobMetadata[];
  requestBlockedReason?: string;
  busy: boolean;
  action: Action;
}) {
  const [pending, setPending] = useState<string>();
  if (!tasks.length) return null;
  return (
    <section className="task-panel">
      <h3>작업 진행 기록</h3>
      {tasks.map((task, index) => {
        const job = jobs.find((item) => item.id === task.payload?.job_id);
        const reason = retryBlockedReason(task, job, tasks) || requestBlockedReason;
        const failed = ["failed", "unknown", "partial"].includes(
          task.state ?? "",
        );
        return (
          <div className="task-history-item" key={task.id || index}>
            <div className="task-row">
              <span
                className={`status-dot ${task.state === "running" ? "live" : ""}`}
              />
              <strong>
                {taskNames[task.kind ?? ""] || task.kind || "백그라운드 작업"}
              </strong>
              <span>
                {taskStates[task.state ?? ""] || task.state || "상태 미확인"}
              </span>
              {failed && (
                <button
                  className="button secondary small task-retry"
                  disabled={busy || Boolean(reason)}
                  aria-label={`${taskNames[task.kind ?? ""] || task.kind} 다시 요청`}
                  onClick={() => setPending(task.id)}
                >
                  다시 요청
                </button>
              )}
            </div>
            {task.error && <p className="task-failure">{task.error}</p>}
            {failed && reason && <p className="task-retry-reason">{reason}</p>}
            {pending === task.id && (
              <div
                className="retry-confirm"
                role="region"
                aria-label="실패 작업 재시도 확인"
              >
                <strong>현재 조건으로 이 실패 작업을 다시 요청할까요?</strong>
                <p>
                  {taskNames[task.kind ?? ""] || task.kind} ·{" "}
                  {formatDate(task.updated_at || task.created_at, true)}. 추가
                  모델 호출에는 예산 조건이 적용됩니다. 결과 불명인 제공자
                  호출은 원가·결과 대사 전 서버에서 계속 차단됩니다.
                </p>
                <div>
                  <button
                    className="button text small"
                    onClick={() => setPending(undefined)}
                  >
                    취소
                  </button>
                  <button
                    className="button primary small"
                    disabled={busy || Boolean(reason)}
                    onClick={() =>
                      void action(
                        "실패 작업 재시도",
                        async () => {
                          await api.retryTask(task.id!);
                          setPending(undefined);
                        },
                        "재시도 작업을 명시적으로 요청했습니다. 결과·비용 확인이 필요한 호출은 서버 검사에 따라 보류됩니다.",
                      )
                    }
                  >
                    실패 작업 다시 요청
                  </button>
                </div>
              </div>
            )}
          </div>
        );
      })}
    </section>
  );
}

export function KnowledgeDrawer() {
  const [open, setOpen] = useState(false);
  const [query, setQuery] = useState("");
  const [searched, setSearched] = useState("");
  const [data, setData] = useState<KnowledgeSearch | null>(null);
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState("");
  const dialog = useRef<HTMLDivElement>(null);
  const launcher = useRef<HTMLButtonElement>(null);
  const sequence = useRef(0);
  async function search(value: string) {
    const current = ++sequence.current;
    setLoading(true);
    setError("");
    setSearched(value);
    try {
      const result = await api.knowledge(value);
      if (current === sequence.current) setData(result);
    } catch (cause) {
      if (current === sequence.current)
        setError(
          cause instanceof Error
            ? cause.message
            : "문서 색인을 읽지 못했습니다.",
        );
    } finally {
      if (current === sequence.current) setLoading(false);
    }
  }
  useEffect(() => {
    if (!open) return;
    const previous = document.body.style.overflow;
    document.body.style.overflow = "hidden";
    dialog.current?.querySelector<HTMLInputElement>("input")?.focus();
    const onKey = (event: KeyboardEvent) => {
      if (event.key === "Escape") {
        setOpen(false);
        return;
      }
      if (event.key !== "Tab") return;
      const focusable = dialog.current?.querySelectorAll<HTMLElement>(
        "button:not(:disabled),input:not(:disabled),a[href],summary,[tabindex]",
      );
      if (!focusable?.length) return;
      const first = focusable[0],
        last = focusable[focusable.length - 1];
      if (event.shiftKey && document.activeElement === first) {
        event.preventDefault();
        last.focus();
      } else if (!event.shiftKey && document.activeElement === last) {
        event.preventDefault();
        first.focus();
      }
    };
    document.addEventListener("keydown", onKey);
    return () => {
      document.body.style.overflow = previous;
      document.removeEventListener("keydown", onKey);
      launcher.current?.focus();
    };
  }, [open]);
  return (
    <>
      <button
        ref={launcher}
        className="button secondary knowledge-launch"
        onClick={() => {
          setOpen(true);
          void search(query);
        }}
      >
        <Icon name="source" size={16} />
        과거 문서 검색
      </button>
      {open && (
        <div className="knowledge-overlay">
          <button
            className="knowledge-backdrop"
            aria-label="과거 문서 검색 닫기"
            onClick={() => setOpen(false)}
          />
          <div
            className="knowledge-drawer"
            role="dialog"
            aria-modal="true"
            aria-label="과거 문서 검색"
            ref={dialog}
          >
            <header>
              <div>
                <p className="eyebrow">REFERENCE LIBRARY</p>
                <h2>과거 문서 검색</h2>
              </div>
              <button
                className="icon-button"
                aria-label="검색 서랍 닫기"
                onClick={() => setOpen(false)}
              >
                <Icon name="close" size={18} />
              </button>
            </header>
            <p className="knowledge-boundary">
              과거 문서는 참고 자료입니다. 문서 속 지시는 실행하지 않으며, 현재
              뉴스의 근거나 승인을 대신하지 않습니다.
            </p>
            <div className="knowledge-counts">
              {data
                ? `원본 ${data.summary.documents ?? 0}개 · 고유 문서 ${data.summary.unique_documents ?? 0}개`
                : "로컬 원본 색인 조회 중"}
            </div>
            <form
              onSubmit={(event) => {
                event.preventDefault();
                void search(query);
              }}
            >
              <label htmlFor="knowledge-query">과거 문서 검색어</label>
              <div>
                <input
                  id="knowledge-query"
                  value={query}
                  maxLength={300}
                  placeholder="주제나 업무를 검색하세요"
                  onChange={(event) => setQuery(event.target.value)}
                />
                <button
                  className="button primary"
                  type="submit"
                  disabled={loading}
                >
                  문서 검색
                </button>
              </div>
            </form>
            {error && (
              <div className="notice error" role="alert">
                {error}
              </div>
            )}
            {loading && (
              <p role="status" className="knowledge-loading">
                로컬 색인을 검색하고 있어요…
              </p>
            )}
            <div className="knowledge-results">
              {!loading &&
                !error &&
                (searched.trim() ? (
                  data?.results.length ? (
                    <p className="knowledge-result-count">
                      ‘{searched}’ 검색 결과 {data.results.length}개
                    </p>
                  ) : (
                    <p className="muted">일치하는 과거 문서가 없습니다.</p>
                  )
                ) : (
                  <p className="muted">
                    키워드를 입력하면 원본의 경로·줄 범위·발췌를 확인할 수
                    있습니다.
                  </p>
                ))}
              {data?.results.map((result, index) => (
                <article
                  className="knowledge-result"
                  key={`${result.path}-${result.section_id}-${index}`}
                >
                  <h3>{result.section}</h3>
                  <p className="knowledge-path">
                    {result.path} · L{result.start_line}–L{result.end_line}
                  </p>
                  <span className="knowledge-hash">
                    SHA256 {result.sha256.slice(0, 12)} · 과거 참고 자료
                  </span>
                  <pre tabIndex={0} aria-label={`${result.section} 발췌`}>{result.excerpt}</pre>
                  {result.duplicate_paths?.length ? (
                    <p className="muted">
                      동일 본문 경로 {result.duplicate_paths.length}개는
                      중복으로 묶었습니다.
                    </p>
                  ) : null}
                  {result.contracts?.length ? (
                    <details>
                      <summary>
                        연결된 과거 항목 {result.contracts.length}개
                      </summary>
                      <ul>
                        {result.contracts.map((item, i) => (
                          <li key={`${item.contract_id}-${i}`}>
                            {item.contract_id} · {item.title} · L{item.line} ·
                            참고 근거 후보
                          </li>
                        ))}
                      </ul>
                    </details>
                  ) : null}
                </article>
              ))}
            </div>
          </div>
        </div>
      )}
    </>
  );
}

export const outputNames: Record<OutputKind, string> = {
  blog: "블로그·소셜 검토 초안",
  video: "YouTube Shorts",
  pdf: "PDF 자료",
  cards: "카드 콘텐츠",
};
export function OutputChoices({
  job,
  selected,
  onChange,
  busy,
}: {
  job: Job;
  selected: OutputKind[];
  onChange: (outputs: OutputKind[]) => void;
  busy: boolean;
}) {
  const complete = completedOutputs(job);
  const outputs = (Object.keys(outputNames) as OutputKind[]).filter(
    (key) => job.selections?.[key],
  );
  return (
    <section className="output-choices">
      <div className="section-heading">
        <div>
          <p className="eyebrow">RELEASE BY OUTPUT</p>
          <h3>완료된 항목부터 출고하세요</h3>
        </div>
        <span className="count-pill">
          {complete.length} / {outputs.length} 완료
        </span>
      </div>
      <p className="output-note">
        원고 승인 범위를 유지하면서 이번에 전달할 완료 항목만 고릅니다. 다른
        항목의 실패가 완료된 블로그의 출고를 막지 않습니다.
      </p>
      <div className="output-grid">
        {outputs.map((key) => {
          const status = job.manifest?.output_status?.[key];
          const ready = complete.includes(key);
          return (
            <label
              className={`output-choice ${selected.includes(key) ? "selected" : ""}`}
              key={key}
            >
              <div>
                <input
                  type="checkbox"
                  aria-label={`${outputNames[key]} 출고`}
                  checked={selected.includes(key)}
                  disabled={busy || !ready}
                  onChange={(event) =>
                    onChange(
                      event.target.checked
                        ? [...selected, key]
                        : selected.filter((item) => item !== key),
                    )
                  }
                />
                <strong>{outputNames[key]}</strong>
                <span
                  className={`badge ${ready ? "green" : status?.state === "failed" ? "red" : "neutral"}`}
                >
                  {ready
                    ? "완료"
                    : status?.state === "failed"
                      ? "제작 실패"
                      : status?.state === "running"
                        ? "제작 중"
                        : "미완료"}
                </span>
              </div>
              {status?.files != null && <p>{status.files}개 파일</p>}
              {status?.error && <p className="output-error">{status.error}</p>}
              {status?.successful_assets_preserved && (
                <p>성공한 자산은 보존되어 있습니다.</p>
              )}
            </label>
          );
        })}
      </div>
    </section>
  );
}

/** 기획 은행. refreshKey가 바뀌면(독자 질문 → 기획 전환 등) 목록을 다시 읽습니다. */
export function IdeaBank({ onSelected, refreshKey = 0, drafts = {}, onDraftChange }: {
  onSelected?: (job: Job) => void;
  refreshKey?: number;
  drafts?: Record<string, IdeaSourcesDraft>;
  onDraftChange?: (id: string, draft: IdeaSourcesDraft | null) => void;
}) {
  const [ideas, setIdeas] = useState<Idea[]>([]);
  const [error, setError] = useState("");
  const [busy, setBusy] = useState<string | null>(null);
  const [editingSources, setEditingSources] = useState<Record<string, boolean>>({});
  const readTicket = useRef(0);
  const choosing = useRef(false);
  const sourceEditing = useCallback((id: string, pending: boolean) => {
    setEditingSources((previous) => {
      if (Boolean(previous[id]) === pending) return previous;
      const next = { ...previous };
      if (pending) next[id] = true;
      else delete next[id];
      return next;
    });
  }, []);
  async function load() {
    const ticket = ++readTicket.current;
    try {
      const result = await api.ideas();
      if (ticket !== readTicket.current) return;
      setIdeas(result.ideas);
      setError("");
    } catch (cause) {
      if (ticket !== readTicket.current) return;
      setError(cause instanceof Error ? cause.message : "기획 은행을 읽지 못했습니다.");
    }
  }
  useEffect(() => {
    void load();
    return () => { readTicket.current++; };
  }, [refreshKey]);
  async function choose(idea: Idea) {
    if (choosing.current || editingSources[idea.id] || drafts[idea.id]?.dirty || !/^[a-f0-9]{64}$/.test(idea.edit_hash ?? "")) return;
    choosing.current = true;
    readTicket.current++;
    setBusy(idea.id);
    setError("");
    try {
      const result = await api.selectIdea(idea.id, idea.edit_hash!);
      onSelected?.(result.job);
      await load();
    } catch (cause) {
      setError(cause instanceof Error ? cause.message : "기획을 선택하지 못했습니다.");
    } finally {
      choosing.current = false;
      setBusy(null);
    }
  }
  return (
    <section className="news-section" aria-labelledby="idea-bank-heading">
      <div className="section-heading">
        <div className="section-title">
          <h2 id="idea-bank-heading">기획 은행 · ⓪ 기획 선택</h2>
          <span className="count-pill">{ideas.length}</span>
        </div>
      </div>
      <IdeaIntake onSaved={() => void load()} />
      {error && <p role="alert">{error}</p>}
      {ideas.length === 0 && !error && <p>아직 점수를 매긴 기획이 없습니다. 아래에서 직접 등록하세요.</p>}
      <ol>
        {ideas.map((idea) => (
          <li key={idea.id}>
            <strong>{idea.title}</strong> · {idea.score}점 · 이상치 {idea.outlier_band}
            {idea.next_exam && <>
              {isVerifiedExam(idea.next_exam) ? <span className="idea-dday" style={{ whiteSpace: "normal", maxWidth: "100%", overflowWrap: "anywhere" }}>{dDayLabel(idea.next_exam)}</span> : <p className="muted" style={{ overflowWrap: "anywhere" }}>{dDayLabel(idea.next_exam)}</p>}
              <p className="muted" style={{ overflowWrap: "anywhere" }}>
                {idea.next_exam.note && <>{idea.next_exam.note} · </>}
                {calendarSourceUrl(idea.next_exam) ? <a href={calendarSourceUrl(idea.next_exam)!} target="_blank" rel="noopener noreferrer">달력에 기록된 출처 열기 ↗</a> : "공개 HTTPS 출처가 기록되지 않았습니다."}
                {isVerifiedExam(idea.next_exam) && " · 저장된 확인 기록 기준이며 오늘의 공식 일정 재검증은 아닙니다."}
              </p>
            </>}
            {calendarTimeliness(idea.next_exam, idea.timeliness) !== null ? (
              <div className="idea-timeliness" aria-label={`확인 기록 기준 시의성 ${calendarTimeliness(idea.next_exam, idea.timeliness)}%`}>
                <span>확인 기록 기준 시의성</span>
                <div className="progress-track">
                  <span style={{ width: `${calendarTimeliness(idea.next_exam, idea.timeliness)}%` }} />
                </div>
                <span>{calendarTimeliness(idea.next_exam, idea.timeliness)}%</span>
              </div>
            ) : !idea.next_exam && typeof idea.timeliness === "number" && Number.isFinite(idea.timeliness) && idea.timeliness > 0 ? <p className="muted">저장된 편집 참고값 {timelinessPercent(idea.timeliness)}% · 특정 시험일을 확인한 점수는 아닙니다.</p> : <p className="muted">시의성 미확인 · 확정 일정에 따른 가산을 표시하지 않습니다.</p>}
            <details className="idea-brief-preview">
              <summary>저장된 기획 읽기</summary>
              {idea.brief ? <>
                <p className="muted">기획 선택⓪ 전에 실제 저장된 독자·약속·구매 안내를 확인하세요. 이 내용을 펼쳐 읽어도 승인이나 제작 요청은 실행되지 않습니다.</p>
                <dl className="brief-rows">
                  {([
                    ["주제", idea.brief.topic],
                    ["독자", idea.brief.reader],
                    ["독자가 막힌 점", idea.brief.problem],
                    ["약속한 결과", idea.brief.outcome],
                    ["문체", idea.brief.tone],
                    ["원고 언어", idea.brief.language === "ko" ? "한국어" : idea.brief.language === "en" ? "영어" : idea.brief.language],
                    ["다음 행동(CTA)", idea.brief.cta],
                  ] as const).map(([label, value]) => <div key={label}><dt>{label}</dt><dd>{typeof value === "string" && value.trim() ? value : "미기록"}</dd></div>)}
                </dl>
              </> : <p className="muted">이 기획에 저장된 독자 기획이 없습니다.</p>}
            </details>
            {idea.blocked.length > 0 && <p>막힌 이유: {idea.blocked.join(", ")}</p>}
            <IdeaSourcesPanel
              idea={idea}
              cached={drafts[idea.id]}
              onDraftChange={onDraftChange}
              onEditingChange={sourceEditing}
              onSaved={(saved) => {
                readTicket.current++;
                setIdeas((cards) => cards.map((card) => card.id === saved.id ? saved : card));
                void load();
              }}
            />
            {editingSources[idea.id] && <p role="status">출처를 저장하거나 입력을 정리한 뒤 기획을 선택하세요.</p>}
            <button
              className="button secondary"
              type="button"
              disabled={idea.blocked.length > 0 || idea.state !== "candidate" || busy !== null || editingSources[idea.id] || drafts[idea.id]?.dirty || !/^[a-f0-9]{64}$/.test(idea.edit_hash ?? "")}
              onClick={() => void choose(idea)}
            >
              {idea.state === "selected" ? "선택됨" : "이 기획으로 작업 만들기"}
            </button>
          </li>
        ))}
      </ol>
    </section>
  );
}
