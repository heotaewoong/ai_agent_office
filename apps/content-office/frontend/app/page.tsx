"use client";

import { useCallback, useEffect, useRef, useState } from "react";
import { api, OfficeApiError } from "../lib/api";
import type {
  Action,
  Article,
  Artifact,
  Dashboard,
  Job,
  Selections,
  SourcePacket,
  Task,
  OutputKind,
  VoiceProfile,
} from "../lib/types";
import {
  acceptJobRefresh,
  completedOutputs,
  validReleaseOutputs,
  approvalIsCurrent,
  canApproveSource,
  formatBytes,
  formatDate,
  formatMoney,
  remainingWindow,
  safeArtifactUrl,
  statusInfo,
  thumbnailArtifact,
  toggleArticle,
} from "../lib/workflow";
import { Icon } from "./icons";
import { WorldView } from "./world-view";
import { PerformancePanel } from "./performance-panel";
import { PackagingPanel } from "./packaging-panel";
import { packagingRequired } from "../lib/packaging";
import {
  EvidenceIntake,
  IdeaBank,
  KnowledgeDrawer,
  TaskHistory,
  OutputChoices,
  outputNames,
  type IntakeDraft,
} from "./support-panels";

type View = "news" | "studio" | "delivery" | "world" | "activity";
type LocalDraft = { title: string; body: string; baseHash?: string };
const views: { id: View; title: string; icon: string; en: string }[] = [
  { id: "news", title: "오늘의 뉴스", icon: "news", en: "DAILY BRIEFING" },
  { id: "studio", title: "콘텐츠 작업실", icon: "pen", en: "CONTENT STUDIO" },
  {
    id: "delivery",
    title: "제작·출고함",
    icon: "package",
    en: "PRODUCTION & DELIVERY",
  },
  { id: "world", title: "오피스 월드", icon: "map", en: "OFFICE WORLD" },
  { id: "activity", title: "운영 기록", icon: "activity", en: "OFFICE LOG" },
];
const defaultSelections: Selections = {
  blog: true,
  video: true,
  pdf: false,
  cards: false,
};

function Badge({ state }: { state: string }) {
  const info = statusInfo(state);
  return (
    <span className={`badge ${info.tone}`}>
      <span className="status-dot" />
      {info.label}
    </span>
  );
}

function Empty({
  title,
  children,
  icon = "news",
}: {
  title: string;
  children: React.ReactNode;
  icon?: string;
}) {
  return (
    <div className="empty-state">
      <span className="empty-symbol">
        <Icon name={icon} size={28} />
      </span>
      <h3>{title}</h3>
      <p>{children}</p>
    </div>
  );
}

