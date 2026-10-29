"use client";

import { useCallback, useEffect, useState } from "react";
import { api } from "../lib/api";
import { costRows, shortCommit, testSummary, type ArchitectureOverview } from "../lib/architecture";
import { formatDate } from "../lib/workflow";

const ROLE_LABEL: Record<string, string> = { image: "영상 장면 배경", card_image: "카드 이미지" };

/** 지금 EC2에서 돌아가는 오피스의 구조도. 그림은 저장소 문서, 숫자는 서버가 배포·실행 기록으로 채운다. */
export function ArchitectureView() {
  const [data, setData] = useState<ArchitectureOverview | null>(null);
  const [error, setError] = useState("");

  const load = useCallback(async () => {
    try {
      setData(await api.architecture());
      setError("");
    } catch (cause) {
      setError(cause instanceof Error ? cause.message : "구조도를 불러오지 못했습니다.");
    }
  }, []);

  useEffect(() => {
    void load();
    const timer = setInterval(() => void load(), 30_000);
    return () => clearInterval(timer);
  }, [load]);

  if (error) return <div className="notice error" role="alert">{error}</div>;
  if (!data) return <p className="muted">구조도를 불러오는 중입니다.</p>;

  const tests = testSummary(data.build);
  const rows = costRows(data.doc.unit_costs, data.usage);
  const windowOpen = data.window.status === "active" && data.window.authorized_end && Date.parse(data.window.authorized_end) > Date.now();

  return (
    <div className="arch">
      <section className="arch-facts" aria-label="지금 실행판">
        <div className="arch-fact">
          <span>실행 중인 커밋</span>
          <strong className="mono">{shortCommit(data.git.commit)}</strong>
          <em>{data.git.subject ?? ""}</em>
        </div>
        <div className="arch-fact">
          <span>배포 시각</span>
          <strong>{data.build ? formatDate(data.build.deployed_at, true) : "기록 없음"}</strong>
          <em className={data.build_matches_running_code ? "" : "warn"}>{data.build_matches_running_code ? "실행 코드와 일치" : "배포 기록과 실행 코드가 다름"}</em>
        </div>
        <div className="arch-fact">
          <span>테스트</span>
          <strong className={tests.failed ? "bad" : ""}>{tests.text}</strong>
          <em>배포할 때 EC2에서 실행</em>
        </div>
        <div className="arch-fact">
          <span>작업 시간</span>
          <strong>{windowOpen ? `열림 · ${formatDate(data.window.authorized_end ?? undefined, true)}까지` : "닫힘"}</strong>
          <em>작업자 {data.worker.state === "online" ? "실행 중" : "멈춤"}</em>
        </div>
        <div className="arch-fact">
          <span>누적 비용</span>
          <strong className="mono">{Math.round(data.budget.spent_krw).toLocaleString("ko-KR")}원</strong>
          <em>한도 {data.budget.cap_krw.toLocaleString("ko-KR")}원 · 남음 {Math.round(data.budget.remaining_krw).toLocaleString("ko-KR")}원</em>
        </div>
      </section>

      <section className="arch-section">
        <h2>{data.doc.headline}</h2>
        <p className="muted arch-lede">{data.doc.summary}</p>
        <div className="arch-flow" role="list">
          {data.doc.flow.map((step, i) =>
            step.kind === "stage" ? (
              <article className="arch-stage" role="listitem" key={i}>
                <span className="arch-num">{step.num}</span>
                <h3>{step.title}</h3>
                <ul>
                  {step.items.map((item) => (
                    <li key={item}>{item}</li>
                  ))}
                </ul>
                <span className="arch-who">{step.who}</span>
              </article>
            ) : step.kind === "gate" ? (
              <div className="arch-gate" role="listitem" key={i}>
                <span className="arch-mark">{step.mark}</span>
                <span className="arch-glabel">{step.label}</span>
              </div>
            ) : (
              <div className="arch-gate plain" role="listitem" key={i} aria-hidden="true">
                <span className="arch-mark">→</span>
              </div>
            ),
          )}
        </div>
        <p className="arch-legend"><span className="arch-dot gate" />사람이 결정하는 관문 · AI가 대신 통과시킬 수 없음</p>
      </section>

      <section className="arch-section">
        <h2>어디에서 무엇이 돌아가나</h2>
        <div className="arch-diagram">
          <InfraDiagram keys={data.keys} text={data.profiles.text} />
        </div>
      </section>

      <section className="arch-section">
        <h2>어떤 모델을 쓰고 얼마가 드나</h2>
        <p className="muted">EC2에서 실제로 호출한 기록을 모아 계산합니다. 공식 단가 × 사용량 추정이며 1달러 = 2,000원으로 예약합니다.</p>
        <div className="arch-table">
          <table>
            <thead>
              <tr><th>하는 일</th><th>실제로 쓴 모델</th><th>단위</th><th>호출</th><th>1회 평균</th><th>설정 위치</th></tr>
            </thead>
            <tbody>
              {rows.map((row) => (
                <tr key={row.role}>
                  <td>{row.task}</td>
                  <td className="mono">{row.models.length ? row.models.join(", ") : <span className="muted">기록 없음</span>}</td>
                  <td>{row.unit}</td>
                  <td className="num">{row.calls}</td>
                  <td className="num">{row.perCall == null ? "—" : `${row.perCall}원`}</td>
                  <td>{row.where}</td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      </section>

      <section className="arch-section">
        <h2>돈과 사고를 막는 장치</h2>
        <div className="arch-rails">
          {data.doc.rails.map((rail) => (
            <div className="arch-rail" key={rail.title}>
              <h3>{rail.title}</h3>
              <p>{rail.text}</p>
            </div>
          ))}
        </div>
      </section>

      <section className="arch-section">
        <h2>지금 상태</h2>
        <div className="arch-status">
          {(["openai", "gemini", "runway", "youtube"] as const).map((key) => (
            <div className="arch-status-row" key={key}>
              <span className={`arch-pill ${data.keys[key] ? "ok" : "off"}`}>{data.keys[key] ? "연결됨" : "미연결"}</span>
              <p>{{ openai: "OpenAI 키 (글·이미지)", gemini: "Gemini 키 (기사 요약·음성)", runway: "Runway 키 (생성 영상)", youtube: "YouTube 업로드 자격" }[key]} <span className="muted">· EC2 환경 파일 기준, 값은 표시하지 않음</span></p>
            </div>
          ))}
          {data.doc.status.map((item) => (
            <div className="arch-status-row" key={item.text}>
              <span className={`arch-pill ${item.state}`}>{item.label}</span>
              <p>{item.text} <span className="muted">· {item.note}</span></p>
            </div>
          ))}
        </div>
      </section>

      <section className="arch-section">
        <h2>최근 변경</h2>
        <ol className="arch-commits">
          {data.git.recent.map((c) => (
            <li key={c.commit}>
              <span className="mono">{c.commit}</span>
              <span>{c.subject}</span>
              <span className="muted">{c.author} · {formatDate(c.at, true)}</span>
            </li>
          ))}
        </ol>
        <p className="muted">이 화면은 30초마다 다시 읽고, 배포할 때마다 커밋·테스트 결과가 자동으로 바뀝니다. 그림은 <span className="mono">backend/config/architecture.json</span>을 고치면 바뀝니다.</p>
      </section>
    </div>
  );
}

function InfraDiagram({ keys, text }: { keys: ArchitectureOverview["keys"]; text: string }) {
  const ext = (on: boolean) => (on ? "arch-ext" : "arch-off");
  return (
    <svg viewBox="0 0 1200 640" role="img" aria-label="서버 배치도">
      <defs>
        <marker id="arch-arr" viewBox="0 0 10 10" refX="9" refY="5" markerWidth="7" markerHeight="7" orient="auto-start-reverse"><path d="M0,0 L10,5 L0,10 z" className="arch-head" /></marker>
      </defs>
      <rect className="arch-box" x="20" y="70" width="170" height="86" rx="10" />
      <text className="t" x="36" y="100">운영자 브라우저</text>
      <text className="s" x="36" y="122">PC · 휴대폰</text>
      <text className="m" x="36" y="142">77-114-15-207.sslip.io</text>
      <rect className="arch-box" x="20" y="214" width="170" height="96" rx="10" />
      <text className="t" x="36" y="244">nginx</text>
      <text className="s" x="36" y="266">HTTPS(Let&apos;s Encrypt)</text>
      <text className="s" x="36" y="286">로그인(기본 인증)</text>
      <rect className="arch-box" x="20" y="470" width="170" height="104" rx="10" />
      <text className="t" x="36" y="500">GitHub main</text>
      <text className="s" x="36" y="522">heotaewoong/</text>
      <text className="s" x="36" y="540">ai_agent_office</text>
      <text className="m" x="36" y="562">pull·test·build·restart</text>
      <path className="arch-wire" d="M105 156 L105 210" markerEnd="url(#arch-arr)" />
      <path className="arch-wire" d="M190 262 L292 262 L292 120 L320 120" markerEnd="url(#arch-arr)" />
      <path className="arch-wire" d="M190 522 L320 522" markerEnd="url(#arch-arr)" />
      <text className="m" x="206" y="512">배포</text>

      <rect className="arch-frame" x="320" y="20" width="560" height="600" rx="14" />
      <text className="f" x="340" y="46">AWS EC2 · us-east-2 · t3.small · Ubuntu</text>
      <rect className="arch-box strong" x="345" y="70" width="230" height="96" rx="10" />
      <text className="t" x="361" y="100">화면 (Next.js)</text>
      <text className="m" x="361" y="122">:3110</text>
      <text className="s" x="361" y="144">뉴스·작업실·출고함·설정·구조도</text>
      <rect className="arch-box strong" x="345" y="214" width="230" height="110" rx="10" />
      <text className="t" x="361" y="244">API (FastAPI)</text>
      <text className="m" x="361" y="266">:8510</text>
      <text className="s" x="361" y="288">승인 기록 · 작업 큐 등록</text>
      <text className="s" x="361" y="308">세션·CSRF·작업 시간 확인</text>
      <rect className="arch-box strong" x="625" y="214" width="230" height="110" rx="10" />
      <text className="t" x="641" y="244">작업자 (worker)</text>
      <text className="s" x="641" y="268">큐에서 꺼내 실행</text>
      <text className="s" x="641" y="288">원고·제작·퀴즈·카드·업로드</text>
      <text className="s" x="641" y="308">마감 시각에 스스로 종료</text>
      <rect className="arch-box strong" x="625" y="70" width="230" height="96" rx="10" />
      <text className="t" x="641" y="100">감시자 (watcher)</text>
      <text className="s" x="641" y="122">작업 시간 마감 감시</text>
      <text className="s" x="641" y="144">끝나면 시간을 닫음</text>
      <rect className="arch-box" x="345" y="380" width="510" height="214" rx="10" />
      <text className="t" x="361" y="410">상태 저장소 (~/.local/state/heobrain-content-office)</text>
      <text className="m" x="361" y="440">office.sqlite</text>
      <text className="s" x="480" y="440">작업 · 승인 ⓪①②③ · 작업 큐 · 비용 장부 · 이벤트</text>
      <text className="m" x="361" y="468">artifacts/</text>
      <text className="s" x="480" y="468">블로그 · 영상 · 썸네일 · PDF · 퀴즈 · 카드 PNG</text>
      <text className="m" x="361" y="496">image-assets/</text>
      <text className="s" x="480" y="496">생성 이미지와 비용 영수증(재사용 캐시)</text>
      <text className="m" x="361" y="524">runtime/</text>
      <text className="s" x="480" y="524">프로세스 장부 · 로그 · 배포 기록</text>
      <text className="m" x="361" y="552">~/office.env</text>
      <text className="s" x="480" y="552">API 키 · 화면·Git에 노출 안 됨</text>
      <path className="arch-wire" d="M460 166 L460 210" markerEnd="url(#arch-arr)" />
      <text className="m" x="468" y="194">/api</text>
      <path className="arch-wire" d="M575 270 L621 270" markerEnd="url(#arch-arr)" />
      <text className="m" x="579" y="262">큐</text>
      <path className="arch-wire" d="M460 324 L460 376" markerEnd="url(#arch-arr)" />
      <path className="arch-wire" d="M740 324 L740 376" markerEnd="url(#arch-arr)" />
      <path className="arch-wire" d="M740 166 L740 210" markerEnd="url(#arch-arr)" />

      <text className="f" x="912" y="46">외부 서비스 (작업자만 호출)</text>
      <rect className={ext(keys.openai)} x="912" y="64" width="270" height="70" rx="10" />
      <text className="e" x="928" y="92">OpenAI · 글</text>
      <text className="m" x="928" y="116">{text.startsWith("gpt-") ? `${text} (현재 글 모델)` : "선택 가능"}</text>
      <rect className={ext(keys.openai)} x="912" y="148" width="270" height="70" rx="10" />
      <text className="e" x="928" y="176">OpenAI · 이미지</text>
      <text className="m" x="928" y="200">gpt-image-2.5-flare</text>
      <rect className={ext(keys.gemini)} x="912" y="232" width="270" height="70" rx="10" />
      <text className="e" x="928" y="260">Gemini</text>
      <text className="m" x="928" y="284">{text.startsWith("gemini") ? `${text} (현재 글 모델)` : "Flash-Lite 기사 요약 · TTS"}</text>
      <rect className="arch-ext" x="912" y="316" width="270" height="70" rx="10" />
      <text className="e" x="928" y="344">RSS 피드</text>
      <text className="m" x="928" y="368">공식 블로그 · arXiv 등</text>
      <rect className={ext(keys.youtube)} x="912" y="400" width="270" height="70" rx="10" />
      <text className="e" x="928" y="428">YouTube Data API</text>
      <text className="m" x="928" y="452">{keys.youtube ? "연결됨 · 비공개 업로드" : "미연결 · 비공개 업로드 전용"}</text>
      <rect className={ext(keys.runway)} x="912" y="484" width="270" height="70" rx="10" />
      <text className="e" x="928" y="512">Runway</text>
      <text className="m" x="928" y="536">{keys.runway ? "연결됨 · 짧은 생성 영상" : "미연결 · 짧은 생성 영상"}</text>
      <path className="arch-wire ext" d="M855 250 L885 250 L885 99 L908 99" markerEnd="url(#arch-arr)" />
      <path className="arch-wire ext" d="M885 183 L908 183" markerEnd="url(#arch-arr)" />
      <path className="arch-wire ext" d="M885 250 L885 267 L908 267" markerEnd="url(#arch-arr)" />
      <path className="arch-wire ext" d="M885 267 L885 351 L908 351" markerEnd="url(#arch-arr)" />
      <path className="arch-wire ext" d="M885 351 L885 435 L908 435" markerEnd="url(#arch-arr)" />
      <path className="arch-wire ext" d="M885 435 L885 519 L908 519" markerEnd="url(#arch-arr)" />
      <rect className="arch-box" x="912" y="572" width="270" height="48" rx="10" />
      <text className="s" x="928" y="601">같은 EC2: n8n · Hermes · magma 사이트</text>
    </svg>
  );
}
