"use client";

import {useCallback, useEffect, useRef, useState, type SyntheticEvent, type KeyboardEvent} from "react";
import {api} from "../lib/api";
import type {ArchitectureOverview} from "../lib/architecture";
import {formatDate} from "../lib/workflow";
import {ArchitectureView as LegacyArchitectureView} from "./architecture-view";
import "./pipeline-studio.css";

const MAP_URL="/api/pipeline-studio";
const BASELINE="20bbd8e";
const money=(value:unknown)=>typeof value==="number" && Number.isFinite(value)?`${Math.round(value).toLocaleString("ko-KR")}원`:"확인 불가";

/** Reads operating state and opens a browser-local review map; never issues a workflow write. */
export function PipelineStudio() {
  const [tab,setTab]=useState<"map"|"operations">("map");
  const [overview,setOverview]=useState<ArchitectureOverview|null>(null);
  const [liveError,setLiveError]=useState("");
  const [liveLoading,setLiveLoading]=useState(true);
  const [loadedAt,setLoadedAt]=useState("");
  const [mapAttempt,setMapAttempt]=useState(0);
  const [sessionReady,setSessionReady]=useState(false);
  const [mapLoaded,setMapLoaded]=useState(false);
  const [mapError,setMapError]=useState("");
  const [fullscreen,setFullscreen]=useState(false);
  const [frameHeight,setFrameHeight]=useState(860);
  const [fullscreenError,setFullscreenError]=useState("");
  const frame=useRef<HTMLIFrameElement>(null);
  const canvas=useRef<HTMLDivElement>(null);
  const alive=useRef(false);
  const requestId=useRef(0);
  const resizeCleanup=useRef<(()=>void)|null>(null);
  useEffect(()=>()=>resizeCleanup.current?.(),[]);
  const load=useCallback(async()=>{
    const ticket=++requestId.current;
    setLiveLoading(true);
    try {
      const next=await api.architecture();
      if(!next?.window || !next.worker || !next.budget || !next.git)throw Error("운영 상태 응답을 확인하지 못했습니다.");
      if(!alive.current || ticket!==requestId.current)return;
      setOverview(next);setLoadedAt(new Date().toISOString());setLiveError("");
    } catch(cause) {
      if(alive.current && ticket===requestId.current)setLiveError(cause instanceof Error?cause.message:"운영 상태를 확인하지 못했습니다.");
    } finally {
      if(alive.current && ticket===requestId.current)setLiveLoading(false);
    }
  },[]);
  useEffect(()=>{
    alive.current=true;void load();
    const refresh=()=>{if(!document.hidden)void load();};
    const timer=setInterval(refresh,30_000);
    document.addEventListener("visibilitychange",refresh);
    return()=>{alive.current=false;requestId.current++;clearInterval(timer);document.removeEventListener("visibilitychange",refresh);};
  },[load]);
  useEffect(()=>{
    resizeCleanup.current?.();resizeCleanup.current=null;
    let current=true;
    const controller=new AbortController();
    const timeout=setTimeout(()=>controller.abort(),15_000);
    setSessionReady(false);setMapLoaded(false);setMapError("");
    // The existing GET issues the same-origin HttpOnly cookie required by the private map.
    void fetch("/api/session",{method:"GET",credentials:"same-origin",cache:"no-store",signal:controller.signal})
      .then(async response=>{
        if(!response.ok)throw Error(`운영자 연결을 확인하지 못했습니다 (${response.status}).`);
        const body=await response.json() as {csrf?:unknown};
        if(typeof body.csrf!=="string" || !body.csrf)throw Error("운영자 연결 응답을 확인하지 못했습니다.");
        if(current)setSessionReady(true);
      }).catch(cause=>{
        if(current)setMapError(`${cause instanceof Error?cause.message:"운영자 연결 오류"} 연결을 확인한 뒤 다시 불러오세요.`);
      }).finally(()=>clearTimeout(timeout));
    return()=>{current=false;controller.abort();clearTimeout(timeout);};
  },[mapAttempt]);
  useEffect(()=>{
    if(!sessionReady || mapLoaded || mapError)return;
    const timer=setTimeout(()=>setMapError("지도가 응답하지 않습니다. 연결을 확인한 뒤 다시 불러오세요."),20_000);
    return()=>clearTimeout(timer);
  },[sessionReady,mapLoaded,mapError]);
  useEffect(()=>{
    const changed=()=>setFullscreen(document.fullscreenElement===canvas.current);
    document.addEventListener("fullscreenchange",changed);
    return()=>document.removeEventListener("fullscreenchange",changed);
  },[]);
  const navigateTabs=(event:KeyboardEvent<HTMLDivElement>)=>{
    if(!["ArrowLeft","ArrowRight","Home","End"].includes(event.key))return;
    event.preventDefault();
    const next=event.key==="Home"?"map":event.key==="End"?"operations":tab==="map"?"operations":"map";
    setTab(next);document.getElementById(`pipeline-tab-${next}`)?.focus();
  };
  const mapOnLoad=(event:SyntheticEvent<HTMLIFrameElement>)=>{
    try {
      const document=event.currentTarget.contentDocument;
      if(!document?.getElementById("currentView"))throw Error("지도 화면을 확인하지 못했습니다. 로그인 또는 연결 상태를 확인한 뒤 다시 불러오세요.");
      resizeCleanup.current?.();
      let animation=0;
      const measure=()=>{
        const height=Math.ceil(document.body.getBoundingClientRect().height);
        if(Number.isFinite(height) && height>0)setFrameHeight(Math.min(12_000,Math.max(600,height)));
      };
      const observer=new ResizeObserver(()=>{cancelAnimationFrame(animation);animation=requestAnimationFrame(measure);});
      observer.observe(document.body);measure();
      resizeCleanup.current=()=>{observer.disconnect();cancelAnimationFrame(animation);};
      setMapLoaded(true);setMapError("");
    } catch(cause) {
      setMapLoaded(false);setMapError(cause instanceof Error?cause.message:"지도 화면을 읽지 못했습니다.");
    }
  };
  const toggleFullscreen=async()=>{
    setFullscreenError("");
    try {
      if(document.fullscreenElement===canvas.current)await document.exitFullscreen();
      else {
        if(!canvas.current?.requestFullscreen)throw Error("Fullscreen API unavailable");
        await canvas.current.requestFullscreen();
      }
    } catch {
      setFullscreenError("이 브라우저에서 전체화면을 열지 못했습니다. 지도를 새 탭에서 열 수 있습니다.");
    }
  };
  const windowStatus=overview?.window.status;
  const end=overview?.window.authorized_end?Date.parse(overview.window.authorized_end):NaN;
  const windowLabel=!overview?(liveError?"확인 불가":"확인 전"):windowStatus==="active" && Number.isFinite(end)?(end>Date.now()?"열림":"닫힘"):["closed","stopped"].includes(windowStatus || "")?"닫힘":"확인 불가";
  const workerState=overview?.worker.state;
  const heartbeat=overview?.worker.heartbeat?Date.parse(overview.worker.heartbeat):NaN;
  const workerLabel=!overview?(liveError?"확인 불가":"확인 전"):workerState==="online"?(Number.isFinite(heartbeat) && Date.now()-heartbeat>=0 && Date.now()-heartbeat<120_000?"온라인 기록":"온라인 · 오래된 기록"):["stopped","offline","closed"].includes(workerState || "")?"중지":workerState==="error"?"오류 기록":"확인 불가";
  const runningCommit=overview?.git.commit?.slice(0,7);
  const livePlaceholder=liveError?"확인 불가":"확인 전";

  return <section className="pipeline-studio" data-testid="pipeline-studio" aria-labelledby="pipeline-studio-title">
    <header className="pipeline-studio-header">
      <div><p className="pipeline-studio-eyebrow">기획부터 출고까지</p><h1 id="pipeline-studio-title">콘텐츠 파이프라인</h1><p className="pipeline-studio-intro">기획과 현재 구현을 나란히 보고, 다음 개선을 직접 정리하세요.</p></div>
      <span className="pipeline-studio-readonly"><i aria-hidden="true"/>운영 상태 조회</span>
    </header>
    <div className="pipeline-studio-live-heading"><span>서버에서 확인한 상태</span><button type="button" data-testid="pipeline-live-refresh" onClick={()=>void load()} disabled={liveLoading}>{liveLoading?"확인 중…":"상태 새로고침"}</button></div>
    {liveError && <div className="pipeline-studio-alert" role="alert" data-testid="pipeline-live-error">{overview?"갱신에 실패해 마지막 조회 내용을 표시합니다. ":""}{liveError}</div>}
    <dl className={`pipeline-studio-metrics${liveError?" is-stale":""}`} aria-label="운영 상태 요약">
      <div data-testid="pipeline-live-budget"><dt>사용 가능 예산</dt><dd>{overview?money(overview.budget.remaining_krw):livePlaceholder}</dd><small>{overview?`한도 ${money(overview.budget.cap_krw)}`:"서버 조회 전"}</small></div>
      <div data-testid="pipeline-live-window"><dt>작업 시간</dt><dd>{windowLabel}</dd><small>{windowLabel==="열림"?`${formatDate(overview?.window.authorized_end || undefined,true)}까지`:"허용된 시간 기준"}</small></div>
      <div data-testid="pipeline-live-worker"><dt>콘텐츠 작업자</dt><dd>{workerLabel}</dd><small>저장된 상태 기록</small></div>
      <div data-testid="pipeline-live-updated"><dt>{liveError && overview?"마지막 조회":"조회 시각"}</dt><dd className="pipeline-studio-time">{loadedAt?formatDate(loadedAt,true):livePlaceholder}</dd><small>{runningCommit?`실행판 ${runningCommit}`:"실행판 확인 전"}</small></div>
    </dl>
    <div className="pipeline-studio-tabs" role="tablist" aria-label="파이프라인 보기" onKeyDown={navigateTabs}>
      <button type="button" role="tab" id="pipeline-tab-map" data-testid="pipeline-tab-map" aria-controls="pipeline-panel-map" aria-selected={tab==="map"} tabIndex={tab==="map"?0:-1} onClick={()=>setTab("map")}>기획·구현 지도</button>
      <button type="button" role="tab" id="pipeline-tab-operations" data-testid="pipeline-tab-operations" aria-controls="pipeline-panel-operations" aria-selected={tab==="operations"} tabIndex={tab==="operations"?0:-1} onClick={()=>setTab("operations")}>운영 상세</button>
    </div>
    <div id="pipeline-panel-map" role="tabpanel" aria-labelledby="pipeline-tab-map" hidden={tab!=="map"}>
      <div className="pipeline-studio-canvas" ref={canvas}>
        <div className="pipeline-studio-map-bar"><div><h3>기획·구현 지도</h3><p>상자를 눌러 확인하고, 직접 편집으로 개선안을 남기세요.</p></div><div className="pipeline-studio-map-actions"><a href={sessionReady?MAP_URL:undefined} aria-disabled={!sessionReady} target="_blank" rel="noopener" data-testid="pipeline-map-new-tab">새 탭에서 열기 <span aria-hidden="true">↗</span></a><button type="button" data-testid="pipeline-map-fullscreen" onClick={()=>void toggleFullscreen()} disabled={!mapLoaded}>{fullscreen?"전체화면 닫기":"전체화면"}</button></div></div>
        {fullscreenError && <p className="pipeline-studio-alert" role="alert" data-testid="pipeline-fullscreen-error">{fullscreenError}</p>}
        <div className="pipeline-studio-frame-wrap" aria-busy={!mapLoaded && !mapError}>
          {!mapLoaded && !mapError && <div className="pipeline-studio-frame-state" role="status" data-testid="pipeline-map-loading"><span className="pipeline-studio-spinner" aria-hidden="true"/><strong>{sessionReady?"지도를 불러오고 있습니다":"운영자 연결을 확인하고 있습니다"}</strong></div>}
          {mapError && <div className="pipeline-studio-frame-state pipeline-studio-frame-error" role="alert" data-testid="pipeline-map-error"><strong>지도를 열지 못했습니다</strong><p>{mapError}</p><button type="button" data-testid="pipeline-map-reload" onClick={()=>setMapAttempt(value=>value+1)}>지도 다시 불러오기</button></div>}
          {sessionReady && <iframe key={mapAttempt} ref={frame} src={MAP_URL} title="기획·구현 파이프라인 지도" data-testid="pipeline-map-frame" allow="fullscreen" onLoad={mapOnLoad} onError={()=>setMapError("지도를 불러오지 못했습니다. 연결을 확인한 뒤 다시 시도하세요.")} style={{visibility:mapLoaded && !mapError?"visible":"hidden",height:fullscreen?"100%":frameHeight}}/>}
        </div>
        <p className="pipeline-studio-baseline">구현 대조 기준 2026-11-17 · {BASELINE}{runningCommit && runningCommit!==BASELINE?` · 현재 실행판 ${runningCommit}은 별도 확인`:""}</p>
      </div>
    </div>
    <div id="pipeline-panel-operations" role="tabpanel" aria-labelledby="pipeline-tab-operations" hidden={tab!=="operations"}>{tab==="operations" && <LegacyArchitectureView/>}</div>
  </section>;
}
