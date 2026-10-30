"use client";
import {useCallback, useEffect, useState} from "react";
import {api} from "../lib/api";
import {QUALITY_LABELS, REJECTION_LABELS, workspaceIsCurrent, reviewBinding, type ImprovementWorkspace} from "../lib/improvements";
import type {Job, Channel} from "../lib/types";

const today = () => new Date(Date.now()+9*3600000).toISOString().slice(0,10);
const text = (form:FormData,key:string) => String(form.get(key) ?? "").trim();

export function ImprovementPanel({job}:{job:Job}) {
  const [data,setData] = useState<ImprovementWorkspace|null>(null);
  const [channels,setChannels] = useState<Channel[]>([]);
  const [error,setError] = useState("");
  const [saved,setSaved] = useState("");
  const [busy,setBusy] = useState(false);
  const [reveal,setReveal] = useState(false);
  const [boundVersion,setBoundVersion] = useState(()=>reviewBinding(job));
  const [formEpoch,setFormEpoch] = useState(0);
  const load = useCallback(async()=>{setData(await api.improvementWorkspace(job.id));},[job.id]);
  useEffect(()=>{let active=true;
    Promise.allSettled([api.improvementWorkspace(job.id),api.channels()]).then(([workspace,registry])=>{
      if(!active)return;
      const errors:string[]=[];
      if(workspace.status==="fulfilled")setData(workspace.value);else errors.push("검토 기록을 불러오지 못했습니다.");
      if(registry.status==="fulfilled")setChannels(registry.value.channels);else errors.push("채널 목록을 불러오지 못했습니다. 품질·학습·경험 기록은 계속 확인할 수 있습니다.");
      if(errors.length)setError(errors.join(" "));
    });
    return()=>{active=false;};
  },[job.id,job.source_hash,job.manifest?.hash,job.quiz?.version,job.quiz?.generated_at,job.drafts?.length]);
  const current=workspaceIsCurrent(data,job.id,job.source_hash)&&boundVersion===reviewBinding(job);
  const sourceAxis=(job.source_packet?.audience as {axis?:string}|undefined)?.axis;
  async function save(run:()=>Promise<unknown>,message:string) {
    if(busy)return;
    setBusy(true);setError("");setSaved("");
    try{await run();setSaved(message);await load();}
    catch(e){setError(e instanceof Error?e.message:"저장 결과를 확인하지 못했습니다. 다시 요청하기 전 기록을 확인하세요.");}
    finally{setBusy(false);}
  }
  return <section className="editor-panel improvement-panel" aria-label="콘텐츠 품질·학습 개선">
    <h2>만든 내용이 도움이 됐는지 확인하기</h2>
    <p>설명·그림·오답·실제 경험·독자 반응을 같은 작업에 기록합니다. 평가 기록은 원고①·출고②·발송③ 승인이 아닙니다.</p>
    <button className="button secondary" disabled={busy} onClick={()=>void load().catch(e=>setError(String(e)))}>기록 새로 확인</button>
    {error&&<p className="notice error" role="alert">{error}</p>}
    {saved&&<p className="notice" role="status">{saved}</p>}
    {!data?<button className="button secondary" onClick={()=>void load().catch(e=>setError(String(e)))}>검토 기록 불러오기</button>:<>
    {!current&&<p className="notice">아직 현재 원고가 없거나 판본이 변경됐습니다. 입력은 보존하며 최신 원고를 확인한 뒤 기록할 수 있습니다.</p>}
    {data.source_hash&&boundVersion!==reviewBinding(job)&&<button className="button secondary" disabled={busy} onClick={()=>{setBoundVersion(reviewBinding(job));setFormEpoch(n=>n+1);setSaved("");}}>평가·집계 입력 초기화 후 현재 판본으로 다시 시작</button>}
    <details><summary>1. 기존판·개선판 품질 비교 · 평가 {data.reviews.length}건</summary>
      <p>같은 내용·목적의 결과를 읽고 들은 뒤 기록하세요. 1점은 부족, 5점은 충분입니다. 사실 오류는 평균 점수로 상쇄하지 않습니다.</p>
      <a className="button secondary" href={`/api/jobs/${encodeURIComponent(job.id)}/quality-reviews.csv`} download>판본별 품질 평가 CSV 내려받기</a>
      <label><input type="checkbox" checked={reveal} onChange={e=>setReveal(e.target.checked)}/> 평가 대상 이름 공개</label>
      <form key={`review-${formEpoch}`} onSubmit={e=>{e.preventDefault();const f=new FormData(e.currentTarget);const target=data.candidates.find(c=>c.id===text(f,"target"));if(!target)return;
        const scores=Object.fromEntries(Object.keys(QUALITY_LABELS).map(k=>[k,Number(f.get(k))]));
        void save(()=>api.saveQualityReview(job.id,{source_hash:data.source_hash,case_id:text(f,"case_id"),target_id:target.id,target_hash:target.hash,scores,critical:f.has("critical"),reasons:f.getAll("reasons"),note:text(f,"note")}),"품질 평가를 기록했습니다. 콘텐츠 승인은 바뀌지 않았습니다.");}}>
        <fieldset className="editor-fields" disabled={busy||!current}>
          <label>평가 대상<select name="target" required>{data.candidates.map((c,n)=><option key={c.id} value={c.id}>{reveal?c.label:`비교 대상 ${String.fromCharCode(65+n)}`}</option>)}</select></label>
          <label>대표 사례 연결<select name="case_id" defaultValue=""><option value="">일반 평가 · 사례 연결 안 함</option>{data.casebook.filter(c=>!sourceAxis||c.axis===sourceAxis).map(c=><option key={c.id} value={c.id}>{c.id} · {c.topic} · {c.split==="holdout"?"최종 확인용":"개발용"}</option>)}</select></label>
          {Object.entries(QUALITY_LABELS).map(([key,label])=><label key={key}>{label}<select name={key} required defaultValue=""><option value="" disabled>직접 확인 후 선택</option>{[1,2,3,4,5].map(n=><option key={n} value={n}>{n}점</option>)}</select></label>)}
          <label><input type="checkbox" name="critical"/> 근거 없는 사실·틀린 정답 등 중대 오류가 있음</label>
          <fieldset><legend>수정이 필요한 부분</legend>{Object.entries(REJECTION_LABELS).map(([key,label])=><label key={key}><input type="checkbox" name="reasons" value={key}/>{label}</label>)}</fieldset>
          <label>직접 확인한 이유<textarea name="note" maxLength={1500} required/></label>
          <button className="button secondary" type="submit">품질 평가 기록</button>
        </fieldset>
      </form>
      {data.reviews.slice(0,8).map(r=><p key={r.id}>{r.source_hash===data.source_hash?"현재 원고":"이전 원고"} · {r.critical?"중대 오류 있음":r.quality_passed?"기록한 기준 충족":"개선 필요"} · {r.note}</p>)}
      <details><summary>A/B축 대표 사례 20개 · 시작용 시나리오</summary><p>완성된 평가 결과가 아닙니다. 실제 원고·기대 결과와 사람 검토를 채워야 합니다. 개발용14개/최종 확인용6개로 나눴습니다.</p><ul>{data.casebook.map(c=><li key={c.id}>{c.id} · {c.topic} · {c.split==="holdout"?"최종 확인용":"개발용"}</li>)}</ul></details>
    </details>
    <details><summary>2. 영상이 설명하는 관계 점검 · {data.storyboard.scenes.length}장면</summary>
      <p>{data.storyboard.note}</p>
      {data.storyboard.scenes.map(s=><article key={s.index}><h3>{s.index}. {s.caption}</h3><p>{({flow:"순서·흐름",comparison:"비교",number:"수치",explanation:"설명"} as Record<string,string>)[s.kind]??s.kind} · 제목 읽기 추정 {s.estimated_read_seconds}초</p><p>{(s.steps.length?s.steps:s.comparison.length?s.comparison:s.key_phrases).join(s.kind==="flow"?" → ":" / ")}</p><p>{s.narration}</p><p>직접 연결한 근거: {s.evidence_ids.join(", ")||"확인 필요"}</p>{s.checks.map(c=><p className="muted" key={c}>{c}</p>)}</article>)}
      {!data.storyboard.scenes.length&&<p>현재 원고의 영상 대본이 준비되면 나타납니다.</p>}
    </details>
    <details><summary>3. 퀴즈 개념·오답 환류 · 관측 {data.learning_observations.length}건</summary>
      <p>{data.learning.note}</p>
      {data.learning.items.length>0&&<><a className="button secondary" href={`/api/jobs/${encodeURIComponent(job.id)}/learning-contract`} download>기존 스토어용 문항 계약 내려받기</a>
      <form key={`learning-${formEpoch}`} onSubmit={e=>{e.preventDefault();const f=new FormData(e.currentTarget);void save(()=>api.saveLearningObservation(job.id,{source_hash:data.source_hash,quiz_hash:data.learning.quiz_hash,question_id:text(f,"question_id"),observation_key:text(f,"observation_key"),attempts:Number(f.get("attempts")),correct:Number(f.get("correct"))}),"익명 문항 집계를 기록했습니다. 스토어 자동 동기화·복습 발송은 실행하지 않았습니다.");}}><fieldset className="editor-fields" disabled={busy||!current}>
        <label>현재 문항<select name="question_id">{data.learning.items.map(q=><option key={q.id} value={q.id}>{q.id} · {q.question}</option>)}</select></label>
        <label>중복 방지용 관측 키<input name="observation_key" required pattern="[a-zA-Z0-9_-]{1,80}" placeholder="예: quiz_Q1_20261030"/></label>
        <label>응답 수<input name="attempts" type="number" min={1} max={1000000} required/></label><label>정답 수<input name="correct" type="number" min={0} max={1000000} required/></label>
        <button className="button secondary">익명 집계 기록</button>
      </fieldset></form></>}
      {data.learning_observations.slice(0,10).map(o=><div key={o.id}><p>{o.source_hash===data.source_hash?"현재":"이전"} 문항 {o.question_id} · 오답 {Number(o.attempts)-Number(o.correct)}/{o.attempts} · 개념: {o.concept_id}</p>{o.source_hash===data.source_hash&&Number(o.attempts)>Number(o.correct)&&<button className="button secondary" disabled={busy||!current} onClick={()=>void save(()=>api.learningToIdea(job.id,o.id,data.source_hash!),"보충 설명 기획 후보를 저장했습니다. 기획·독자 질문 화면에서 근거 보완 후 직접 선택⓪하세요.")}>다음 보충 설명 기획 후보로 저장</button>}</div>)}
      <p className="muted">관측 기간이 겹칠 수 있어 여러 집계를 합산하지 않습니다. 개인별 망각곡선·점수 상승을 추정하지 않습니다.</p>
    </details>
    <details><summary>4. 확인된 실제 경험 자료 · {data.experiences.length}건</summary>
      <p>공개 콘텐츠에 쓸 수 있는 사실만 등록하세요. ‘원고 생성에 사용’을 고르면 주제와 맞는 자료 최대3개를 다음 원고 생성 모델에 전달합니다. 현재 원고·승인은 바뀌지 않습니다.</p>
      <form onSubmit={e=>{e.preventDefault();const f=new FormData(e.currentTarget);void save(()=>api.addExperience({title:text(f,"title"),axis:text(f,"axis"),facts:text(f,"facts"),evidence_note:text(f,"evidence_note"),checked_on:text(f,"checked_on"),tags:text(f,"tags").split(",").map(t=>t.trim()).filter(Boolean),confirmed:f.has("confirmed"),use_in_content:f.has("use_in_content")}),"경험 자료를 기록했습니다. 관련된 다음 원고에만 선택적으로 사용합니다.");}}><fieldset className="editor-fields" disabled={busy}>
        <label>경험 제목<input name="title" maxLength={150} required/></label><label>관련 축<select name="axis"><option value="A">학습·시험</option><option value="B">AI·업무 생산성</option><option value="both">두 축 공통</option></select></label>
        <label>실제로 확인한 사실<textarea name="facts" minLength={10} maxLength={2500} required/></label><label>근거·확인 방법<input name="evidence_note" maxLength={1000} required/></label>
        <label>확인일<input name="checked_on" type="date" defaultValue={today()} max={today()} required/></label><label>관련 주제(쉼표로 구분)<input name="tags" maxLength={480} required placeholder="옵시디언, 동기화"/></label>
        <label><input type="checkbox" name="confirmed"/> 사실을 직접 확인했습니다</label><label><input type="checkbox" name="use_in_content"/> 새 원고 생성 모델에 이 자료 사용 허용</label>
        <button className="button secondary">경험 자료 저장</button>
      </fieldset></form>
      {data.experiences.slice(0,10).map(x=><details key={x.id}><summary>{x.title} · {x.confirmed&&x.use_in_content?"원고 참고 허용":"보관만"}</summary><p>{x.facts}</p><p>근거: {x.evidence_note}</p>{x.use_in_content&&x.record_hash&&<button className="button secondary" disabled={busy} onClick={()=>void save(()=>api.withdrawExperienceUse(x.id,x.record_hash!),"다음 원고에서의 사용을 중지했습니다. 기존 원고·게시물은 변경하지 않았습니다.")}>다음 원고에서 사용 중지</button>}</details>)}
    </details>
    <details><summary>5. 채널별 독자 행동·성과 · 기록 {data.outcomes.length}건</summary>
      <p>실제 게시 주소와 관측값을 기록하세요. 수동 입력이며 플랫폼 인증 영수증/인과적 매출 증명이 아닙니다. 무료 주문은 매출에서 제외합니다.</p>
      <a className="button secondary" href={`/api/jobs/${encodeURIComponent(job.id)}/channel-outcomes.csv`} download>채널 성과 CSV 내려받기</a>
      <form key={`outcome-${formEpoch}`} onSubmit={e=>{e.preventDefault();const f=new FormData(e.currentTarget);const metrics=Object.fromEntries(["views","saves","quiz_completed","downloads","free_orders","paid_orders","paid_revenue_krw"].map(k=>[k,Number(f.get(k))]));void save(()=>api.saveChannelOutcome(job.id,{source_hash:data.source_hash,channel_id:text(f,"channel_id"),campaign_id:text(f,"campaign_id"),variant_id:text(f,"variant_id"),external_url:text(f,"external_url"),observed_on:text(f,"observed_on"),period:text(f,"period"),...metrics}),"채널별 관측을 기록했습니다. 실제 게시/결제는 실행하지 않았습니다.");}}><fieldset className="editor-fields" disabled={busy||!current}>
        <label>채널<select name="channel_id" required>{channels.map(c=><option key={c.key} value={c.key}>{c.label}</option>)}</select></label><label>실제 게시 HTTPS 주소<input name="external_url" type="url" required maxLength={1500}/></label>
        <label>캠페인 ID(선택)<input name="campaign_id" maxLength={80} pattern="[a-zA-Z0-9_-]*"/></label><label>변형 ID(선택)<input name="variant_id" maxLength={80} pattern="[a-zA-Z0-9_-]*"/></label>
        <label>관측일<input name="observed_on" type="date" defaultValue={today()} max={today()} required/></label><label>게시 후 관측 구간<select name="period"><option>24h</option><option>7d</option><option>28d</option></select></label>
        {Object.entries({views:"조회",saves:"저장",quiz_completed:"퀴즈 완료",downloads:"자료 수령",free_orders:"무료 주문",paid_orders:"유료 주문",paid_revenue_krw:"유료 매출(원)"}).map(([k,v])=><label key={k}>{v}<input name={k} type="number" min={0} max={1000000000} defaultValue={0} required/></label>)}
        <button className="button secondary">관측값 저장</button>
      </fieldset></form>
      {data.outcomes.slice(0,10).map(o=><p key={o.id}>{o.channel_id} · 조회 {o.views} · 무료 주문 {o.free_orders}건 · 유료 매출 {o.paid_revenue_krw}원 · 운영자 입력</p>)}
    </details>
    <p className="muted">각 분류의 최근500개 기록 안에서 조회합니다. 실제 외부 전달·학습 효과는 별도 검증이 필요합니다.</p>
    </>}
  </section>;
}
