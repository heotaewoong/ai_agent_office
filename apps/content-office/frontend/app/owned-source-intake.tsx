"use client";
import {useId,useRef,useState} from "react";
import {api} from "../lib/api";
import type {Job} from "../lib/types";
import styles from "./owned-source-intake.module.css";

export function OwnedSourceIntake({onCreated}:{onCreated:(job:Job)=>void}) {
  const id=useId();
  const [url,setUrl]=useState(""); const [title,setTitle]=useState("");
  const [body,setBody]=useState(""); const [owned,setOwned]=useState(false);
  const [busy,setBusy]=useState(false);const [error,setError]=useState("");
  const [notice,setNotice]=useState("");const revision=useRef(0);
  const [mode,setMode]=useState<"write"|"url">("write");
  const bodyLength=body.trim().length;
  const ready=Boolean(owned&&title.trim()&&bodyLength>=100);
  const nextStep=!title.trim()?"제목을 입력해 주세요.":bodyLength<100?`본문을 ${100-bodyLength}자 더 적으면 다음으로 이동할 수 있어요.`:!owned?"자료 사용 권한을 확인해 주세요.":"준비됐어요. 작업실에서 원고 검수를 이어가세요.";
  async function preview(){
    if(busy)return;setBusy(true);setError("");const current=++revision.current;
    try{
      const value=await api.previewOwnedSource(url);
      if(current===revision.current){setTitle(value.title);setBody(value.body);setNotice(`본문을 가져왔습니다. 사진 ${value.image_count}개 · 표·코드·문단을 원문과 대조한 뒤 작업으로 저장하세요.`);}
    }catch(e){setError(e instanceof Error?e.message:"본문을 가져오지 못했습니다.");}finally{setBusy(false);}
  }
  async function create(){
    if(busy)return;setBusy(true);setError("");
    try{const job=await api.createOwnedSource({title,body,source_url:url,owner_confirmed:owned});onCreated(job);}
    catch(e){setError(e instanceof Error?e.message:"작업을 저장하지 못했습니다.");}finally{setBusy(false);}
  }
  return <section className={styles.panel} aria-label="내 원고로 콘텐츠 만들기" aria-busy={busy}>
    <header className={styles.header}>
      <span className={styles.eyebrow}>내 콘텐츠 시작하기</span>
      <h2>내 글이나 아이디어로 콘텐츠 만들기</h2>
      <p>원고 하나를 블로그·카드뉴스·영상으로 이어가세요.<br/>먼저 내용을 준비하면 작업실에서 기획과 검수를 시작할 수 있어요.</p>
      <ol className={styles.steps} aria-label="원고 등록 순서"><li><span>1</span> 입력 방식 선택</li><li><span>2</span> 제목·본문 작성</li><li><span>3</span> 확인 후 작업실 열기</li></ol>
    </header>
    <fieldset disabled={busy} className={styles.fields}>
      <legend className={styles.srOnly}>원고 등록</legend>
      <div className={styles.methods} role="group" aria-label="원고 입력 방식">
        <button type="button" aria-pressed={mode==="write"} className={styles.method} onClick={()=>setMode("write")}><span className={styles.methodIcon} aria-hidden="true">Aa</span><span><strong>직접 쓰거나 붙여넣기</strong><small>내 글·메모·준비한 원고로 시작</small></span><span className={styles.choice} aria-hidden="true">{mode==="write"?"✓":""}</span></button>
        <button type="button" aria-pressed={mode==="url"} className={styles.method} onClick={()=>setMode("url")}><span className={styles.methodIcon} aria-hidden="true">↗</span><span><strong>티스토리 글 가져오기</strong><small>내가 작성한 공개 글 주소로 시작</small></span><span className={styles.choice} aria-hidden="true">{mode==="url"?"✓":""}</span></button>
      </div>
      <div className={styles.importBox} hidden={mode!=="url"}>
        <label htmlFor={id+"-url"}>티스토리 공개 글 주소</label>
        <div className={styles.importRow}><input className={styles.input} id={id+"-url"} type="url" value={url} maxLength={2000} placeholder="https://내블로그.tistory.com/entry/글주소" aria-describedby={id+"-url-help"} onChange={e=>{revision.current++;setUrl(e.target.value);setNotice("");}} />
        <button type="button" className={styles.importButton} disabled={!url.trim()||busy} onClick={()=>void preview()}>{busy?"처리 중…":"본문 가져와 확인하기"}</button></div>
        <p id={id+"-url-help"}>공개 글만 가져올 수 있어요. 로그인 글이나 불러오지 못한 글은 직접 붙여넣어 주세요.</p>
      </div>
      {mode==="write"&&url&&<p className={styles.hint}>입력한 원문 링크도 함께 저장됩니다. <button type="button" onClick={()=>setMode("url")}>링크 확인</button></p>}
      {notice&&<p className={styles.success} role="status">{notice}</p>}
      <div className={styles.field}>
        <div className={styles.labelRow}><label htmlFor={id+"-title"}>콘텐츠 제목 <span>필수</span></label><span>{title.length}/200</span></div>
        <input className={styles.input} id={id+"-title"} value={title} maxLength={200} placeholder="예: 퇴근 후 30분, 영어 단어를 오래 기억하는 방법" onChange={e=>setTitle(e.target.value)} />
      </div>
      <div className={styles.field}>
        <div className={styles.labelRow}><label htmlFor={id+"-body"}>원고·자료·만들고 싶은 내용 <span>필수</span></label><span>{bodyLength.toLocaleString("ko-KR")}/50,000자</span></div>
        <textarea className={styles.body} id={id+"-body"} value={body} rows={12} maxLength={50000} aria-describedby={id+"-body-help"} placeholder={"준비한 원고를 붙여넣거나, 전하고 싶은 내용을 적어 주세요.\n\n누구에게 도움이 되는 글인가요?\n어떤 경험이나 방법을 전하고 싶나요?\n읽고 나서 무엇을 할 수 있으면 좋을까요?"} onChange={e=>{revision.current++;setBody(e.target.value);}} />
        <div id={id+"-body-help"} className={styles.bodyHelp}><span>본문 100자 이상 · 최대 50,000자</span><span>사진·표·코드는 Markdown으로 보존해요.</span></div>
      </div>
      <label className={styles.consent}><input type="checkbox" checked={owned} onChange={e=>setOwned(e.target.checked)} /><span>내가 작성했거나 제작에 사용할 권한이 있는 자료입니다.</span></label>
      {error&&<p className={styles.error} role="alert">{error}</p>}
      <footer className={styles.footer}><div><strong>{nextStep}</strong><p>저장 후에도 수정할 수 있어요. 원고 승인·유료 제작·공개 게시에는 별도 확인이 필요해요.</p></div><button className={styles.submit} type="button" aria-describedby={id+"-next"} disabled={busy||!ready} onClick={()=>void create()}>{busy?"처리 중…":"내 원고로 작업실 열기"}<span aria-hidden="true">→</span></button></footer>
      <p id={id+"-next"} className={styles.srOnly}>{nextStep}</p>
    </fieldset>
    <p className={styles.bottomNote}>아직 원고가 없나요? 아래 독자 질문·기획 등록에서 주제 하나부터 시작해도 좋아요.</p>
  </section>;
}
