"use client";

import { useEffect, useRef, useState } from "react";
import { api } from "../lib/api";
import type { Action, Idea, Job, KnowledgeSearch, Task, OutputKind } from "../lib/types";
import {
  completedOutputs,
  evidenceInputAllowed,
  retryBlockedReason,
  formatDate,
} from "../lib/workflow";
import { dDayLabel, timelinessPercent } from "../lib/calendar";
import { Icon } from "./icons";
import { IdeaIntake } from "./idea-intake";

export type IntakeDraft = {
  text: string;
  version: string | null;
  acknowledged: boolean;
};

export function EvidenceIntake({
  job,
  busy,
  dirty,
  model,
  draft,
  onChange,
  action,
}: {
  job: Job;
  busy: boolean;
  dirty: boolean;
  model?: string;
  draft?: IntakeDraft;
  onChange: (value: IntakeDraft | null) => void;
  action: Action;
}) {
  const text = draft?.text ?? "";
  const version = draft ? draft.version : (job.source_hash ?? null);
  const stale = Boolean(text && version !== (job.source_hash ?? null));
  if (!evidenceInputAllowed(job)) return null;
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
            이 기사에서 직접 확인한 공개 원문만 입력하세요. 등록하면 현재 승인과
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
            입력한 텍스트는 현재 설정된 Gemini{model ? ` (${model})` : ""}로
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
            onChange={(event) =>
              onChange(
                event.target.value
                  ? { text: event.target.value, version, acknowledged: false }
                  : null,
              )
            }
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
                onChange({ text, version, acknowledged: event.target.checked })
              }
            />
            <span>이 기사의 공개 원문이며 재사용할 권한을 확인했습니다.</span>
          </label>
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
          <button
            className="button secondary"
            disabled={locked || !valid}
            onClick={() =>
              void action(
                "공개 원문 근거 등록",
                async () => {
                  await api.registerEvidence(job.id, text, version);
                  onChange(null);
                },
                "공개 원문을 등록하고 근거 추출·새 원고 작업을 요청했습니다. 생성 완료와 승인은 별도입니다.",
              )
            }
          >
            근거 등록하고 새 원고 만들기
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
  action,
}: {
  tasks: Task[];
  jobs: Job[];
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
        const reason = retryBlockedReason(task, job, tasks);
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
  blog: "블로그",
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
export function IdeaBank({ onSelected, refreshKey = 0 }: { onSelected?: (job: Job) => void; refreshKey?: number }) {
  const [ideas, setIdeas] = useState<Idea[]>([]);
  const [error, setError] = useState("");
  const [busy, setBusy] = useState<string | null>(null);
  async function load() {
    try {
      setIdeas((await api.ideas()).ideas);
      setError("");
    } catch (cause) {
      setError(cause instanceof Error ? cause.message : "기획 은행을 읽지 못했습니다.");
    }
  }
  useEffect(() => {
    void load();
  }, [refreshKey]);
  async function choose(id: string) {
    setBusy(id);
    try {
      const result = await api.selectIdea(id);
      onSelected?.(result.job);
      await load();
    } catch (cause) {
      setError(cause instanceof Error ? cause.message : "기획을 선택하지 못했습니다.");
    } finally {
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
            {idea.next_exam && <span className="idea-dday">{dDayLabel(idea.next_exam)}</span>}
            {typeof idea.timeliness === "number" && (
              <div className="idea-timeliness" aria-label={`시의성 ${timelinessPercent(idea.timeliness)}%`}>
                <span>시의성</span>
                <div className="progress-track">
                  <span style={{ width: `${timelinessPercent(idea.timeliness)}%` }} />
                </div>
                <span>{timelinessPercent(idea.timeliness)}%</span>
              </div>
            )}
            {idea.blocked.length > 0 && <p>막힌 이유: {idea.blocked.join(", ")}</p>}
            <button
              className="button secondary"
              type="button"
              disabled={idea.blocked.length > 0 || idea.state === "selected" || busy === idea.id}
              onClick={() => void choose(idea.id)}
            >
              {idea.state === "selected" ? "선택됨" : "이 기획으로 작업 만들기"}
            </button>
          </li>
        ))}
      </ol>
    </section>
  );
}
