"use client";

import { useState } from "react";
import { api } from "../lib/api";
import { validatePackagingBrief } from "../lib/packaging";
import type { Job, PackagingBrief } from "../lib/types";
import type { Action } from "./page";

export function PackagingPanel({
  job,
  busy,
  action,
  onSaved,
}: {
  job: Job;
  busy: boolean;
  action: Action;
  onSaved: (job: Job) => void;
}) {
  void onSaved; // action이 저장 뒤 작업을 다시 불러온다
  const p = job.packaging;
  const [titles, setTitles] = useState<string[]>(() => [0, 1, 2].map((i) => p?.titles?.[i] ?? ""));
  const [thumbs, setThumbs] = useState(() =>
    [0, 1, 2].map((i) => ({ text: p?.thumbnails?.[i]?.text ?? "", visual: p?.thumbnails?.[i]?.visual ?? "" })),
  );
  const [hook, setHook] = useState(p?.hook ?? "");
  const [logline, setLogline] = useState(p?.logline ?? "");
  const [reasons, setReasons] = useState<string[]>(() => [0, 1, 2].map((i) => p?.reasons?.[i] ?? ""));
  const [chosen, setChosen] = useState(() => {
    const idx = p?.chosen_title ? p.titles.indexOf(p.chosen_title) : 0;
    return idx >= 0 ? idx : 0;
  });
  const [issues, setIssues] = useState<string[]>([]);

  const stale =
    !!job.source_packet?.packaging_hash &&
    !!p?.packaging_hash &&
    job.source_packet.packaging_hash !== p.packaging_hash;

  function submit() {
    const brief: PackagingBrief = {
      titles: titles.map((t) => t.trim()),
      thumbnails: thumbs.map((t) => ({ text: t.text.trim(), visual: t.visual.trim() })),
      hook: hook.trim(),
      logline: logline.trim(),
      reasons: reasons.map((r) => r.trim()).filter(Boolean),
      chosen_title: titles[chosen]?.trim() || undefined,
    };
    const found = validatePackagingBrief(brief);
    setIssues(found);
    if (found.length) return;
    void action("패키지 확정", () => api.setPackaging(job.id, brief), "패키지를 확정했습니다. 이제 원고를 생성할 수 있어요.");
  }

  return (
    <section className="editor-panel v6-packaging">
      <div className="section-heading">
        <div>
          <span className="eyebrow">패키지 카드</span>
          <h2>제목·썸네일·훅을 먼저 정해요</h2>
        </div>
        {p && <span className="muted">확정됨 · {p.packaging_hash.slice(0, 8)}</span>}
      </div>
      {p && <p className="muted">내용을 고쳐 다시 확정할 수 있어요. 다시 확정하면 새 해시가 적용됩니다.</p>}
      {stale && (
        <div className="notice error">
          원고는 이전 패키지로 작성됐습니다. 원고를 다시 생성하면 새 패키지가 반영됩니다.
        </div>
      )}
      <div className="editor-fields">
        {titles.map((t, i) => (
          <div key={i} className="v6-packaging-row">
            <label htmlFor={`pk-title-${i}`}>
              <input type="radio" name="pk-chosen" checked={chosen === i} disabled={busy} onChange={() => setChosen(i)} /> 제목 {i + 1}안
            </label>
            <input id={`pk-title-${i}`} value={t} disabled={busy} onChange={(e) => setTitles(titles.map((x, j) => (j === i ? e.target.value : x)))} />
          </div>
        ))}
        {thumbs.map((t, i) => (
          <div key={i} className="v6-packaging-row">
            <label htmlFor={`pk-thumb-${i}`}>썸네일 {i + 1}안 글자 (12자 이내)</label>
            <input id={`pk-thumb-${i}`} value={t.text} disabled={busy} onChange={(e) => setThumbs(thumbs.map((x, j) => (j === i ? { ...x, text: e.target.value } : x)))} />
            <input aria-label={`썸네일 ${i + 1}안 장면`} placeholder="장면 설명" value={t.visual} disabled={busy} onChange={(e) => setThumbs(thumbs.map((x, j) => (j === i ? { ...x, visual: e.target.value } : x)))} />
          </div>
        ))}
        <label htmlFor="pk-hook">훅 (첫 문장)</label>
        <textarea id="pk-hook" rows={2} value={hook} disabled={busy} onChange={(e) => setHook(e.target.value)} />
        <label htmlFor="pk-logline">로그라인</label>
        <input id="pk-logline" value={logline} disabled={busy} onChange={(e) => setLogline(e.target.value)} />
        {reasons.map((r, i) => (
          <div key={i}>
            <label htmlFor={`pk-reason-${i}`}>통할 이유 {i + 1}</label>
            <input id={`pk-reason-${i}`} value={r} disabled={busy} onChange={(e) => setReasons(reasons.map((x, j) => (j === i ? e.target.value : x)))} />
          </div>
        ))}
      </div>
      {issues.length > 0 && (
        <div className="notice error">
          <ul>
            {issues.map((m) => (
              <li key={m}>{m}</li>
            ))}
          </ul>
        </div>
      )}
      <button className="button primary" disabled={busy} onClick={submit}>
        {p ? "다시 확정" : "패키지 확정"}
      </button>
    </section>
  );
}