export default function Office() {
  const [view, setView] = useState<View>("news");
  const [localDrafts, setLocalDrafts] = useState<Record<string, LocalDraft>>(
    {},
  );
  const [intakeDrafts, setIntakeDrafts] = useState<Record<string, IntakeDraft>>(
    {},
  );
  const hasUnsavedDrafts =
    Object.keys(localDrafts).length > 0 || Object.keys(intakeDrafts).length > 0;
  useEffect(() => {
    if (!hasUnsavedDrafts) return;
    const warn = (event: BeforeUnloadEvent) => {
      event.preventDefault();
      event.returnValue = "";
    };
    window.addEventListener("beforeunload", warn);
    return () => window.removeEventListener("beforeunload", warn);
  }, [hasUnsavedDrafts]);
  const [dashboard, setDashboard] = useState<Dashboard | null>(null);
  const [selected, setSelected] = useState<string[]>([]);
  const [activeId, setActiveId] = useState("");
  const [job, setJob] = useState<Job | null>(null);
  const [busy, setBusy] = useState("");
  const [error, setError] = useState("");
  const [notice, setNotice] = useState("");
  const [loading, setLoading] = useState(true);
  const [connected, setConnected] = useState(false);
  const [showAll, setShowAll] = useState(false);
  const [now, setNow] = useState(Date.now());
  const [lastLoaded, setLastLoaded] = useState<string>();
  const alive = useRef(true);

  const loadDashboard = useCallback(async () => {
    try {
      const data = await api.dashboard();
      if (!alive.current) return;
      setDashboard(data);
      setConnected(true);
      setLastLoaded(new Date().toISOString());
      setActiveId((current) => current || data.jobs?.[0]?.id || "");
      setSelected((current) =>
        current.filter((id) =>
          data.articles.some((article) => article.id === id),
        ),
      );
    } catch (cause) {
      if (alive.current) {
        setConnected(false);
        setError(
          cause instanceof Error
            ? cause.message
            : "오피스에 연결하지 못했습니다.",
        );
      }
    } finally {
      if (alive.current) setLoading(false);
    }
  }, []);

  useEffect(() => {
    alive.current = true;
    void loadDashboard();
    const timer = setInterval(() => {
      void loadDashboard();
      setNow(Date.now());
    }, 5_000);
    return () => {
      alive.current = false;
      clearInterval(timer);
    };
  }, [loadDashboard]);

  const loadJob = useCallback(async () => {
    if (!activeId) return;
    const data = await api.job(activeId);
    if (alive.current) setJob((current) => acceptJobRefresh(current, data));
  }, [activeId]);

  useEffect(() => {
    if (!activeId) return;
    let current = true;
    const fetchJob = async () => {
      try {
        const value = await api.job(activeId);
        if (current) setJob(value);
      } catch (cause) {
        if (current)
          setError(
            cause instanceof Error ? cause.message : "작업을 읽지 못했습니다.",
          );
      }
    };
    setJob(null);
    void fetchJob();
    const timer = setInterval(() => void fetchJob(), 4_000);
    return () => {
      current = false;
      clearInterval(timer);
    };
  }, [activeId]);

  async function action(
    label: string,
    execute: () => Promise<unknown>,
    success: string,
  ): Promise<boolean> {
    if (busy || !connected) return false;
    setBusy(label);
    setError("");
    setNotice("");
    try {
      await execute();
      await Promise.all([loadDashboard(), loadJob()]);
      setNotice(success);
      return true;
    } catch (cause) {
      const message =
        cause instanceof Error ? cause.message : "요청을 처리하지 못했습니다.";
      if (cause instanceof OfficeApiError && cause.status === 409) {
        try {
          await loadJob();
          setError(
            `${message} 최신 작업을 조회했습니다. 수정 내용을 보존한 채 새 버전을 확인하세요.`,
          );
        } catch {
          setError(
            `${message} 최신 작업 조회도 실패했습니다. 연결을 확인해 주세요.`,
          );
        }
      } else setError(message);
      return false;
    } finally {
      setBusy("");
    }
  }

  async function createJobs() {
    await action(
      "작업 만들기",
      async () => {
        const result = await api.createJobs(selected);
        setActiveId(result.jobs[0]?.id || activeId);
        setView("studio");
        setSelected([]);
      },
      "작업을 만들었습니다. 기사별 근거를 확인하고 원고 생성을 시작하세요.",
    );
  }

  const jobs = dashboard?.jobs ?? [];
  const articles = dashboard?.articles ?? [];
  const reviewCount = jobs.filter(
    (item) => item.state === "source_review" || item.state === "release_review",
  ).length;
  const end =
    dashboard?.window?.authorized_end ??
    dashboard?.window?.end ??
    dashboard?.window?.ends_at ??
    dashboard?.window?.end_at;
  const currentView = views.find((item) => item.id === view)!;
  const budget = dashboard?.budget;

  return (
    <div className="office-shell">
      <a href="#main-content" className="skip-link">
        본문으로 이동
      </a>
      <aside className="sidebar">
        <button
          className="brand"
          onClick={() => setView("news")}
          aria-label="HeoBrain 오늘의 뉴스"
        >
          <span className="brand-mark">
            h<span>•</span>
          </span>
          <span>
            HeoBrain<small>CONTENT OFFICE</small>
          </span>
        </button>
        <div className="workspace-label">
          <span className="tiny-square" /> 나의 콘텐츠 오피스{" "}
          <span className="workspace-number">01</span>
        </div>
        <nav aria-label="오피스 메뉴">
          {views.map((item) => (
            <button
              key={item.id}
              className={`nav-item ${view === item.id ? "active" : ""}`}
              aria-current={view === item.id ? "page" : undefined}
              onClick={() => setView(item.id)}
            >
              <Icon name={item.icon} />
              <span>{item.title}</span>
              {item.id === "studio" && reviewCount > 0 && (
                <span className="nav-count">{reviewCount}</span>
              )}
              {view === item.id && <span className="nav-active-dot" />}
            </button>
          ))}
        </nav>
        <div className="sidebar-bottom">
          <div className="local-status">
            <span className={`status-dot ${connected ? "live" : ""}`} />
            <span>
              {connected
                ? "로컬 오피스 연결됨"
                : loading
                  ? "오피스 연결 중"
                  : "연결 확인 필요"}
            </span>
          </div>
          <div className="sidebar-window">
            <Icon name="clock" size={16} />
            <span>{remainingWindow(end, now)}</span>
            <small>남음</small>
          </div>
          <div className="operator">
            <span className="avatar">H</span>
            <span>
              나의 편집실<small>운영자 · LOCAL WORKSPACE</small>
            </span>
            <span className="operator-dot">↗</span>
          </div>
        </div>
      </aside>

      <div className="main-shell">
        <header className="topbar">
          <div>
            <span className="breadcrumb">워크스페이스</span>
            <span className="slash">/</span>
            <span>{currentView.title}</span>
          </div>
          <div className="topbar-right">
            <span className="today-date">
              {new Intl.DateTimeFormat("ko-KR", {
                timeZone: "Asia/Seoul",
                year: "numeric",
                month: "2-digit",
                day: "2-digit",
                weekday: "short",
              }).format(now)}
            </span>
            <span className="local-chip">LOCAL</span>
          </div>
        </header>
        <main id="main-content" tabIndex={-1}>
          <div className="page-heading">
            <div>
              <p className="eyebrow">
                {currentView.en}
                <span className="eyebrow-line" />
              </p>
              <h1>
                {currentView.title}
                <span className="orange-period">.</span>
              </h1>
              <p className="page-description">
                {view === "news"
                  ? "좋은 콘텐츠는, 믿을 수 있는 소식에서 시작됩니다."
                  : view === "studio"
                    ? "근거를 살피고, 문장을 다듬고, 다음 제작을 결정하세요."
                    : view === "delivery"
                      ? "완성된 결과를 확인하고, 내가 승인한 버전으로 출고하세요."
                      : view === "world"
                        ? "지금 진행 중인 모든 작업을 한 공간에서 보고, 바로 이동하거나 요청하세요."
                        : "수집부터 검수까지, 오피스가 실제로 수행한 기록입니다."}
              </p>
            </div>
            <div className="heading-actions">
              <KnowledgeDrawer />
              {view === "news" && (
                <button
                  className="button secondary"
                  disabled={!!busy || !connected}
                  onClick={() =>
                    void action(
                      "RSS 수집 요청",
                      () => api.refresh(),
                      "RSS 수집을 요청했습니다. 실제 수집 결과가 들어오면 목록이 갱신됩니다.",
                    )
                  }
                >
                  <Icon
                    name="refresh"
                    size={17}
                    className={busy === "RSS 수집 요청" ? "spin" : ""}
                  />
                  RSS 새로 수집
                </button>
              )}
            </div>
          </div>

          {error && (
            <div className="notice error" role="alert">
              <Icon name="alert" size={18} />
              <span>{error}</span>
              <button aria-label="오류 알림 닫기" onClick={() => setError("")}>
                <Icon name="close" size={16} />
              </button>
            </div>
          )}
          {notice && (
            <div className="notice success" role="status">
              <Icon name="check" size={18} />
              <span>{notice}</span>
              <button aria-label="알림 닫기" onClick={() => setNotice("")}>
                <Icon name="close" size={16} />
              </button>
            </div>
          )}
          {busy && (
            <div className="busy-line" role="status">
              <span className="spinner" />
              {busy} 처리 중… 서버의 저장 결과를 확인하고 있어요.
            </div>
          )}

          {loading ? (
            <div className="loading-panel" role="status">
              <span className="spinner" />
              <h2>오늘의 오피스를 불러오고 있어요</h2>
              <p>실제 RSS 수집 기록과 저장된 작업을 확인합니다.</p>
            </div>
          ) : !dashboard ? (
            <Empty title="로컬 오피스에 연결할 수 없어요" icon="activity">
              API와 작업자가 실행 중인지 확인한 뒤{" "}
              <button
                className="inline-button"
                onClick={() => void loadDashboard()}
              >
                다시 연결
              </button>
              해 주세요.
            </Empty>
          ) : (
            <>
              {view === "news" && (
                <>
                  <section className="brief-banner" aria-label="수집 현황">
                    <div className="brief-copy">
                      <span className="brief-label">
                        <span className="orange-star">✳</span> 오늘의 에디터
                        노트
                      </span>
                      <h2>
                        흩어진 AI 소식이
                        <br />
                        <span>나만의 콘텐츠가 되는 곳.</span>
                      </h2>
                      <p>
                        공식 출처를 읽고, 한국 독자에게 전할 뉴스를 골라 보세요.
                        <br className="desktop-break" /> 원고와 제작의 결정은
                        언제나 내 손에 있습니다.
                      </p>
                      <div className="brief-foot">
                        <span className="status-dot live" />
                        실제 수집 데이터<span className="dot-divider">·</span>
                        <span>Asia/Seoul</span>
                      </div>
                    </div>
                    <div className="brief-stats">
                      <div>
                        <span className="stat-label">수집된 기사</span>
                        <strong>
                          {articles.length.toString().padStart(2, "0")}
                          <small>건</small>
                        </strong>
                        <span className="stat-note">선정 가능한 뉴스 후보</span>
                      </div>
                      <div>
                        <span className="stat-label">연결한 공식 피드</span>
                        <strong>
                          {dashboard.feeds.length.toString().padStart(2, "0")}
                          <small>개</small>
                        </strong>
                        <span className="stat-note">
                          실패·빈 피드는 운영 기록에
                        </span>
                      </div>
                    </div>
                  </section>
                  <IdeaBank
                    onSelected={(j) => {
                      setActiveId(j.id);
                      setView("studio");
                      void loadDashboard();
                    }}
                  />
                  <section
                    className="news-section"
                    aria-labelledby="news-heading"
                  >
                    <div className="section-heading">
                      <div className="section-title">
                        <h2 id="news-heading">오늘 주목할 뉴스</h2>
                        <span className="count-pill">{articles.length}</span>
                      </div>
                      <span className="section-meta">
                        최대 3개 선택 · 점수는 편집 기준
                      </span>
                    </div>
                    {articles.length === 0 ? (
                      <Empty title="선정할 기사가 아직 없어요">
                        RSS를 수집하면 발행일과 근거가 있는 후보가 여기에
                        나타납니다. 실패한 피드와 날짜가 없는 항목은 운영
                        기록에서 확인하세요.
                      </Empty>
                    ) : (
                      <div className="article-grid">
                        {(showAll ? articles : articles.slice(0, 6)).map(
                          (article, index) => (
                            <ArticleCard
                              key={article.id}
                              article={article}
                              index={index}
                              checked={selected.includes(article.id)}
                              disabled={
                                !!busy ||
                                !connected ||
                                (selected.length >= 3 &&
                                  !selected.includes(article.id))
                              }
                              onToggle={() =>
                                setSelected((current) =>
                                  toggleArticle(current, article.id),
                                )
                              }
                            />
                          ),
                        )}
                      </div>
                    )}
                    {articles.length > 6 && (
                      <button
                        className="show-more"
                        onClick={() => setShowAll(!showAll)}
                      >
                        {showAll
                          ? "주요 뉴스만 보기"
                          : `후보 ${articles.length - 6}건 더 살펴보기`}
                        <Icon name="chevron" size={16} />
                      </button>
                    )}
                  </section>
                  <div className="selection-bar">
                    <div>
                      <span className="selection-icon">
                        <Icon name="check" size={18} />
                      </span>
                      <div>
                        <strong>
                          {selected.length > 0
                            ? `${selected.length}개의 뉴스를 골랐어요`
                            : "오늘 전할 뉴스를 골라 주세요"}
                        </strong>
                        <p>
                          {selected.length === 3
                            ? "선택을 마쳤습니다. 콘텐츠 작업실에서 이어 가세요."
                            : `원고로 만들 뉴스를 최대 3개까지 선택할 수 있어요.`}
                        </p>
                      </div>
                    </div>
                    <button
                      className="button primary"
                      disabled={selected.length === 0 || !!busy || !connected}
                      onClick={() => void createJobs()}
                    >
                      콘텐츠 작업 만들기
                      <Icon name="arrow" size={18} />
                    </button>
                  </div>
                  <BudgetStrip budget={dashboard.budget} />
                </>
              )}

              {(view === "studio" || view === "delivery") && (
                <div className="studio-layout">
                  <section
                    className="job-sidebar"
                    aria-label="콘텐츠 작업 목록"
                  >
                    <div className="section-heading">
                      <h2>내 작업</h2>
                      <span className="count-pill">{jobs.length}</span>
                    </div>
                    {jobs.length === 0 ? (
                      <div className="small-empty">
                        <p>진행 중인 작업이 없어요.</p>
                        <button
                          className="inline-button"
                          onClick={() => setView("news")}
                        >
                          오늘의 뉴스 고르기 →
                        </button>
                      </div>
                    ) : (
                      jobs.map((item) => (
                        <button
                          key={item.id}
                          className={`job-item ${item.id === activeId ? "active" : ""}`}
                          onClick={() => setActiveId(item.id)}
                        >
                          <Badge state={item.state} />
                          <strong>
                            {item.title ||
                              item.article?.editorial_title ||
                              item.article?.title}
                          </strong>
                          <span>
                            {formatDate(item.updated_at, true)}
                            <Icon name="chevron" size={14} />
                          </span>
                        </button>
                      ))
                    )}
                  </section>
                  <section className="job-content">
                    {!activeId ? (
                      <Empty title="첫 콘텐츠를 만들어 보세요" icon="pen">
                        오늘의 뉴스에서 기사를 선택하면 근거와 원고가 이곳에
                        모입니다.
                      </Empty>
                    ) : !job ? (
                      <div className="loading-panel" role="status">
                        <span className="spinner" />
                        작업을 불러오는 중…
                      </div>
                    ) : view === "studio" ? (
                      <Studio
                        key={job.id}
                        job={job}
                        model={dashboard.provider?.model}
                        intake={intakeDrafts[job.id]}
                        onIntakeChange={(value) =>
                          setIntakeDrafts((current) => {
                            const next = { ...current };
                            if (value) next[job.id] = value;
                            else delete next[job.id];
                            return next;
                          })
                        }
                        cached={localDrafts[job.id]}
                        onDraftChange={(id, value) =>
                          setLocalDrafts((current) => {
                            const next = { ...current };
                            if (value) next[id] = value;
                            else delete next[id];
                            return next;
                          })
                        }
                        busy={!!busy || !connected}
                        action={action}
                        onSaved={(value) => setJob(value)}
                        onDelivery={() => setView("delivery")}
                      />
                    ) : (
                      <>
                        {localDrafts[job.id] && (
                          <div className="notice error" role="alert">
                            <Icon name="alert" size={18} />
                            <span>
                              작업실에 저장하지 않은 원고 변경이 있습니다.
                              저장과 재검수를 마친 뒤 제작·출고를 진행하세요.
                            </span>
                          </div>
                        )}
                        <Delivery
                          voice={dashboard.provider?.voice}
                          key={job.id}
                          job={job}
                          busy={
                            !!busy || !connected || Boolean(localDrafts[job.id])
                          }
                          action={action}
                        />
                      </>
                    )}
                  </section>
                </div>
              )}

              {view === "world" && (
                <WorldView
                  activeId={activeId}
                  busy={!!busy || !connected}
                  onOpen={(v, id) => {
                    if (id && dashboard?.jobs.some((j) => j.id === id))
                      setActiveId(id);
                    setView(v);
                  }}
                  onAction={async (a, id) => {
                    const ok = await action(
                      a === "draft" ? "원고 생성" : "제작 시작",
                      () => (a === "draft" ? api.draft(id) : api.produce(id)),
                      a === "draft"
                        ? "원고 생성 작업을 요청했습니다."
                        : "제작을 요청했습니다.",
                    );
                    if (!ok) throw new Error("요청을 처리하지 못했습니다.");
                  }}
                />
              )}

              {view === "activity" && (
                <Activity
                  dashboard={dashboard}
                  job={job}
                  onChoose={(id) => setActiveId(id)}
                  activeId={activeId}
                  busy={!!busy || !connected}
                  action={action}
                />
              )}
            </>
          )}
          <footer className="page-footer">
            <span>
              HeoBrain <span className="footer-slash">/</span> 내 생각을
              콘텐츠로.
            </span>
            <span>
              {lastLoaded
                ? `화면 조회 ${formatDate(lastLoaded, true)} KST`
                : "연결을 기다리는 중"}
              <span className="dot-divider">·</span>직접 검토하고 승인하는
              오피스
            </span>
          </footer>
        </main>
      </div>
    </div>
  );
}

