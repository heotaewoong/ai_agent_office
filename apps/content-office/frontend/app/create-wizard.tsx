"use client";

// 새 글 만들기(2026-11-27): 기획 고르기부터 원고 생성까지 한 화면, 다섯 단계.
// 기존 API만 써요(기획 등록, 글 유형 저장, 근거 찾기, 기획 선택⓪, 제목 제안과 패키지 저장, 원고 생성).
// 승인①과 공개 게시는 여기서 하지 않아요. 원고가 나오면 콘텐츠 작업실로 넘겨요.

import Link from "next/link";
import { useCallback, useEffect, useRef, useState } from "react";
import { api } from "../lib/api";
import { officeHref } from "../lib/navigation";
import { researchKinds, type ResearchKind } from "../lib/source-library";
import type { Idea, IdeaBookEvidence, IdeaPublicEvidence, Job } from "../lib/types";
import { statusInfo, workWindowBlockedReason } from "../lib/workflow";
import { Icon } from "./icons";
import styles from "./create-wizard.module.css";

type Step = "topic" | "kind" | "evidence" | "title" | "write";
type Suggestion = {
  titles: string[];
  hooks: string[];
  hook: string;
  thumbnails: { text: string; visual: string }[];
  logline: string;
  reasons: string[];
};
const STEPS: { id: Step; label: string }[] = [
  { id: "topic", label: "주제" },
  { id: "kind", label: "글 유형" },
  { id: "evidence", label: "근거" },
  { id: "title", label: "제목" },
  { id: "write", label: "원고" },
];
const KINDS = researchKinds.filter((kind) => kind.id !== "W5");
const WINDOW_MINUTES = 120;
const TITLE_MAX = 45;

function message(cause: unknown, fallback: string) {
  return cause instanceof Error && cause.message ? cause.message : fallback;
}

function host(url: string) {
  try { return new URL(url).hostname.replace(/^www\./, ""); } catch { return ""; }
}

function recommended(ideas: Idea[]) {
  return ideas
    .filter((idea) => idea.state === "candidate" && idea.blocked.length === 0 && !idea.research?.blocked)
    .sort((a, b) => b.score - a.score)
    .slice(0, 6);
}

function defaultPicks(idea: Idea): string[] {
  const items = idea.public_evidence ?? [];
  const linked = new Set((idea.public_discovery?.claims ?? []).flatMap((claim) => claim.evidence_ids));
  const picked = items.filter((item) => linked.has(item.id)).map((item) => item.id);
  return (picked.length ? picked : items.map((item) => item.id)).slice(0, 5);
}

async function ensureWindow() {
  // 원고와 유료 호출은 작업 시간 안에서만 돌아요. 닫혀 있으면 두 시간을 열어요.
  const dashboard = await api.dashboard();
  if (workWindowBlockedReason(dashboard.window)) await api.startWindow(WINDOW_MINUTES);
}

