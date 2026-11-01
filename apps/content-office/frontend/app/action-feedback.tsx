"use client";
import { feedbackMessage } from "../lib/action-feedback";
export function ActionFeedback({busy,error,notice,onDismiss}:{busy:string;error:string;notice:string;onDismiss:()=>void}) {
 const item=feedbackMessage(busy,error,notice);
 if(!item)return null;
 return <aside aria-label="작업 처리 상태" role={item.kind==="error"?"alert":"status"} aria-live={item.kind==="error"?"assertive":"polite"} style={{position:"fixed",bottom:16,right:16,zIndex:10000,width:"min(440px, calc(100vw - 32px))",maxHeight:"40vh",overflowY:"auto",padding:18,borderRadius:12,border:`2px solid ${item.kind==="error"?"#a12d20":"#426547"}`,background:"#fff",color:"#203326",boxShadow:"0 4px 24px #0003"}}>
 <strong>{item.kind==="pending"?"◷ ":item.kind==="error"?"! ":"✓ "}{item.title}</strong>
 <p style={{margin:"8px 0",overflowWrap:"anywhere"}}>{item.message}</p>
 {!busy&&<button type="button" onClick={onDismiss} style={{minHeight:44}}>처리 상태 닫기</button>}
 </aside>;
}