function ArticleCard({
  article,
  index,
  checked,
  disabled,
  onToggle,
}: {
  article: Article;
  index: number;
  checked: boolean;
  disabled: boolean;
  onToggle: () => void;
}) {
  const reasons = article.score_reasons ?? [];
  return (
    <article className={`article-card ${checked ? "selected" : ""}`}>
      <div className="card-top">
        <span className="article-source">
          <span className={`source-letter source-${index % 3}`}>
            {article.feed_name?.slice(0, 1) || "R"}
          </span>
          {article.feed_name || "공식 RSS"}
        </span>
        <label
          className={`select-box ${disabled && !checked ? "disabled" : ""}`}
        >
          <input
            type="checkbox"
            checked={checked}
            disabled={disabled}
            onChange={onToggle}
            aria-label={`${article.editorial_title || article.title} 선택`}
          />
          <span>
            <Icon name="check" size={13} />
          </span>
        </label>
      </div>
      <div className="article-tags">
        <span>
          {article.category || (index < 3 ? "EDITOR'S PICK" : "AI UPDATE")}
        </span>
        <time dateTime={article.published_at}>
          {formatDate(article.published_at)}
        </time>
      </div>
      <h3>{article.editorial_title || article.title}</h3>
      <p className="article-summary">
        {article.summary ||
          "원문과 선정 근거를 확인한 뒤 한국어 콘텐츠로 다듬을 수 있습니다."}
      </p>
      <div className="why-picked">
        <span className="why-label">선정 이유</span>
        {reasons.length ? (
          <ul>
            {reasons.slice(0, 2).map((reason, i) => (
              <li key={i}>{reason}</li>
            ))}
          </ul>
        ) : (
          <p>별도 선정 이유가 제공되지 않았습니다.</p>
        )}
        {reasons.length > 2 && (
          <details>
            <summary>근거 {reasons.length - 2}개 더 보기</summary>
            <ul>
              {reasons.slice(2).map((reason, i) => (
                <li key={i}>{reason}</li>
              ))}
            </ul>
          </details>
        )}
      </div>
      <div className="card-bottom">
        <span className="editor-score">
          <span className="score-bars">
            <i />
            <i />
            <i />
            <i />
          </span>
          <strong>{article.score}</strong>
          <small>편집 점수</small>
        </span>
        <a
          href={article.url}
          target="_blank"
          rel="noopener noreferrer"
          className="source-link"
        >
          원문 읽기
          <Icon name="external" size={14} />
        </a>
      </div>
    </article>
  );
}

function BudgetStrip({ budget }: { budget: Dashboard["budget"] }) {
  const used =
    budget.cap_krw > 0
      ? Math.min(
          100,
          ((budget.spent_krw + budget.reserved_krw) / budget.cap_krw) * 100,
        )
      : 0;
  return (
    <section
      className="budget-strip"
      aria-label="외부 API 사용량 원가 추정과 예산"
    >
      <div>
        <span className="budget-icon">₩</span>
        <div>
          <strong>오늘의 API 예산</strong>
          <span>확인한 사용량의 원가 추정치와 열린 예약</span>
        </div>
      </div>
      <div className="budget-meter">
        <span className="budget-estimate-label">확인 사용량 원가(추정)</span>
        <div className="budget-numbers">
          <span>
            <b>{formatMoney(budget.spent_krw)}</b>원{" "}
            <small>+ {formatMoney(budget.reserved_krw)}원 예약</small>
          </span>
          <span>한도 {formatMoney(budget.cap_krw)}원</span>
        </div>
        <div className="progress-track">
          <span style={{ width: `${used}%` }} />
        </div>
      </div>
      <span className="remaining-budget">
        {formatMoney(budget.remaining_krw)}
        <small>원 남음</small>
      </span>
      <p className="budget-note">
        실제 청구액이 아닌 사용량 기준 원가 추정치입니다. {budget.fx_note || ""}
        {budget.pricing_as_of ? ` · 단가 기준 ${budget.pricing_as_of}` : ""}
      </p>
    </section>
  );
}

