// Register before reload and also check tabs that finished before registration.
export function readyPage(tabId, navigate) {
 return new Promise((resolve,reject)=>{
  const finish=error=>{clearTimeout(timer);chrome.tabs.onUpdated.removeListener(listener);error?reject(error):resolve();};
  const listener=(id,change)=>{if(id===tabId && change.status==='complete')finish();};
  const timer=setTimeout(()=>finish(Error('페이지 준비 지연')),20000);
  chrome.tabs.onUpdated.addListener(listener);
  Promise.resolve().then(()=>navigate?.()).then(()=>chrome.tabs.get(tabId)).then(tab=>{if(tab.status==='complete')finish();}).catch(finish);
 });
}