export function CreateWizard() {
  const [step, setStep] = useState<Step>("topic");
  const [ideas, setIdeas] = useState<Idea[] | null>(null);
  const [idea, setIdea] = useState<Idea | null>(null);
  const [kind, setKind] = useState<ResearchKind | "">("");
  const [picks, setPicks] = useState<string[]>([]);
  const [bookPicks, setBookPicks] = useState<string[]>([]);
  const [job, setJob] = useState<Job | null>(null);
  const [suggestion, setSuggestion] = useState<Suggestion | null>(null);
  const [issues, setIssues] = useState<string[][]>([]);
  const [chosen, setChosen] = useState(0);
  const [titleText, setTitleText] = useState("");
  const [busy, setBusy] = useState("");
  const [error, setError] = useState("");
  const [form, setForm] = useState({ title: "", url: "" });
  const [started, setStarted] = useState<number | null>(null);
  const [now, setNow] = useState(Date.now());
  const searched = useRef<string>("");
  const suggested = useRef<string>("");

  const loadIdeas = useCallback(async () => {
    const { ideas: list } = await api.ideas();
    setIdeas(list);
    return list;
  }, []);

  // 처음 열 때 기획 목록을 읽고, 주소에 작업 번호가 있으면 이어서 보여 줘요(새로고침해도 진행이 안 사라지게).
  useEffect(() => {
    let alive = true;
    const jobId = new URLSearchParams(window.location.search).get("job");
    loadIdeas().catch((cause) => { if (alive) setError(message(cause, "기획 목록을 불러오지 못했어요.")); });
    if (jobId) {
      api.job(jobId).then((current) => {
        if (!alive) return;
        setJob(current);
        if (!current.packaging && current.article?.origin === "idea" && current.state === "research_ready") setStep("title");
        else { setStep("write"); setStarted(Date.now()); }
      }).catch(() => undefined);
    }
    return () => { alive = false; };
  }, [loadIdeas]);

  function remember(jobId: string) {
    const url = new URL(window.location.href);
    url.searchParams.set("job", jobId);
    window.history.replaceState(window.history.state, "", url.toString());
  }

  async function run(label: string, work: () => Promise<void>, fallback: string) {
    if (busy) return;
    setBusy(label);
    setError("");
    try { await work(); } catch (cause) { setError(message(cause, fallback)); } finally { setBusy(""); }
  }

  function chooseIdea(next: Idea) {
    setIdea(next);
    setKind(next.research?.kind && next.research.kind !== "W5" ? next.research.kind : "W3");
    setPicks([]);
    setBookPicks([]);
    setError("");
    setStep("kind");
  }

  async function addOwnTopic() {
    const title = form.title.trim();
    const url = form.url.trim();
    if (!title) { setError("어떤 글을 쓸지 제목을 한 줄로 적어 주세요."); return; }
    if (!/^https:\/\//.test(url)) { setError("근거가 될 원문 링크(https로 시작)를 넣어 주세요."); return; }
    await run("기획 등록", async () => {
      const saved = await api.addIdea({ title, source_url: url, demand: 0, primary_sources: 1, fit: 0, covered_before: false, policy_flags: [] });
      const list = await loadIdeas();
      const fresh = list.find((item) => item.id === saved.id) ?? saved;
      if (fresh.blocked.length) throw new Error(`이 기획은 막혔어요: ${fresh.blocked.join(", ")}`);
      setForm({ title: "", url: "" });
      chooseIdea(fresh);
    }, "기획을 저장하지 못했어요.");
  }

  async function confirmKind() {
    if (!idea || !kind) return;
    if (kind === "W4") return;
    await run("글 유형 저장", async () => {
      const area = idea.research?.area;
      if (area && (kind !== idea.research?.kind || idea.research?.kind_guessed)) await api.saveResearchChoice(idea.id, { kind, area });
      setStep("evidence");
    }, "글 유형을 저장하지 못했어요.");
  }

  // 근거 단계에 들어오면 한 번 자동으로 찾아요. 이미 찾아 둔 근거가 있으면 그대로 써요.
  useEffect(() => {
    if (step !== "evidence" || !idea || searched.current === idea.id) return;
    searched.current = idea.id;
    if (idea.public_evidence?.length) { setPicks(defaultPicks(idea)); return; }
    void run("근거 찾기", async () => {
      const saved = await api.searchIdeaPublicEvidence(idea.id, idea.edit_hash ?? "");
      setIdea(saved);
      setPicks(defaultPicks(saved));
    }, "근거를 찾지 못했어요. 아래 '다시 찾기'를 눌러 주세요.");
  }, [step, idea]); // eslint-disable-line react-hooks/exhaustive-deps

  async function searchAgain() {
    if (!idea) return;
    await run("근거 찾기", async () => {
      const saved = await api.searchIdeaPublicEvidence(idea.id, idea.edit_hash ?? "");
      setIdea(saved);
      setPicks(defaultPicks(saved));
    }, "근거를 찾지 못했어요.");
  }

  async function searchBooks() {
    if (!idea) return;
    await run("책에서 찾기", async () => {
      const saved = await api.searchIdeaBookEvidence(idea.id, idea.edit_hash ?? "");
      setIdea(saved);
    }, "내 책에서 찾지 못했어요.");
  }

  async function confirmEvidence() {
    if (!idea) return;
    await run("기획 확정", async () => {
      const result = await api.selectIdea(idea.id, idea.edit_hash ?? "", picks, bookPicks);
      setJob(result.job);
      remember(result.job.id);
      setStep("title");
    }, "기획을 확정하지 못했어요.");
  }

  // 제목 단계에 들어오면 모델이 제목 3안을 한 번 제안해요.
  useEffect(() => {
    if (step !== "title" || !job || suggested.current === job.id) return;
    suggested.current = job.id;
    void suggest();
  }, [step, job]); // eslint-disable-line react-hooks/exhaustive-deps

  async function suggest() {
    if (!job) return;
    await run("제목 제안", async () => {
      await ensureWindow();
      const out = await api.suggestPackaging(job.id);
      setSuggestion(out.suggestion);
      setIssues(out.issues);
      setChosen(0);
      setTitleText(out.suggestion.titles[0] ?? "");
    }, "제목을 제안받지 못했어요. '다시 제안'을 눌러 주세요.");
  }

  function pickTitle(index: number) {
    if (!suggestion) return;
    setChosen(index);
    setTitleText(suggestion.titles[index] ?? "");
  }

  async function startDraft() {
    if (!job || !suggestion) return;
    const titles = suggestion.titles.map((title, index) => (index === chosen ? titleText.trim() : title));
    await run("원고 만들기", async () => {
      await api.setPackaging(job.id, {
        titles, thumbnails: suggestion.thumbnails, hook: suggestion.hooks[chosen] ?? suggestion.hook,
        logline: suggestion.logline, reasons: suggestion.reasons, chosen_title: titles[chosen],
      });
      await ensureWindow();
      await api.draft(job.id);
      setStarted(Date.now());
      setStep("write");
    }, "원고 만들기를 시작하지 못했어요.");
  }

  // 원고 단계에서는 4초마다 작업 상태를 읽어요. 끝나거나 멈추면 그만 읽어요.
  const done = job?.state === "source_review" || job?.state === "source_approved";
  const stopped = job?.state === "blocked" || job?.state === "failed" || job?.state === "source_rejected";
  useEffect(() => {
    if (step !== "write" || !job || done || stopped) return;
    const timer = window.setInterval(() => {
      setNow(Date.now());
      api.job(job.id).then(setJob).catch(() => undefined);
    }, 4000);
    return () => window.clearInterval(timer);
  }, [step, job, done, stopped]);

  const index = STEPS.findIndex((item) => item.id === step);
  const list = ideas ? recommended(ideas) : null;
  const books = idea?.book_evidence ?? [];
  const evidence = idea?.public_evidence ?? [];
  const elapsed = started ? Math.max(0, Math.round((now - started) / 1000)) : 0;

  return (
    <section className={styles.wizard} aria-labelledby="create-heading">
      <h2 id="create-heading" className="visually-hidden">새 글 만들기</h2>
      <ol className={styles.steps} aria-label="진행 단계">
        {STEPS.map((item, i) => (
          <li key={item.id} className={i < index ? styles.past : i === index ? styles.now : ""} aria-current={i === index ? "step" : undefined}>
            <span className={styles.dot}>{i < index ? <Icon name="check" size={14} /> : i + 1}</span>
            <span>{item.label}</span>
          </li>
        ))}
      </ol>

      {error && <p className={styles.error} role="alert"><Icon name="alert" size={18} />{error}</p>}
      {busy && <p className={styles.busy} role="status"><Icon name="refresh" size={16} className="spin" />{busy} 중이에요</p>}

      {step === "topic" && (
        <div className={styles.panel}>
          <h3 className={styles.question}>무엇을 쓸까요?</h3>
          <p className={styles.help}>추천 기획을 누르거나, 아래에 제목과 원문 링크를 넣으세요.</p>
          {list === null ? <p className={styles.help}>기획을 불러오는 중이에요.</p> : list.length === 0 ? (
            <p className={styles.help}>바로 쓸 수 있는 추천 기획이 없어요. 아래에 직접 넣어 주세요.</p>
          ) : (
            <ul className={styles.cards}>
              {list.map((item) => (
                <li key={item.id}>
                  <button type="button" className={styles.card} onClick={() => chooseIdea(item)} disabled={!!busy}>
                    <span className={styles.cardTitle}>{item.title}</span>
                    <span className={styles.cardMeta}>
                      {item.research?.kind_label && <span>{item.research.kind_label}</span>}
                      {item.research?.area_label && <span>{item.research.area_label}</span>}
                      {item.source_url && <span>{host(item.source_url)}</span>}
                    </span>
                  </button>
                </li>
              ))}
            </ul>
          )}
          <form className={styles.own} onSubmit={(event) => { event.preventDefault(); void addOwnTopic(); }}>
            <label>제목<input value={form.title} maxLength={200} placeholder="예: Claude로 블로그 초안 10분 만에 쓰는 법" onChange={(e) => setForm({ ...form, title: e.target.value })} /></label>
            <label>원문 링크<input value={form.url} inputMode="url" placeholder="https://" onChange={(e) => setForm({ ...form, url: e.target.value })} /></label>
            <button className="button primary" type="submit" disabled={!!busy}>이 주제로 시작</button>
          </form>
          <p className={styles.help}>내 티스토리 글로 만들 때는 <Link href="/plans">기획·독자 질문</Link>의 &apos;내 글이나 아이디어로 콘텐츠 만들기&apos;를 써요.</p>
        </div>
      )}

      {step === "kind" && idea && (
        <div className={styles.panel}>
          <p className={styles.topic}>{idea.title}</p>
          <h3 className={styles.question}>어떤 글로 쓸까요?</h3>
          <p className={styles.help}>{idea.research?.kind_guessed === false ? "저장해 둔 유형이에요." : "제목을 보고 골라 뒀어요. 맞으면 그대로 다음을 누르세요."}</p>
          <div className={styles.kinds} role="radiogroup" aria-label="글 유형">
            {KINDS.map((item) => (
              <button key={item.id} type="button" role="radio" aria-checked={kind === item.id} className={styles.kind} onClick={() => setKind(item.id)}>
                <strong>{item.label}</strong><span>{item.help}</span>
              </button>
            ))}
          </div>
          {kind === "W4" && <p className={styles.note}>내 경험 글은 내 원고가 근거예요. <Link href="/plans">기획·독자 질문</Link>의 &apos;내 글이나 아이디어로 콘텐츠 만들기&apos;에서 만들어요.</p>}
          <div className={styles.actions}>
            <button type="button" className="button text" onClick={() => setStep("topic")}>주제 다시 고르기</button>
            <button type="button" className="button primary" disabled={!!busy || !kind || kind === "W4"} onClick={() => void confirmKind()}>다음: 근거 찾기</button>
          </div>
        </div>
      )}

      {step === "evidence" && idea && (
        <div className={styles.panel}>
          <p className={styles.topic}>{idea.title}</p>
          <h3 className={styles.question}>이 근거로 쓸까요?</h3>
          <p className={styles.help}>자료 창고와 공개 원문에서 찾아 체크해 뒀어요. 엉뚱한 문단만 체크를 풀어 주세요.</p>
          {idea.public_discovery?.status === "insufficient" && <p className={styles.note}>찾은 근거가 부족해요. 이대로 가면 원고 대신 보류가 나올 수 있어요.</p>}
          {evidence.length > 0 && (
            <ul className={styles.evidence}>
              {evidence.map((item: IdeaPublicEvidence) => (
                <li key={item.id}>
                  <label className={styles.evRow}>
                    <input type="checkbox" checked={picks.includes(item.id)} onChange={(e) => setPicks(e.target.checked ? [...picks, item.id] : picks.filter((id) => id !== item.id))} />
                    <span>
                      <span className={styles.evTitle}>{item.title || host(item.url)}</span>
                      <span className={styles.evQuote}>{(item.highlight || item.quote).slice(0, 220)}</span>
                      <span className={styles.evMeta}>{host(item.url)}{item.published ? `, ${item.published}` : ""}</span>
                    </span>
                  </label>
                </li>
              ))}
            </ul>
          )}
          {books.length > 0 && (
            <ul className={styles.evidence} aria-label="내 책 근거">
              {books.map((item: IdeaBookEvidence) => (
                <li key={item.id}>
                  <label className={styles.evRow}>
                    <input type="checkbox" checked={bookPicks.includes(item.id)} onChange={(e) => setBookPicks(e.target.checked ? [...bookPicks, item.id] : bookPicks.filter((id) => id !== item.id))} />
                    <span>
                      <span className={styles.evTitle}>{item.title}{item.printed_page ? `, ${item.printed_page}쪽` : ""}</span>
                      <span className={styles.evQuote}>{item.quote.slice(0, 220)}</span>
                      <span className={styles.evMeta}>내 책</span>
                    </span>
                  </label>
                </li>
              ))}
            </ul>
          )}
          <div className={styles.actions}>
            <button type="button" className="button text" onClick={() => setStep("kind")}>뒤로</button>
            <button type="button" className="button secondary" disabled={!!busy} onClick={() => void searchAgain()}>다시 찾기</button>
            <button type="button" className="button secondary" disabled={!!busy} onClick={() => void searchBooks()}>내 책에서도 찾기</button>
            <button type="button" className="button primary" disabled={!!busy} onClick={() => void confirmEvidence()}>
              {picks.length + bookPicks.length > 0 ? `근거 ${picks.length + bookPicks.length}개로 확정` : "근거 없이 확정"}
            </button>
          </div>
          <p className={styles.help}>확정이 승인⓪이에요. 이때부터 작업이 생겨요.</p>
        </div>
      )}

      {step === "title" && (
        <div className={styles.panel}>
          {job && <p className={styles.topic}>{job.title}</p>}
          <h3 className={styles.question}>어떤 제목이 좋을까요?</h3>
          <p className={styles.help}>근거를 보고 제목 3안과 첫 문장을 제안했어요. 하나만 누르면 나머지는 알아서 맞춰요.</p>
          {suggestion && (
            <div className={styles.titles} role="radiogroup" aria-label="제목 3안">
              {suggestion.titles.map((title, i) => (
                <button key={i} type="button" role="radio" aria-checked={chosen === i} className={styles.titleCard} onClick={() => pickTitle(i)}>
                  <span className={styles.titleNo}>{i + 1}안</span>
                  <strong>{title}</strong>
                  <span>{suggestion.hooks[i]}</span>
                  {issues[i]?.length ? <em>{issues[i].join(", ")}</em> : null}
                </button>
              ))}
            </div>
          )}
          {suggestion && (
            <label className={styles.edit}>고른 제목 고치기 ({titleText.length}/{TITLE_MAX}자)
              <input value={titleText} maxLength={80} onChange={(e) => setTitleText(e.target.value)} aria-invalid={titleText.length > TITLE_MAX} />
            </label>
          )}
          <div className={styles.actions}>
            <button type="button" className="button secondary" disabled={!!busy || !job} onClick={() => void suggest()}>다시 제안</button>
            <button type="button" className="button primary" disabled={!!busy || !suggestion || !titleText.trim() || titleText.length > TITLE_MAX} onClick={() => void startDraft()}>
              원고 만들기 <Icon name="arrow" size={17} />
            </button>
          </div>
          <p className={styles.help}>원고 생성은 작업 시간이 닫혀 있으면 {WINDOW_MINUTES}분을 열고 시작해요. 비용은 작업별 예산 안에서만 써요.</p>
        </div>
      )}

      {step === "write" && job && (
        <div className={styles.panel}>
          <p className={styles.topic}>{job.title}</p>
          {done ? (
            <>
              <h3 className={styles.question}>원고가 나왔어요</h3>
              <p className={styles.help}>검수와 고쳐 쓰기까지 끝났어요. 읽고 승인①을 해 주세요.</p>
              <div className={styles.actions}>
                <Link className="button primary" href={officeHref("studio", job.id)}>원고 읽고 승인① <Icon name="arrow" size={17} /></Link>
                <Link className="button text" href="/create">새 글 하나 더</Link>
              </div>
            </>
          ) : stopped ? (
            <>
              <h3 className={styles.question}>원고를 멈췄어요</h3>
              <p className={styles.note}>{job.error || statusInfo(job.state).next}</p>
              <div className={styles.actions}>
                <Link className="button primary" href={officeHref("studio", job.id)}>작업실에서 보기</Link>
                <Link className="button text" href="/create">다른 주제로</Link>
              </div>
            </>
          ) : (
            <>
              <h3 className={styles.question}>원고를 쓰는 중이에요</h3>
              <ol className={styles.progress}>
                <li className={styles.past}>근거 확정</li>
                <li className={elapsed < 40 ? styles.now : styles.past}>근거 정리와 보류 판단</li>
                <li className={elapsed >= 40 && elapsed < 120 ? styles.now : elapsed >= 120 ? styles.past : ""}>원고 쓰기</li>
                <li className={elapsed >= 120 ? styles.now : ""}>검사, 검수, 고쳐 쓰기</li>
              </ol>
              <p className={styles.help}>{statusInfo(job.state).label}, {Math.floor(elapsed / 60)}분 {elapsed % 60}초 지났어요. 보통 2~4분 걸려요. 이 화면을 닫아도 계속 돌아가요.</p>
            </>
          )}
        </div>
      )}
    </section>
  );
}