function Studio({
  job,
  model,
  intake,
  onIntakeChange,
  cached,
  onDraftChange,
  busy,
  action,
  onSaved,
  onDelivery,
}: {
  job: Job;
  model?: string;
  intake?: IntakeDraft;
  onIntakeChange: (value: IntakeDraft | null) => void;
  cached?: LocalDraft;
  onDraftChange: (id: string, value: LocalDraft | null) => void;
  busy: boolean;
  action: Action;
  onSaved: (job: Job) => void;
  onDelivery: () => void;
}) {
  const [title, setTitle] = useState(
    cached?.title ?? job.source_packet?.title ?? job.title,
  );
  const [body, setBody] = useState(
    cached?.body ?? job.source_packet?.body ?? "",
  );
  const [dirty, setDirty] = useState(Boolean(cached));
  const [baseHash, setBaseHash] = useState(cached?.baseHash ?? job.source_hash);
  const [selections, setSelections] = useState<Selections>(
    job.selections ?? defaultSelections,
  );
  const [editorTab, setEditorTab] = useState<"write" | "evidence" | "video">(
    "write",
  );
  const [approvalVersion, setApprovalVersion] = useState<string>();
  const stale = baseHash !== job.source_hash && dirty;
  useEffect(() => {
    if (!dirty) {
      setTitle(job.source_packet?.title ?? job.title);
      setBody(job.source_packet?.body ?? "");
      setBaseHash(job.source_hash);
    }
  }, [
    job.source_hash,
    job.title,
    job.source_packet?.title,
    job.source_packet?.body,
    dirty,
  ]);
  const quality = job.source_packet?.quality;
  const locked =
    busy ||
    [
      "drafting",
      "production_queued",
      "producing",
      "needs_reconciliation",
    ].includes(job.state);
  const sourceReady = Boolean(job.source_packet?.body);
  const evidenceItems =
    job.source_packet?.evidence ?? job.article?.evidence ?? [];
  const passed = canApproveSource(job, dirty || stale);
  const selectionCount = Object.values(selections).filter(Boolean).length;

  function edit(nextTitle: string, nextBody: string) {
    setTitle(nextTitle);
    setBody(nextBody);
    setDirty(true);
    setApprovalVersion(undefined);
    onDraftChange(job.id, { title: nextTitle, body: nextBody, baseHash });
  }
  function resetEditor() {
    onDraftChange(job.id, null);
    setDirty(false);
    setTitle(job.source_packet?.title ?? job.title);
    setBody(job.source_packet?.body ?? "");
    setBaseHash(job.source_hash);
  }
  async function save() {
    const packet: SourcePacket = { ...job.source_packet, title, body };
    await action(
      "원고 저장",
      async () => {
        const updated = await api.saveSource(job.id, packet, baseHash ?? null);
        onSaved(updated);
        onDraftChange(job.id, null);
        setDirty(false);
        setBaseHash(updated.source_hash);
      },
      "새 원고를 저장하고 독립 검수를 요청했습니다. 이전 승인은 현재 원고에 적용되지 않습니다.",
    );
  }

  return (
    <>
      <div className="job-heading">
        <div>
          <Badge state={job.state} />
          <h2>
            {job.title || job.article?.editorial_title || job.article?.title}
          </h2>
          <p>{statusInfo(job.state).next}</p>
        </div>
        <a
          href={job.article?.url}
          target="_blank"
          rel="noopener noreferrer"
          className="icon-button"
          aria-label="기사 원문 새 창으로 열기"
        >
          <Icon name="external" size={18} />
        </a>
      </div>
      <WorkflowSteps state={job.state} />
      {job.error && (
        <div className="notice error" role="alert">
          <Icon name="alert" size={18} />
          <span>{job.error}</span>
        </div>
      )}
      {job.article?.origin === "idea" && (
        <PackagingPanel
          key={job.packaging?.packaging_hash ?? "new"}
          job={job}
          busy={locked}
          action={action}
        />
      )}
      <EvidenceIntake
        job={job}
        model={model}
        draft={intake}
        onChange={onIntakeChange}
        busy={busy}
        dirty={dirty}
        action={action}
      />
      <div className="editor-panel">
        <div className="editor-toolbar">
          <div className="tabs" aria-label="원고와 근거">
            <button
              className={editorTab === "write" ? "active" : ""}
              onClick={() => setEditorTab("write")}
            >
              <Icon name="pen" size={16} />
              원고 편집
            </button>
            <button
              className={editorTab === "evidence" ? "active" : ""}
              onClick={() => setEditorTab("evidence")}
            >
              <Icon name="source" size={16} />
              근거 {evidenceItems.length}
            </button>
            <button
              className={editorTab === "video" ? "active" : ""}
              onClick={() => setEditorTab("video")}
            >
              <Icon name="play" size={15} />
              영상 대본
            </button>
          </div>
          <span className="editor-save-state">
            {dirty
              ? "저장하지 않은 변경"
              : sourceReady
                ? `버전 ${job.source_hash?.slice(0, 8) || "미확인"}`
                : "원고 준비 전"}
          </span>
        </div>
        {editorTab === "write" ? (
          !sourceReady ? (
            <Empty title="근거에서 첫 원고를 시작하세요" icon="pen">
              원고 생성 후 Critique와 Eval이 독립적으로 검수합니다. 검수 결과가
              오기 전에는 승인할 수 없어요.
              <button
                className="button primary"
                disabled={locked || packagingRequired(job)}
                onClick={() =>
                  void action(
                    "원고 생성",
                    () => api.draft(job.id),
                    "원고 생성 작업을 요청했습니다. 저장된 진행 기록이 곧 갱신됩니다.",
                  )
                }
              >
                원고 생성 시작
                <Icon name="arrow" size={17} />
              </button>
              {packagingRequired(job) && (
                <p className="muted">패키지(제목·썸네일·훅)를 먼저 확정하세요.</p>
              )}
            </Empty>
          ) : (
            <div className="editor-fields">
              <label htmlFor="draft-title">콘텐츠 제목</label>
              <input
                id="draft-title"
                className="title-input"
                value={title}
                disabled={locked}
                onChange={(event) => edit(event.target.value, body)}
              />
              <div className="body-label">
                <label htmlFor="draft-body">본문 · Markdown</label>
                <span>{body.length.toLocaleString("ko-KR")}자</span>
              </div>
              <textarea
                id="draft-body"
                value={body}
                disabled={locked}
                spellCheck={false}
                onChange={(event) => edit(title, event.target.value)}
              />
              <div className="editor-foot">
                <p>
                  변경 내용을 저장하면 같은 원고를 다시 검수하고, 이전 승인은
                  해제됩니다.
                </p>
                <button
                  className="button secondary small"
                  disabled={
                    !dirty || locked || stale || !body.trim() || !title.trim()
                  }
                  onClick={() => void save()}
                >
                  저장하고 재검수
                </button>
              </div>
            </div>
          )
        ) : editorTab === "video" ? (
          <VideoPlan packet={job.source_packet} />
        ) : (
          <div className="evidence-list">
            {evidenceItems.length ? (
              evidenceItems.map((evidence, index) => {
                const url =
                  evidence.evidence_url || evidence.url || evidence.source_url;
                return (
                  <div className="evidence-item" key={evidence.id || index}>
                    <span className="evidence-number">
                      {(index + 1).toString().padStart(2, "0")}
                    </span>
                    <div>
                      <h3>
                        {evidence.claim ||
                          evidence.statement_ko ||
                          evidence.statement ||
                          "확인된 근거"}
                      </h3>
                      {(evidence.scope || evidence.limitation) && (
                        <p>{evidence.scope || evidence.limitation}</p>
                      )}
                      {typeof url === "string" && /^https:\/\//.test(url) && (
                        <a href={url} target="_blank" rel="noopener noreferrer">
                          근거 원문 확인
                          <Icon name="external" size={13} />
                        </a>
                      )}
                    </div>
                  </div>
                );
              })
            ) : (
              <Empty title="저장된 근거가 아직 없어요" icon="source">
                기사 원문과 검증된 주장 연결이 준비되면 표시됩니다.
              </Empty>
            )}
          </div>
        )}
      </div>
      {stale && (
        <div className="notice error" role="alert">
          <Icon name="alert" size={18} />
          <span>
            다른 원고 버전이 저장됐습니다. 현재 입력을 복사한 뒤 최신 원고를
            다시 불러오세요.
          </span>
          <button className="text-action" onClick={resetEditor}>
            저장된 원고 불러오기
          </button>
        </div>
      )}
      {sourceReady && (
        <>
          <QualityPanel job={job} />
          <section className="channel-panel">
            <div className="section-heading">
              <div>
                <p className="eyebrow">MAKE IT YOURS</p>
                <h3>어디에 전할까요?</h3>
              </div>
              <span className="muted">
                원고 승인과 함께 제작 항목이 저장돼요
              </span>
            </div>
            <div className="channel-options">
              {(
                [
                  {
                    id: "blog",
                    icon: "file",
                    title: "블로그",
                    description: "티스토리 · 네이버",
                  },
                  {
                    id: "video",
                    icon: "play",
                    title: "YouTube Shorts",
                    description: "세로 영상 · 자막 · 썸네일",
                  },
                  {
                    id: "pdf",
                    icon: "download",
                    title: "PDF 자료",
                    description: "요약 · 체크리스트",
                  },
                  {
                    id: "cards",
                    icon: "grid",
                    title: "카드 콘텐츠",
                    description: "선택 제작",
                  },
                ] as const
              ).map((channel) => (
                <label
                  className={`channel-option ${selections[channel.id] ? "selected" : ""}`}
                  key={channel.id}
                >
                  <input
                    type="checkbox"
                    checked={selections[channel.id]}
                    disabled={
                      locked ||
                      [
                        "source_approved",
                        "release_review",
                        "partial_release_review",
                        "release_approved",
                      ].includes(job.state)
                    }
                    onChange={(event) => {
                      setSelections((current) => ({
                        ...current,
                        [channel.id]: event.target.checked,
                      }));
                      setApprovalVersion(undefined);
                    }}
                  />
                  <Icon name={channel.icon} size={21} />
                  <strong>{channel.title}</strong>
                  <span>{channel.description}</span>
                  <span className="channel-check">
                    <Icon name="check" size={12} />
                  </span>
                </label>
              ))}
            </div>
          </section>
          <div className="approval-panel">
            <div>
              <h3>
                {job.state === "source_approved"
                  ? "이 원고로 제작할 준비가 됐어요"
                  : "읽고 확인한 원고만 다음으로"}
              </h3>
              <p>
                {dirty
                  ? "변경 내용을 먼저 저장하고 재검수를 기다려 주세요."
                  : quality?.status !== "passed" || quality.critical
                    ? "독립 검수 통과와 중대 오류 해소가 필요합니다."
                    : "근거·숫자·표현을 확인했다면 현재 버전을 승인하세요."}
              </p>
            </div>
            <div className="approval-actions">
              {job.state === "source_approved" ? (
                <button
                  className="button primary"
                  disabled={locked || dirty || stale}
                  onClick={() =>
                    void action(
                      "콘텐츠 제작",
                      async () => {
                        await api.produce(job.id);
                        onDelivery();
                      },
                      "콘텐츠 제작을 요청했습니다. 제작·출고함에서 진행 상황을 확인하세요.",
                    )
                  }
                >
                  선택 항목 제작 시작
                  <Icon name="arrow" size={17} />
                </button>
              ) : (
                <>
                  <button
                    className="button text"
                    disabled={
                      locked ||
                      !job.source_hash ||
                      dirty ||
                      job.state !== "source_review"
                    }
                    onClick={() =>
                      void action(
                        "원고 거절",
                        () =>
                          api.reviewSource(
                            job.id,
                            job.source_hash!,
                            "rejected",
                            selections,
                          ),
                        "원고를 거절했습니다. 수정 후 다시 검수할 수 있습니다.",
                      )
                    }
                  >
                    거절
                  </button>
                  <button
                    className="button primary"
                    disabled={locked || !passed || selectionCount === 0}
                    onClick={() => setApprovalVersion(job.source_hash)}
                  >
                    <Icon name="check" size={17} />
                    원고 승인
                  </button>
                </>
              )}
            </div>
          </div>
          {approvalVersion && (
            <div
              className="confirm-panel"
              role="region"
              aria-label="원고 승인 최종 확인"
            >
              <h3>현재 원고와 제작 항목을 승인할까요?</h3>
              <p>
                원고 {approvalVersion.slice(0, 12)} ·{" "}
                {Object.entries(selections)
                  .filter(([, value]) => value)
                  .map(
                    ([key]) =>
                      ({
                        blog: "블로그",
                        video: "YouTube Shorts",
                        pdf: "PDF",
                        cards: "카드",
                      })[key],
                  )
                  .join(", ")}
                . 외부 게시와 출고는 별도 검토 단계입니다.
              </p>
              {!approvalIsCurrent(approvalVersion, job.source_hash) && (
                <p className="critical-issue">
                  원고 버전이 변경됐습니다. 돌아가서 새 원고를 읽은 뒤 다시
                  승인하세요.
                </p>
              )}
              <div>
                <button
                  className="button secondary small"
                  onClick={() => setApprovalVersion(undefined)}
                >
                  돌아가기
                </button>
                <button
                  className="button primary small"
                  disabled={
                    locked ||
                    !passed ||
                    !approvalIsCurrent(approvalVersion, job.source_hash)
                  }
                  onClick={() =>
                    void action(
                      "원고 승인",
                      async () => {
                        await api.reviewSource(
                          job.id,
                          approvalVersion,
                          "approved",
                          selections,
                        );
                        setApprovalVersion(undefined);
                      },
                      "현재 원고와 제작 선택을 승인했습니다. 제작 시작을 눌러 이어 가세요.",
                    )
                  }
                >
                  이 버전 승인하기
                </button>
              </div>
            </div>
          )}
          {["blocked", "source_rejected", "failed"].includes(job.state) && (
            <div className="recovery-actions">
              <button
                className="button secondary small"
                disabled={locked || dirty}
                onClick={() =>
                  void action(
                    "원고 재검수",
                    () => api.evaluate(job.id),
                    "현재 원고의 독립 재검수를 요청했습니다.",
                  )
                }
              >
                같은 원고 재검수
              </button>
              <button
                className="button text small"
                disabled={locked || dirty}
                onClick={() =>
                  void action(
                    "새 원고 생성",
                    () => api.draft(job.id),
                    "새 원고 생성을 요청했습니다. 기존 원고를 바탕으로 한 승인은 다시 필요합니다.",
                  )
                }
              >
                새 원고 생성
              </button>
            </div>
          )}
        </>
      )}
      <TaskProgress job={job} busy={busy} action={action} />
    </>
  );
}

