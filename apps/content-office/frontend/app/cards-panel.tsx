"use client";

import { useCallback, useEffect, useState } from "react";
import { api } from "../lib/api";
import { formatDate, safeArtifactUrl, sourceApproved } from "../lib/workflow";
import type { Action, Cards, Job } from "../lib/types";
import { Icon } from "./icons";

const POLL_MS = 4_000;
const POLL_LIMIT = 30;

/** 승인 원고 → 카드뉴스 6~8장. 넘침·오탈자 검사 결과를 함께 보여줍니다. */
export function CardsPanel({ job, busy, action, blockedReason }: { job: Job; busy: boolean; action: Action; blockedReason?: string | null }) {
  const [cards, setCards] = useState<Cards | null>(null);
  const [loadError, setLoadError] = useState("");
  const [pending, setPending] = useState<{ before: string } | null>(null);
  const [images, setImages] = useState(true);
  const [unavailableImages, setUnavailableImages] = useState<string[]>([]);
  const approved = sourceApproved(job.state) && job.source_approval?.decision === "approved" && job.source_approval.version === job.source_hash;

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
      () => api.requestCards(job.id, images ? undefined : false),
      images
        ? "선택한 배경 이미지 프로필로 카드뉴스 생성을 요청했습니다. 이미지 없음이면 글자 카드만 만듭니다."
        : "카드뉴스 생성을 요청했습니다. 결과가 저장되면 아래에 표시됩니다.",
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
          <label className="card-image-toggle">
            <input type="checkbox" checked={images} onChange={(event) => setImages(event.target.checked)} />
            제작 설정의 배경 이미지 프로필 사용 (이미지 없음이면 글자 카드)
          </label>
          <button className="button secondary small" type="button" disabled={busy || Boolean(blockedReason) || !approved || Boolean(pending)} onClick={() => void generate()}>
            {pending ? "생성 중" : stale ? "현재 원고로 다시 생성" : cards ? "다시 생성" : "카드뉴스 생성"}
          </button>
          <button className="button text small" type="button" disabled={busy} onClick={() => { setUnavailableImages([]); void load(); }} aria-label="카드뉴스 새로고침">
            <Icon name="refresh" size={14} className={pending ? "spin" : ""} />
            새로고침
          </button>
          {cards && !stale && count >= 6 && count <= 8 && cards.slides.every((slide) => slide.artifact_id) && (
            <a className="button secondary small"
              href={`/api/jobs/${encodeURIComponent(job.id)}/cards/archive?version=${cards.version}&source_hash=${encodeURIComponent(cards.source_hash)}`}
              download aria-label={`카드뉴스 ${count}장 전체 ZIP 다운로드`}>
              <Icon name="download" size={14} />
              전체 {count}장 ZIP 내려받기
            </a>
          )}
        </div>
      </div>
      <p className="muted">카드뉴스만 전체 ZIP으로 받거나 글·영상과 함께 통합 검토 ZIP으로 받을 수 있습니다. 검사 이슈도 포함되며, 출고 승인②와 플랫폼 업로드는 별도입니다.</p>
      <p className="muted">원고 승인에서 카드뉴스를 선택하면 검사에 통과한 현재 원고의 6~8장을 정식 제작물에 넣습니다. 여기서 별도로 다시 만든 카드는 기존 출고 승인본을 바꾸지 않습니다.</p>
      {approved && job.manifest?.hash && <a className="button secondary small" href={`/api/jobs/${encodeURIComponent(job.id)}/review-package`}>글·영상·카드 검토 ZIP 받기</a>}
      {!approved && <div className="notice" role="status"><span>현재 원고의 승인①이 없어 새 카드를 만들 수 없습니다. 수정한 원고를 확인하고, 제작 항목에서 카드뉴스를 선택해 승인하세요. <a href={`/scripts/${encodeURIComponent(job.id)}`}>현재 원고 검토·승인①으로 이동</a></span></div>}
      {approved && blockedReason && <p className="notice" role="status">{blockedReason}</p>}
      {pending && <p className="muted">생성 요청을 받았습니다. 작업자가 저장하면 자동으로 표시됩니다.</p>}
      {loadError && <p className="field-error">{loadError}</p>}
      {stale && (
        <div className="notice">
          <Icon name="alert" size={16} />
          <span>이전 원고({cards?.source_hash.slice(0, 8)})로 만든 카드 미리보기입니다. {approved ? "현재 승인 원고로 다시 생성할 수 있습니다." : "새 카드는 현재 원고를 승인①한 뒤 만들 수 있습니다."}</span>
        </div>
      )}
      {cards && (
        <>
          <div className="derived-meta">
            <span className={`badge ${cards.checks.passed ? "green" : "orange"}`}>{stale ? "이전 원고 · " : ""}{cards.checks.passed ? "검사 통과" : `검사 이슈 ${cards.checks.issues.length}개`}</span>
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
                    {url && !unavailableImages.includes(url) ? <img src={url} alt={`${slide.index}장 · ${slide.title}`} loading="lazy" onError={() => setUnavailableImages((previous) => previous.includes(url) ? previous : [...previous, url])} /> : <span className="muted">{url ? "이미지를 불러오지 못했습니다. 새로고침으로 다시 확인하세요." : "이미지 없음"}</span>}
                  </div>
                  <span className="thumbnail-number">{String(slide.index).padStart(2, "0")}</span>
                  <h4>{slide.title}</h4>
                  <p>{slide.body}</p>
                  {url && (
                    <a href={url} download aria-label={`${slide.index}장 다운로드`}>
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
