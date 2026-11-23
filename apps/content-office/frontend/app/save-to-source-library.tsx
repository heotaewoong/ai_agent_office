"use client";

import Link from "next/link";
import { useEffect, useState } from "react";
import { api } from "../lib/api";
import { safeOriginRef, type SourceArea, type SourceLinkResult, type SourceOrigin } from "../lib/source-library";
import styles from "./source-library.module.css";

let areasCache: Promise<SourceArea[]> | null = null;
function loadAreas() {
  areasCache ??= api.sourceLibrary().then((library) => library.areas).catch((cause) => { areasCache = null; throw cause; });
  return areasCache;
}

type Props = {
  /** 공개 주소를 넣거나(links), 내가 만든 글을 메모로 넣습니다(memo). 둘 중 하나만 줍니다. */
  links?: string[];
  memo?: { title: string; text: string };
  title?: string;
  origin: SourceOrigin;
  originRef?: string;
  defaultArea?: string;
  mine?: boolean;
};

/** 기획·뉴스·제작물 카드에서 자료 창고로 보내는 작은 버튼. 분야를 고른 뒤에만 저장합니다. */
export function SaveToSourceLibrary({ links, memo, title, origin, originRef, defaultArea = "", mine = false }: Props) {
  const [open, setOpen] = useState(false);
  const [areas, setAreas] = useState<SourceArea[]>([]);
  const [area, setArea] = useState(defaultArea);
  const [busy, setBusy] = useState(false);
  const [done, setDone] = useState("");
  const [error, setError] = useState("");
  const urls = (links ?? []).filter((url) => /^https:\/\//i.test(url)).slice(0, 10);
  const usable = memo ? memo.text.trim().length >= 80 : urls.length > 0;

  useEffect(() => {
    if (!open || areas.length) return;
    let alive = true;
    loadAreas().then((list) => { if (alive) setAreas(list); }).catch(() => { if (alive) setError("분야 목록을 불러오지 못했습니다."); });
    return () => { alive = false; };
  }, [open, areas.length]);

  if (!usable) return null;

  async function save() {
    if (!area || busy) return;
    setBusy(true);
    setError("");
    const entry = { area, mine, origin, origin_ref: safeOriginRef(originRef) };
    try {
      if (memo) {
        const { item } = await api.addSourceMemo(memo.title, memo.text, { ...entry, mine: true });
        if (item.status === "done") setDone(`문단 ${item.passages}개로 넣었습니다.`);
        else if (item.status === "duplicate") setDone("이미 창고에 있는 내용입니다.");
        else setError(item.note || "넣지 못했습니다.");
      } else {
        const results: SourceLinkResult[] = [];
        for (const url of urls) results.push(...(await api.addSourceLinks([url], entry, urls.length === 1 ? title : undefined)).results);
        const saved = results.filter((row) => (row.result === "added" && row.item?.status === "done") || row.result === "exists").length;
        const failed = results.find((row) => row.result === "rejected" || (row.result === "added" && row.item?.status !== "done"));
        if (saved) setDone(saved === results.length ? `${saved}건을 넣었습니다.` : `${results.length}건 중 ${saved}건을 넣었습니다.`);
        if (failed) setError(failed.reason || failed.item?.note || "일부 주소를 읽지 못했습니다.");
        if (!saved && failed) setDone("창고에 ‘확인 필요’로 남겼어요.");
      }
    } catch (cause) {
      setError(cause instanceof Error ? cause.message : "넣지 못했습니다.");
    } finally {
      setBusy(false);
    }
  }

  return (
    <span className={styles.save}>
      {!open && !done && <button className="button secondary small" type="button" onClick={() => setOpen(true)}>자료 창고에 넣기</button>}
      {open && !done && (
        <>
          <select value={area} disabled={busy} aria-label="자료 창고 분야" onChange={(event) => setArea(event.target.value)}>
            <option value="">분야를 고르세요</option>
            {areas.map((choice) => <option key={choice.id} value={choice.id}>{choice.label}</option>)}
          </select>
          <button className="button primary small" type="button" disabled={!area || busy} onClick={() => void save()}>{busy ? "넣는 중…" : "넣기"}</button>
          <button className="button text small" type="button" disabled={busy} onClick={() => setOpen(false)}>취소</button>
        </>
      )}
      <span aria-live="polite">
        {done && <span className={styles.saveDone}>{done} <Link href="/sources">자료 창고 열기</Link></span>}
        {error && <span className={styles.saveError} role="alert"> {error}</span>}
      </span>
    </span>
  );
}
