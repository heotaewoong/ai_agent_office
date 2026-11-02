"use client";
import {useEffect,useId,useRef,useState} from 'react';
import {api} from '../lib/api';

type Item={id:string;title:string;updated_at?:string;state?:string;tasks?:{state?:string}[]};
export type JobTrashRequest={job:Item;trigger:HTMLButtonElement};
export function jobTrashWorking(job:Item){return ['drafting','production_queued','producing','needs_reconciliation'].includes(job.state??'')||Boolean(job.tasks?.some(task=>['queued','running','claimed','unknown'].includes(task.state??'')));}
export function JobTrash({job,items,deleteRequest,onDeleteRequestHandled,busy,unsaved,onChanged}:{job?:Item;items?:Item[];deleteRequest?:JobTrashRequest;onDeleteRequestHandled?:()=>void;busy:boolean;unsaved:boolean;onChanged:(deletedId?:string)=>Promise<void>}){
 const dialog=useRef<HTMLDialogElement>(null),trigger=useRef<HTMLButtonElement|null>(null),trashButton=useRef<HTMLButtonElement>(null);
 const heading=useId();
 const [mode,setMode]=useState<'delete'|'trash'>('trash');
 const [snapshot,setSnapshot]=useState<Item>();
 const [fromList,setFromList]=useState(false);
 const [rows,setRows]=useState<Item[]>([]);
 const [pending,setPending]=useState(false),[error,setError]=useState(''),[notice,setNotice]=useState('');
 const working=Boolean(job&&jobTrashWorking(job));
 useEffect(()=>{if(deleteRequest){void open(deleteRequest.trigger,'delete',deleteRequest.job,true);onDeleteRequestHandled?.();}},[deleteRequest]);
 function close(){if(!pending)dialog.current?.close();}
 async function open(button:HTMLButtonElement,which:'delete'|'trash',target=job,list=false){
  if(busy||pending)return;
  trigger.current=button;setMode(which);setSnapshot(target?{...target}:undefined);setFromList(list);setError('');setNotice('');
  dialog.current?.showModal();
  if(which==='trash'){
   setPending(true);
   try{setRows((await api.trashJobs()).jobs);}catch(e){setError(e instanceof Error?e.message:'휴지통을 불러오지 못했습니다.');}
   finally{setPending(false);}
  }
 }
 async function move(item:Item,restore=false){
  if(pending||busy||!item.updated_at)return;
  if(!restore&&(fromList?!items?.some(current=>current.id===item.id):item.id!==job?.id)){setError('선택한 작업이 바뀌었습니다. 취소한 뒤 다시 확인하세요.');return;}
  setPending(true);setError('');let saved=false;
  try{
   if(restore)await api.restoreJob(item.id,item.updated_at);else await api.trashJob(item.id,item.updated_at);
   saved=true;
   if(restore)setRows(current=>current.filter(row=>row.id!==item.id));else dialog.current?.close();
   setNotice(restore?'작업을 복원했습니다. 자동 제작·전송은 시작하지 않습니다.':'작업을 휴지통으로 이동했습니다. 휴지통에서 복원할 수 있습니다.');
   await onChanged(restore?undefined:item.id);
   if(restore)dialog.current?.querySelector<HTMLElement>('h2')?.focus();
  }catch(e){setError(saved?'이동은 완료됐지만 목록 조회에 실패했습니다. 다시 이동하지 말고 목록을 새로 확인하세요.':e instanceof Error?e.message:'요청 결과를 확인하지 못했습니다. 휴지통과 운영 기록을 먼저 확인하세요.');}
  finally{setPending(false);if(saved&&!restore)requestAnimationFrame(()=>trashButton.current?.focus());}
 }
 return <>
  <div className="job-trash-actions" aria-label="작업 정리">
   {job&&<button type="button" className="button secondary" disabled={busy||pending||unsaved||working||!job.updated_at} onClick={e=>void open(e.currentTarget,'delete')}>작업 삭제</button>}
   <button ref={trashButton} type="button" className="button text" disabled={busy||pending} onClick={e=>void open(e.currentTarget,'trash')}>휴지통</button>
   {unsaved&&<span className="muted">수정 내용을 저장하거나 취소한 뒤 삭제할 수 있습니다.</span>}
   {working&&<span className="muted">처리 중이거나 결과 불명인 작업은 운영 기록에서 결과를 확인한 뒤 삭제할 수 있습니다.</span>}
  </div>
  {notice&&<p role="status">{notice}</p>}
  {error&&!dialog.current?.open&&<p role="alert">{error}</p>}
  <dialog className="job-trash-dialog" ref={dialog} aria-labelledby={heading} onCancel={e=>{if(pending)e.preventDefault();}} onClose={()=>requestAnimationFrame(()=>{if(!dialog.current?.open)(trigger.current?.isConnected?trigger.current:trashButton.current)?.focus();})}>
   <h2 id={heading} tabIndex={-1}>{mode==='delete'?'작업 삭제 확인':'작업 휴지통'}</h2>
   {mode==='delete'?<>
    <p><strong>{snapshot?.title}</strong></p>
    <p>이 작업을 콘텐츠 작업실과 제작·출고함의 목록에서 함께 숨깁니다. 휴지통에서 복원할 수 있습니다.</p>
    <p>원고·승인 이력·EC2 파일·원본 사진·녹음과 외부 플랫폼 게시물은 삭제하지 않습니다.</p>
   </>:<>
    <p>복원하면 두 화면의 목록에 다시 나타납니다. 제작·전송·새 승인은 자동으로 시작하지 않습니다.</p>
    {!pending&&rows.length===0&&!error&&<p>휴지통이 비어 있습니다.</p>}
    <ul className="job-trash-list">{rows.map(row=><li key={row.id}><span>{row.title}</span><button type="button" className="button secondary" aria-label={`${row.title} 복원`} disabled={pending||busy} onClick={()=>void move(row,true)}>복원</button></li>)}</ul>
   </>}
   {pending&&<p role="status">처리 중입니다…</p>}
   {error&&<p role="alert">{error}</p>}
   <div className="job-trash-actions">
    <button type="button" className="button secondary" disabled={pending} onClick={close}>{mode==='delete'?'취소':'닫기'}</button>
    {mode==='delete'&&<button type="button" className="button primary" disabled={pending||busy||!snapshot?.updated_at} onClick={()=>snapshot&&void move(snapshot)}>휴지통으로 이동</button>}
    {mode==='trash'&&error&&<button type="button" className="button secondary" disabled={pending} onClick={()=>trigger.current&&void open(trigger.current,'trash')}>목록 새로 확인</button>}
   </div>
  </dialog>
 </>;
}
