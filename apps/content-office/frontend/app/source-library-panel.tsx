"use client";

import { useCallback, useEffect, useMemo, useRef, useState } from "react";
import { api } from "../lib/api";
import {
  canPaste, displayDay, evidenceHint, fileToBase64, filterSources, sourceFilters, sourceKinds, sourceOrigins, sourceStatus, sourceSummary,
  splitLinks, vectorSummary,
  type SourceFilter, type SourceHit, type SourceItem, type SourceLibrary, type SourceLinkResult, type SourcePatch,
} from "../lib/source-library";
import { TrustedSources } from "./trusted-sources";
import styles from "./source-library.module.css";

type Method = "link" | "memo" | "file";
const methods: { id: Method; label: string; help: string }[] = [
  { id: "link", label: "링크", help: "공식 문서, 블로그, 논문 주소" },
  { id: "memo", label: "메모", help: "내 경험, 아이디어, 요약" },
  { id: "file", label: "파일", help: "txt, md, docx, pdf" },
];

function message(cause: unknown, fallback: string) {
  return cause instanceof Error && cause.message ? cause.message : fallback;
}

/** 자료 창고. 넣은 자료는 문단으로 저장되고, '초안 근거로 사용'을 켠 자료만 근거 후보가 됩니다. */
export function SourceLibraryPanel({ active }: { active: boolean }) {
  const [library, setLibrary] = useState<SourceLibrary | null>(null);
  const [loadError, setLoadError] = useState("");
  const [method, setMethod] = useState<Method>("link");
  const [area, setArea] = useState("");
  const [mine, setMine] = useState(false);
  const [links, setLinks] = useState("");
  const [memoTitle, setMemoTitle] = useState("");
  const [memoText, setMemoText] = useState("");
  const [file, setFile] = useState<File | null>(null);
  const [saving, setSaving] = useState(false);
  const [formError, setFormError] = useState("");
  const [outcome, setOutcome] = useState<SourceLinkResult[] | string>("");
  const [listArea, setListArea] = useState("");
  const [filter, setFilter] = useState<SourceFilter>("all");
  const [titleQuery, setTitleQuery] = useState("");
  const [query, setQuery] = useState("");
  const [evidenceOnly, setEvidenceOnly] = useState(false);
  const [hits, setHits] = useState<SourceHit[] | null>(null);
  const [searching, setSearching] = useState(false);
  const [searchError, setSearchError] = useState("");
  const [pending, setPending] = useState("");
  const [rowError, setRowError] = useState<{ id: string; text: string } | null>(null);
  const [opened, setOpened] = useState<{ id: string; passages: string[] } | null>(null);
  const [confirmDelete, setConfirmDelete] = useState("");
  const [paste, setPaste] = useState<{ id: string; text: string; title: string } | null>(null);
  const [bulkBusy, setBulkBusy] = useState(false);
  const [bulkNote, setBulkNote] = useState("");
  const fileInput = useRef<HTMLInputElement>(null);

  const load = useCallback(async () => {
    try {
      setLibrary(await api.sourceLibrary());
      setLoadError("");
    } catch (cause) {
      setLoadError(message(cause, "자료 창고를 불러오지 못했습니다."));
    }
  }, []);

  useEffect(() => {
    if (active) void load();
  }, [active, load]);

  const preparing = !!library && library.vectors.pending > 0 && library.vectors.available;
  useEffect(() => {
    if (!active || !preparing) return;
    const timer = window.setInterval(() => void load(), 8000);
    return () => window.clearInterval(timer);
  }, [active, preparing, load]);

  const visible = useMemo(() => filterSources(library?.items ?? [], listArea, filter, titleQuery), [library, listArea, filter, titleQuery]);
  const visibleReady = visible.filter((item) => item.status === "done");
  const limits = library?.limits ?? { links: 10, file_mb: 8, memo_chars: 60_000 };
  const pasted = splitLinks(links);
  const ready =
    !!area &&
    (method === "link" ? pasted.length > 0 && pasted.length <= limits.links
      : method === "memo" ? !!memoTitle.trim() && memoText.trim().length >= 80 && memoText.length <= limits.memo_chars
      : !!file && file.size <= limits.file_mb * 1_000_000);

  async function save() {
    if (!ready || saving) return;
    setSaving(true);
    setFormError("");
    setOutcome("");
    const entry = { area, mine: method === "memo" ? true : mine };
    try {
      if (method === "link") {
        // 한 요청에 한 주소씩 보내야 느린 사이트가 있어도 화면 요청 제한(30초)에 걸리지 않고 진행 상황이 보입니다.
        const results: SourceLinkResult[] = [];
        for (const url of pasted) {
          const response = await api.addSourceLinks([url], entry);
          results.push(...response.results);
          setLibrary(response);
          setOutcome([...results]);
        }
        if (results.every((row) => row.result !== "rejected")) setLinks("");
      } else if (method === "memo") {
        const response = await api.addSourceMemo(memoTitle.trim(), memoText, entry);
        setLibrary(response);
        setOutcome(response.item.status === "done" ? `'${response.item.title}' 메모를 문단 ${response.item.passages}개로 저장했습니다.` : response.item.note);
        if (response.item.status === "done") { setMemoTitle(""); setMemoText(""); }
      } else if (file) {
        const response = await api.addSourceFile(file.name, await fileToBase64(file), entry);
        setLibrary(response);
        setOutcome(response.item.status === "done" ? `'${response.item.title}' 파일을 문단 ${response.item.passages}개로 저장했습니다.` : response.item.note);
        setFile(null);
        if (fileInput.current) fileInput.current.value = "";
      }
    } catch (cause) {
      setFormError(message(cause, "자료를 넣지 못했습니다."));
    } finally {
      setSaving(false);
    }
  }

  async function run(item: SourceItem, work: () => Promise<SourceLibrary>, fallback: string) {
    setPending(item.id);
    setRowError(null);
    try {
      setLibrary(await work());
      setConfirmDelete("");
      return true;
    } catch (cause) {
      setRowError({ id: item.id, text: message(cause, fallback) });
      return false;
    } finally {
      setPending("");
    }
  }

  function change(item: SourceItem, patch: SourcePatch) {
    void run(item, () => api.updateSourceItem(item.id, patch), "바꾸지 못했습니다.");
  }

  async function submitPaste(item: SourceItem) {
    if (!paste || paste.id !== item.id || paste.text.trim().length < 80) return;
    const ok = await run(item, () => api.fillSourceText(item.id, paste.text, paste.title.trim() || undefined), "본문을 저장하지 못했습니다.");
    if (ok) setPaste(null);
  }

  async function bulk(value: boolean) {
    const ids = (value ? visibleReady.filter((item) => !item.use_as_evidence) : visible.filter((item) => item.use_as_evidence)).map((item) => item.id);
    if (!ids.length || bulkBusy) return;
    setBulkBusy(true);
    setBulkNote("");
    try {
      const response = await api.setSourceEvidence(ids, value);
      setLibrary(response);
      setBulkNote(value ? `자료 ${response.changed}건을 초안 근거로 켰습니다.` : `자료 ${response.changed}건의 근거 사용을 껐습니다.`);
    } catch (cause) {
      setBulkNote(message(cause, "한 번에 바꾸지 못했습니다."));
    } finally {
      setBulkBusy(false);
    }
  }

  async function toggleOpen(item: SourceItem) {
    if (opened?.id === item.id) return setOpened(null);
    setPending(item.id);
    setRowError(null);
    try {
      setOpened({ id: item.id, passages: (await api.sourceItem(item.id)).passage_texts });
    } catch (cause) {
      setRowError({ id: item.id, text: message(cause, "문단을 불러오지 못했습니다.") });
    } finally {
      setPending("");
    }
  }

  async function search() {
    if (!query.trim() || searching) return;
    setSearching(true);
    setSearchError("");
    try {
      setHits((await api.searchSourceLibrary(query.trim(), listArea, evidenceOnly)).results);
    } catch (cause) {
      setSearchError(message(cause, "검색하지 못했습니다."));
    } finally {
      setSearching(false);
    }
  }

  const vectorLine = library ? vectorSummary(library.vectors) : "";

  return (
    <div className={styles.page}>
      <section className={styles.summary} aria-label="자료 창고 현황">
        <div>
          <strong>{library ? sourceSummary(library.stats) : "자료 창고를 불러오는 중입니다."}</strong>
          <p>넣은 자료는 문단으로 잘라 보관합니다. <b>초안 근거로 사용</b>을 켠 링크는 기획의 ‘공개 원문 근거 찾기’에 후보로 나오고, 켠 메모와 파일은 ‘내 글로 만들기’에서 불러올 수 있어요. 꺼 둔 자료는 보관만 합니다.</p>
          {vectorLine && <p className={styles.vectorLine} role="status" data-pending={preparing}>{vectorLine}</p>}
        </div>
        <button className="button secondary small" type="button" onClick={() => void load()}>새로 고침</button>
      </section>
      {loadError && <p className="notice error" role="alert"><span>{loadError}</span></p>}

      <section className={styles.card} aria-labelledby="source-add-title">
        <h2 id="source-add-title">자료 넣기</h2>
        <div className={styles.methods} role="group" aria-label="넣는 방법">
          {methods.map((choice) => (
            <button key={choice.id} type="button" className={styles.method} aria-pressed={method === choice.id} onClick={() => { setMethod(choice.id); setFormError(""); setOutcome(""); }}>
              <strong>{choice.label}</strong>
              <small>{choice.help}</small>
            </button>
          ))}
        </div>

        {method === "link" && (
          <label className={styles.field}>
            주소 <span>한 줄에 하나씩, 한 번에 {limits.links}개까지 · 유튜브는 제목만 가져와요</span>
            <textarea className={styles.input} rows={4} value={links} placeholder="https://" spellCheck={false} disabled={saving} onChange={(event) => setLinks(event.target.value)} />
            {pasted.length > limits.links && <em className="field-error">{limits.links}개까지만 넣을 수 있습니다. 지금 {pasted.length}개입니다.</em>}
          </label>
        )}
        {method === "memo" && (
          <>
            <label className={styles.field}>
              제목
              <input className={styles.input} value={memoTitle} maxLength={200} placeholder="예: 편입 한 달 전 복습 방법" disabled={saving} onChange={(event) => setMemoTitle(event.target.value)} />
            </label>
            <label className={styles.field}>
              내용 <span>{memoText.length.toLocaleString("ko-KR")} / {limits.memo_chars.toLocaleString("ko-KR")}자 · 80자 이상</span>
              <textarea className={styles.input} rows={8} value={memoText} placeholder="직접 해 본 것, 그때 숫자, 느낀 점을 적어 두면 나중에 글의 재료가 됩니다." disabled={saving} onChange={(event) => setMemoText(event.target.value)} />
            </label>
          </>
        )}
        {method === "file" && (
          <label className={styles.field}>
            파일 <span>txt, md, docx, pdf · {limits.file_mb}MB까지</span>
            <input ref={fileInput} className={styles.input} type="file" accept=".txt,.md,.docx,.pdf" disabled={saving} onChange={(event) => setFile(event.target.files?.[0] ?? null)} />
            {file && file.size > limits.file_mb * 1_000_000 && <em className="field-error">파일이 {limits.file_mb}MB보다 큽니다.</em>}
          </label>
        )}

        <div className={styles.tags}>
          <label className={styles.field}>
            분야
            <select className={styles.input} value={area} disabled={saving} onChange={(event) => setArea(event.target.value)}>
              <option value="">분야를 고르세요</option>
              {library?.areas.map((choice) => <option key={choice.id} value={choice.id}>{choice.label}</option>)}
            </select>
          </label>
          {method !== "memo" && (
            <label className={styles.check}>
              <input type="checkbox" checked={mine} disabled={saving} onChange={(event) => setMine(event.target.checked)} />
              내가 쓴 글이거나 내 경험입니다
            </label>
          )}
          <button className="button primary" type="button" disabled={!ready || saving} onClick={() => void save()}>
            {saving ? "읽고 저장하는 중…" : "창고에 넣기"}
          </button>
        </div>
        <div aria-live="polite">
          {formError && <p className={styles.error} role="alert">{formError}</p>}
          {typeof outcome === "string" && outcome && <p className={styles.success}>{outcome}</p>}
          {Array.isArray(outcome) && outcome.length > 0 && (
            <ul className={styles.results}>
              {outcome.map((row) => (
                <li key={row.url} data-tone={row.result === "added" && row.item?.status === "done" ? "ok" : row.result === "exists" ? "same" : "warn"}>
                  <strong>
                    {row.result === "rejected" ? "넣지 않음" : row.result === "exists" ? "이미 있음" : row.item?.status === "done" ? `문단 ${row.item.passages}개 저장` : sourceStatus[row.item?.status ?? "needs_check"].label}
                  </strong>
                  <span>{row.item?.title && row.item.title !== row.url ? row.item.title : row.url}</span>
                  {(row.reason || (row.item?.status !== "done" && row.item?.note)) && <small>{row.reason || row.item?.note}</small>}
                </li>
              ))}
            </ul>
          )}
        </div>
      </section>

      <section className={styles.card} aria-labelledby="source-search-title">
        <h2 id="source-search-title">창고에서 찾기</h2>
        <form className={styles.search} onSubmit={(event) => { event.preventDefault(); void search(); }}>
          <input className={styles.input} value={query} maxLength={300} placeholder="예: Hermes OpenClaw 차이" aria-label="찾을 내용" onChange={(event) => setQuery(event.target.value)} />
          <label className={styles.check}>
            <input type="checkbox" checked={evidenceOnly} onChange={(event) => setEvidenceOnly(event.target.checked)} />
            근거로 켠 자료만
          </label>
          <button className="button secondary" type="submit" disabled={!query.trim() || searching}>{searching ? "찾는 중…" : "찾기"}</button>
        </form>
        <p className={styles.hint}>아래 목록에서 고른 분야 안에서 낱말이 맞는 문단을 찾습니다. 기획의 근거 찾기는 같은 문단을 뜻으로 찾습니다.</p>
        <div aria-live="polite">
          {searchError && <p className={styles.error} role="alert">{searchError}</p>}
          {hits && hits.length === 0 && <p className={styles.hint}>맞는 문단이 없습니다. 낱말을 바꾸거나 분야를 전체로 바꿔 보세요.</p>}
          {hits && hits.length > 0 && (
            <ol className={styles.hits}>
              {hits.map((hit) => (
                <li key={`${hit.item_id}-${hit.paragraph}`}>
                  <header>
                    {hit.url ? <a href={hit.url} target="_blank" rel="noopener noreferrer">{hit.title}</a> : <strong>{hit.title}</strong>}
                    <span className="badge neutral">{hit.area_label}</span>
                    <span className="badge neutral">{hit.paragraph}번째 문단</span>
                    {hit.use_as_evidence && <span className="badge green">근거로 사용</span>}
                  </header>
                  <p>{hit.text}</p>
                </li>
              ))}
            </ol>
          )}
        </div>
      </section>

      <TrustedSources active={active} areas={library?.areas ?? []} />

      <section className={styles.card} aria-labelledby="source-list-title">
        <h2 id="source-list-title">보관 중인 자료</h2>
        <div className={styles.filters}>
          <div className={styles.chips} role="group" aria-label="분야">
            <button type="button" aria-pressed={listArea === ""} onClick={() => setListArea("")}>전체 분야</button>
            {library?.areas.map((choice) => (
              <button key={choice.id} type="button" aria-pressed={listArea === choice.id} onClick={() => setListArea(choice.id)}>{choice.label} {choice.items}</button>
            ))}
          </div>
          <div className={styles.chips} role="group" aria-label="보기">
            {sourceFilters.map((choice) => (
              <button key={choice.id} type="button" aria-pressed={filter === choice.id} onClick={() => setFilter(choice.id)}>{choice.label}</button>
            ))}
          </div>
          <input className={styles.input} value={titleQuery} placeholder="제목이나 주소로 거르기" aria-label="제목이나 주소로 거르기" onChange={(event) => setTitleQuery(event.target.value)} />
          {visible.length > 0 && (
            <div className={styles.bulk}>
              <span>지금 보이는 자료 {visible.length}건</span>
              <button className="button secondary small" type="button" disabled={bulkBusy || !visibleReady.some((item) => !item.use_as_evidence)} onClick={() => void bulk(true)}>모두 근거로 켜기</button>
              <button className="button text small" type="button" disabled={bulkBusy || !visible.some((item) => item.use_as_evidence)} onClick={() => void bulk(false)}>모두 끄기</button>
              <span aria-live="polite">{bulkNote}</span>
            </div>
          )}
        </div>

        {library && library.items.length === 0 && (
          <div className="empty-state">
            <h3>아직 넣은 자료가 없어요</h3>
            <p>위에서 링크나 메모를 넣거나, 오늘의 뉴스와 기획 카드의 ‘자료 창고에 넣기’를 눌러 보세요.</p>
          </div>
        )}
        {library && library.items.length > 0 && visible.length === 0 && <p className={styles.hint}>고른 조건에 맞는 자료가 없습니다.</p>}

        <ul className={styles.list}>
          {visible.map((item) => {
            const state = sourceStatus[item.status];
            const busy = pending === item.id;
            const pasting = paste?.id === item.id ? paste : null;
            return (
              <li key={item.id} className={styles.item} data-evidence={item.use_as_evidence}>
                <div className={styles.itemMain}>
                  <div className={styles.itemTitle}>
                    {item.url ? <a href={item.url} target="_blank" rel="noopener noreferrer">{item.title}</a> : <strong>{item.title}</strong>}
                  </div>
                  <div className={styles.meta}>
                    <span className={`badge ${state.tone}`}>{state.label}</span>
                    <span className="badge neutral">{sourceKinds[item.kind]}</span>
                    <span className="badge neutral">{sourceOrigins[item.origin]}</span>
                    {item.mine && <span className="badge orange">내 자료</span>}
                    {item.lane === "example" && <span className="badge orange">사례·참고</span>}
                    {item.pasted && <span className="badge neutral">직접 붙여 넣은 본문</span>}
                    {item.status === "done" && <span>문단 {item.passages}개</span>}
                    <span>{displayDay(item.created_at)}</span>
                  </div>
                  {item.note && <p className={styles.note}>{item.note}</p>}
                  {rowError?.id === item.id && <p className={styles.error} role="alert">{rowError.text}</p>}
                  {pasting && (
                    <form className={styles.pasteForm} onSubmit={(event) => { event.preventDefault(); void submitPaste(item); }}>
                      <label className={styles.field}>
                        제목 <span>비워 두면 지금 제목을 그대로 써요</span>
                        <input className={styles.input} value={pasting.title} maxLength={200} disabled={busy} onChange={(event) => setPaste({ ...pasting, title: event.target.value })} />
                      </label>
                      <label className={styles.field}>
                        본문 <span>{pasting.text.trim().length.toLocaleString("ko-KR")}자 · 80자 이상 · 링크 주소는 출처로 그대로 남아요</span>
                        <textarea className={styles.input} rows={8} value={pasting.text} disabled={busy} placeholder="원문에서 복사한 본문이나 영상 자막을 붙여 넣으세요." onChange={(event) => setPaste({ ...pasting, text: event.target.value })} />
                      </label>
                      <div className={styles.rowButtons}>
                        <button className="button primary small" type="submit" disabled={busy || pasting.text.trim().length < 80}>{busy ? "저장하는 중…" : "본문 저장"}</button>
                        <button className="button text small" type="button" disabled={busy} onClick={() => setPaste(null)}>취소</button>
                      </div>
                    </form>
                  )}
                </div>
                <div className={styles.itemActions}>
                  <label className={styles.switch} data-on={item.use_as_evidence}>
                    <input type="checkbox" role="switch" checked={item.use_as_evidence} disabled={busy || item.status !== "done"} onChange={(event) => change(item, { use_as_evidence: event.target.checked })} />
                    <span>초안 근거로 사용</span>
                  </label>
                  {item.use_as_evidence && <small className={styles.switchHint}>{evidenceHint(item)}</small>}
                  <select className={styles.inputSmall} value={item.area} disabled={busy} aria-label={`${item.title} 분야`} onChange={(event) => change(item, { area: event.target.value })}>
                    {library?.areas.map((choice) => <option key={choice.id} value={choice.id}>{choice.label}</option>)}
                  </select>
                  <div className={styles.rowButtons}>
                    {item.kind === "link" && <button className="button text small" type="button" disabled={busy} onClick={() => change(item, { lane: item.lane === "example" ? "fact" : "example" })}>{item.lane === "example" ? "사실 근거로 바꾸기" : "사례·참고로 바꾸기"}</button>}
                    {item.status === "done" && <button className="button text small" type="button" disabled={busy} aria-expanded={opened?.id === item.id} onClick={() => void toggleOpen(item)}>{opened?.id === item.id ? "문단 닫기" : "문단 보기"}</button>}
                    {canPaste(item) && !pasting && <button className="button text small" type="button" disabled={busy} onClick={() => setPaste({ id: item.id, text: "", title: item.title === item.url ? "" : item.title })}>본문 붙여넣기</button>}
                    {item.status === "needs_check" && item.kind === "link" && <button className="button text small" type="button" disabled={busy} onClick={() => void run(item, () => api.retrySourceItem(item.id), "다시 읽지 못했습니다.")}>다시 읽기</button>}
                    {confirmDelete === item.id ? (
                      <>
                        <button className="button text small" type="button" disabled={busy} onClick={() => void run(item, () => api.deleteSourceItem(item.id), "지우지 못했습니다.")}>정말 지우기</button>
                        <button className="button text small" type="button" onClick={() => setConfirmDelete("")}>취소</button>
                      </>
                    ) : (
                      <button className="button text small" type="button" disabled={busy} onClick={() => setConfirmDelete(item.id)}>지우기</button>
                    )}
                  </div>
                </div>
                {opened?.id === item.id && (
                  <ol className={styles.passages}>
                    {opened.passages.map((text, index) => <li key={index}>{text}</li>)}
                  </ol>
                )}
              </li>
            );
          })}
        </ul>
      </section>
    </div>
  );
}