function VideoPlan({ packet }: { packet?: SourcePacket | null }) {
  const video = packet?.video;
  if (!video?.scenes?.length)
    return (
      <Empty title="영상 대본이 아직 없어요" icon="play">
        원고 생성과 함께 준비된 장면별 대본이 이곳에 표시됩니다.
      </Empty>
    );
  return (
    <div className="video-plan">
      <p className="eyebrow">YOUTUBE SHORTS · 제작 계획</p>
      <h3>{video.title || packet?.title}</h3>
      {video.description && (
        <p className="video-description">{video.description}</p>
      )}
      <ol className="scene-list">
        {video.scenes.map((scene, index) => (
          <li key={index}>
            <span className="scene-number">
              SCENE {(index + 1).toString().padStart(2, "0")}
            </span>
            <h4>{scene.caption || `장면 ${index + 1}`}</h4>
            <div>
              <span>말하기</span>
              <p>{scene.narration || "말하기 대본 없음"}</p>
            </div>
            <div>
              <span>화면</span>
              <p>{scene.visual || "화면 계획 없음"}</p>
            </div>
          </li>
        ))}
      </ol>
      <p className="plan-note">
        장면과 말하기 대본을 검토하는 단계입니다. 실제 음성 길이와 자막은 제작
        후 확인합니다.
      </p>
    </div>
  );
}

function WorkflowSteps({ state }: { state: string }) {
  const stage =
    state === "release_approved"
      ? 4
      : ["release_review", "partial_release_review"].includes(state)
        ? 3
        : ["producing", "production_queued", "source_approved"].includes(state)
          ? 2
          : ["source_review", "source_rejected", "blocked"].includes(state)
            ? 1
            : 0;
  return (
    <ol className="workflow-steps" aria-label="콘텐츠 제작 단계">
      {["근거·원고", "원고 승인", "콘텐츠 제작", "출고 검토"].map(
        (label, index) => (
          <li
            key={label}
            className={
              index < stage ? "done" : index === stage ? "current" : ""
            }
          >
            <span>
              {index < stage ? <Icon name="check" size={12} /> : index + 1}
            </span>
            {label}
          </li>
        ),
      )}
    </ol>
  );
}

