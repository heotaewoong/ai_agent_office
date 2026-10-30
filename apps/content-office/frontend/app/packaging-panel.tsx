"use client";

import { useId, useState } from "react";
import { api } from "../lib/api";
import { validatePackagingBrief, TITLE_MAX, THUMB_TEXT_MAX, HOOK_MAX } from "../lib/packaging";
import type { Action, Job, PackagingBrief } from "../lib/types";
import styles from "./packaging-panel.module.css";

export function PackagingPanel({
  job,
  busy,
  action,
}: {
  job: Job;
  busy: boolean;
  action: Action;
}) {
  const p = job.packaging;
  const id = useId();
  const [dirty, setDirty] = useState(false);
  const [titles, setTitles] = useState<string[]>(() => [0, 1, 2].map((i) => p?.titles?.[i] ?? ""));
  const [thumbs, setThumbs] = useState(() =>
    [0, 1, 2].map((i) => ({ text: p?.thumbnails?.[i]?.text ?? "", visual: p?.thumbnails?.[i]?.visual ?? "" })),
  );
  const [hook, setHook] = useState(p?.hook ?? "");
  const [logline, setLogline] = useState(p?.logline ?? "");
  const [reasons, setReasons] = useState<string[]>(() => [0, 1, 2].map((i) => p?.reasons?.[i] ?? ""));
  const [chosen, setChosen] = useState(() => {
    const idx = p?.chosen_title ? p.titles?.indexOf(p.chosen_title) : 0;
    return idx >= 0 ? idx : 0;
  });
  const [issues, setIssues] = useState<string[]>([]);

  const stale =
    !!job.source_packet?.packaging_hash &&
    !!p?.packaging_hash &&
    job.source_packet.packaging_hash !== p.packaging_hash;

  function markDirty() {
    setDirty(true);
    setIssues([]);
  }

  async function submit() {
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
    const result = await action("패키지 확정", () => api.setPackaging(job.id, brief), "패키지를 확정했습니다. 이제 원고를 생성할 수 있어요.");
    if (result === true) setDirty(false);
  }

  return (
    <section className={styles.panel} aria-label="제목·썸네일·훅 기획" aria-busy={busy}>
      <header className={styles.header}>
        <div><span className={styles.eyebrow}>콘텐츠의 첫인상 설계</span>
          <h2>제목·썸네일·훅을 먼저 정해요</h2>
          <p>세 가지 후보를 나란히 비교하고, 사용할 제목을 골라 주세요.</p>
        </div>
        <span className={styles.status}>{dirty ? "수정 중 · 확정 전" : p ? "확정된 기획" : "기획 준비 중"}</span>
      </header>
      {stale && (
        <div className="notice error">
          원고는 이전 패키지로 작성됐습니다. 원고를 다시 생성하면 새 패키지가 반영됩니다.
        </div>
      )}
      <div className={styles.content}>
        <div className={styles.stepHeading}><span>01</span><div><h3>후보 비교와 제목 선택</h3><p>제목은 하나를 선택하고, 썸네일 문구 3안은 제작 후 최종 이미지를 비교할 때 활용해요.</p></div></div>
        <div className={styles.cards} role="group" aria-label="제목 후보 3안">
          {titles.map((t, i) => <article className={`${styles.card} ${chosen===i?styles.selected:""}`} key={i}>
            <label className={styles.choose}><input aria-label={`제목 ${i+1}안 선택`} type="radio" name={`${id}-chosen`} checked={chosen===i} disabled={busy} onChange={()=>{setChosen(i);markDirty();}}/><strong>후보 {String(i+1).padStart(2,"0")}</strong><span>{chosen===i?"선택한 제목":"제목 선택"}</span></label>
            <div className={styles.thumbnail} aria-label={`썸네일 ${i+1}안 문구 미리보기`}><span>문구 배치 예시</span><strong>{thumbs[i].text||"핵심 문구를 적어 주세요"}</strong><small>이미지는 제작 단계에서 확인해요</small></div>
            <p className={styles.candidateTitle}>{t||"어떤 제목이 눈길을 끌까요?"}</p>
            <div className={styles.field}><div className={styles.labelRow}><label htmlFor={`${id}-title-${i}`}>제목 {i+1}안</label><span className={t.length>TITLE_MAX?styles.over:undefined}>{t.length}/{TITLE_MAX}</span></div>
              <input id={`${id}-title-${i}`} value={t} disabled={busy} aria-invalid={t.length>TITLE_MAX} onChange={e=>{setTitles(titles.map((x,j)=>j===i?e.target.value:x));markDirty();}} placeholder="전할 가치를 한 문장으로"/>
            </div>
            <div className={styles.field}><div className={styles.labelRow}><label htmlFor={`${id}-thumb-${i}`}>썸네일 {i+1}안 글자</label><span className={thumbs[i].text.length>THUMB_TEXT_MAX?styles.over:undefined}>{thumbs[i].text.length}/{THUMB_TEXT_MAX}</span></div>
              <input id={`${id}-thumb-${i}`} value={thumbs[i].text} disabled={busy} aria-invalid={thumbs[i].text.length>THUMB_TEXT_MAX} onChange={e=>{setThumbs(thumbs.map((x,j)=>j===i?{...x,text:e.target.value}:x));markDirty();}} placeholder="12자 이내의 핵심 문구"/>
            </div>
            <div className={styles.field}><label htmlFor={`${id}-visual-${i}`}>썸네일 {i+1}안 장면</label><textarea id={`${id}-visual-${i}`} rows={3} value={thumbs[i].visual} disabled={busy} onChange={e=>{setThumbs(thumbs.map((x,j)=>j===i?{...x,visual:e.target.value}:x));markDirty();}} placeholder="보여줄 대상·상황·구도를 적어 주세요"/></div>
          </article>)}
        </div>
        <p className={styles.swipeHint}>좌우로 넘겨 후보 3안을 비교할 수 있어요.</p>
        <div className={styles.detailsGrid}>
          <div className={styles.writing}><div className={styles.stepHeading}><span>02</span><div><h3>첫 문장과 한 줄 설명</h3><p>제목에서 약속한 내용을 첫 문장으로 이어 주세요.</p></div></div>
            <div className={styles.field}><div className={styles.labelRow}><label htmlFor={`${id}-hook`}>훅 (첫 문장)</label><span className={hook.trim().length>HOOK_MAX?styles.over:undefined}>{hook.trim().length}/{HOOK_MAX}</span></div><textarea id={`${id}-hook`} rows={3} value={hook} disabled={busy} aria-invalid={hook.trim().length>HOOK_MAX} onChange={e=>{setHook(e.target.value);markDirty();}} placeholder="계속 읽고 싶어지는 첫 문장"/></div>
            <div className={styles.field}><label htmlFor={`${id}-logline`}>한 줄 설명 (로그라인)</label><textarea id={`${id}-logline`} rows={2} value={logline} disabled={busy} onChange={e=>{setLogline(e.target.value);markDirty();}} placeholder="누구의 어떤 문제를 어떻게 해결하나요?"/></div>
          </div>
          <aside className={styles.preview} aria-label="선택한 제목 미리보기"><span className={styles.eyebrow}>선택한 제목 · {chosen+1}안</span><h3>{titles[chosen]||"제목을 입력하면 여기에 보여요"}</h3><p>{hook||"첫 문장을 적으면 제목과의 흐름을 함께 확인할 수 있어요."}</p><div><strong>한 줄 설명</strong><p>{logline||"독자가 얻게 될 결과를 짧게 정리해 보세요."}</p></div></aside>
        </div>
        <div className={styles.stepHeading}><span>03</span><div><h3>이 기획이 통할 이유</h3><p>독자의 관심·실행 가능성·내 경험 중 2~3가지 근거를 남겨 주세요.</p></div></div>
        <div className={styles.reasons}>{reasons.map((r,i)=><div className={styles.field} key={i}><label htmlFor={`${id}-reason-${i}`}>통할 이유 {i+1}{i===2&&<small> · 선택</small>}</label><textarea id={`${id}-reason-${i}`} rows={2} value={r} disabled={busy} onChange={e=>{setReasons(reasons.map((x,j)=>j===i?e.target.value:x));markDirty();}} placeholder={i===0?"독자가 지금 이 내용을 찾는 이유":i===1?"직접 실행할 수 있는 구체적인 방법":"내 경험·사례가 더해 주는 가치"}/></div>)}</div>
      {issues.length > 0 && (
        <div className={styles.issues} role="alert">
          <strong>확정 전에 확인해 주세요</strong>
          <ul>
            {issues.map((m) => (
              <li key={m}>{m}</li>
            ))}
          </ul>
        </div>
      )}
        <footer className={styles.footer}><div><strong>{dirty?"수정한 내용을 확인한 뒤 확정해 주세요.":p?"확정된 기획을 보면서 수정할 수 있어요.":"선택한 제목과 기획을 다음 원고에 사용해요."}</strong><p>확정은 원고 승인·유료 제작·게시와 별도입니다.{p&&" 다시 확정하면 다음 원고에 새 기획을 반영할 수 있어요."}</p>{p&&<small>확정 버전 {p.packaging_hash.slice(0,8)}</small>}</div><button className={styles.submit} disabled={busy} onClick={submit}>{busy?"처리 중…":p?"다시 확정":"패키지 확정"}<span aria-hidden="true">→</span></button></footer>
      </div>
    </section>
  );
}
