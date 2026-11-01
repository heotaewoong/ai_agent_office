/* Isolated world only. Enable an adapter only after real account/save/reopen verification. */
(() => {
 if(globalThis.heobrainDraftListener)return;
 globalThis.heobrainDraftListener=true;
 const visible=e=>e.getClientRects().length>0;
 const exact=(root,labels)=>[...root.querySelectorAll('button,[role="button"]')].filter(visible).filter(e=>labels.includes((e.getAttribute('aria-label')||e.textContent).trim()));
 const click=(root,labels)=>{if(!labels.every(globalThis.HeoBrainDraftGuards.safeButton))throw Error('공개·예약 버튼은 실행하지 않습니다');const found=exact(root,labels);if(found.length!==1)throw Error('초안 전용 버튼을 확인하지 못했습니다');found[0].click();};
 const editor=()=>{const a=[...document.querySelectorAll('[contenteditable="true"][role="textbox"],.ql-editor[contenteditable="true"]')].filter(visible);if(a.length!==1)throw Error('편집 영역 확인 필요');return a[0];};
 const expectedAccount=async(item)=>{
  if(item.channel_key==='tistory_main')return location.hostname==='onethingflow.tistory.com' && location.pathname.startsWith('/manage/') && !!document.querySelector('#post-title-inp');
  if(item.channel_key==='naver_blog_main')return location.hostname==='blog.naver.com' && location.pathname==='/oneflowwhy/postwrite' && !!document.querySelector('.se-documentTitle,.se-section-documentTitle');
  if(item.channel_key==='linkedin_personal'){
   const me=exact(document,['Me','나']);if(me.length!==1)return false;
   const wasOpen=me[0].getAttribute('aria-expanded')==='true';
   try{if(!wasOpen)click(document,['Me','나']);return !!(await wait(()=>[...document.querySelectorAll('a[href*="/in/"]')].filter(visible).find(a=>globalThis.HeoBrainDraftGuards.linkedInProfile(a.href,item.account_id,a.getAttribute('aria-label')||a.textContent||''))));}
   catch{return false;}
   finally{if(!wasOpen && me[0].isConnected && me[0].getAttribute('aria-expanded')==='true')me[0].click();}
  }
  if(item.channel_key==='threads_main')return [...document.querySelectorAll('a[aria-label="프로필"],a[aria-label="Profile"]')].filter(visible).some(a=>new URL(a.href).pathname==='/'+item.account_id);
  return false;
 };
 const wait=async fn=>{for(let i=0;i<30;i++){const result=fn();if(result)return result;await new Promise(r=>setTimeout(r,200));}throw Error('편집 화면 준비 지연');};
 const put=(e,text)=>{if((e.value||e.innerText||'').trim())throw Error('기존 초안을 보존합니다');e.focus();if(e instanceof HTMLInputElement || e instanceof HTMLTextAreaElement){const setter=Object.getOwnPropertyDescriptor(e instanceof HTMLTextAreaElement?HTMLTextAreaElement.prototype:HTMLInputElement.prototype,'value').set;setter.call(e,text);e.dispatchEvent(new Event('input',{bubbles:true}));}else document.execCommand('insertText',false,text);};
 const text=e=>(e.value||e.innerText||'').replace(/\r/g,'').trim();
 const blogFields=item=>{
  if(item.channel_key==='tistory_main')return [document.querySelector('#post-title-inp'),document.querySelector('#editor-tistory_ifr')?.contentDocument?.body];
  return [document.querySelector('.se-documentTitle [contenteditable="true"],.se-section-documentTitle [contenteditable="true"]'),document.querySelector('.se-main-container .se-text [contenteditable="true"]')];
 };
 chrome.runtime.onMessage.addListener((message,sender,reply)=>{
  if(sender.id!==chrome.runtime.id || !['save-nonpublic','verify-nonpublic'].includes(message.kind))return false;
  (async()=>{
   const item=message.item;
   if(Date.parse(item.authorized_end)<=Date.now() || item.visibility!=='draft' || !(await expectedAccount(item)))throw Error('로그인 계정 확인 필요');
   if(['tistory_main','naver_blog_main'].includes(item.channel_key)){
    const fields=await wait(()=>{const f=blogFields(item);return f.every(Boolean)?f:null;});
    if(message.kind==='verify-nonpublic'){
     if(text(fields[0])!==item.title.trim() || text(fields[1])!==item.text.replace(/\r/g,'').trim())throw Error('저장본 재열기 본문 불일치');
     reply({verified:true,external_id:location.origin+'/draft/'+item.id});return;
    }
    put(fields[0],item.title);put(fields[1],item.text);
    if(text(fields[0])!==item.title.trim() || text(fields[1])!==item.text.replace(/\r/g,'').trim())throw Error('본문 입력 검증 실패');
    click(document,['임시저장','임시 저장']);
    await wait(()=>/임시\s?저장(되었습니다|이 완료| 완료)|저장되었습니다/.test(document.body.innerText));
    reply({state:'saved_candidate'});return;
   }
   if(!['linkedin_personal','threads_main'].includes(item.channel_key))throw Error('Meta Business Suite의 실제 계정·초안 지원 확인이 필요합니다');
   const isLinked=item.channel_key==='linkedin_personal';
   click(document,isLinked?['게시물 작성','글 올리기','Start a post']:['만들기','Create']);
   const field=await wait(()=>{try{return editor();}catch{return null;}});
   if(message.kind==='verify-nonpublic'){
    if(field.innerText.replace(/\r/g,'').trim()!==item.text.replace(/\r/g,'').trim())throw Error('재열기 본문 불일치');
    reply({verified:true,external_id:location.origin+'/draft/'+item.id});return;
   }
   if(field.innerText.trim())throw Error('기존 초안을 보존하기 위해 중단했습니다');
   put(field,item.text);
   if(field.innerText.replace(/\r/g,'').trim()!==item.text.replace(/\r/g,'').trim())throw Error('본문 입력 확인 실패');
   const modal=field.closest('[role="dialog"]');
   if(!modal)throw Error('작성 창 범위 확인 필요');
   click(modal,isLinked?['닫기','취소','Close','Cancel']:['취소','Cancel','Close']);
   const dialogs=[...document.querySelectorAll('[role="dialog"]')].filter(visible);
   if(dialogs.length!==1)throw Error('초안 저장 확인창 필요');
   click(dialogs[0],['초안으로 저장','임시저장','저장','Save draft','Save as draft','Save']);
   reply({state:'saved_candidate'});
  })().catch(()=>reply({verified:false,state:'blocked'}));
  return true;
 });
})();