function QualityPanel({ job }: { job: Job }) {
  const quality = job.source_packet?.quality;
  const gateItems = quality?.gates?.items ?? [];
  const gateWarnings = gateItems.filter((item) => item.level === "warn");
  const criticalIssues = [
    ...new Set([
      ...(quality?.deterministic_checks?.issues ?? []),
      ...(quality?.reviews?.flatMap((review) => review.critical_issues ?? []) ??
        []),
      ...gateItems
        .filter((item) => item.level === "block")
        .map((item) => item.message),
    ]),
  ];
  return (
    <section className="quality-panel">
      <div className="section-heading">
        <h3>독립 검수 결과</h3>
        <div style={{ display: "flex", gap: 8, alignItems: "center" }}>
          {quality?.gates && (
            <span
              className={`badge ${quality.gates.status === "pass" ? "green" : quality.gates.status === "warn" ? "orange" : "red"}`}
            >
              {quality.gates.status === "pass"
                ? "게이트 통과"
                : quality.gates.status === "warn"
                  ? "게이트 경고"
                  : "게이트 차단"}
            </span>
          )}
          <span
            className={`badge ${quality?.status === "passed" && !quality.critical ? "green" : "orange"}`}
          >
            {quality?.status === "passed" && !quality.critical
              ? "검수 통과"
              : quality?.status === "blocked"
                ? "수정 필요"
                : "검수 미완료"}
          </span>
        </div>
      </div>
      {criticalIssues.length > 0 && (
        <div className="quality-issues" role="alert">
          <strong>
            <Icon name="alert" size={15} />
            중대 수정 사항 {criticalIssues.length}개
          </strong>
          <ul>
            {criticalIssues.map((issue, index) => (
              <li key={index}>{issue}</li>
            ))}
          </ul>
        </div>
      )}
      {gateWarnings.length > 0 && (
        <details>
          <summary>게이트 경고 {gateWarnings.length}개</summary>
          <ul>
            {gateWarnings.map((item, index) => (
              <li key={index}>{item.message}</li>
            ))}
          </ul>
        </details>
      )}
      {quality?.reviews?.length ? (
        <div className="review-grid">
          {quality.reviews.map((review, index) => (
            <div className="review-card" key={`${review.role}-${index}`}>
              <div>
                <span>
                  {review.role === "critique"
                    ? "CRITIQUE · 비평"
                    : review.role === "eval"
                      ? "EVAL · 평가"
                      : review.role}
                </span>
                {review.score != null && (
                  <strong>
                    {review.score}
                    <small>점</small>
                  </strong>
                )}
              </div>
              <p>
                {review.summary ||
                  (review.passed
                    ? "검수를 통과했습니다."
                    : "검수 내용을 확인하세요.")}
              </p>
              {review.critical_issues?.map((issue, i) => (
                <p className="critical-issue" key={i}>
                  <Icon name="alert" size={13} />
                  {issue}
                </p>
              ))}
              {review.minor_issues?.length ? (
                <details>
                  <summary>추가 의견 {review.minor_issues.length}개</summary>
                  <ul>
                    {review.minor_issues.map((issue, i) => (
                      <li key={i}>{issue}</li>
                    ))}
                  </ul>
                </details>
              ) : null}
            </div>
          ))}
        </div>
      ) : (
        <p className="muted">
          현재 원고 버전에 연결된 검수 결과가 없습니다. 검수 중이거나 제공자
          연결 확인이 필요할 수 있습니다.
        </p>
      )}
      {quality?.refine_count != null && (
        <p className="quality-foot">
          수정 {quality.refine_count} / 최대 2회 · 비평과 평가는 서로의 답변을
          받지 않습니다.
        </p>
      )}
      <p className="quality-foot">
        {quality?.note ||
          "모델의 검수 결과입니다. 원고와 근거를 직접 읽고 최종 판단해 주세요."}
      </p>
    </section>
  );
}

function TaskProgress({
  job,
  tasks,
  jobs,
  busy,
  action,
}: {
  job?: Job;
  tasks?: Task[];
  jobs?: Job[];
  busy: boolean;
  action: Action;
}) {
  return (
    <TaskHistory
      tasks={tasks ?? job?.tasks ?? []}
      jobs={jobs ?? (job ? [job] : [])}
      busy={busy}
      action={action}
    />
  );
}

