"use client";

import { useCallback, useEffect, useState } from "react";
import { api } from "../lib/api";
import { storyMood } from "../lib/noeri";
import type { Action, Job, MemoryStory } from "../lib/types";
import { formatDate, safeArtifactUrl, sourceApproved } from "../lib/workflow";
import { Icon } from "./icons";
import { Noeri } from "./noeri";

const POLL_MS = 4_000;
const POLL_LIMIT = 45;
const KIND_LABEL: Record<string, string> = { cover: "표지", page: "장면", recall: "떠올려 보기", answers: "정답" };

/** 승인 원고 → 뇌리가 주인공인 그림 기억 이야기. 글은 모델이 쓰고 그림은 코드가 그립니다(이미지 비용 0원). */
export function MemoryStoryPanel({ job, busy, action }: { job: Job; busy: boolean; action: Action }) {
  const [story, setStory] = useState<MemoryStory | null>(null);
  const [loadError, setLoadError] = useState("");
  const [pending, setPending] = useState<{ before: string } | null>(null);
  const [showAnswers, setShowAnswers] = useState(false);
  const [large, setLarge] = useState<string | null>(null);
  const approved = sourceApproved(job.state);

  const load = useCallback(async () => {
    try {
      const result = await api.story(job.id);
      setStory(result.story);
      setLoadError("");
      return result.story;
    } catch (cause) {
      setLoadError(cause instanceof Error ? cause.message : "그림 기억 이야기를 불러오지 못했습니다.");
      return null;
    }
  }, [job.id]);

  useEffect(() => {
    void load();
  }, [load, job.updated_at, job.source_hash]);

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
    const ok = await action("그림 기억 이야기 만들기", () => api.requestStory(job.id),
      "그림 기억 이야기를 요청했습니다. 작업자가 글을 쓰고 장면을 그리면 아래에 표시됩니다.");
    if (ok === true) setPending({ before: story?.generated_at ?? "" });
  }

  const stale = Boolean(story && !story.current);
  const pages = story?.files ?? [];
  const sheet = story?.sheet_url ? safeArtifactUrl(story.sheet_url) : null;
  const mood = storyMood(story, Boolean(pending));

  return (
    <section className="editor-panel derived-panel story-panel" aria-label="그림 기억 이야기">
      <div className="story-heading">
        <Noeri mood={mood} size={84} label={`뇌리 표정: ${pending ? "만드는 중" : story ? (story.checks.passed ? "검사 통과" : "고칠 곳 있음") : "기다리는 중"}`} />
        <div>
          <span className="eyebrow">그림 기억 이야기 · 이미지 비용 0원</span>
          <h2>뇌리가 주인공인 4~6장 + 떠올려 보기</h2>
          <p className="muted">원고에서 기억할 것 하나를 장면 하나에 묶어요. 글은 글 모델이(퀴즈와 같은 1~2회 호출), 그림은 코드가 그려서 가짜 사람이나 이미지 생성 비용이 없어요.</p>
        </div>
        <div className="derived-actions">
          <button className="button secondary small" type="button" disabled={busy || !approved || Boolean(pending)} onClick={() => void generate()}>
            {story ? "다시 만들기" : "이야기 만들기"}
          </button>
          <button className="button text small" type="button" disabled={busy} onClick={() => void load()} aria-label="그림 기억 이야기 새로고침">
            <Icon name="refresh" size={14} className={pending ? "spin" : ""} />
            새로고침
          </button>
        </div>
      </div>
      <details className="story-why">
        <summary>왜 이렇게 만드나요?</summary>
        <ul>
          <li><strong>글과 그림을 같이</strong> 보면 한쪽만 볼 때보다 오래 남아요(이중 부호화). 그래서 한 장에 기억할 것 하나, 장면 하나만 둬요.</li>
          <li><strong>마지막은 교훈 대신 떠올려 보기</strong>예요. 답을 꺼내 보는 연습(인출 연습)이 다시 읽기보다 기억에 남아요. 정답은 다음 장에 있어요.</li>
          <li><strong>그림 계약</strong>: 글에 나온 물건(책, 노트, 러닝머신…)이 그 장 그림에 없으면 검사가 잡아요. 원고에 없는 숫자도 잡아요.</li>
          <li>방법은 connect-ai-writer의 그림책 동화(story.mjs)에서 배웠고, 동화 대신 HeoBrain 학습용으로 바꿔 새로 만들었어요.</li>
        </ul>
      </details>
      {!approved && <p className="muted">① 원고 승인 뒤에 만들 수 있어요. 출고 승인②와 게시는 따로 사람이 해요.</p>}
      {pending && <p className="muted" role="status">요청을 받았어요. 작업 시간이 열려 있고 작업자가 켜져 있으면 1~2분 안에 그려져요.</p>}
      {loadError && <p className="field-error">{loadError}</p>}
      {stale && (
        <div className="notice error">
          <Icon name="alert" size={16} />
          <span>이전 원고({story?.source_hash.slice(0, 8)})로 만든 이야기예요. 현재 원고로 다시 만드세요.</span>
        </div>
      )}
      {story && (
        <>
          <div className="derived-meta">
            <span className={`badge ${story.checks.passed ? "green" : "orange"}`}>{story.checks.passed ? "검사 통과" : `고칠 곳 ${story.checks.issues.length}`}</span>
            <span className="muted">
              {story.title} · 버전 {story.version} · {formatDate(story.generated_at, true)} · 장면 {story.pages.length}장{story.refined ? " · 한 번 고쳐 씀" : ""}
            </span>
            {sheet && <a className="button text small" href={sheet} target="_blank" rel="noreferrer">한 장에 모아 보기</a>}
          </div>
          {story.checks.issues.length > 0 && (
            <ul className="derived-issues" role="alert">
              {story.checks.issues.map((issue, i) => <li key={i}>{issue}</li>)}
            </ul>
          )}
          <ol className="story-strip" aria-label="그림 기억 이야기 장면 순서">
            {pages.map((file, i) => {
              const url = file.url ? safeArtifactUrl(file.url) : null;
              const page = file.kind === "page" && file.index ? story.pages[file.index - 1] : null;
              return (
                <li key={file.artifact_id} className={`story-card story-${file.kind}`}>
                  {url ? (
                    <button type="button" className="story-thumb" onClick={() => setLarge(url)} aria-label={`${i + 1}번째 장 크게 보기`}>
                      <img src={url} alt={page ? `${page.anchor}: ${page.text}` : KIND_LABEL[file.kind] ?? file.kind} loading="lazy" />
                    </button>
                  ) : <div className="story-thumb missing">그림 없음</div>}
                  <span className="story-kind">{String(i + 1).padStart(2, "0")} · {KIND_LABEL[file.kind] ?? file.kind}{file.truncated ? " · 글이 잘림" : ""}</span>
                  {page && <span className="story-anchor">기억할 것 <b>{page.anchor}</b></span>}
                </li>
              );
            })}
          </ol>
          <div className="story-recall">
            <h3>떠올려 보기</h3>
            <ol>{story.recall.map((item, i) => <li key={i}>{item.question}{showAnswers && <strong className="story-answer"> → {item.answer}</strong>}</li>)}</ol>
            <label className="derived-toggle">
              <input type="checkbox" checked={showAnswers} onChange={(e) => setShowAnswers(e.target.checked)} />
              정답 보기
            </label>
          </div>
          <p className="muted small">{story.note}</p>
        </>
      )}
      {!story && !loadError && approved && !pending && <p className="muted">아직 만든 이야기가 없어요. 카드뉴스와 따로, 원하는 원고에서만 만들어요.</p>}
      {large && (
        <div className="story-lightbox" role="dialog" aria-modal="true" aria-label="장면 크게 보기" tabIndex={-1}
          onClick={() => setLarge(null)} onKeyDown={(e) => { if (e.key === "Escape") setLarge(null); }}>
          <img src={large} alt="크게 본 장면" />
          <button type="button" className="button secondary" onClick={() => setLarge(null)} autoFocus>닫기</button>
        </div>
      )}
    </section>
  );
}
