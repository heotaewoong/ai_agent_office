const status=document.querySelector('#status');
async function refresh(){const s=await chrome.storage.local.get(['enabled','connections','lastRun','results','error']);document.querySelector('#enabled').checked=s.enabled===true;status.textContent=JSON.stringify({로그인연결:s.connections||{},마지막처리:s.lastRun||'아직 없음',채널결과:s.results||[],오류:s.error||''},null,2);}
document.querySelector('#enabled').addEventListener('change',async e=>{await chrome.storage.local.set({enabled:e.target.checked});await refresh();});
for(const command of ['connect','run'])document.getElementById(command).addEventListener('click',async()=>{status.textContent='확인 중…';try{const r=await chrome.runtime.sendMessage({command});if(!r?.ok)throw Error();await refresh();}catch{status.textContent='Windows 실행기가 연결되지 않았습니다. 설치 안내서를 확인하세요.';}});
await refresh();
document.querySelector('#verify').addEventListener('click',async()=>{status.textContent='저장·재열기 검증 중…';try{await chrome.runtime.sendMessage({command:'verify-channel',channel:document.querySelector('#channel').value});await refresh();}catch{status.textContent='연결·작업 시간·승인된 대기 초안을 확인하세요.';}});