function Delivery({
  voice,
  job,
  busy,
  action,
}: {
  voice?: VoiceProfile;
  job: Job;
  busy: boolean;
  action: Action;
}) {
  const [preview, setPreview] = useState<string>();
  const [releaseVersion, setReleaseVersion] = useState<string>();
  const [mediaReviewed, setMediaReviewed] = useState(false);
  const [releaseOutputs, setReleaseOutputs] = useState<OutputKind[]>(() =>
    completedOutputs(job),
  );
  const [confirmedOutputs, setConfirmedOutputs] = useState<OutputKind[]>([]);
  const initializedOutputs = useRef(Boolean(job.manifest));
  useEffect(() => {
    if (!job.manifest) return;
    const allowed = completedOutputs(job);
    if (!initializedOutputs.current) {
      setReleaseOutputs(allowed);
      initializedOutputs.current = true;
    } else
      setReleaseOutputs((current) =>
        current.filter((key) => allowed.includes(key)),
      );
  }, [job.manifest?.hash, job.manifest?.completed_outputs?.join("|")]);
  const requiresMediaReview = confirmedOutputs.includes("video");
  const requiresThumbnail = releaseOutputs.includes("video");
  const files = job.manifest?.files ?? [];
  const blogFormats = [
    { name: "tistory.html", label: "HTML", format: "html" },
    { name: "tistory.md", label: "Markdown", format: "markdown" },
    { name: "naver.txt", label: "네이버 텍스트", format: "naver" },
  ].flatMap((format) => {
    const file = files.find((file) => file.name === format.name);
    return file ? [{ ...format, file }] : [];
  });
  const videoFile = files.find(
    (file) => file.kind === "video" || /\.mp4$/i.test(file.name),
  );
  const selected =
    files.find((file) => file.id === preview) ??
    blogFormats[0]?.file ??
    videoFile ??
    files[0];
  const current = selected && safeArtifactUrl(selected.url);
  const blogFormat = blogFormats.find((format) => format.file.id === selected?.id);
  const previewUrl =
    blogFormat && current
      ? `/api/jobs/${encodeURIComponent(job.id)}/blog-preview${blogFormat.format === "html" ? "" : `?format=${blogFormat.format}`}`
      : current;
  const isVideo =
    selected && (selected.kind === "video" || /\.mp4$/i.test(selected.name));
  const isImage = selected && /\.(png|jpg|jpeg|webp)$/i.test(selected.name);
  return (
    <>
      <div className="job-heading">
        <div>
          <Badge state={job.state} />
          <h2>{job.title}</h2>
          <p>{statusInfo(job.state).next}</p>
        </div>
        <span className="count-pill">{files.length} FILES</span>
      </div>
      <WorkflowSteps state={job.state} />
      {job.error && (
        <div className="notice error" role="alert">
          <Icon name="alert" size={18} />
          <span>{job.error}</span>
        </div>
      )}
      {files.length === 0 ? (
        <Empty
          title={
            job.state === "producing" || job.state === "production_queued"
              ? "콘텐츠를 제작하고 있어요"
              : "제작된 파일이 아직 없어요"
          }
          icon="package"
        >
          {job.state === "source_approved"
            ? "승인한 원고로 선택 항목을 제작하세요."
            : "원고 승인과 제작이 끝나면 블로그·영상·썸네일 파일이 표시됩니다."}
          {job.state === "source_approved" && (
            <button
              className="button primary"
              disabled={busy}
              onClick={() =>
                void action(
                  "콘텐츠 제작",
                  () => api.produce(job.id),
                  "선택한 콘텐츠 제작을 요청했습니다.",
                )
              }
            >
              제작 시작
              <Icon name="arrow" size={17} />
            </button>
          )}
        </Empty>
      ) : (
        <>
          <section className="preview-toolbar" aria-label="제작물 읽기">
            <div className="preview-output-buttons" role="group" aria-label="제작물 보기">
              {blogFormats.length > 0 && (
                <button
                  className={`button ${blogFormat ? "primary" : "secondary"}`}
                  aria-pressed={Boolean(blogFormat)}
                  onClick={() => setPreview(blogFormats[0].file.id)}
                >
                  <Icon name="file" size={18} />블로그 읽기
                </button>
              )}
              {videoFile && (
                <button
                  className={`button ${isVideo ? "primary" : "secondary"}`}
                  aria-pressed={Boolean(isVideo)}
                  onClick={() => setPreview(videoFile.id)}
                >
                  <Icon name="play" size={18} />영상 보기
                </button>
              )}
            </div>
            {blogFormat && (
              <div className="preview-formats" role="group" aria-label="블로그 파일 형식">
                {blogFormats.map(({ file, label }) => (
                  <button
                    key={file.id}
                    aria-pressed={selected?.id === file.id}
                    onClick={() => setPreview(file.id)}
                  >
                    {label}
                  </button>
                ))}
              </div>
            )}
            <div className="preview-heading">
              <div>
                <strong>{blogFormat ? "제작된 블로그 본문" : selected?.name}</strong>
                <p>출고 승인 전에도 읽고 내려받을 수 있습니다.</p>
              </div>
              {current && (
                <div className="preview-file-actions">
                  <a href={current} target="_blank" rel="noopener noreferrer" aria-label="원본 파일 새 창에서 보기">
                    원본 보기<Icon name="arrow" size={14} />
                  </a>
                  <a href={current} download={selected.name} aria-label="현재 파일 다운로드">
                    다운로드<Icon name="download" size={15} />
                  </a>
                </div>
              )}
            </div>
          </section>
          <div className="delivery-note">
            <Icon name="source" size={16} />
            <span>
              현재 파일 버전 <code>{job.manifest?.hash.slice(0, 12)}</code> ·
              미리보기로 내용을 확인한 후 출고를 승인하세요.
            </span>
          </div>
          <div className={`artifact-preview ${blogFormat ? "blog-preview" : ""}`}>
            {!current ? (
              <p>허용된 로컬 파일 주소를 확인할 수 없습니다.</p>
            ) : isVideo ? (
              <video
                controls
                preload="metadata"
                src={current}
                aria-label={selected.name}
              />
            ) : isImage ? (
              <img src={current} alt={selected.name} />
            ) : (
              <iframe
                sandbox=""
                title={blogFormat ? `${job.title} · ${blogFormat.label}` : selected.name}
                src={previewUrl ?? undefined}
              />
            )}
          </div>
          {!blogFormat && (
            <ThumbnailChoices
              job={job}
              busy={busy}
              action={action}
              onPreview={setPreview}
            />
          )}
          {isVideo && voice?.name && <section className="voice-profile" aria-label="음성 제작 설정"><Icon name="play" size={18}/><div><strong>새 영상의 음성 설정: {voice.name}</strong><p>{voice.paid?"유료 음성 프로필":"유료 음성 호출 없음"}{voice.job_cap_krw!=null?` · 음성 작업당 상한 ${formatMoney(voice.job_cap_krw)}원`:""}{voice.automatic_fallback===false?" · 자동 대체 없음":""}</p>{voice.note&&<p>{voice.note}</p>}</div></section>}
          <details className="delivery-files">
            <summary>전체 제작 파일 {files.length}개 보기</summary>
            <div className="file-list">
              {files.map((file) => (
                <ArtifactRow
                  file={file}
                  key={file.id}
                  active={file.id === selected?.id}
                  onPreview={() => setPreview(file.id)}
                />
              ))}
            </div>
          </details>
          <OutputChoices
            job={job}
            selected={releaseOutputs}
            onChange={(outputs) => {
              setReleaseOutputs(outputs);
              setReleaseVersion(undefined);
              setMediaReviewed(false);
            }}
            busy={busy || !["release_review", "partial_release_review"].includes(job.state)}
          />
          <div className="approval-panel">
            <div>
              <h3>
                {job.state === "release_approved"
                  ? "출고를 승인한 패키지입니다"
                  : "마지막 확인, 출고 승인"}
              </h3>
              <p>
                파일을 내려받아 직접 게시하는 패키지입니다. 이 화면은 외부
                채널에 자동 게시하지 않습니다.
              </p>
              {job.state === "release_approved" &&
                job.release_approval?.outputs && (
                  <p>
                    승인된 출고 범위:{" "}
                    {job.release_approval.outputs
                      .map((key) => outputNames[key])
                      .join(", ")}
                  </p>
                )}
            </div>
            <div className="approval-actions">
              {["release_review", "partial_release_review"].includes(
                job.state,
              ) && (
                <>
                  <button
                    className="button text"
                    disabled={busy}
                    onClick={() =>
                      void action(
                        "출고 거절",
                        () =>
                          api.reviewRelease(
                            job.id,
                            job.manifest!.hash,
                            "rejected",
                          ),
                        "출고를 거절했습니다. 운영 기록에서 다음 조치를 확인하세요.",
                      )
                    }
                  >
                    출고 거절
                  </button>
                  <button
                    className="button primary"
                    disabled={
                      busy ||
                      !validReleaseOutputs(job, releaseOutputs) ||
                      Boolean(
                        requiresThumbnail &&
                          !job.manifest?.selected_thumbnail_id,
                      )
                    }
                    onClick={() => {
                      setMediaReviewed(false);
                      setConfirmedOutputs([...releaseOutputs]);
                      setReleaseVersion(job.manifest?.hash);
                    }}
                  >
                    <Icon name="check" size={17} />
                    출고 승인
                  </button>
                </>
              )}
              {job.state === "release_approved" && (
                <>
                  <span className="badge green">
                    <Icon name="check" size={14} />
                    수동 게시 준비
                  </span>
                  <a
                    className="button primary"
                    href={`/api/jobs/${encodeURIComponent(job.id)}/package`}
                    download
                  >
                    <Icon name="download" size={17} />
                    출고 패키지 다운로드
                  </a>
                </>
              )}
            </div>
          </div>
          {releaseVersion && (
            <div
              className="confirm-panel"
              role="region"
              aria-label="출고 승인 확인"
            >
              <h3>현재 파일 버전을 출고 승인할까요?</h3>
              <p>
                파일 목록과 버전 {releaseVersion.slice(0, 12)}에 대한
                승인입니다. 외부 업로드·공개 계정 연결은 포함되지 않습니다. 출고
                항목:{" "}
                {confirmedOutputs.map((key) => outputNames[key]).join(", ")}
              </p>
              {!approvalIsCurrent(releaseVersion, job.manifest?.hash) && (
                <p className="critical-issue">
                  파일 버전이 변경됐습니다. 새 파일을 확인한 뒤 다시 승인하세요.
                </p>
              )}
              {requiresMediaReview && (
                <label className="media-review-check">
                  <input
                    type="checkbox"
                    checked={mediaReviewed}
                    disabled={
                      busy ||
                      !approvalIsCurrent(releaseVersion, job.manifest?.hash)
                    }
                    onChange={(event) => setMediaReviewed(event.target.checked)}
                  />
                  <span>영상 재생·음성·자막을 확인했습니다</span>
                </label>
              )}
              <div>
                <button
                  className="button secondary small"
                  onClick={() => setReleaseVersion(undefined)}
                >
                  돌아가기
                </button>
                <button
                  className="button primary small"
                  disabled={
                    busy ||
                    !["release_review", "partial_release_review"].includes(
                      job.state,
                    ) ||
                    !validReleaseOutputs(job, confirmedOutputs) ||
                    (requiresMediaReview && !mediaReviewed) ||
                    (requiresThumbnail &&
                      !job.manifest?.selected_thumbnail_id) ||
                    !approvalIsCurrent(releaseVersion, job.manifest?.hash)
                  }
                  onClick={() =>
                    void action(
                      "출고 승인",
                      async () => {
                        await api.reviewRelease(
                          job.id,
                          releaseVersion,
                          "approved",
                          mediaReviewed,
                          confirmedOutputs,
                        );
                        setReleaseVersion(undefined);
                      },
                      "현재 파일 패키지의 출고를 승인했습니다. 내려받아 직접 게시할 수 있습니다.",
                    )
                  }
                >
                  이 파일 버전 승인하기
                </button>
              </div>
            </div>
          )}
        </>
      )}
      <TaskProgress job={job} busy={busy} action={action} />
    </>
  );
}

