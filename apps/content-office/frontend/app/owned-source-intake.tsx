"use client";
import {useId,useRef,useState} from "react";
import {api} from "../lib/api";
import type {Job} from "../lib/types";

export function OwnedSourceIntake({onCreated}:{onCreated:(job:Job)=>void}) {
  const id=useId();
  const [url,setUrl]=useState(""); const [title,setTitle]=useState("");
  const [body,setBody]=useState(""); const [owned,setOwned]=useState(false);
  const [busy,setBusy]=useState(false);const [error,setError]=useState("");
  const [notice,setNotice]=useState("");const revision=useRef(0);
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
  return <section className="editor-panel" aria-label="내 원고로 콘텐츠 만들기">
    <h2>내 글이나 아이디어로 콘텐츠 만들기</h2>
    <p>공개 티스토리 글을 가져오거나, 만들고 싶은 콘텐츠의 원고를 직접 적어 주세요. 저장 뒤 작업실에서 독자·기획·원고 검수를 이어갑니다.</p>
    <fieldset disabled={busy} style={{border:0,padding:0}}>
      <label htmlFor={id+"-url"}>티스토리 공개 글 주소 (직접 작성하면 비워 두세요)</label>
      <input id={id+"-url"} type="url" value={url} maxLength={2000} placeholder="https://내블로그.tistory.com/entry/글주소" onChange={e=>{revision.current++;setUrl(e.target.value);setNotice("");}} />
      <button type="button" className="button secondary small" disabled={!url||busy} onClick={()=>void preview()}>본문 가져와 확인하기</button>
      <label htmlFor={id+"-title"}>콘텐츠 제목</label>
      <input id={id+"-title"} value={title} maxLength={200} onChange={e=>setTitle(e.target.value)} />
      <label htmlFor={id+"-body"}>원고·자료·만들고 싶은 내용 (100~50,000자)</label>
      <textarea id={id+"-body"} value={body} rows={10} maxLength={50000} onChange={e=>{revision.current++;setBody(e.target.value);}} />
      <p className="muted">사진·표·코드는 Markdown으로 보존합니다. 로그인 글·지원하지 않는 스킨은 직접 붙여 넣으세요. 저장은 원고 승인이나 유료 제작을 실행하지 않습니다.</p>
      <label><input type="checkbox" checked={owned} onChange={e=>setOwned(e.target.checked)} /> 내가 작성했거나 제작에 사용할 권한이 있는 자료입니다.</label>
      <button className="button primary" type="button" disabled={busy||!owned||!title.trim()||body.trim().length<100} onClick={()=>void create()}>{busy?"처리 중…":"내 원고로 작업실 열기"}</button>
    </fieldset>
    {notice&&<p role="status">{notice}</p>}{error&&<p className="notice error" role="alert">{error}</p>}
  </section>;
}
