"use client";

import { useCallback, useEffect, useState } from "react";
import { api } from "../lib/api";
import { formatDate, safeArtifactUrl, sourceApproved } from "../lib/workflow";
import type { Action, Cards, Job } from "../lib/types";
import { Icon } from "./icons";

const POLL_MS = 4_000;
const POLL_LIMIT = 30;

/** 승인 원고 → 카드뉴스 6~8장. 넘침·오탈자 검사 결과를 함께 보여줍니다. */
export function CardsPanel({ job, busy, action }: { job: Job; busy: boolean; action: Action }) {
  const [cards, setCards] = useState<Cards | null>(null);
  const [loadError, setLoadError] = useState("");
  const [pending, setPending] = useState<{ before: string } | null>(null);
  const approved = sourceApproved(job.state);

  const load = useCallback(async () => {
    try {
      const result = await api.cards(job.id);
      setCards(result.cards);
      setLoadError("");
      return result.cards;
    } catch (cause) {
      setLoadError(cause instanceof Error ? cause.message : "카드뉴스를 불러오지 못했습니다.");
      return null;
    }
  }, [job.id]);

  // 화면의 작업 새로고침(4초)이 작업 변화를 감지할 때마다 결과를 다시 읽습니다. 제작 시작 뒤 자동 생성된 카드뉴스도 이 경로로 들어옵니다.
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
      "카드뉴스 생성",
      () => api.requestCards(job.id),
      "카드뉴스 생성을 요청했습니다. 결과가 저장되면 아래에 표시됩니다.",
    );
    if (ok === true) setPending({ before: cards?.generated_at ?? "" });
  }

  const stale = Boolean(cards && job.source_hash && cards.source_hash !== job.source_hash);
  const count = cards?.slides.length ?? 0;

  return (
    <section className="editor-panel derived-panel cards-panel" aria-label="카드뉴스">
      <div className="section-heading">
        <div>
          <span className="eyebrow">카드뉴스</span>
          <h2>승인 원고로 6~8장</h2>
        </div>
        <div className="derived-actions">
          <button className="button secondary small" type="button" disabled={busy || !approved || Boolean(pending)} onClick={() => void generate()}>
            {cards ? "다시 생성" : "카드뉴스 생성"}
          </button>
          <button className="button text small" type="button" disabled={busy} onClick={() => void load()} aria-label="카드뉴스 새로고침">
            <Icon name="refresh" size={14} className={pending ? "spin" : ""} />
            새로고침
          </button>
        </div>
      </div>
      {!approved && <p className="muted">① 원고 승인 뒤에만 만들 수 있습니다. 장면 배경은 제작 설정의 배경 이미지 프로필을 따르고 한국어 글자는 로컬에서 얹습니다.</p>}
      {pending && <p className="muted">생성 요청을 받았습니다. 작업자가 저장하면 자동으로 표시됩니다.</p>}
      {loadError && <p className="field-error">{loadError}</p>}
      {stale && (
        <div className="notice error">
          <Icon name="alert" size={16} />
          <span>이 카드뉴스는 이전 원고 버전({cards?.source_hash.slice(0, 8)})으로 만들었습니다. 현재 원고로 다시 생성하세요.</span>
        </div>
      )}
      {cards && (
        <>
          <div className="derived-meta">
            <span className={`badge ${cards.checks.passed ? "green" : "orange"}`}>{cards.checks.passed ? "검사 통과" : `검사 이슈 ${cards.checks.issues.length}`}</span>
            <span className={`badge ${count >= 6 && count <= 8 ? "neutral" : "orange"}`}>{count}장</span>
            <span className="muted">
              버전 {cards.version} · {formatDate(cards.generated_at, true)} · 원고 {cards.source_hash.slice(0, 8)}
            </span>
          </div>
          {cards.checks.issues.length > 0 && (
            <ul className="derived-issues" role="alert">
              {cards.checks.issues.map((issue, i) => (
                <li key={i}>{issue}</li>
              ))}
            </ul>
          )}
          <div className="cards-grid">
            {cards.slides.map((slide) => {
              const url = slide.artifact_id ? safeArtifactUrl(`/api/artifacts/${slide.artifact_id}`) : null;
              return (
                <article className="card-slide" key={slide.index}>
                  <div className="card-slide-image">
                    {url ? <img src={url} alt={`${slide.index + 1}장 · ${slide.title}`} loading="lazy" /> : <span className="muted">이미지 없음</span>}
                  </div>
                  <span className="thumbnail-number">{String(slide.index + 1).padStart(2, "0")}</span>
                  <h4>{slide.title}</h4>
                  <p>{slide.body}</p>
                  {url && (
                    <a href={url} download aria-label={`${slide.index + 1}장 다운로드`}>
                      <Icon name="download" size={13} />
                      내려받기
                    </a>
                  )}
                </article>
              );
            })}
          </div>
        </>
      )}
      {!cards && !loadError && approved && !pending && <p className="muted">아직 만든 카드뉴스가 없습니다.</p>}
    </section>
  );
}