function ThumbnailChoices({
  job,
  busy,
  action,
  onPreview,
}: {
  job: Job;
  busy: boolean;
  action: Action;
  onPreview: (id: string) => void;
}) {
  const candidates = job.manifest?.thumbnail_candidates ?? [];
  if (!candidates.length) return null;
  const scoreLabels: Record<string, string> = {
    readability: "가독성",
    clarity: "명확성",
    relevance: "관련성",
    hook: "후크",
    total: "종합",
    compliance: "근거 준수",
    visual: "시각 구성",
    layout: "구성",
    text_fit: "텍스트 배치",
    contrast: "대비",
    overall: "종합",
  };
  return (
    <section className="thumbnail-section">
      <div className="section-heading">
        <div>
          <p className="eyebrow">THUMBNAIL CONTACT SHEET</p>
          <h3>어떤 첫인상을 전할까요?</h3>
        </div>
        <span className="count-pill">{candidates.length}안 비교</span>
      </div>
      <p className="thumbnail-note">
        이미지를 눌러 크게 보고, 출고할 썸네일 한 안을 선택하세요. 점수는 로컬
        편집 기준이며 클릭 성과 예측이 아닙니다.
      </p>
      <div className="thumbnail-grid">
        {candidates.map((candidate, index) => {
          const artifact = thumbnailArtifact(candidate);
          const url = safeArtifactUrl(artifact.url);
          const selected = artifact.id === job.manifest?.selected_thumbnail_id;
          return (
            <article
              className={`thumbnail-card ${selected ? "selected" : ""}`}
              key={artifact.id}
            >
              <button
                className="thumbnail-image"
                disabled={!url}
                onClick={() => onPreview(artifact.id)}
                aria-label={`썸네일 ${index + 1} 크게 보기`}
              >
                {url ? (
                  <img
                    src={url}
                    alt={candidate.title || `썸네일 후보 ${index + 1}`}
                    loading="lazy"
                  />
                ) : (
                  <span>파일 주소 확인 필요</span>
                )}
              </button>
              <div className="thumbnail-card-body">
                <div className="thumbnail-badges">
                  <span className="thumbnail-number">
                    {(index + 1).toString().padStart(2, "0")}
                  </span>
                  {selected ? (
                    <span className="badge green">최종 선택</span>
                  ) : artifact.id === job.manifest?.best_candidate_id ? (
                    <span className="badge neutral">편집 추천</span>
                  ) : null}
                </div>
                <h4>{candidate.title || artifact.name}</h4>
                {candidate.subtitle && <p>{candidate.subtitle}</p>}
                <span className="thumbnail-angle">
                  {[candidate.angle, candidate.layout]
                    .filter(Boolean)
                    .join(" · ")}
                </span>
                {candidate.scores && (
                  <div className="thumbnail-scores">
                    {Object.entries(candidate.scores).map(([key, score]) => (
                      <span key={key}>
                        {scoreLabels[key] || key} <b>{score}</b>
                      </span>
                    ))}
                  </div>
                )}
                <button
                  className={`button small ${selected ? "secondary" : "primary"}`}
                  disabled={
                    busy ||
                    selected ||
                    !["release_review", "partial_release_review"].includes(
                      job.state,
                    )
                  }
                  aria-label={`썸네일 ${index + 1} 선택`}
                  onClick={() =>
                    void action(
                      "최종 썸네일 선택",
                      () => api.selectThumbnail(job.id, artifact.id),
                      "최종 썸네일을 저장했습니다. 파일 버전이 바뀌어 현재 패키지로 출고 검토가 필요합니다.",
                    )
                  }
                >
                  {selected ? (
                    <>
                      <Icon name="check" size={13} />
                      선택한 썸네일
                    </>
                  ) : (
                    "이 안으로 선택"
                  )}
                </button>
              </div>
            </article>
          );
        })}
      </div>
      {!job.manifest?.selected_thumbnail_id && (
        <p className="thumbnail-pending">
          출고 승인 전에 최종 썸네일을 선택해 주세요.
        </p>
      )}
    </section>
  );
}

function ArtifactRow({
  file,
  active,
  onPreview,
}: {
  file: Artifact;
  active: boolean;
  onPreview: () => void;
}) {
  const url = safeArtifactUrl(file.url);
  return (
    <div className={`file-row ${active ? "active" : ""}`}>
      <span className="file-icon">
        <Icon name={/\.mp4$/i.test(file.name) ? "play" : "file"} size={18} />
      </span>
      <button className="file-name" onClick={onPreview}>
        <strong>{file.name}</strong>
        <span>
          {file.kind} · {formatBytes(file.size)}
          {file.sha256 ? ` · SHA256 ${file.sha256.slice(0, 10)}` : ""}
        </span>
      </button>
      {url ? (
        <a
          href={url}
          download={file.name}
          className="icon-button"
          aria-label={`${file.name} 다운로드`}
        >
          <Icon name="download" size={18} />
        </a>
      ) : (
        <span className="muted">파일 경로 확인 필요</span>
      )}
    </div>
  );
}

function Activity({
  dashboard,
  job,
  onChoose,
  activeId,
  busy,
  action,
}: {
  dashboard: Dashboard;
  job: Job | null;
  onChoose: (id: string) => void;
  activeId: string;
  busy: boolean;
  action: Action;
}) {
  return (
    <div className="activity-page">
      <BudgetStrip budget={dashboard.budget} />
      <PerformancePanel />
      <section className="feed-panel">
        <div className="section-heading">
          <div>
            <p className="eyebrow">SOURCE HEALTH</p>
            <h2>피드 수집 기록</h2>
          </div>
          <span className="section-meta">실패와 기사 없음은 구분합니다</span>
        </div>
        {dashboard.feeds.length ? (
          <div className="table-scroll">
            <table>
              <thead>
                <tr>
                  <th>공식 피드</th>
                  <th>수집 상태</th>
                  <th>항목</th>
                  <th>조회 시각 · KST</th>
                </tr>
              </thead>
              <tbody>
                {dashboard.feeds.map((feed, index) => (
                  <tr key={feed.id || index}>
                    <td>
                      <strong>{feed.name || feed.id || "공식 피드"}</strong>
                      {feed.url && (
                        <a
                          href={feed.url}
                          target="_blank"
                          rel="noopener noreferrer"
                        >
                          RSS 원문
                          <Icon name="external" size={12} />
                        </a>
                      )}
                    </td>
                    <td>
                      <span
                        className={`feed-status ${feed.error ? "has-error" : ""}`}
                      >
                        {feed.error
                          ? "수집 실패"
                          : feed.state === "ok" ||
                              feed.status === 200 ||
                              feed.status === "ok" ||
                              feed.status === "success"
                            ? "수집 성공"
                            : String(
                                feed.state ?? feed.status ?? "상태 미확인",
                              )}
                      </span>
                      {feed.error && (
                        <small className="feed-error">{feed.error}</small>
                      )}
                    </td>
                    <td>{feed.item_count ?? feed.count ?? "—"}</td>
                    <td>
                      {formatDate(
                        feed.checked_at || feed.retrieved_at || feed.fetched_at,
                        true,
                      )}
                    </td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        ) : (
          <Empty title="수집 기록이 없어요" icon="activity">
            RSS 수집 후 실제 상태와 실패 원인이 기록됩니다.
          </Empty>
        )}
      </section>
      <section className="agent-panel">
        <div className="section-heading">
          <div>
            <p className="eyebrow">RESPONSIBILITIES</p>
            <h2>담당 에이전트</h2>
          </div>
        </div>
        {dashboard.agents.length ? (
          <div className="agent-grid">
            {dashboard.agents.map((agent, index) => (
              <div className="agent-card" key={agent.name || index}>
                <span className="agent-avatar">
                  {(agent.name || agent.role || "A").slice(0, 1)}
                </span>
                <strong>{agent.name || agent.role}</strong>
                <span>
                  {agent.state ||
                    agent.status ||
                    agent.mode ||
                    "실행 상태 미제공"}
                </span>
                {(agent.detail || agent.description) && (
                  <p>{agent.detail || agent.description}</p>
                )}
              </div>
            ))}
          </div>
        ) : (
          <p className="muted">
            등록된 에이전트 실행 상태가 없습니다. 실행되지 않은 역할을 완료로
            표시하지 않습니다.
          </p>
        )}
      </section>
      <section className="event-panel">
        <div className="section-heading">
          <div>
            <p className="eyebrow">PERSISTENT ACTIVITY</p>
            <h2>작업별 이벤트</h2>
          </div>
          <select
            aria-label="기록을 볼 작업 선택"
            value={activeId}
            onChange={(event) => onChoose(event.target.value)}
          >
            <option value="">작업 선택</option>
            {dashboard.jobs.map((item) => (
              <option key={item.id} value={item.id}>
                {item.title}
              </option>
            ))}
          </select>
        </div>
        {job?.events?.length ? (
          <div className="timeline">
            {job.events
              .slice()
              .reverse()
              .map((event, index) => (
                <div className="timeline-item" key={event.id || index}>
                  <span className="timeline-dot" />
                  <time>{formatDate(event.created_at || event.at, true)}</time>
                  <div>
                    <strong>
                      {event.message ||
                        event.kind ||
                        event.event ||
                        event.state ||
                        "작업 이벤트"}
                    </strong>
                    {(event.payload ?? event.data) != null && (
                      <details>
                        <summary>상세 기록</summary>
                        <pre>
                          {JSON.stringify(event.payload ?? event.data, null, 2)}
                        </pre>
                      </details>
                    )}
                  </div>
                </div>
              ))}
          </div>
        ) : (
          <p className="muted">선택한 작업의 저장된 이벤트가 아직 없습니다.</p>
        )}
        <TaskProgress
          tasks={dashboard.tasks ?? job?.tasks ?? []}
          jobs={dashboard.jobs}
          busy={busy}
          action={action}
        />
      </section>
    </div>
  );
}
