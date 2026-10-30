"use client";

import { useCallback, useEffect, useState } from "react";
import { api } from "../lib/api";
import { costRows, flowStages, imageRoute, pipelineSvg, shortCommit, testSummary, type ArchitectureOverview } from "../lib/architecture";
import { formatDate } from "../lib/workflow";

/** 공정 정의와 실행 사실을 분리해 읽는, 제작을 실행하지 않는 안내 화면. */
export function ArchitectureView() {
  const [data, setData] = useState<ArchitectureOverview | null>(null);
  const [error, setError] = useState("");
  const [loadedAt, setLoadedAt] = useState("");
  const load = useCallback(async () => {
    try {
      setData(await api.architecture());
      setLoadedAt(new Date().toISOString());
      setError("");
    } catch (cause) {
      setError(cause instanceof Error ? cause.message : "공정도를 불러오지 못했습니다.");
    }
  }, []);
  useEffect(() => {
    void load();
    const timer = setInterval(() => void load(), 30_000);
    return () => clearInterval(timer);
  }, [load]);

  if (!data) return error ? <div className="notice error" role="alert">{error} <button onClick={() => void load()}>다시 불러오기</button></div> : <p className="muted" role="status">공정도와 운영 기록을 불러오는 중입니다.</p>;
  const stages = flowStages(data.doc.flow);
  const gates = stages.flatMap((row) => row.gates);
  const rows = costRows(data.doc.unit_costs, data.usage);
  const tests = testSummary(data.build);
  const windowOpen = data.window.status === "active" && data.window.authorized_end && Date.parse(data.window.authorized_end) > Date.now();
  const downloadMap = () => {
    const url = URL.createObjectURL(new Blob([pipelineSvg(data.doc)], { type: "image/svg+xml;charset=utf-8" }));
    const link = document.createElement("a");
    link.href = url;
    link.download = "heobrain-content-pipeline.svg";
    link.click();
    setTimeout(() => URL.revokeObjectURL(url), 1000);
  };

  return (
    <div className="arch">
      {error && <div className="notice error" role="alert">갱신하지 못해 마지막 조회 내용을 표시합니다. {error} <button onClick={() => void load()}>다시 불러오기</button></div>}
      <section className="arch-hero" aria-labelledby="pipeline-title">
        <div className="arch-eyebrow">HEOBRAIN / CONTENT OPERATIONS</div>
        <div className="arch-hero-heading">
          <h2 id="pipeline-title">{data.doc.headline}</h2>
          <button className="arch-export" onClick={downloadMap}>전체 공정도 SVG 내려받기 <span aria-hidden="true">↗</span></button>
        </div>
        <p>{data.doc.summary}</p>
        <div className="arch-intro-facts"><span>{stages.length}개 공정</span><span>{gates.length}개 사람 승인</span><span>선택 제작 · 완료 출력별 출고</span><span>실행과 안내를 구분</span></div>
        <nav className="arch-jump" aria-label="파이프라인 내용 바로가기">
          <a href="#pipeline-flow">공정별 자세히 <span aria-hidden="true">↓</span></a>
          <a href="#pipeline-branches">병렬·별도 흐름 <span aria-hidden="true">↓</span></a>
          <a href="#pipeline-runtime">서버·연결 경계 <span aria-hidden="true">↓</span></a>
          <a href="#pipeline-cost">비용·운영 기록 <span aria-hidden="true">↓</span></a>
        </nav>
        <p className="arch-freshness">정의 {data.doc.definition_version ?? "저장소 문서"} · 운영 기록 마지막 조회 {formatDate(loadedAt, true)} · 읽기 전용 안내</p>
      </section>

      <section className="arch-section" aria-labelledby="pipeline-overview-title">
        <div className="arch-section-heading"><span className="arch-index">01</span><div><h2 id="pipeline-overview-title">한눈에 보는 제작 순서</h2><p>위에서 아래로, 번호 순서대로 진행합니다. 단계 이름을 누르면 세부 내용으로 이동합니다.</p></div></div>
        <ol className="arch-overview" aria-label="콘텐츠 파이프라인 전체 순서">
          {stages.map(({ stage, gates: next }, i) => <li key={stage.id ?? i}>
            <a href={`#pipeline-stage-${i + 1}`}><span className="arch-step-index">{String(i + 1).padStart(2, "0")}</span><strong>{stage.num.split("·").pop()?.trim() ?? stage.title}</strong><span>{stage.output ?? stage.title}</span><small>{next.length ? next.map((g) => `${g.mark} ${g.label}`).join(" · ") : i === stages.length - 1 ? "검토한 교훈을 기획으로" : "다음 공정으로"}</small></a>
          </li>)}
        </ol>
        <div className="arch-approval-key"><strong>사람이 결정하는 4개의 관문</strong><div>{gates.map((gate) => <span key={gate.mark}><b>{gate.mark}</b> {gate.label}</span>)}</div><p>AI가 승인을 만들지 않습니다. 승인 기록은 외부 게시·발급·발송 완료를 뜻하지 않습니다.</p></div>
      </section>

      <section id="pipeline-flow" className="arch-section" tabIndex={-1} aria-labelledby="pipeline-flow-title">
        <div className="arch-section-heading"><span className="arch-index">02</span><div><h2 id="pipeline-flow-title">각 공정에서 무엇을 받고, 무엇을 남기나</h2><p>입력 → 처리 → 산출물 → 사람 확인을 같은 순서로 읽습니다.</p></div></div>
        <div className="arch-stage-grid">
          {stages.map(({ stage, gates: after }, i) => <article className="arch-process" id={`pipeline-stage-${i + 1}`} key={stage.id ?? i} tabIndex={-1} aria-labelledby={`pipeline-stage-title-${i + 1}`}>
            <header><span className="arch-step-index">{String(i + 1).padStart(2, "0")}</span><div><span className="arch-kicker">{stage.num}</span><h3 id={`pipeline-stage-title-${i + 1}`}>{stage.title}</h3></div></header>
            {stage.input && <div className="arch-io"><span>입력</span><p>{stage.input}</p></div>}
            <ul className="arch-checklist">{stage.items.map((item) => <li key={item}>{item}</li>)}</ul>
            {stage.output && <div className="arch-io result"><span>산출물</span><p>{stage.output}</p></div>}
            <p className="arch-owner"><strong>담당·도구</strong> {stage.who}</p>
            {stage.entry && <p className="arch-entry"><strong>앱에서 찾기</strong> {stage.entry}</p>}
            {after.map((gate) => <div className="arch-human-gate" key={gate.mark}><span aria-hidden="true">{gate.mark}</span><div><strong>사람 확인 · {gate.label}</strong><p>{gate.checks ?? "이 관문은 사람이 직접 확인합니다."}</p></div></div>)}
            {!after.length && <p className="arch-continue">{i === stages.length - 1 ? "↺ 검토·승인한 교훈을 다음 기획에 반영" : "→ 위 결과를 다음 공정의 입력으로 전달"}</p>}
          </article>)}
        </div>
      </section>

      {!!data.doc.lanes?.length && <section id="pipeline-branches" className="arch-section" tabIndex={-1} aria-labelledby="pipeline-branches-title">
        <div className="arch-section-heading"><span className="arch-index">03</span><div><h2 id="pipeline-branches-title">한 줄로 묶으면 안 되는 병렬·별도 흐름</h2><p>제작 분기, 상품 혜택, 동의·발송을 구분해야 선행조건과 실제 실행을 혼동하지 않습니다.</p></div></div>
        <div className="arch-lanes">{data.doc.lanes.map((lane) => <article className="arch-lane" key={lane.id}>
          <div className="arch-lane-heading"><span className={`arch-pill ${lane.state}`}>{lane.label}</span><h3>{lane.title}</h3><p>{lane.phase}</p></div>
          <ol>{lane.steps.map((step, i) => <li key={step}><span>{String(i + 1).padStart(2, "0")}</span><p>{step}</p></li>)}</ol>
          <p className="arch-boundary"><strong>실행 경계</strong>{lane.boundary}</p>
        </article>)}</div>
      </section>}

      <section id="pipeline-runtime" className="arch-section" tabIndex={-1} aria-labelledby="pipeline-runtime-title">
        <div className="arch-section-heading"><span className="arch-index">04</span><div><h2 id="pipeline-runtime-title">같은 서버 안에서도 실행 책임은 나뉩니다</h2><p>화면·API·작업자·저장소와, 외부 서비스의 실제 호출 경로를 분리해 봅니다.</p></div></div>
        <RuntimeMap data={data} />
        <div className="arch-runtime-separate"><strong>같은 EC2의 다른 도구</strong><p>Hermes · n8n · magma 사이트가 같은 서버에 있어도 이 콘텐츠 앱의 작업 큐와 자동 연결된 것은 아닙니다. Hermes 비서팀의 업무 전달·결과 회수는 보류된 별도 작업입니다.</p></div>
      </section>

      <section className="arch-section" aria-labelledby="pipeline-safety-title">
        <div className="arch-section-heading"><span className="arch-index">05</span><div><h2 id="pipeline-safety-title">실패해도 남겨야 할 것, 넘지 말아야 할 것</h2><p>원고 판본·완료 자산·비용 예약·실제 외부 결과를 보존합니다.</p></div></div>
        <div className="arch-rails">{data.doc.rails.map((rail) => <article className="arch-rail" key={rail.title}><h3>{rail.title}</h3><p>{rail.text}</p></article>)}</div>
      </section>

      <section id="pipeline-cost" className="arch-section" tabIndex={-1} aria-labelledby="pipeline-cost-title">
        <div className="arch-section-heading"><span className="arch-index">06</span><div><h2 id="pipeline-cost-title">선택한 경로와 집계된 비용</h2><p>설정·호출 기록·키 존재는 서로 다른 정보입니다. 키가 있다고 실제 호출 성공으로 표시하지 않습니다.</p></div></div>
        <div className="arch-selected"><div><span>현재 글 모델</span><strong className="mono">{data.profiles.text}</strong></div><div><span>현재 이미지 프로필</span><strong>{imageRoute(data.profiles.image)}</strong><small className="mono">{data.profiles.image}</small></div><p>구독 경로와 API 경로의 비용은 다릅니다. 선택된 프로필과 호출 영수증을 확인하세요. 키·토큰 값은 표시하지 않습니다.</p></div>
        <div className="arch-table" role="region" aria-label="모델별 집계 비용 표 · 좁은 화면에서는 가로로 이동" tabIndex={0}><table>
          <caption>원고 모델 이벤트와 완료 이미지 영수증의 집계입니다. 음성·클립·청구서 전체의 완전한 합계가 아니며, 기록 없음은 무료라는 뜻이 아닙니다.</caption>
          <thead><tr><th scope="col">하는 일</th><th scope="col">기록된 모델</th><th scope="col">집계 단위</th><th scope="col">호출</th><th scope="col">1회 평균</th><th scope="col">설정 위치</th></tr></thead>
          <tbody>{rows.map((row) => <tr key={row.role}><th scope="row">{row.task}</th><td className="mono">{row.models.length ? row.models.join(", ") : <span className="muted">집계 기록 없음</span>}</td><td>{row.unit}</td><td className="num">{row.calls}</td><td className="num">{row.perCall == null ? "—" : `${row.perCall}원`}</td><td>{row.where}</td></tr>)}</tbody>
        </table></div>
        <p className="arch-footnote">원화 예약은 내부 환산 기준 1달러 = 2,000원을 사용합니다. 사용량×단가 추정과 제공자의 최종 청구는 구분합니다.</p>
      </section>

      <section className="arch-section" aria-labelledby="pipeline-status-title">
        <div className="arch-section-heading"><span className="arch-index">07</span><div><h2 id="pipeline-status-title">실행판·설정·검증 기록</h2><p>아래 숫자는 서버가 읽은 운영 기록입니다. 문서에 저장된 검증 메모와 지금 실행한 결과를 구분합니다.</p></div></div>
        <div className="arch-facts" aria-label="지금 실행판">
          <div className="arch-fact"><span>실행 중인 커밋</span><strong className="mono">{shortCommit(data.git.commit)}</strong><em>{data.git.subject ?? ""}</em></div>
          <div className="arch-fact"><span>배포 기록</span><strong>{data.build ? formatDate(data.build.deployed_at, true) : "기록 없음"}</strong><em className={data.build_matches_running_code ? "" : "warn"}>{data.build_matches_running_code ? "실행 코드와 일치" : data.build ? "배포 기록과 실행 코드가 다름" : "배포 검증 기록 없음"}</em></div>
          <div className="arch-fact"><span>배포 시 검사</span><strong className={tests.failed ? "bad" : ""}>{tests.text}</strong><em>실제 사용자 제작·게시의 성공을 뜻하지 않음</em></div>
          <div className="arch-fact"><span>작업 시간</span><strong>{windowOpen ? `열림 · ${formatDate(data.window.authorized_end ?? undefined, true)}까지` : "닫힘"}</strong><em>작업자 상태 기록: {data.worker.state === "online" ? "온라인" : data.worker.state ?? "없음"}</em></div>
          <div className="arch-fact"><span>장부의 누적 비용</span><strong className="mono">{Math.round(data.budget.spent_krw).toLocaleString("ko-KR")}원</strong><em>한도 {data.budget.cap_krw.toLocaleString("ko-KR")}원 · 남음 {Math.round(data.budget.remaining_krw).toLocaleString("ko-KR")}원</em></div>
        </div>
        <div className="arch-status">{(["openai", "gemini", "runway", "youtube"] as const).map((key) => <div className="arch-status-row" key={key}><span className={`arch-pill ${data.keys[key] ? "ok" : "off"}`}>{data.keys[key] ? "설정 존재" : "설정 없음"}</span><p>{{ openai: "OpenAI API 키", gemini: "Gemini API 키", runway: "Runway API 키", youtube: "YouTube 클라이언트 ID" }[key]} <span className="muted">· 환경변수 존재 여부만 확인. 실제 인증·채널 연결·호출 성공은 별도 검증.</span></p></div>)}</div>
        <h3 className="arch-subheading">저장소에 기록된 검증 메모</h3>
        <div className="arch-status">{data.doc.status.map((item) => <div className="arch-status-row" key={item.text}><span className={`arch-pill ${item.state}`}>{item.label}</span><p>{item.text} <span className="muted">· {item.note}</span></p></div>)}</div>
        <details className="arch-audit"><summary>최근 커밋과 문서 원본 확인</summary><ol className="arch-commits">{data.git.recent.map((c) => <li key={c.commit}><span className="mono">{c.commit}</span><span>{c.subject}</span><span className="muted">{c.author} · {formatDate(c.at, true)}</span></li>)}</ol><p className="arch-footnote">공정 정의는 backend/config/architecture.json, 운영 기록은 서버에서 읽습니다. 30초마다 갱신하며 SVG도 같은 정의에서 만듭니다.</p></details>
      </section>
    </div>
  );
}

