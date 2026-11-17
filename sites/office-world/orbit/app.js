import {createSpaceCity} from './scene.js';
import {createWorkspacePanels} from './panels.js';
import {createKnowledgeLab} from './lab.js';
import {createOperationsLab} from './ops.js';
import {createCoveragePanel} from './coverage.js';
import {createOperationalPanel} from './operational.js';
import {createOfficeBridge} from './bridge.js';

const $=s=>document.querySelector(s);
const escape=s=>String(s??'').replace(/[&<>"']/g,c=>({'&':'&amp;','<':'&lt;','>':'&gt;','"':'&quot;',"'":'&#39;'}[c]));
const icon=(name,cls='')=>`<svg class="icon ${cls}" aria-hidden="true"><use href="./icons.svg#${name}"/></svg>`;
const nav=[['city','orbit','본사'],['tasks','tasks','작업'],['people','people','동료 설계'],['chat','channels','루미'],['meetings','people','회의 설계'],['memory','memory','AI 실습'],['automation','automation','예약 설계'],['library','library','결과물']];
const dock=[['approvals','approvals','검토함'],['knowledge','memory','지식 검색'],['skills','skills','스킬 관측'],['connections','connections','연결 설계'],['costs','costs','비용'],['channels','channels','채널'],['research','research','연구 설계'],['maps','maps','맵 선택']];
const labels={hq:'루미 본사',content:'콘텐츠',marketing:'마케팅·상품',data:'데이터',development:'개발'};
const teamText={content:'Noah · Mia',marketing:'Ethan · Oliver',data:'Ada',development:'Sam'};
const colors={hq:'#b39258',content:'#bf784f',marketing:'#ad6996',data:'#658db9',development:'#a78b4f'};
const tints={content:'#f4e8de',marketing:'#f3e4ec',data:'#e4ebf3',development:'#eee8d9'};
const worlds=[{id:'orbital',name:'궤도 본사',en:'ORBITAL',desc:'별 사이에 떠 있는 우리의 본사'},{id:'cloud',name:'구름 위 캠퍼스',en:'CLOUD',desc:'공중도시로 이어지는 맑은 하늘'},{id:'garden',name:'가든 테라스',en:'GARDEN',desc:'차분한 자연빛과 초록의 풍경'},{id:'night',name:'미드나잇',en:'MIDNIGHT',desc:'집중을 위한 밤과 따뜻한 불빛'}];
let scene=null,panels=null,knowledge=null,operations=null,coverage=null,operational=null,bridge=null,currentPanel=null,viewMode='3d',activeWorld='orbital',tour=false,quality='balanced',toastTimer,renderFrame,data,activeSection='city',summary={state:'loading'},snapshotAvailable=false;
const reduced=matchMedia('(prefers-reduced-motion: reduce)').matches;
if(reduced)document.body.classList.add('reduced-motion');
function toast(message){clearTimeout(toastTimer);$('#toast').textContent=message;$('#toast').hidden=false;toastTimer=setTimeout(()=>$('#toast').hidden=true,4000);}
function setActive(id){activeSection=id;scene?.setPaused?.(id!=='city'||viewMode==='2d');document.querySelectorAll('.rail [data-section]').forEach(b=>{b.classList.toggle('active',b.dataset.section===id);if(b.dataset.section===id)b.setAttribute('aria-current','page');else b.removeAttribute('aria-current');});}
const operationalSections={tasks:'tasks',approvals:'approvals',library:'reports',reports:'reports',channels:'channels',costs:'costs',knowledge:'knowledge','live-knowledge':'knowledge',overview:'overview'};
function formatTime(value){const date=new Date(value);return value&&Number.isFinite(date.getTime())?new Intl.DateTimeFormat('ko-KR',{timeZone:'Asia/Seoul',month:'2-digit',day:'2-digit',hour:'2-digit',minute:'2-digit',hour12:false}).format(date)+' KST':'시각 미확인';}
function updateOperationalSummary(next){
 summary=next;
 const count=value=>Number.isInteger(value)&&value>=0?String(value):'—';
 $('#job-count').textContent=count(next.jobCount);$('#blocked-count').textContent=count(next.blockedCount);$('#approval-count').textContent=count(next.approvalCount);
 const states={loading:'운영 조회 중',ready:'운영 응답 확인',stale:'이전 응답 · 갱신 실패',error:'운영 조회 실패'};
 const status=states[next.state]||states.error;
 $('#connection-status').textContent=status;$('#connection-status').dataset.state=next.state;
 $('#snapshot-note').textContent=[status,next.fetchedAt?formatTime(next.fetchedAt):'아직 현재 수치를 확인하지 못했습니다.',next.message].filter(Boolean).join(' · ');
 $('#snapshot-metrics').setAttribute('aria-busy',String(next.state==='loading'));
 $('#approval-note').textContent=next.state==='ready'?'원고·출고 검토 단계의 작업':next.state==='stale'?'마지막 정상 조회의 검토 대기':next.state==='loading'&&Number.isInteger(next.approvalCount)?'갱신 중 · 이전 조회 값':'운영 응답 확인 후 표시';
 $('#refresh-operational').disabled=next.state==='loading';
}
function openSection(id,context){
 if(id==='maps'){openDialog('map-dialog');return;}
 if(id==='chat'){bridge?.openAssistant('lumi');return;}
 currentPanel?.close();currentPanel=null;
 if(id==='city'){setActive('city');return;}
 if(operationalSections[id]){currentPanel=operational;operational.open(operationalSections[id]);}
 else if(id==='coverage'){currentPanel=coverage;coverage.open();}
 else if(['memory','training','evolution','long'].includes(id)){
  currentPanel=knowledge;knowledge.open(({memory:'short',training:'training',evolution:'evolution',long:'long'})[id]);
 }else if(['people','meetings','automation','connections'].includes(id)){
  currentPanel=operations;operations.open(id==='connections'?'setup':id,context);
 }else{currentPanel=panels;$('#workspace').hidden=false;panels.open(id==='snapshot-tasks'?'tasks':id,context);}
 setActive(id);
}
function selectTeam(id,{open=false}={}){
 openSection('city');scene?.focus(id);tour=false;updateTour();
 document.querySelectorAll('[data-focus]').forEach(b=>b.classList.toggle('selected',b.dataset.focus===id));
 document.querySelectorAll('.city-label').forEach(b=>b.setAttribute('aria-pressed',String(b.dataset.focus===id)));
 if(open)openSection(id==='hq'?'approvals':'people',{team:id});
 else toast(`${labels[id]}로 이동했습니다. 한 번 더 누르면 ${id==='hq'?'운영 검토함':'관측 프로필과 팀 설계'}이 열립니다.`);
}
let currentFocus=null;
function handleFocus(id){const open=currentFocus===id;currentFocus=id;selectTeam(id,{open});}
function openDialog(id){const d=$('#'+id);if(!d.open)d.showModal();scene?.setPaused?.(true);}
function updateTour(){const b=$('#tour-toggle');b.setAttribute('aria-pressed',String(tour));b.setAttribute('aria-label',tour?'도시 둘러보기 일시정지':'도시 자동 둘러보기');b.innerHTML=icon(tour?'pause':'play');}
function buildWorlds(){
 $('#world-grid').innerHTML=worlds.map(w=>`<button class="world-card ${w.id===activeWorld?'selected':''}" data-world="${w.id}" aria-pressed="${w.id===activeWorld}"><small>${w.en}</small><strong>${w.name}</strong><span>${w.desc}</span></button>`).join('');
 $('#world-grid').querySelectorAll('button').forEach(b=>b.addEventListener('click',()=>{activeWorld=b.dataset.world;scene?.setWorld(activeWorld);$('#world-label').textContent=worlds.find(w=>w.id===activeWorld).name;buildWorlds();$('#map-dialog').close();toast('도시의 분위기를 바꿨습니다. 업무 데이터는 그대로입니다.');}));
}
function commandResults(q=''){
 const entries=[...nav,...dock,['coverage','features','원본 기능 대조'],['features','features','기능 위치 지도'],['snapshot-tasks','tasks','Hermes 작업 관측 사본'],['settings','settings','회사 설정 설계']].map(([section,ic,name])=>({section,icon:ic,name,type:operationalSections[section]?'운영 조회':section==='chat'?'기존 비서':'설계·관측'}));
 entries.push(...[{section:'long',name:'장기 기억 · 지식 검토와 검색'},{section:'training',name:'SFT · DPO 학습 데이터와 계획'},{section:'evolution',name:'SLERP · Task Arithmetic 모델 병합 원리'}].map(e=>({...e,icon:'memory',type:'새 체험 화면'})));
 for(const t of data.teams)entries.push({section:'people',icon:t.id,name:t.name+'팀',type:'팀',context:{team:t.id}});
 for(const f of data.features)entries.push({section:'features',icon:'features',name:f.name,type:f.product,context:{featureId:f.id,query:f.name}});
 const found=entries.filter(e=>`${e.name} ${e.type}`.toLowerCase().includes(q.toLowerCase())).slice(0,24);
 $('#command-results').innerHTML=found.length?found.map((e,i)=>`<button class="command-result" data-index="${i}">${icon(e.icon)}<span>${escape(e.name)}</span><small>${escape(e.type)}</small>${icon('chevron','small')}</button>`).join(''):'<p class="dialog-note">검색 결과가 없습니다. 다른 단어를 입력해 보세요.</p>';
 $('#command-results').querySelectorAll('button').forEach(b=>b.addEventListener('click',()=>{const e=found[+b.dataset.index];$('#command-dialog').close();openSection(e.section,e.context);}));
}
async function init(){
 data={teams:Object.keys(teamText).map(id=>({id,name:labels[id]})),profiles:[],cards:[],features:[]};
 try{const response=await fetch('./data.json');if(!response.ok)throw new Error('관측 기록 응답 오류');const snapshot=await response.json();if(!['teams','profiles','cards','features'].every(key=>Array.isArray(snapshot[key])))throw new Error('관측 기록 형식 오류');data=snapshot;snapshotAvailable=true;}catch(error){console.warn('Hermes 관측 사본을 불러오지 못했습니다.',error);}
 $('#primary-nav').innerHTML=nav.map(([id,ic,name])=>`<button data-section="${id}" aria-label="${name}" title="${name}">${icon(ic)}<span>${name}</span></button>`).join('');
 $('#dock-items').innerHTML=dock.map(([id,ic,name])=>`<button class="dock-item" data-section="${id}">${icon(ic)}<span>${name}</span></button>`).join('');
 $('#team-list').innerHTML=data.teams.map(t=>`<button class="team-row" data-focus="${t.id}" style="--team:${colors[t.id]};--tint:${tints[t.id]}" aria-label="${t.name} 오피스"><span class="team-emblem">${icon(t.id)}</span><span class="team-text"><strong>${t.name}</strong><small>${teamText[t.id]}</small></span>${icon('chevron')}</button>`).join('');
 $('#snapshot-source-note').textContent=snapshotAvailable?`${formatTime(data.cardCapturedAt)} · Hermes 작업 ${data.cards.length}개를 담은 관측 사본입니다. 현재 운영 수치와 합산하지 않습니다.`:'관측 사본을 불러오지 못했습니다. 프로필·기능 목록은 확인이 필요합니다.';
 panels=createWorkspacePanels($('#workspace'),{data,onNavigate:openSection,onToast:toast});
 coverage=createCoveragePanel($('#coverage-workspace'),{onNavigate:openSection});
 knowledge=createKnowledgeLab($('#knowledge-workspace'),{onToast:toast});
 operations=createOperationsLab($('#operations-workspace'),{data,onToast:toast,onWorld:()=>openDialog('map-dialog')});
 bridge=createOfficeBridge({onFocus:({itemId}={})=>{if(labels[itemId])selectTeam(itemId);},onRefresh:()=>operational?.refresh(),onObservation:()=>toast('기존 비서의 처리 상태가 갱신됐습니다. 결과와 승인 여부는 해당 기록에서 확인하세요.'),onReportAction:()=>scene?.setPaused?.(true),onToast:toast});
 operational=createOperationalPanel($('#operational-workspace'),{onNavigate:(view,itemId)=>view==='maps'?openDialog('map-dialog'):bridge.open(view,itemId),onAssistant:profile=>bridge.openAssistant(profile||'lumi'),onToast:toast,onSummary:updateOperationalSummary});
 updateOperationalSummary({state:'loading'});
 document.querySelectorAll('[data-section]').forEach(b=>b.addEventListener('click',()=>openSection(b.dataset.section)));
 document.querySelectorAll('[data-focus]').forEach(b=>b.addEventListener('click',()=>handleFocus(b.dataset.focus)));
 $('#refresh-operational').addEventListener('click',()=>operational.refresh());
 $('#home-link').addEventListener('click',e=>{e.preventDefault();openSection('city');});
 $('#city-labels').innerHTML=Object.entries(labels).map(([id,name])=>`<button class="city-label" data-focus="${id}" style="--team:${colors[id]}" aria-label="${name} 보기" aria-pressed="false"><span class="label-dot"></span>${name}<small>${id==='hq'?'LUMI':teamText[id]}</small></button>`).join('');
 $('#city-labels').querySelectorAll('button').forEach(b=>b.addEventListener('click',()=>handleFocus(b.dataset.focus)));
 setActive('city');buildWorlds();
 $('.flat-teams').innerHTML=data.teams.map(t=>`<button data-flat-team="${t.id}" style="--flat-color:${colors[t.id]}">${icon(t.id)}<strong>${escape(t.name)}</strong><small>${teamText[t.id]}</small><span>관측 프로필·팀 설계 →</span></button>`).join('');
 document.querySelectorAll('[data-flat-team]').forEach(b=>b.onclick=()=>openSection('people',{team:b.dataset.flatTeam}));
 try{
  scene=createSpaceCity($('#city-canvas'),{onSelect:handleFocus,onReady:()=>{$('#loading').hidden=true;},reducedMotion:reduced});
  function positions(){
   if(scene&&activeSection==='city'&&!document.hidden){const anchors=scene.getProjectedAnchors();for(const [id,p]of Object.entries(anchors)){const b=$(`.city-label[data-focus="${id}"]`);b.style.left=p.x+'px';b.style.top=p.y+'px';b.hidden=!p.visible||p.x<0||p.y<0||p.x>$('#city-canvas').clientWidth||p.y>$('#city-canvas').clientHeight;}}
   renderFrame=requestAnimationFrame(positions);
  }positions();
 }catch(error){$('#loading').hidden=true;$('#city-canvas').innerHTML=`<div class="error-panel"><h2>3D 화면을 열지 못했어요.</h2><p>2D 버튼이나 업무 화면을 이용할 수 있습니다. 운영 조회와 기존 승인 절차는 그대로 이용합니다.</p><button id="fallback-work">업무 화면 열기</button></div>`;$('#fallback-work').onclick=()=>openSection('tasks');console.error(error);}
 window.__heobrainOffice={getMetrics:()=>scene?.getMetrics()||{status:'unavailable'},getState:()=>({activeSection,viewMode,activeWorld,tour,quality,snapshotCards:snapshotAvailable?data.cards.length:null,features:data.features.length,operationalState:summary.state,jobCount:summary.jobCount??null,mode:'operations-with-design-lab'}),focus:selectTeam,openSection};
 window.__heobrainPreview=window.__heobrainOffice;
 commandResults();
 operational.refresh();
}
$('#view-mode').onclick=()=>{viewMode=viewMode==='3d'?'2d':'3d';document.body.classList.toggle('flat-mode',viewMode==='2d');$('#flat-office').hidden=viewMode!=='2d';$('#view-mode').setAttribute('aria-pressed',String(viewMode==='2d'));$('#view-mode').setAttribute('aria-label',viewMode==='2d'?'3D 도시 모드':'2D 업무 모드');$('#view-mode').innerHTML='<span>'+ (viewMode==='2d'?'3D':'2D')+'</span>';scene?.setPaused?.(viewMode==='2d');};
$('#map-open').onclick=()=>openDialog('map-dialog');$('#concept-open').onclick=()=>openDialog('concept-dialog');
$('#view-reset').onclick=()=>{openSection('city');scene?.reset();currentFocus=null;tour=false;updateTour();document.querySelectorAll('.city-label').forEach(b=>b.setAttribute('aria-pressed','false'));};
$('#tour-toggle').onclick=()=>{if(reduced){toast('동작 줄이기 설정에 따라 자동 회전을 멈춰 둡니다.');return;}tour=!tour;scene?.setTour(tour);updateTour();};
$('#focus-mode').onclick=()=>{const enabled=document.body.classList.toggle('focus-city');$('#focus-mode').setAttribute('aria-pressed',String(enabled));};
$('#quality-toggle').onclick=()=>{quality=quality==='balanced'?'low':quality==='low'?'high':'balanced';scene?.setQuality(quality);$('#quality-toggle').innerHTML=`<span>${quality==='low'?'ECO':quality==='high'?'HQ':'HD'}</span>`;toast(({low:'저전력 · 그림자 줄이기',balanced:'균형 · 기본 품질',high:'선명하게 · 높은 품질'})[quality]);};
$('#owner-settings').onclick=()=>openSection('settings');$('#help-open').onclick=()=>toast('작업·검토함·결과물은 운영 조회입니다. 루미는 기존 비서 화면을 엽니다. 동료·회의·학습·예약 설계는 실행 없는 실습입니다.');
document.querySelectorAll('.dialog-close').forEach(b=>b.onclick=()=>b.closest('dialog').close());
document.addEventListener('close',e=>{if(e.target.tagName==='DIALOG')scene?.setPaused?.(activeSection!=='city'||viewMode==='2d'||!!document.querySelector('dialog[open]'));},true);
document.querySelectorAll('dialog').forEach(d=>d.addEventListener('click',e=>{if(e.target===d){const r=d.getBoundingClientRect();if(e.clientX<r.left||e.clientX>r.right||e.clientY<r.top||e.clientY>r.bottom)d.close();}}));
$('#command-open').onclick=()=>{openDialog('command-dialog');$('#command-input').focus();};
$('#command-input').oninput=e=>commandResults(e.target.value);
document.addEventListener('keydown',e=>{if((e.ctrlKey||e.metaKey)&&e.key.toLowerCase()==='k'){e.preventDefault();openDialog('command-dialog');$('#command-input').focus();}if(e.key==='Escape'&&!document.querySelector('dialog[open]')&&activeSection!=='city')openSection('city');});
$('#new-brief').onclick=()=>openDialog('brief-dialog');
$('#brief-form').addEventListener('submit',e=>{
 e.preventDefault();const text=$('#brief-text').value.trim();if(text.length<5){toast('주제를 다섯 글자 이상 적어 주세요.');return;}
 const team=data.teams.find(t=>t.id===$('#brief-team').value);$('#brief-form').hidden=true;$('#brief-result').hidden=false;
 $('#brief-result').innerHTML=`<div class="brief-preview"><div class="eyebrow">기획 카드 예시 · 실행 안 됨</div><h3>${escape(team.name)}팀에 전달할 내용</h3><p>${escape(text)}</p><ul><li>역할: ${escape(teamText[team.id])}</li><li>첫 단계: 근거·대상 독자·완료 조건 확인</li><li>결과물: 검토 가능한 초안과 확인 근거</li><li>종료 조건: 사용자 검토 대기</li></ul></div><div class="brief-result-actions"><button id="brief-edit">다시 수정</button><button id="brief-export">기획안 파일 받기</button></div><p class="dialog-note">지금은 브라우저에서 입력한 내용을 정리했습니다. 실제 루미 요청·칸반 등록은 하지 않았습니다.</p>`;
 $('#brief-edit').onclick=()=>{$('#brief-form').hidden=false;$('#brief-result').hidden=true;$('#brief-text').focus();};
 $('#brief-export').onclick=()=>{const blob=new Blob([`# HeoBrain 업무 기획 미리보기\n\n팀: ${team.name}\n상태: 미실행 로컬 기획안\n\n${text}\n\n완료 조건: 근거가 포함된 초안을 만든 뒤 사용자 검토 대기\n`],{type:'text/markdown;charset=utf-8'});const url=URL.createObjectURL(blob);const a=document.createElement('a');a.href=url;a.download='HeoBrain-업무기획-미리보기.md';a.click();setTimeout(()=>URL.revokeObjectURL(url),1000);};
});
$('#city-canvas').addEventListener('space-city-error',e=>toast(e.detail));
document.addEventListener('workspace-close',()=>setActive('city'));
document.addEventListener('workspace-open',e=>setActive(e.detail.section==='reports'?'library':e.detail.section));
window.addEventListener('pagehide',()=>{cancelAnimationFrame(renderFrame);scene?.dispose();panels?.destroy();knowledge?.destroy();operations?.destroy();coverage?.destroy();operational?.destroy();bridge?.destroy();});
init().catch(error=>{$('#loading').textContent='본사 화면을 열지 못했습니다. 새로고침 후 다시 확인해 주세요.';updateOperationalSummary({state:'error',message:'화면 초기화 실패'});console.error(error);});
