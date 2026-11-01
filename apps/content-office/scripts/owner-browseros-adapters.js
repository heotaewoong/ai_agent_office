async function heobrainBrowserOSDrafts({operation,item,ticket}) {
 // Reviewed, local source only. Payload values select no code, selectors or buttons.
 const fail=reason=>({ok:false,reason});
 if(item?.channel_key?.startsWith('instagram'))return fail('instagram_held');
 if(item?.visibility!=='draft'||!Number.isFinite(Date.parse(item.authorized_end))||Date.parse(item.authorized_end)<=Date.now())return fail('public_or_expired');
 const key=item.channel_key;
 if(!['tistory_main','naver_blog_main','linkedin_personal','threads_main'].includes(key))return fail('unsupported_target');
 const norm=s=>(s||'').replace(/\r\n?/g,'\n').trim();
 const visible=e=>!!e&&e.getClientRects().length>0;
 const all=(selector,root=document)=>[...root.querySelectorAll(selector)].filter(visible);
 const label=e=>norm(e.getAttribute('aria-label')||e.innerText||e.textContent);
 const wait=async fn=>{for(let n=0;n<40;n++){const value=fn();if(value)return value;await new Promise(r=>setTimeout(r,200));}throw Error('page_contract_timeout');};
 const single=values=>{if(values.length!==1)throw Error('ambiguous_or_missing_control');return values[0];};
 const safeLabels=new Set(['임시저장','임시 저장','저장','초안으로 저장','Save draft','Save as draft','Save',
  '닫기','Close','Dismiss','Cancel','취소','게시물 작성','글 올리기','Start a post','만들기','Create',
  '임시 저장본','Drafts','초안','팝업닫기']);
 const buttons=(labels,root=document)=>all('button,[role="button"]',root).filter(e=>labels.includes(label(e)));
 const click=(labels,root=document)=>{
  if(labels.some(l=>!safeLabels.has(l)))throw Error('unsafe_action');
  single(buttons(labels,root)).click();
 };
 const dialog=()=>single(all('dialog,[role="dialog"]'));
 const account=()=>{
  if(key==='tistory_main'){
   let host;try{host=new URL(item.target?.public_url).hostname;}catch{return false;}
   return location.hostname==='onethingflow.tistory.com'&&host===location.hostname&&location.pathname.startsWith('/manage/')&&!!document.querySelector('#post-title-inp');
  }
  if(key==='naver_blog_main')return location.hostname==='blog.naver.com'&&location.pathname==='/'+item.account_id+'/postwrite'
   &&[...document.querySelectorAll('a[href]')].some(a=>{const u=new URL(a.href);return u.hostname==='admin.blog.naver.com'&&u.pathname==='/'+item.account_id;})
   &&!!document.querySelector('.se-documentTitle');
  if(key==='linkedin_personal'){
   if(location.hostname!=='www.linkedin.com'||!/^in\/[A-Za-z0-9-]+$/.test(item.account_id))return false;
   // The editable identity-module link belongs to the signed-in sidebar, not feed authors.
   return all('a[href*="profileFormEntryPoint=identityModuleMirror"]').some(e=>{
    const u=new URL(e.href);return u.hostname===location.hostname&&u.pathname.startsWith('/'+item.account_id+'/edit/');
   });
  }
  if(location.hostname!=='www.threads.com')return false;
  const editors=all('[data-barcelona-composer-body="true"]');
  return editors.some(e=>[...e.querySelectorAll('span')].some(s=>norm(s.textContent)===item.account_id))
   ||all('svg[aria-label="프로필"],svg[aria-label="Profile"]').some(e=>{
    const a=e.closest('a');return a&&new URL(a.href).pathname.replace(/^\/@?/,'')===item.account_id;
   });
 };
 const tistoryFields=()=>[document.querySelector('#post-title-inp'),document.querySelector('#editor-tistory_ifr')?.contentDocument?.body];
 const naverFields=()=>[document.querySelector('.se-documentTitle .se-text-paragraph'),
  ...document.querySelectorAll('.se-component.se-text .se-text-paragraph')];
 const socialField=()=>single(all('[contenteditable="true"][role="textbox"]'));
 const readNode=e=>{
  if('value' in e)return norm(e.value);
  if(key!=='naver_blog_main')return norm(e.innerText);
  const clone=e.cloneNode(true);clone.querySelectorAll('.se-placeholder').forEach(p=>p.remove());
  return norm(clone.textContent);
 };
 const fields=()=>key==='tistory_main'?tistoryFields():key==='naver_blog_main'?naverFields():[socialField()];
 const content=()=>{
  const f=fields();if(f.some(e=>!e)||!f.length)throw Error('editor_missing');
  if(key==='tistory_main')return {title:readNode(f[0]),text:readNode(f[1])};
  if(key==='naver_blog_main')return {title:readNode(f[0]),text:norm(f.slice(1).map(readNode).join('\n\n'))};
  return {title:'',text:readNode(f[0])};
 };
 const equal=c=>c.text===norm(item.text)&&(!['tistory_main','naver_blog_main'].includes(key)||c.title===norm(item.title));
 const put=(e,value)=>{
  if(readNode(e))throw Error('existing_native_draft');
  e.focus();
  if(e.tagName==='TEXTAREA'||e.tagName==='INPUT'){
   const win=e.ownerDocument.defaultView;
   const proto=e.tagName==='TEXTAREA'?win.HTMLTextAreaElement.prototype:win.HTMLInputElement.prototype;
   Object.getOwnPropertyDescriptor(proto,'value').set.call(e,value);
   e.dispatchEvent(new Event('input',{bubbles:true}));e.dispatchEvent(new Event('change',{bubbles:true}));
  }else{
   const doc=e.ownerDocument;const selection=doc.getSelection();const range=doc.createRange();
   range.selectNodeContents(e);selection.removeAllRanges();selection.addRange(range);
   if(!doc.execCommand('insertText',false,value))throw Error('editor_input_failed');
  }
 };
 const ensureComposer=async()=>{
  if(key==='linkedin_personal'){
   if(buttons(['Start a post','게시물 작성','글 올리기']).length!==1)throw Error('composer_entry_missing');
   // LinkedIn keeps a single native draft: never replace it for the next office item.
   if(all('button,[role="button"]').some(e=>/^(Draft:|초안:)/.test(norm(e.innerText))))throw Error('existing_native_draft');
   click(['Start a post','게시물 작성','글 올리기']);
   await wait(()=>all('[contenteditable="true"][role="textbox"]').length===1);
  }else if(key==='threads_main'){
   if(!all('[contenteditable="true"][role="textbox"]').length){
    const entry=all('[aria-label="만들기"],[aria-label="Create"],svg[aria-label="새로운 스레드"]').map(e=>e.closest('[role="button"],button')||e);
    single([...new Set(entry)]).click();
   }
   await wait(()=>all('[contenteditable="true"][role="textbox"]').length===1);
  }else await wait(()=>fields().length>=2&&fields().every(Boolean));
 };
 const openList=async()=>{
  if(key==='tistory_main')single(all('a.count[aria-label^="임시저장"]')).click();
  else if(key==='naver_blog_main')single(all('button[aria-label^="임시저장된 글 보기"]')).click();
  else if(key==='threads_main'){
   await ensureComposer();click(['임시 저장본','Drafts']);
  }
  // LinkedIn's Draft card itself is the observed list entry on the reloaded feed.
  await wait(()=>listRows().length>0);return {ok:true};
 };
 const listRows=()=>{
  if(key==='tistory_main')return all('[role="dialog"] .info_editor a.link_info').map(e=>({e,title:norm(e.textContent),label:norm(e.closest('.info_editor').innerText)}));
  if(key==='naver_blog_main')return all('button.article_button__p0NRG').map(e=>({e,title:norm(e.querySelector('strong')?.textContent),label:norm(e.innerText)}));
  if(key==='linkedin_personal')return all('button,[role="button"]').filter(e=>/^(Draft:|초안:)/.test(norm(e.innerText))).map(e=>({e,label:norm(e.innerText)}));
  return all('[role="dialog"] [role="button"]').filter(e=>{
   const t=norm(e.innerText);return t.startsWith(item.account_id+'\n')&&!e.querySelector('[contenteditable]');
  }).map(e=>({e,label:norm(e.innerText)}));
 };
 try{
  if(operation==='prepare'){
   await wait(()=>document.readyState==='complete');
   await ensureComposer();
   if(!account())return fail('account_unverified');
   const c=content();if(c.title||c.text)return fail('existing_native_draft');
   return {ok:true,empty:true,account_verified:true};
  }
  if(operation==='open-list'){
   await wait(()=>document.readyState==='complete');
   if(key==='threads_main')await ensureComposer();
   await wait(()=>account());
   return await openList();
  }
  if(!account())return fail('account_unverified');
  if(operation==='inspect')return {ok:true,account_verified:true,...content()};
  if(['focus-title','focus-body'].includes(operation)){
   if(key!=='naver_blog_main')return fail('unsupported_operation');
   const c=content(),f=fields();
   if(f.length!==2||c.text||(operation==='focus-title'?!!c.title:c.title!==norm(item.title)))return fail('existing_native_draft');
   const e=f[operation==='focus-title'?0:1],rect=e.getBoundingClientRect();
   // SmartEditor owns a hidden input buffer. Select its paragraph through its
   // normal mouse handlers, then the runner uses the official SDK's native type.
   for(const type of ['mousedown','mouseup','click'])e.dispatchEvent(new MouseEvent(type,{bubbles:true,clientX:rect.left+5,clientY:rect.top+5}));
   const active=document.activeElement;
   const input=active?.tagName==='IFRAME'?active.contentDocument?.activeElement:active;
   if(!input?.isContentEditable&&input?.tagName!=='TEXTAREA'&&input?.tagName!=='INPUT')return fail('naver_input_focus_unconfirmed');
   return {ok:true};
  }
  if(operation==='check-input'){
   await wait(()=>equal(content()));return {ok:true};
  }
  if(operation==='fill'){
   const c=content();if(c.title||c.text)return fail('existing_native_draft');
   const f=fields();
   // Preflight every field before the first input; partial overwrite is forbidden.
   if(f.some(e=>readNode(e)))return fail('existing_native_draft');
   if(key==='tistory_main'){put(f[0],item.title);put(f[1],item.text);}
   else if(key==='naver_blog_main'){
    return fail('naver_native_input_required');
   }else put(f[0],item.text);
   if(!equal(content()))return fail('input_body_mismatch');
   return {ok:true};
  }
  if(operation==='save'){
   if(!equal(content()))return fail('input_changed_before_save');
   if(key==='tistory_main')click(['임시저장']);
   else if(key==='naver_blog_main')click(['저장']);
   else{
    const modal=dialog();click(key==='linkedin_personal'?['닫기','Close','Dismiss']:['취소','Cancel'],modal);
    await wait(()=>buttons(['초안으로 저장','저장','Save draft','Save as draft','Save']).length===1);
    click(['초안으로 저장','저장','Save draft','Save as draft','Save'],dialog());
   }
   // This is only a candidate. No receipt until independent reload/list/reopen.
   await new Promise(r=>setTimeout(r,1000));return {ok:true};
  }
  if(operation==='open-draft'){
   const rows=listRows().filter(r=>r.title!==undefined?r.title===norm(item.title):r.label.includes(norm(item.text).slice(0,90)));
   const chosen=single(rows);
   if(!chosen.label||/^(게시|발행|Post|Publish|Schedule|Delete|삭제)$/.test(label(chosen.e)))return fail('unsafe_list_entry');
   const digest=await crypto.subtle.digest('SHA-256',new TextEncoder().encode(chosen.label));
   const list_key=[...new Uint8Array(digest)].map(b=>b.toString(16).padStart(2,'0')).join('');
   chosen.e.click();
   await wait(()=>{try{return equal(content());}catch{return false;}});
   return {ok:true,list_key,external_id:location.href};
  }
  if(operation==='verify'){
   if(!ticket?.list_key||ticket.external_id!==location.href)return fail('observed_list_identity_required');
   const c=content();if(!equal(c))return fail('reopened_body_mismatch');
   return {ok:true,verified:true,persisted:true,account_verified:true,list_key:ticket.list_key,external_id:location.href,...c};
  }
  return fail('unsupported_operation');
 }catch(e){return fail(/^[a-z_]{1,100}$/.test(e.message)?e.message:'page_contract_changed');}
}