function RuntimeMap({ data }: { data: ArchitectureOverview }) {
  return <div className="arch-runtime" aria-label="운영자에서 저장소와 외부 서비스까지의 실행 경로">
    <div className="arch-runtime-access"><span className="arch-kicker">접근 경로</span><h3>운영자 브라우저</h3><p>PC · 휴대폰</p><span className="arch-route-arrow" aria-hidden="true">↓</span><h3>nginx</h3><p>HTTPS 인증서 · 기본 인증<br />공개 화면과 API의 앞단</p><span className="arch-route-arrow" aria-hidden="true">→</span><div className="arch-deploy-note"><strong>GitHub main</strong><p>코드 검토 → 검사 → 빌드 → 정확한 커밋 배포</p><small>모델 실행이나 콘텐츠 발행과 별개</small></div></div>
    <div className="arch-runtime-core"><div className="arch-runtime-label"><span className="arch-pill ok">현재 운영</span><strong>AWS EC2 · 콘텐츠 오피스</strong></div>
      <ol className="arch-services"><li><b>1</b><div><h3>화면 · Next.js <code>:3110</code></h3><p>뉴스·기획·원고·출고·설정·파이프라인 읽기</p></div></li><li><b>2</b><div><h3>API · FastAPI <code>:8510</code></h3><p>승인·현재 판본·세션·Origin/CSRF·시간·예산 확인 → 업무 큐 등록</p></div></li><li><b>3</b><div><h3>작업자 · Python worker</h3><p>큐의 원고·제작·퀴즈·카드·전달 업무 실행. watcher는 마감 시간을 감시합니다.</p></div></li></ol>
      <div className="arch-storage"><h3>하나의 상태·비용 장부</h3><dl><div><dt>SQLite</dt><dd>작업·승인⓪①②③·업무 큐·예약 비용·이벤트</dd></div><div><dt>artifacts/</dt><dd>블로그·영상·음성·자막·썸네일·PDF·퀴즈·카드</dd></div><div><dt>image-assets/</dt><dd>완료 이미지·비용 영수증·재사용 캐시</dd></div><div><dt>runtime/</dt><dd>프로세스 장부·로그·배포 기록</dd></div><div><dt>비공개 설정</dt><dd>API 키·구독 로그인. 화면·Git·도해에는 값 미노출</dd></div></dl></div>
    </div>
    <div className="arch-runtime-providers"><span className="arch-kicker">업무별로 선택·호출</span><h3>입력과 외부 서비스</h3><dl><div><dt>원고·검수 모델</dt><dd className="mono">{data.profiles.text}</dd></div><div><dt>장면·카드 이미지</dt><dd>{imageRoute(data.profiles.image)}</dd></div><div><dt>요약·음성</dt><dd>선택한 Gemini·음성 프로필</dd></div><div><dt>RSS/Atom</dt><dd>공식 블로그·arXiv 등 공개 피드</dd></div><div><dt>YouTube</dt><dd>자격·채널·승인 대조가 필요한 비공개 전달</dd></div><div><dt>Runway</dt><dd>별도 키·프로필이 필요한 생성 클립</dd></div></dl><p className="arch-footnote">선택된 모델·프로필과 자격 설정, 실제 외부 성공은 별개입니다.</p></div>
  </div>;
}
