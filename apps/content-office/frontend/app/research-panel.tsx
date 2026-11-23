"use client";

import Link from "next/link";
import { useEffect, useId, useState } from "react";
import { api } from "../lib/api";
import {
  candidateMeta, libraryLine, researchBadge, safeOriginRef, savedCandidateNote, splitCandidates,
  type ResearchCandidate, type ResearchPlan, type ResearchResult, type SourceArea,
} from "../lib/source-library";
import { loadSourceAreas } from "./save-to-source-library";
import styles from "./source-library.module.css";

type Props = {
  ideaId: string;
  title: string;
  summary?: string;
  /** 서버가 기획 목록에 붙여 준 조사 기준. 없으면 찾기 버튼만 보여 줍니다. */
  plan?: ResearchPlan;
};

/**
 * 기획 카드의 외부 조사 칸. 주제가 어떤 주장을 하는지에 따라 조사가 필요한지 알려 주고,
 * 누르면 무료 공개 출처에서 후보를 찾아 보여 줍니다. 운영자가 고른 후보만 자료 창고에 들어가고 근거로 켜집니다.
 */
export function ResearchPanel({ ideaId, title, summary = "", plan }: Props) {
  const [open, setOpen] = useState(false);
  const [result, setResult] = useState<ResearchResult | null>(null);
  const [areas, setAreas] = useState<SourceArea[]>([]);
  const [area, setArea] = useState(plan?.area ?? "");
  const [query, setQuery] = useState("");
  const [busy, setBusy] = useState<"search" | "save" | null>(null);
  const [error, setError] = useState("");
  const [picked, setPicked] = useState<string[]>([]);
  const [saved, setSaved] = useState<Record<string, { ok: boolean; text: string }>>({});
  const id = useId();
  const shown = result?.plan ?? plan;
  const badge = shown ? researchBadge(shown.need) : null;
  const groups = splitCandidates(result?.candidates ?? []);
  const waiting = picked.filter((key) => !saved[key]);
  const savedAny = Object.values(saved).some((row) => row.ok);

  useEffect(() => {
    if (!open || areas.length) return;
    let alive = true;
    loadSourceAreas().then((list) => { if (alive) setAreas(list); }).catch(() => undefined);
    return () => { alive = false; };
  }, [open, areas.length]);

  async function search(force: boolean) {
    if (busy) return;
    setOpen(true);
    setBusy("search");
    setError("");
    try {
      const found = await api.runResearch({ title, summary, ...(area ? { area } : {}), ...(query.trim() ? { query: query.trim() } : {}), force });
      setResult(found);
      setPicked([]);
      setSaved({});
      if (!area) setArea(found.plan.area);
      if (!query.trim()) setQuery(found.queries.english);
    } catch (cause) {
      setError(cause instanceof Error ? cause.message : "후보를 찾지 못했습니다. 잠시 뒤 다시 눌러 주세요.");
    } finally {
      setBusy(null);
    }
  }

  async function save() {
    if (busy || !area || !result) return;
    setBusy("save");
    setError("");
    for (const candidate of result.candidates.filter((row) => waiting.includes(row.key))) {
      try {
        const entry = { area, origin: "research" as const, origin_ref: safeOriginRef(ideaId), lane: candidate.lane, use_as_evidence: true as const };
        const [row] = (await api.addSourceLinks([candidate.url], entry, candidate.title)).results;
        setSaved((current) => ({ ...current, [candidate.key]: savedCandidateNote(row) }));
      } catch (cause) {
        setSaved((current) => ({ ...current, [candidate.key]: { ok: false, text: cause instanceof Error ? cause.message : "넣지 못했습니다." } }));
      }
    }
    setBusy(null);
  }

  function toggle(key: string, on: boolean) {
    setPicked((current) => (on ? [...new Set([...current, key])] : current.filter((value) => value !== key)));
  }

  function list(heading: string, help: string, rows: ResearchCandidate[]) {
    if (!rows.length) return null;
    return (
      <div className={styles.candidateGroup}>
        <h4>{heading} <span>{help}</span></h4>
        <ul className={styles.candidates}>
          {rows.map((row) => {
            const outcome = saved[row.key];
            return (
              <li key={row.key} data-picked={picked.includes(row.key)}>
                <label>
                  <input type="checkbox" checked={picked.includes(row.key)} disabled={busy !== null || !!outcome} onChange={(event) => toggle(row.key, event.target.checked)} />
                  <span>
                    <strong>{row.title}</strong>
                    <small>{candidateMeta(row)}</small>
                  </span>
                </label>
                {row.snippet && <p>{row.snippet}</p>}
                <p className={styles.candidateFlags}>
                  <a href={row.url} target="_blank" rel="noopener noreferrer">원문 열기 ↗</a>
                  {row.in_library && <span>이미 창고에 있어요. 고르면 근거로 켜져요.</span>}
                  {row.needs_paste && <span>영상은 창고에서 자막을 붙여 넣어야 근거로 쓸 수 있어요.</span>}
                </p>
                {outcome && <p className={outcome.ok ? styles.saveDone : styles.saveError} role={outcome.ok ? undefined : "alert"}>{outcome.text}</p>}
              </li>
            );
          })}
        </ul>
      </div>
    );
  }

  return (
    <div className={styles.research} data-need={shown?.need ?? "unknown"}>
      <div className={styles.researchHead}>
        {badge && <span className={`badge ${badge.tone}`}>{badge.label}</span>}
        {shown && <span className={styles.researchReason}>{shown.summary.replace(/^[^:]+:\s*/, "")}</span>}
        {!open && (
          <button className={shown && shown.need === "none" ? "button text small" : "button secondary small"} type="button" disabled={busy !== null}
            onClick={() => void search(shown?.need === "none")}>
            {shown?.need === "none" ? "그래도 찾아보기" : "외부 조사 후보 찾기"}
          </button>
        )}
      </div>
      {shown?.warning && <p className={styles.saveError}>{shown.warning}</p>}
      {open && (
        <div className={styles.researchBody}>
          <div className={styles.researchControls}>
            <label htmlFor={`${id}-area`}>분야</label>
            <select id={`${id}-area`} value={area} disabled={busy !== null} onChange={(event) => setArea(event.target.value)}>
              {!area && <option value="">분야를 고르세요</option>}
              {(areas.length ? areas : shown ? [{ id: shown.area, label: shown.area_label, items: 0 }] : []).map((choice) => (
                <option key={choice.id} value={choice.id}>{choice.label}</option>
              ))}
            </select>
            <label htmlFor={`${id}-query`}>검색어</label>
            <input id={`${id}-query`} value={query} maxLength={200} disabled={busy !== null} placeholder="논문과 저장소는 영어 낱말로 찾아요"
              onChange={(event) => setQuery(event.target.value)} onKeyDown={(event) => { if (event.key === "Enter") { event.preventDefault(); void search(true); } }} />
            <button className="button secondary small" type="button" disabled={busy !== null} onClick={() => void search(true)}>{busy === "search" ? "찾는 중…" : "다시 찾기"}</button>
            <button className="button text small" type="button" disabled={busy !== null} onClick={() => setOpen(false)}>접기</button>
          </div>
          <div aria-live="polite">
            {busy === "search" && <p className={styles.hint}>무료 공개 출처에서 찾고 있어요. 10초쯤 걸려요.</p>}
            {error && <p className={styles.saveError} role="alert">{error}</p>}
            {result && busy !== "search" && (
              <>
                <p className={styles.hint}>{libraryLine(result.library)}</p>
                {result.notes.length > 0 && <ul className={styles.researchNotes}>{result.notes.map((note) => <li key={note}>{note}</li>)}</ul>}
                {result.searched && result.candidates.length === 0 && <p className={styles.hint}>맞는 후보가 없어요. 검색어를 바꿔서 다시 찾아 보세요.</p>}
              </>
            )}
          </div>
          {result && busy !== "search" && (
            <>
              {list("사실 근거 후보", "공식 문서, 논문, 저장소. 수치와 사실 주장을 받쳐요.", groups.fact)}
              {list("사례·참고 후보", "등록한 크리에이터. 출처를 밝혀 사례로만 소개해요.", groups.example)}
              {result.candidates.length > 0 && (
                <div className={styles.researchSave}>
                  <button className="button primary small" type="button" disabled={busy !== null || !area || waiting.length === 0} onClick={() => void save()}>
                    {busy === "save" ? "창고에 넣는 중…" : `고른 ${waiting.length}건을 창고에 넣고 근거로 쓰기`}
                  </button>
                  {!area && <span className={styles.saveError}>분야를 먼저 골라 주세요.</span>}
                  {savedAny && (
                    <span className={styles.saveDone}>
                      1분쯤 뒤 이 카드의 근거 찾기를 다시 누르면 방금 넣은 자료가 후보로 나와요. <Link href="/sources">자료 창고 열기</Link>
                    </span>
                  )}
                </div>
              )}
            </>
          )}
        </div>
      )}
    </div>
  );
}
