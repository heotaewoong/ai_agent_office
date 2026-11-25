"use client";

import Link from "next/link";
import { useEffect, useId, useRef, useState } from "react";
import { api } from "../lib/api";
import {
  autoLine, candidateMeta, choiceLine, confirmedKind, kindNotice, libraryLine, mergeTavily, researchBadge, researchKinds, safeOriginRef, savedCandidateNote,
  splitCandidates, tavilyLabel, verdictBadge, type ResearchCandidate, type ResearchKind, type ResearchPlan, type ResearchResult, type SourceArea,
  type TavilyUsage,
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
 * 기획 카드의 외부 조사 칸. 글 유형과 분야는 사람이 고르고, 고르기 전에는 서버가 제목으로 추측한 값을 기본값으로만 보여 줍니다.
 * 주제의 주장과 고른 유형에 따라 조사가 필요한지 알려 주고, 누르면 무료 공개 출처에서 후보를 찾아 보여 줍니다.
 * 기획을 열면 서버가 자료 창고를 먼저 보고 판정(맞음, 애매, 틀림)에 따라 바깥 후보를 대신 찾아 둡니다(기획마다 한 번, 결과 저장).
 * 운영자가 고른 후보만 자료 창고에 들어가고 근거로 켜집니다.
 */
export function ResearchPanel({ ideaId, title, summary = "", plan }: Props) {
  const [current, setCurrent] = useState<ResearchPlan | undefined>(plan);
  const [open, setOpen] = useState(false);
  const [choosing, setChoosing] = useState(false);
  const [draft, setDraft] = useState<{ kind: ResearchKind | ""; area: string }>({ kind: "", area: "" });
  const [result, setResult] = useState<ResearchResult | null>(null);
  const [areas, setAreas] = useState<SourceArea[]>([]);
  const [query, setQuery] = useState("");
  const [busy, setBusy] = useState<"search" | "tavily" | "save" | "choice" | null>(null);
  const [tavily, setTavily] = useState<TavilyUsage | null>(null);
  const [error, setError] = useState("");
  const [picked, setPicked] = useState<string[]>([]);
  const [saved, setSaved] = useState<Record<string, { ok: boolean; text: string }>>({});
  const id = useId();
  const shown = result?.plan ?? current;
  const area = shown?.area ?? "";
  const badge = shown ? researchBadge(shown.need) : null;
  const notice = shown ? kindNotice(shown) : null;
  const groups = splitCandidates(result?.candidates ?? []);
  const waiting = picked.filter((key) => !saved[key]);
  const savedAny = Object.values(saved).some((row) => row.ok);
  const verdict = verdictBadge(result?.verdict);
  const autoNote = result ? autoLine(result) : null;
  const autoStarted = useRef(false);

  // 기획 목록을 새로 받으면 서버가 저장된 선택으로 다시 계산한 기준을 씁니다.
  useEffect(() => { setCurrent(plan); }, [plan]);

  // 조사 결과를 연 뒤에만 Tavily 사용량(키가 있는지와 이번 달 횟수)을 묻습니다. 키 자체는 오지 않습니다.
  useEffect(() => {
    if (!open || tavily) return;
    let alive = true;
    api.tavilyUsage().then((usage) => { if (alive) setTavily(usage); }).catch(() => undefined);
    return () => { alive = false; };
  }, [open, tavily]);

  useEffect(() => {
    if (!choosing || areas.length) return;
    let alive = true;
    loadSourceAreas().then((list) => { if (alive) setAreas(list); }).catch(() => { if (alive) setError("분야 목록을 불러오지 못했습니다."); });
    return () => { alive = false; };
  }, [choosing, areas.length]);

  function startChoosing() {
    setDraft({ kind: shown?.kind ?? "", area: shown?.area ?? "" });
    setError("");
    setChoosing(true);
  }

  async function saveChoice(kind: ResearchKind | "", chosenArea: string) {
    if (busy || !kind || !chosenArea) return;
    setBusy("choice");
    setError("");
    try {
      await api.saveResearchChoice(ideaId, { kind, area: chosenArea });
      const [next] = (await api.researchPlans([{ id: ideaId, title, summary, kind, area: chosenArea }])).plans;
      if (next) {
        setCurrent(next);
        setResult((value) => (value ? { ...value, plan: next } : value));
      }
      setChoosing(false);
    } catch (cause) {
      setError(cause instanceof Error ? cause.message : "고른 값을 저장하지 못했습니다. 잠시 뒤 다시 눌러 주세요.");
    } finally {
      setBusy(null);
    }
  }

  async function search(force: boolean, override?: string, auto = false) {
    if (busy || shown?.blocked) return;
    const text = (override ?? query).trim();
    const kind = confirmedKind(shown);
    setOpen(true);
    setBusy("search");
    setError("");
    try {
      // 사람이 고른 값만 보냅니다. 추측한 값은 서버가 같은 방법으로 다시 추측합니다.
      const found = await api.runResearch({
        id: safeOriginRef(ideaId), title, summary, ...(shown && !shown.area_guessed ? { area: shown.area } : {}), ...(kind ? { kind } : {}),
        ...(text ? { query: text } : {}), ...(auto ? { auto: true } : { force }),
      });
      setResult(found);
      if (found.tavily) setTavily(found.tavily);
      setPicked([]);
      setSaved({});
      setQuery(text || found.queries.english);
    } catch (cause) {
      setError(cause instanceof Error ? cause.message : "후보를 찾지 못했습니다. 잠시 뒤 다시 눌러 주세요.");
    } finally {
      setBusy(null);
    }
  }

  // 기획을 열면 한 번 자동 조사를 부릅니다. 범위 밖(W5)과 내 경험 글, 기획 ID가 없는 카드는 부르지 않습니다.
  useEffect(() => {
    if (autoStarted.current || !plan || plan.blocked || plan.experience_first || !safeOriginRef(ideaId)) return;
    autoStarted.current = true;
    void search(false, undefined, true);
  }, [plan, ideaId]);

  async function searchTavily() {
    if (busy || shown?.blocked || !result || !tavily?.has_key || tavily.remaining <= 0) return;
    const text = query.trim();
    setBusy("tavily");
    setError("");
    try {
      // 사람이 누를 때만 1회 부릅니다. 검색어는 기획 제목이나 적어 둔 검색어뿐이고 개인 DB 문장은 보내지 않습니다.
      const found = await api.runTavily({ id: safeOriginRef(ideaId), title, ...(text && text !== result.queries.english ? { query: text } : {}) });
      setTavily(found.tavily);
      setResult((value) => (value ? mergeTavily(value, found) : value));
    } catch (cause) {
      setError(cause instanceof Error ? cause.message : "Tavily로 찾지 못했습니다. 자동으로 다시 부르지 않아요.");
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
        setSaved((value) => ({ ...value, [candidate.key]: savedCandidateNote(row) }));
      } catch (cause) {
        setSaved((value) => ({ ...value, [candidate.key]: { ok: false, text: cause instanceof Error ? cause.message : "넣지 못했습니다." } }));
      }
    }
    setBusy(null);
  }

  function toggle(key: string, on: boolean) {
    setPicked((value) => (on ? [...new Set([...value, key])] : value.filter((item) => item !== key)));
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
                  {row.idea_only && <span>Tavily로 찾은 글이에요. 사례로만 쓰고 사실 근거로 쓰려면 원문을 직접 확인해 주세요.</span>}
                </p>
                {outcome && <p className={outcome.ok ? styles.saveDone : styles.saveError} role={outcome.ok ? undefined : "alert"}>{outcome.text}</p>}
              </li>
            );
          })}
        </ul>
      </div>
    );
  }

  const guessed = !!shown && (shown.kind_guessed || shown.area_guessed);
  const help = researchKinds.find((choice) => choice.id === draft.kind)?.help;
  return (
    <div className={styles.research} data-need={shown?.need ?? "unknown"}>
      <div className={styles.researchHead}>
        {badge && <span className={`badge ${badge.tone}`}>{badge.label}</span>}
        {shown && <span className={styles.researchReason}>{shown.summary.replace(/^[^:]+:\s*/, "")}</span>}
        {!open && !shown?.blocked && (
          <button className={shown && shown.need === "none" ? "button text small" : "button secondary small"} type="button" disabled={busy !== null}
            onClick={() => void search(shown?.need === "none")}>
            {shown?.need === "none" ? "그래도 찾아보기" : "외부 조사 후보 찾기"}
          </button>
        )}
      </div>
      {shown && !choosing && (
        <p className={styles.researchChoice}>
          <span>{choiceLine(shown)}</span>
          {guessed && (
            <button className="button text small" type="button" disabled={busy !== null} onClick={() => void saveChoice(shown.kind, shown.area)}>
              {busy === "choice" ? "저장 중…" : "이대로 확정"}
            </button>
          )}
          <button className="button text small" type="button" disabled={busy !== null} onClick={startChoosing}>바꾸기</button>
        </p>
      )}
      {choosing && (
        <div className={styles.researchControls}>
          <label htmlFor={`${id}-kind`}>글 유형</label>
          <select id={`${id}-kind`} value={draft.kind} disabled={busy !== null} onChange={(event) => setDraft({ ...draft, kind: event.target.value as ResearchKind })}>
            {!draft.kind && <option value="">글 유형을 고르세요</option>}
            {researchKinds.map((choice) => <option key={choice.id} value={choice.id}>{choice.label}</option>)}
          </select>
          <label htmlFor={`${id}-area`}>분야</label>
          <select id={`${id}-area`} value={draft.area} disabled={busy !== null} onChange={(event) => setDraft({ ...draft, area: event.target.value })}>
            {!draft.area && <option value="">분야를 고르세요</option>}
            {(areas.length ? areas : shown ? [{ id: shown.area, label: shown.area_label, items: 0 }] : []).map((choice) => (
              <option key={choice.id} value={choice.id}>{choice.label}</option>
            ))}
          </select>
          <button className="button secondary small" type="button" disabled={busy !== null || !draft.kind || !draft.area}
            onClick={() => void saveChoice(draft.kind, draft.area)}>{busy === "choice" ? "저장 중…" : "저장"}</button>
          <button className="button text small" type="button" disabled={busy !== null} onClick={() => setChoosing(false)}>취소</button>
          {help && <span className={styles.researchChoice}>{help}</span>}
        </div>
      )}
      {notice && <p className={styles.saveError}>{notice}</p>}
      {shown?.warning && <p className={styles.saveError}>{shown.warning}</p>}
      {error && !open && <p className={styles.saveError} role="alert">{error}</p>}
      {open && (
        <div className={styles.researchBody}>
          <div className={styles.researchControls}>
            <label htmlFor={`${id}-query`}>검색어</label>
            <input id={`${id}-query`} value={query} maxLength={200} disabled={busy !== null} placeholder="비워 두면 영어 검색어를 자동으로 만들어요"
              onChange={(event) => setQuery(event.target.value)} onKeyDown={(event) => { if (event.key === "Enter") { event.preventDefault(); void search(true); } }} />
            <button className="button secondary small" type="button" disabled={busy !== null || !!shown?.blocked} onClick={() => void search(true)}>{busy === "search" ? "찾는 중…" : "다시 찾기"}</button>
            {result && (
              <button className="button secondary small" type="button" title="사람이 누를 때만 한 번 찾아요. 자동으로 다시 부르지 않아요."
                disabled={busy !== null || !!shown?.blocked || !tavily?.has_key || (tavily?.remaining ?? 0) <= 0} onClick={() => void searchTavily()}>
                {busy === "tavily" ? "Tavily로 찾는 중…" : tavilyLabel(tavily)}
              </button>
            )}
            <button className="button text small" type="button" disabled={busy !== null} onClick={() => setOpen(false)}>접기</button>
          </div>
          {shown && shown.blanks.length > 0 && (
            <div className={styles.researchBlanks}>
              <h4>{shown.kind_guessed ? "추측한 글 유형에서 채울 빈칸" : `${shown.kind_label} 글에서 채울 빈칸`}</h4>
              <ul>{shown.blanks.map((blank) => <li key={blank}>{blank}</li>)}</ul>
            </div>
          )}
          <div aria-live="polite">
            {busy === "search" && <p className={styles.hint}>무료 공개 출처에서 찾고 있어요. 10초쯤 걸려요.</p>}
            {error && <p className={styles.saveError} role="alert">{error}</p>}
            {result && busy !== "search" && (
              <>
                <p className={styles.hint}>{libraryLine(result.library)}</p>
                {verdict && (
                  <p className={styles.hint}>
                    <span className={`badge ${verdict.tone}`}>{verdict.label}</span> {result.verdict?.reason}
                    {autoNote ? ` ${autoNote}` : ""}
                  </p>
                )}
                {result.queries.translated && (
                  <p className={styles.researchAlternatives}>
                    <span>한글 주제에 맞는 영어 검색어를 자동으로 만들었어요.{result.queries.alternatives?.length ? " 다른 검색어로도 찾아볼 수 있어요." : ""}</span>
                    {(result.queries.alternatives ?? []).map((choice) => (
                      <button key={choice} className="button text small" type="button" disabled={busy !== null} onClick={() => void search(true, choice)}>{choice}</button>
                    ))}
                  </p>
                )}
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
