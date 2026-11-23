"use client";

import { useCallback, useEffect, useState } from "react";
import { api } from "../lib/api";
import { sourceLanes, type SourceArea, type SourceLane, type TrustedSource } from "../lib/source-library";
import styles from "./source-library.module.css";

const laneHelp: Record<SourceLane, string> = {
  example: "크리에이터의 유튜브 채널이나 블로그. 방법과 사례를 출처와 함께 소개할 때 써요.",
  fact: "기관 공지나 공식 블로그. 일정, 기준, 새 기능 같은 사실을 확인할 때 써요.",
};

/** 자료 창고의 '믿는 출처' 칸. 여기 등록한 곳의 새 글만 외부 조사 후보로 올라옵니다. */
export function TrustedSources({ active, areas }: { active: boolean; areas: SourceArea[] }) {
  const [sources, setSources] = useState<TrustedSource[] | null>(null);
  const [url, setUrl] = useState("");
  const [name, setName] = useState("");
  const [area, setArea] = useState("");
  const [lane, setLane] = useState<SourceLane>("example");
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState("");
  const [done, setDone] = useState("");
  const [confirm, setConfirm] = useState("");

  const load = useCallback(async () => {
    try {
      setSources((await api.trustedSources()).sources);
    } catch {
      setSources((current) => current ?? []);
    }
  }, []);

  useEffect(() => {
    if (active) void load();
  }, [active, load]);

  async function add() {
    if (busy || !url.trim() || !area) return;
    setBusy(true);
    setError("");
    setDone("");
    try {
      const made = await api.addTrustedSource({ url: url.trim(), area, lane, ...(name.trim() ? { name: name.trim() } : {}) });
      setSources(made.sources);
      setDone(`'${made.source.name}'을 등록했어요. 새 글 ${made.source.recent ?? 0}개를 읽을 수 있어요.`);
      setUrl("");
      setName("");
    } catch (cause) {
      setError(cause instanceof Error ? cause.message : "등록하지 못했습니다.");
    } finally {
      setBusy(false);
    }
  }

  async function remove(id: string) {
    setBusy(true);
    setError("");
    setDone("");
    try {
      setSources((await api.deleteTrustedSource(id)).sources);
    } catch (cause) {
      setError(cause instanceof Error ? cause.message : "지우지 못했습니다.");
    } finally {
      setBusy(false);
      setConfirm("");
    }
  }

  return (
    <section className={styles.card} aria-labelledby="source-trusted-title">
      <h2 id="source-trusted-title">믿는 출처</h2>
      <p className={styles.hint} style={{ marginTop: 0 }}>
        기획 카드에서 외부 조사를 누르면 여기 등록한 곳의 새 글 가운데 주제에 맞는 것만 후보로 보여 줘요. 논문과 GitHub는 등록하지 않아도 찾아요.
      </p>
      <form className={styles.trustedForm} onSubmit={(event) => { event.preventDefault(); void add(); }}>
        <label className={styles.field}>
          주소 <span>유튜브 채널 주소, 블로그 주소, RSS 주소 가운데 하나</span>
          <input className={styles.input} value={url} disabled={busy} inputMode="url" placeholder="https://www.youtube.com/@채널이름" onChange={(event) => setUrl(event.target.value)} />
        </label>
        <div className={styles.tags}>
          <label className={styles.field}>
            분야
            <select className={styles.input} value={area} disabled={busy} onChange={(event) => setArea(event.target.value)}>
              <option value="">분야를 고르세요</option>
              {areas.map((choice) => <option key={choice.id} value={choice.id}>{choice.label}</option>)}
            </select>
          </label>
          <label className={styles.field}>
            쓰임새
            <select className={styles.input} value={lane} disabled={busy} onChange={(event) => setLane(event.target.value as SourceLane)}>
              <option value="example">{sourceLanes.example} (크리에이터)</option>
              <option value="fact">{sourceLanes.fact} (공식 출처)</option>
            </select>
          </label>
          <label className={styles.field}>
            이름 <span>비워 두면 채널 이름을 써요</span>
            <input className={styles.input} value={name} disabled={busy} maxLength={120} onChange={(event) => setName(event.target.value)} />
          </label>
          <button className="button primary" type="submit" disabled={busy || !url.trim() || !area}>{busy ? "확인하는 중…" : "출처 등록"}</button>
        </div>
        <p className={styles.hint}>{laneHelp[lane]}</p>
      </form>
      <div aria-live="polite">
        {done && <p className={styles.success}>{done}</p>}
        {error && <p className={styles.error} role="alert">{error}</p>}
      </div>
      {sources && sources.length === 0 && <p className={styles.hint}>아직 등록한 출처가 없어요. 믿고 보는 채널이나 블로그를 분야별로 넣어 보세요.</p>}
      {sources && sources.length > 0 && (
        <ul className={styles.trustedList}>
          {sources.map((source) => (
            <li key={source.id}>
              <div>
                <a href={source.url} target="_blank" rel="noopener noreferrer">{source.name}</a>
                <div className={styles.meta}>
                  <span className={`badge ${source.lane === "example" ? "orange" : "green"}`}>{source.lane_label}</span>
                  <span className="badge neutral">{source.area_label}</span>
                </div>
              </div>
              {confirm === source.id ? (
                <span className={styles.rowButtons}>
                  <button className="button text small" type="button" disabled={busy} onClick={() => void remove(source.id)}>정말 빼기</button>
                  <button className="button text small" type="button" onClick={() => setConfirm("")}>취소</button>
                </span>
              ) : (
                <button className="button text small" type="button" disabled={busy} onClick={() => setConfirm(source.id)}>빼기</button>
              )}
            </li>
          ))}
        </ul>
      )}
    </section>
  );
}
