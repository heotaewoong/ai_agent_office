import {TARGETS,validateItem,proof} from './policy.mjs';
const HOST='kr.heobrain.owner_drafts';
let running=false;
const native=async message=>{const answer=await chrome.runtime.sendNativeMessage(HOST,message);if(!answer?.ok)throw Error(answer?.error||'PC 실행기 연결 실패');return answer;};
async function cycle(testChannel) {
 if(running || (!testChannel && !(await chrome.storage.local.get('enabled')).enabled))return;
 running=true;
 try {
  const cache=await chrome.storage.local.get(['connectionCheckedAt']);
  if(!cache.connectionCheckedAt || Date.now()-cache.connectionCheckedAt>240000){const status=await native({command:'status'});await chrome.storage.local.set({connections:status.connections,connectionCheckedAt:Date.now()});}
  const {items}=await native({command:'poll'});
  const results=[];
  for(const candidate of items){
   if(testChannel && candidate.channel_key!==testChannel)continue;
   const target=validateItem(candidate);
   // Browser adapters are enabled only after account, save and reopen tests on the actual site.
   const {verifiedAdapters={}}=await chrome.storage.local.get('verifiedAdapters');
   if(target.platform!=='youtube' && !testChannel && verifiedAdapters[candidate.channel_key]!==chrome.runtime.getManifest().version){results.push({channel:candidate.channel_key,state:'adapter_verification_required'});continue;}
   const {item}=await native({command:'claim',id:candidate.id});
   validateItem(item);
   try{
    let result;
    if(target.platform==='youtube')result=await native({command:'youtube-private',id:item.id,claim_id:item.claim_id});
    else result=await webDraft(item,target);
    if(result.state==='platform_draft')await chrome.storage.local.set({verifiedAdapters:{...verifiedAdapters,[candidate.channel_key]:chrome.runtime.getManifest().version}});
    results.push({channel:item.channel_key,state:result.state});
   }catch{
    // It may have saved before disconnection. Never retry a claimed item automatically.
    await native({command:'receipt',id:item.id,claim_id:item.claim_id,proof:proof(item,'unknown',undefined,'플랫폼 결과를 확인하지 못했습니다. 자동 재전송하지 않습니다')}).catch(()=>{});
    results.push({channel:item.channel_key,state:'unknown'});
   }
  }
  await chrome.storage.local.set({lastRun:new Date().toISOString(),results,error:''});
 }catch{await chrome.storage.local.set({error:'PC 실행기·작업 시간·초안 판본을 확인하세요. 공개 발행하지 않았습니다.'});}
 finally{running=false;}
}
async function webDraft(item,target){
 const tab=await chrome.tabs.create({url:target.url,active:false});
 // Separate isolated content script; never evaluates code or selectors received from the server.
 await new Promise((resolve,reject)=>{
  const timeout=setTimeout(()=>{chrome.tabs.onUpdated.removeListener(listener);reject(Error('페이지 준비 지연'));},20000);
  const listener=(id,change)=>{if(id===tab.id && change.status==='complete'){clearTimeout(timeout);chrome.tabs.onUpdated.removeListener(listener);resolve();}};
  chrome.tabs.onUpdated.addListener(listener);
 });
 const frame = async()=>{const frames=await chrome.scripting.executeScript({target:{tabId:tab.id,allFrames:true},func:()=>location.href});return target.platform==='naver' ? frames.find(f=>new URL(f.result).pathname==='/oneflowwhy/postwrite')?.frameId : 0;};
 const frameId=await frame();
 if(frameId===undefined)throw Error('대상 편집 프레임 확인 필요');
 await chrome.scripting.executeScript({target:{tabId:tab.id,frameIds:[frameId]},files:['guards.js','web-adapters.js']});
 const response=await chrome.tabs.sendMessage(tab.id,{kind:'save-nonpublic',item},{frameId});
 if(response?.state!=='saved_candidate')throw Error('임시저장 미확인');
 await chrome.tabs.reload(tab.id);
 await new Promise(resolve=>{const timer=setTimeout(resolve,15000);const listener=(id,change)=>{if(id===tab.id&&change.status==='complete'){clearTimeout(timer);chrome.tabs.onUpdated.removeListener(listener);resolve();}};chrome.tabs.onUpdated.addListener(listener);});
 const reopened=await frame();if(reopened===undefined)throw Error('저장본 프레임 확인 필요');
 await chrome.scripting.executeScript({target:{tabId:tab.id,frameIds:[reopened]},files:['guards.js','web-adapters.js']});
 const checked=await chrome.tabs.sendMessage(tab.id,{kind:'verify-nonpublic',item},{frameId:reopened});
 if(!checked?.verified)throw Error('임시저장 재열기 확인 필요');
 return native({command:'receipt',id:item.id,claim_id:item.claim_id,proof:proof(item,'platform_draft',checked.external_id)});
}
chrome.runtime.onInstalled.addListener(()=>chrome.alarms.create('owner-drafts',{periodInMinutes:1}));
chrome.runtime.onStartup.addListener(()=>chrome.alarms.create('owner-drafts',{periodInMinutes:1}));
chrome.alarms.onAlarm.addListener(a=>{if(a.name==='owner-drafts')void cycle();});
chrome.runtime.onMessage.addListener((message,sender,reply)=>{
 if(sender.id!==chrome.runtime.id || sender.tab)return false;
 if(message?.command==='run'){void cycle().then(()=>reply({ok:true}));return true;}
 if(message?.command==='verify-channel' && TARGETS[message.channel]){void cycle(message.channel).then(()=>reply({ok:true}));return true;}
 if(message?.command==='connect'){native({command:'status'}).then(async status=>{await chrome.storage.local.set({connections:status.connections,connectionCheckedAt:Date.now()});reply({ok:true});}).catch(()=>reply({ok:false}));return true;}
 return false;
});
