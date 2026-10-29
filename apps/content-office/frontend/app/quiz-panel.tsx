"use client";

import { useCallback, useEffect, useState } from "react";
import { api } from "../lib/api";
import { formatDate, safeArtifactUrl, sourceApproved } from "../lib/workflow";
import type { Action, Job, Quiz } from "../lib/types";
import { Icon } from "./icons";

const POLL_MS = 4_000;
const POLL_LIMIT = 30;

/** 승인 원고 → 4지선다 5문항 JSON. 문제만 만들고 풀기·채점은 스토어의 기존 퀴즈 도구가 합니다. */
export function QuizPanel({ job, busy, action }: { job: Job; busy: boolean; action: Action }) {
  const [quiz, setQuiz] = useState<Quiz | null>(null);
  const [loadError, setLoadError] = useState("");
  const [showAnswers, setShowAnswers] = useState(false);
  const [pending, setPending] = useState<{ before: string } | null>(null);
  const [copied, setCopied] = useState("");
  const approved = sourceApproved(job.state);

  const load = useCallback(async () => {
    try {
      const result = await api.quiz(job.id);
      setQuiz(result.quiz);
      setLoadError("");
      return result.quiz;
    } catch (cause) {
      setLoadError(cause instanceof Error ? cause.message : "퀴즈를 불러오지 못했습니다.");
      return null;
    }
  }, [job.id]);

  // 화면의 작업 새로고침(4초)이 작업 변화를 감지할 때마다 결과를 다시 읽습니다. 제작 시작 뒤 자동 생성된 퀴즈도 이 경로로 들어옵니다.
  useEffect(() => {
    void load();
  }, [load, job.updated_at, job.state, job.manifest?.hash, job.source_hash]);

  useEffect(() => {
    if (!pending) return;
    let tries = 0;
    const timer = setInterval(() => {
      tries += 1;
      void load().then((value) => {
        if ((value && value.generated_at !== pending.before) || tries >= POLL_LIMIT) setPending(null);
      });
    }, POLL_MS);
    return () => clearInterval(timer);
  }, [pending, load]);

  async function generate() {
    const ok = await action(
      "퀴즈 생성",
      () => api.requestQuiz(job.id),
      "퀴즈 생성을 요청했습니다. 결과가 저장되면 아래에 표시됩니다.",
    );
    if (ok === true) setPending({ before: quiz?.generated_at ?? "" });
  }

  const json = quiz ? JSON.stringify(quiz, null, 2) : "";
  async function copyJson() {
    try {
      await navigator.clipboard.writeText(json);
      setCopied("JSON을 복사했습니다.");
    } catch {
      setCopied("복사하지 못했습니다. 아래 JSON을 직접 선택하세요.");
    }
  }
  function downloadJson() {
    const blob = new Blob([json], { type: "application/json" });
    const url = URL.createObjectURL(blob);
    const a = document.createElement("a");
    a.href = url;
    a.download = `quiz-${job.id}-${quiz?.version ?? "v"}.json`;
    a.click();
    URL.revokeObjectURL(url);
  }

  const stale = Boolean(quiz && job.source_hash && quiz.source_hash !== job.source_hash);
  const artifactUrl = quiz?.artifact_id ? safeArtifactUrl(`/api/artifacts/${quiz.artifact_id}`) : null;

  return (
    <section className="editor-panel derived-panel quiz-panel" aria-label="퀴즈 JSON">
      <div className="section-heading">
        <div>
          <span className="eyebrow">퀴즈 JSON</span>
          <h2>승인 원고로 4지선다 5문항</h2>
        </div>
        <div className="derived-actions">
          <button className="button secondary small" type="button" disabled={busy || !approved || Boolean(pending)} onClick={() => void generate()}>
            {quiz ? "다시 생성" : "퀴즈 생성"}
          </button>
          <button className="button text small" type="button" disabled={busy} onClick={() => void load()} aria-label="퀴즈 새로고침">
            <Icon name="refresh" size={14} className={pending ? "spin" : ""} />
            새로고침
          </button>
        </div>
      </div>
      {!approved && <p className="muted">① 원고 승인 뒤에만 만들 수 있습니다. 문제만 만들고 풀기·채점은 스토어의 퀴즈 도구가 합니다.</p>}
      {pending && <p className="muted">생성 요청을 받았습니다. 작업자가 저장하면 자동으로 표시됩니다.</p>}
      {loadError && <p className="field-error">{loadError}</p>}
      {stale && (
        <div className="notice error">
          <Icon name="alert" size={16} />
          <span>이 퀴즈는 이전 원고 버전({quiz?.source_hash.slice(0, 8)})으로 만들었습니다. 현재 원고로 다시 생성하세요.</span>
        </div>
      )}
      {quiz && (
        <>
          <div className="derived-meta">
            <span className={`badge ${quiz.checks.passed ? "green" : "orange"}`}>{quiz.checks.passed ? "검사 통과" : `검사 이슈 ${quiz.checks.issues.length}`}</span>
            <span className="muted">
              버전 {quiz.version} · {formatDate(quiz.generated_at, true)} · 원고 {quiz.source_hash.slice(0, 8)} · {quiz.questions.length}문항
            </span>
          </div>
          {quiz.checks.issues.length > 0 && (
            <ul className="derived-issues" role="alert">
              {quiz.checks.issues.map((issue, i) => (
                <li key={i}>{issue}</li>
              ))}
            </ul>
          )}
          <label className="derived-toggle">
            <input type="checkbox" checked={showAnswers} onChange={(e) => setShowAnswers(e.target.checked)} />
            정답·해설 보기
          </label>
          <ol className="quiz-list">
            {quiz.questions.map((q, index) => (
              <li key={q.id || index}>
                <strong>{q.question}</strong>
                <ol className="quiz-choices" type="A">
                  {q.choices.map((choice, ci) => (
                    <li key={ci} className={showAnswers && ci === q.answer ? "answer" : ""}>
                      {choice}
                      {showAnswers && ci === q.answer && <span className="badge green">정답</span>}
                    </li>
                  ))}
                </ol>
                {showAnswers && (
                  <p className="quiz-explanation">
                    {q.explanation}
                    {q.evidence.length > 0 && <small> · 근거 {q.evidence.join(", ")}</small>}
                  </p>
                )}
              </li>
            ))}
          </ol>
          <div className="derived-actions">
            <button className="button secondary small" type="button" onClick={() => void copyJson()}>
              JSON 복사
            </button>
            <button className="button secondary small" type="button" onClick={downloadJson}>
              <Icon name="download" size={14} />
              JSON 다운로드
            </button>
            {artifactUrl && (
              <a className="button text small" href={artifactUrl} download>
                저장된 파일
              </a>
            )}
            {copied && <span className="muted">{copied}</span>}
          </div>
        </>
      )}
      {!quiz && !loadError && approved && !pending && <p className="muted">아직 만든 퀴즈가 없습니다.</p>}
    </section>
  );
}
