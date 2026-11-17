/** HeoBrain isolated preview. Original snapshot is never mutated; no network or storage calls. */
const SECTIONS = {
  tasks: ['업무 보드', '막힌 곳을 발견하고, 다음 한 걸음을 정하세요.'],
  people: ['팀과 동료', '같은 동료가 여러 팀을 지원해도, 프로필은 하나입니다.'],
  memory: ['기억과 지식', '대화에서 배운 내용을, 다음 작업의 기준으로.'],
  skills: ['스킬 라이브러리', '좋은 작업 방식을 반복 가능한 절차로 만듭니다.'],
  connections: ['연결 관리', '도구의 역할과 권한을 한눈에 확인하세요.'],
  costs: ['비용과 사업', '비용을 확인한 뒤 실행하고, 결과를 근거로 판단합니다.'],
  channels: ['콘텐츠 채널', '원문은 하나로, 채널에 맞게 전달합니다.'],
  library: ['산출물 서재', '초안·근거·검토 기록을 같은 작업에 모읍니다.'],
  settings: ['회사 설정', '우리 회사의 공통 기준과 작업 환경을 정리합니다.'],
  features: ['전체 기능 지도', 'Connect AI와 DeskRPG 기능을 목적에 맞게 모았습니다.'],
  approvals: ['내 검토함', '확인할 내용과 실행할 범위를 먼저 읽습니다.'],
  meetings: ['회의실', '논의의 끝에는 결정과 다음 작업이 남도록.'],
  automation: ['반복 업무', '시작 조건과 멈출 조건이 분명한 자동화.'],
  research: ['AI 연구실', '데이터·모델·평가를 구분해서 관리합니다.'],
  maps: ['오피스와 공간', '하나의 회사, 이어지는 세계관. 공간의 역할과 스타일을 살펴보세요.'],
  training: ['학습 설계', 'SFT·DPO 데이터와 실행 조건을 검토합니다.'],
  evolution: ['모델 병합', '호환성 확인과 원리 실습을 구분합니다.'],
};
const STATUS = { blocked: '막힘', done: '완료 기록', ready: '준비', running: '진행', in_progress: '진행', queued: '대기', pending: '대기', review: '검토', backlog: '할 일', cancelled: '취소', failed: '실패' };
const PRESET_TEAMS = [
  { id:'content',name:'콘텐츠',color:'#be7656',profileIds:['noah','mia','ethan','oliver'],leadProfileIds:['noah','mia'] },
  { id:'marketing',name:'마케팅·상품',color:'#a375a6',profileIds:['ethan','oliver','noah','mia'],leadProfileIds:['ethan','oliver'] },
  { id:'data',name:'데이터',color:'#4b94a6',profileIds:['ada','oliver','sam'],leadProfileIds:['ada'] },
  { id:'development',name:'개발',color:'#aa874b',profileIds:['sam'],leadProfileIds:['sam'] },
];
const MEMORY = [
  {id:'m1',type:'long',tag:'브랜드 기준',title:'쉽게 시작하고, 직접 적용할 수 있게',body:'AI·자동화·공부·생산성에 관심 있는 초보자를 위해 씁니다. HeoBrain을 시험 공부에만 한정하지 않습니다.',source:'사용자가 정한 콘텐츠 방향 · 화면 구성 예시'},
  {id:'m2',type:'long',tag:'발행 원칙',title:'티스토리는 원문, HeoBrain은 선택 소개',body:'HeoBrain에서는 선택한 글의 제목·요약·원문 링크를 소개합니다. 새 글은 기본 미노출입니다.',source:'사용자 대화에서 확인한 기준 · 화면 구성 예시'},
  {id:'m3',type:'short',tag:'현재 작업',title:'우주도시 오피스 디자인 검토',body:'중앙 루미 본사와 콘텐츠·마케팅/상품·데이터·개발 4팀을 연결합니다. 실제 운영 반영은 디자인 확인 후 결정합니다.',source:'이번 요청 · Hermes 저장소를 조회한 값이 아님'},
  {id:'m4',type:'long',tag:'분석 기준',title:'재현 가능한 주제를 먼저 고르기',body:'재현 가능성을 먼저 판단한 뒤, 플랫폼 안에서 정확한 조회수를 비교합니다. 약식 조회수와 근거가 적은 후보는 따로 표시합니다.',source:'사용자가 정한 분석 방향 · 화면 구성 예시'},
];
const SKILLS = [
  {id:'s1',name:'콘텐츠 기획과 집필',owner:'Ethan · Noah',kind:'콘텐츠',steps:['독자·경험·목표 확인','근거를 붙인 브리프 작성','1인칭 초안·윤문','사람 검토에서 멈추기']},
  {id:'s2',name:'공개 자료 수집과 검증',owner:'Oliver · Ada',kind:'데이터',steps:['공개 자료·무료 잔여량 확인','수집 출처와 시각 기록','없는 지표는 NULL','DB 변경 범위 안내 후 승인 대기']},
  {id:'s3',name:'시각자료와 모션 제작',owner:'Mia',kind:'디자인',steps:['선택한 시안 확인','출처·민감정보 점검','검토 이미지 또는 무음 영상','사람 검토에서 멈추기']},
  {id:'s4',name:'개발·검산·검증',owner:'Sam · Ada',kind:'개발',steps:['기존 구현 읽기','원본 보존','변경 부분 검사','실제 화면과 결과 비교']},
];
const CONNECTIONS = [
  {name:'EC2 · Hermes',subtitle:'루미와 기존 프로필의 실행 환경',scope:'현재 화면은 마지막 관측 기록만 사용',state:'실시간 미연결'},
  {name:'BlueKiwi',subtitle:'작업 절차와 브랜드 기준',scope:'검토 도구 연결 화면 예시',state:'상태 조회 전'},
  {name:'Bitwarden',subtitle:'서비스별 비밀값 보관',scope:'비밀값을 이 미리보기에 입력하지 않습니다',state:'상태 조회 전'},
  {name:'Threads',subtitle:'계정 확인과 발행 경로',scope:'실제 게시·토큰 갱신 호출 없음',state:'상태 조회 전'},
  {name:'Bright Data',subtitle:'공개 자료 수집',scope:'무료 잔여량을 확인한 후 별도 실행',state:'상태 조회 전'},
  {name:'GitHub',subtitle:'코드와 비공개 검토 이력',scope:'저장소·원격 권한 변경 없음',state:'상태 조회 전'},
];
const ORIGINAL_MAPS = [
  ['trading','종합상사','책상 섬·임원석·회의 공간'],
  ['agency','크리에이티브 스튜디오','촬영·아이데이션·라운지'],
  ['tech','테크 스타트업','집중 업무석·스프린트 회의'],
  ['executive','임원 오피스','월넛 업무석·라운드 미팅'],
  ['publishing','출판사','서가·편집석·원고 검토'],
];
const DESK_PRESETS = {focus:['집중형','개인 책상·모니터·수납을 중심으로 모읍니다.'],collaboration:['협업형','서로 마주 보는 책상과 공동 검토 공간을 둡니다.'],studio:['스튜디오형','집필 책상과 촬영·시각 검토 공간을 함께 둡니다.']};
const esc = value => String(value ?? '').replace(/[&<>"']/g, char => ({'&':'&amp;','<':'&lt;','>':'&gt;','"':'&quot;',"'":'&#39;'}[char]));
const pill = (text,kind='neutral') => `<span class="ws-pill ws-pill-${kind}">${esc(text)}</span>`;
const button = (label,action,value='',extra='') => `<button type="button" class="ws-button" data-action="${action}" data-value="${esc(value)}" ${extra}>${esc(label)}</button>`;
const empty = text => `<div class="ws-empty"><strong>여기는 아직 비어 있어요.</strong><p>${esc(text)}</p></div>`;

export function createWorkspacePanels(host, {data = {}, onNavigate = () => {}, onToast = () => {}} = {}) {
  const features = Array.isArray(data.features) ? data.features : [];
  const cards = Array.isArray(data.cards) ? data.cards : [];
  const profiles = Array.isArray(data.profiles) ? data.profiles : [];
  const teams = data.teams?.length ? data.teams : PRESET_TEAMS;
  const state = {section:'tasks',query:'',filter:'all',view:'board',detail:null,context:{},memory:'all',pinned:new Set(),review:null,routine:false,meeting:false,meetingTopic:'',configDraft:'',researchTab:'dataset',deskPreset:'focus',appearance:{}};
  let returnFocus = null, active = false;
  const date = (() => { try { return new Intl.DateTimeFormat('ko-KR',{month:'long',day:'numeric',hour:'2-digit',minute:'2-digit',timeZone:'Asia/Seoul'}).format(new Date(data.capturedAt)); } catch { return '시각 미확인'; } })();
  host.classList.add('ws-host'); host.hidden = true;
  const notify = msg => { onToast(msg); };
  const filtered = rows => rows.filter(row => JSON.stringify(row).toLocaleLowerCase().includes(state.query.toLocaleLowerCase()));
  const teamName = id => teams.find(t => t.id===id)?.name || id;
  const featureRoute = feature => {
    const id=feature.id, n=Number(id.slice(1));
    if(id[0]==='C') return ({1:'settings',2:'people',3:'tasks',4:'tasks',5:'tasks',6:'tasks',7:'approvals',8:'meetings',9:'library',10:'costs',11:'costs',12:'channels',13:'connections',14:'costs',15:'channels',16:'memory',17:'memory',18:'training',19:'research',20:'connections',21:'automation',22:'connections',23:'channels',24:'settings',25:'meetings',26:'settings',27:'settings',28:'settings',29:'settings'})[n] || 'features';
    if(n<=4)return'maps'; if(n<=10) return n<=7?'people':'settings'; if(n<=14)return'connections'; if(n<=19)return'people'; if(n<=25)return'meetings'; if(n<=28)return'approvals'; if(n<=39)return'tasks'; if(n<=43)return'meetings'; if(n<=46)return'automation'; if(n<=49)return'library'; if(n<=53)return'skills'; if(n===54)return'memory'; if(n===55)return'skills'; if(n<=60)return'connections'; if(n===64)return'maps'; return'settings';
  };
  function controls() {
    let filters='';
    if(state.section==='tasks') filters=`<select aria-label="작업 상태" data-filter><option value="all">모든 상태</option><option value="blocked">막힌 작업</option><option value="ready">준비</option><option value="running">진행</option><option value="done">완료 기록</option></select><div class="ws-segment">${button('칸반','view','board',`aria-pressed="${state.view==='board'}"`)}${button('목록','view','list',`aria-pressed="${state.view==='list'}"`)}</div>`;
    if(state.section==='features') filters=`<select aria-label="기능 출처" data-filter><option value="all">모든 출처</option><option value="Connect AI">Connect AI · ${features.filter(f=>f.product==='Connect AI').length}</option><option value="DeskRPG">DeskRPG · ${features.filter(f=>f.product==='DeskRPG').length}</option></select>`;
    if(state.section==='people') filters=`<select aria-label="팀 선택" data-filter><option value="all">모든 동료</option>${teams.map(t=>`<option value="${esc(t.id)}">${esc(t.name)}</option>`).join('')}<option value="technical">이관·점검 프로필</option></select>`;
    if(state.section==='memory') filters=`<div class="ws-segment">${['all','long','short','growth'].map((id,i)=>button(['전체','장기 기억','작업 기억','성장 기록'][i],'memory-type',id,`aria-pressed="${state.memory===id}"`)).join('')}</div>`;
    return `<div class="ws-controls"><label class="ws-search"><span>검색</span><input type="search" placeholder="${state.section==='tasks'?'작업 제목, 담당자 검색':'이름이나 설명으로 찾기'}" value="${esc(state.query)}" aria-label="${esc(SECTIONS[state.section][0])} 검색" data-search></label>${filters}</div>`;
  }
  function render() {
    const selection = document.activeElement?.hasAttribute('data-search') ? {start:document.activeElement.selectionStart,end:document.activeElement.selectionEnd} : null;
    host.innerHTML=`<section class="ws-panel" role="dialog" aria-modal="true" aria-labelledby="ws-title" tabindex="-1"><header class="ws-header"><div><span class="ws-eyebrow">HEOBRAIN WORKSPACE</span><h2 id="ws-title">${esc(SECTIONS[state.section][0])}</h2><p>${esc(SECTIONS[state.section][1])}</p></div>${button('닫기','close','','aria-label="업무 화면 닫기"')}</header><div class="ws-source">${pill('로컬 미리보기','gold')}<span>운영에는 저장하지 않습니다 · 관측 기록 ${esc(date)}</span></div>${controls()}<div class="ws-content">${renderBody()}</div><footer class="ws-footer"><span>업무의 시작과 승인은 실제 연결 후 별도로 확인합니다.</span>${button('전체 기능 지도','section','features')}</footer></section>`;
    const filter=host.querySelector('[data-filter]'); if(filter)filter.value=state.filter;
    if(selection){ const input=host.querySelector('[data-search]'); input?.focus(); try{input.setSelectionRange(selection.start,selection.end);}catch{} }
  }
  function taskCard(card,index) {
    return `<button type="button" class="ws-task" data-action="card" data-value="${index}"><span class="ws-task-meta"><span>${esc(card.board)}</span>${pill(STATUS[card.status]||card.status,card.status==='blocked'?'rose':'neutral')}</span><strong>${esc(card.title)}</strong><span class="ws-task-bottom"><span class="ws-initial">${esc((card.assignee||'?').slice(0,1).toUpperCase())}</span>${esc(card.assignee||'담당 미확인')}<span class="ws-task-id">#${esc(card.id).slice(0,8)}</span></span></button>`;
  }
  function taskBody() {
    if(state.detail?.type==='card'){
      const c=cards[state.detail.index]; if(!c)return empty('기록을 찾을 수 없습니다.');
      return `<div class="ws-detail">${button('목록으로','back')}<div class="ws-detail-kicker">${pill('실제 관측 기록','blue')}${pill(STATUS[c.status]||c.status,c.status==='blocked'?'rose':'neutral')}</div><h3>${esc(c.title)}</h3><dl class="ws-details-grid"><div><dt>담당</dt><dd>${esc(c.assignee||'미확인')}</dd></div><div><dt>원본 보드</dt><dd>${esc(c.board)}</dd></div><div><dt>원본 카드 ID</dt><dd>${esc(c.id)}</dd></div><div><dt>분류 기준</dt><dd>${esc(c.classification||'화면상 협업 팀 기준')}</dd></div></dl><div class="ws-note"><strong>다음 판단에 필요한 정보</strong><p>본문·부모 작업·승인·실행 로그는 현재 관측에 포함되지 않았습니다. ‘완료’ 기록만으로 실제 게시나 품질 검증을 완료했다고 판단하지 않습니다.</p></div><div class="ws-actions">${button('관련 담당자 보기','person-from-card',c.assignee||'')}${button('승인 흐름 살펴보기','section','approvals')}</div></div>`;
    }
    const list=filtered(cards).filter(c=>state.filter==='all'||c.status===state.filter).filter(c=>!state.context.team||(c.teams||[]).includes(state.context.team));
    const heading=`<div class="ws-section-line"><span><strong>${list.length}</strong>개 작업 ${state.context.team?'· '+esc(teamName(state.context.team)):''}</span><span>원본 상태를 그대로 표시</span></div>`;
    if(!list.length)return heading+empty('검색어나 상태 필터를 바꿔 보세요.');
    if(state.view==='list')return heading+`<div class="ws-task-list">${list.map(c=>taskCard(c,cards.indexOf(c))).join('')}</div>`;
    const groups=[['할 일',['backlog','ready','queued','pending']],['진행',['running','in_progress']],['막힘·검토',['blocked','review','failed']],['완료 기록',['done','cancelled']]];
    const known=new Set(groups.flatMap(x=>x[1])); if(list.some(c=>!known.has(c.status)))groups.push(['그 외',list.filter(c=>!known.has(c.status)).map(c=>c.status)]);
    return heading+`<div class="ws-kanban">${groups.map(([name,statuses])=>{const rows=list.filter(c=>statuses.includes(c.status));return `<section class="ws-column"><h3>${name}<span>${rows.length}</span></h3>${rows.length?rows.map(c=>taskCard(c,cards.indexOf(c))).join(''):'<div class="ws-column-empty">현재 관측 기록 없음</div>'}</section>`;}).join('')}</div>`;
  }
  function appearanceControls(profile) {
    const selected=state.appearance[profile.id]||'navy';
    return `<div class="ws-appearance"><div><span class="ws-eyebrow">CHARACTER STYLE · 프로필 카드 예시</span><strong>동료의 표시 색상</strong><small>카드의 색상만 바뀌며 실제 캐릭터·좌석은 유지합니다.</small></div><div class="ws-segment">${[['navy','네이비'],['brass','브라스'],['sage','세이지']].map(([id,name])=>button(name,'appearance',profile.id+':'+id,`aria-pressed="${selected===id}"`)).join('')}</div></div>`;
  }
  function peopleBody() {
    const ps=filtered(profiles).filter(p=>state.filter==='technical'?(p.visibleInOffice===false||/windows-before-mig|ec2-migration-probe/.test(p.id)):p.visibleInOffice!==false&&!/windows-before-mig|ec2-migration-probe/.test(p.id)).filter(p=>state.filter==='all'||state.filter==='technical'||(p.teams||teams.filter(t=>t.profileIds.includes(p.id)).map(t=>t.id)).includes(state.filter));
    if(state.detail?.type==='person'){
      const p=profiles.find(p=>p.id===state.detail.id); if(!p)return empty('해당 프로필은 현재 관측에 없습니다.');
      return `<div class="ws-detail">${button('동료 목록','back')}<div class="ws-person-title"><span class="ws-avatar ws-avatar-large ws-avatar-${state.appearance[p.id]||'navy'}">${esc(p.id.slice(0,1).toUpperCase())}</span><div><h3>${esc(p.displayName||p.id)}</h3><p>${esc(p.role||'역할 정보 미확인')}</p></div></div>${appearanceControls(p)}<div class="ws-fact-grid"><article><span>담당 작업</span><strong>${cards.filter(c=>c.assignee===p.id).length}</strong><small>관측된 카드 기준</small></article><article><span>협업 팀</span><strong>${teams.filter(t=>t.profileIds.includes(p.id)).length}</strong><small>화면 분류 · 운영 배정 유지</small></article><article><span>현재 모델</span><strong class="ws-text-value">미확인</strong><small>이번 화면에서 호출하지 않음</small></article></div><h4>이 동료의 작업</h4><div class="ws-task-list">${cards.filter(c=>c.assignee===p.id).slice(0,6).map(c=>taskCard(c,cards.indexOf(c))).join('')||empty('관측된 담당 작업이 없습니다.')}</div><div class="ws-actions">${button('스킬 보기','section','skills')}${button('기억 보기','section','memory')}</div></div>`;
    }
    return `<div class="ws-section-line"><span>총괄과 4팀 · ${ps.length}개 프로필 표시</span><span>공유 담당자는 중복 생성하지 않습니다</span></div><div class="ws-people-grid">${ps.map(p=>`<button type="button" class="ws-person" data-action="person" data-value="${esc(p.id)}"><span class="ws-avatar">${esc(p.id.slice(0,1).toUpperCase())}</span><div><strong>${esc(p.displayName||p.id)}</strong><p>${esc(p.role||'역할 정보 미확인')}</p><span class="ws-person-teams">${teams.filter(t=>t.profileIds.includes(p.id)).map(t=>pill(t.name)).join('')||pill(p.id==='lumi'?'총괄':'공통 지원')}</span></div><span class="ws-count">${cards.filter(c=>c.assignee===p.id).length}<small>작업</small></span></button>`).join('')||empty('해당 조건의 프로필이 없습니다.')}</div>`;
  }
  function memoryBody(){
    if(state.memory==='growth')return `<div class="ws-note ws-note-slim">${pill('학습 흐름 예시','gold')}<span>실제 피드백·학습 그래프는 아직 조회하지 않았습니다. 동료의 성장 수치를 만들어 내지 않습니다.</span></div><div class="ws-fact-grid"><article><span>검토된 피드백</span><strong class="ws-text-value">미조회</strong><small>사람이 남긴 평가 기준</small></article><article><span>반영된 작업 규칙</span><strong class="ws-text-value">미조회</strong><small>승인된 기억·스킬 변경</small></article><article><span>다음 실행에서 재검증</span><strong class="ws-text-value">미실행</strong><small>동일 기준의 실제 결과 필요</small></article></div><ol class="ws-step-list"><li><span>01</span><div><strong>내가 피드백을 남깁니다.</strong><small>예: 확인하지 않은 결과를 성과처럼 쓰지 않기.</small></div></li><li><span>02</span><div><strong>어디에 반영할지 검토합니다.</strong><small>이번 작업 메모인지, 회사 공통 기준인지 구분합니다.</small></div></li><li><span>03</span><div><strong>승인한 기준을 다음 작업에서 확인합니다.</strong><small>저장된 규칙이 실제 결과에 반영됐는지 대조합니다.</small></div></li></ol>`;
    const rows=filtered(MEMORY).filter(m=>state.memory==='all'||m.type===state.memory);
    return `<div class="ws-note ws-note-slim">${pill('기억 화면 예시','gold')}<span>대화에서 합의한 기준을 재구성했습니다. 실제 Hermes 기억 파일을 읽거나 쓰지 않습니다.</span></div><div class="ws-grid">${rows.map(m=>`<article class="ws-card"><div class="ws-card-top">${pill(m.tag,m.type==='long'?'blue':'gold')}${button(state.pinned.has(m.id)?'고정 해제':'고정','pin',m.id,`aria-pressed="${state.pinned.has(m.id)}"`)}</div><h3>${esc(m.title)}</h3><p>${esc(m.body)}</p><small>${esc(m.source)}</small></article>`).join('')||empty('다른 검색어를 입력해 보세요.')}</div><div class="ws-note"><strong>회사 기준 → 팀 절차 → 이번 작업</strong><p>오래 유지할 원칙과 이번 작업에서만 쓸 정보를 나눕니다. 기준 변경은 사람의 검토 후 실제 기억에 반영합니다.</p></div>`;
  }
  function skillsBody(){
    const rows=filtered(SKILLS);
    if(state.detail?.type==='skill'){
      const s=SKILLS.find(s=>s.id===state.detail.id);return `<div class="ws-detail">${button('스킬 목록','back')}${pill('절차 미리보기','gold')}<h3>${esc(s.name)}</h3><p>${esc(s.owner)}</p><ol class="ws-step-list">${s.steps.map((x,i)=>`<li><span>${String(i+1).padStart(2,'0')}</span><div><strong>${esc(x)}</strong><small>다음 단계에 전달할 근거와 결과를 함께 남깁니다.</small></div></li>`).join('')}</ol><div class="ws-note">설치 여부를 확인한 목록이 아닌 사용자 작업 흐름을 바탕으로 만든 화면 예시입니다. 실행·설치 요청을 보내지 않습니다.</div>${button('관련 기능 확인','filter-feature','스킬')}</div>`;
    }
    return `<div class="ws-note ws-note-slim">${pill('절차 예시','gold')}<span>설치된 스킬 목록은 아직 읽지 않았습니다. 절차 상세를 열어 확인할 수 있습니다.</span></div><div class="ws-grid">${rows.map(s=>`<button type="button" class="ws-card ws-card-button" data-action="skill" data-value="${s.id}"><span class="ws-card-top">${pill(s.kind)}<span>${s.steps.length}단계</span></span><h3>${esc(s.name)}</h3><p>${esc(s.owner)}</p><small>절차와 검토 지점 보기</small></button>`).join('')}</div><div class="ws-actions">${button('스킬·기억 전체 기능','filter-feature','스킬')}${button('도구 연결 보기','section','connections')}</div>`;
  }
  function connectionsBody(){
    return `<div class="ws-note ws-note-slim">${pill('읽기 전용 미리보기','blue')}<span>등록 정보·키·사용량은 조회하지 않았습니다. 연결된 서비스처럼 초록불을 표시하지 않습니다.</span></div><div class="ws-grid">${filtered(CONNECTIONS).map((c,i)=>`<article class="ws-card"><div class="ws-card-top"><span class="ws-service-mark">${esc(c.name.slice(0,1))}</span>${pill(c.state)}</div><h3>${esc(c.name)}</h3><p>${esc(c.subtitle)}</p><small>${esc(c.scope)}</small>${button('권한·연결 안내','connection',String(CONNECTIONS.indexOf(c)))}</article>`).join('')}</div>${state.detail?.type==='connection'?`<div class="ws-note"><h3>${esc(CONNECTIONS[state.detail.index].name)} 연결을 검토할 때</h3><ol><li>현재 계정과 기존 설정을 먼저 읽습니다.</li><li>목적에 필요한 읽기·쓰기 범위를 구분합니다.</li><li>로그인과 권한 승인은 사용자가 직접 확인합니다.</li><li>실제 호출 결과와 비용을 검증한 뒤 상태를 표시합니다.</li></ol><p>이 화면에서는 연결 시험, 키 입력, 권한 변경을 수행하지 않습니다.</p></div>`:''}`;
  }
  function costsBody(){
    return `<div class="ws-fact-grid"><article><span>모델 사용 금액</span><strong class="ws-text-value">미확인</strong><small>결제·사용량 원천 연결 전</small></article><article><span>EC2 운영 비용</span><strong class="ws-text-value">미확인</strong><small>AWS 청구서 조회 안 함</small></article><article><span>상품 매출</span><strong class="ws-text-value">미확인</strong><small>HeoBrain 운영 DB 조회 안 함</small></article></div><div class="ws-grid"><article class="ws-card"><span class="ws-eyebrow">EXECUTION POLICY</span><h3>실행 전 비용 확인</h3><p>구독 포함·무료 잔여량·별도 과금을 구분합니다. 알 수 없는 비용을 0원으로 간주하지 않습니다.</p><label class="ws-field">미리보기 예산 메모<input data-budget placeholder="예: 추가 과금 없이, 구독 범위만" maxlength="120"></label>${button('메모 적용 · 이 화면만','budget-note')}</article><article class="ws-card"><span class="ws-eyebrow">BUSINESS REVIEW</span><h3>주문과 실제 결제를 나눠 보기</h3><p>0원·유료·취소·환불을 구분하고, 묶음 결제액은 주문 단위로 유지합니다. 상품별 배분은 임의로 계산하지 않습니다.</p>${button('분석 기준 보기','business-rule')}</article></div>${state.detail?.type==='business'?`<div class="ws-note"><strong>확인할 원천</strong><p>주문·결제 상태·상품 목록·이용 기록을 먼저 읽고, 기간과 기준을 정합니다. 이 미리보기에는 가상의 매출 그래프를 넣지 않았습니다.</p></div>`:''}`;
  }
  function channelsBody(){
    const channels=[['티스토리','원문','경험과 방법을 한 편의 본문으로 정리합니다.'],['HeoBrain','선택 소개','선택한 글의 제목·요약·원문 링크를 소개합니다.'],['Threads','짧은 소개','원문으로 이어지는 짧은 문장과 질문을 준비합니다.'],['YouTube · Instagram','채널별 제작','영상·카드뉴스 등 채널에 맞는 형식을 준비합니다.']];
    return `<div class="ws-flow"><div>경험·자료</div><span>→</span><div>원문 초안</div><span>→</span><div>채널별 검토</div><span>→</span><div class="ws-flow-end">사람 승인</div></div><div class="ws-grid">${channels.map(([name,tag,body],i)=>`<article class="ws-card">${pill(tag,'blue')}<h3>${name}</h3><p>${body}</p>${button('소개 문구 예시 보기','channel',i)}</article>`).join('')}</div>${state.detail?.type==='channel'?`<div class="ws-note"><span class="ws-eyebrow">문구 예시 · 게시되지 않음</span><h3>AI와 대화하던 내가, 작은 자동화 사무실을 만든 과정</h3><p>${['Windows에서 EC2의 루미를 연결하고, 글의 원문과 각 채널의 역할을 나눴습니다. 막혔던 인증과 토큰 설정부터 차근차근 기록합니다.','EC2·루미 연결 경험을 정리한 글입니다. 준비한 것과 실제 검증한 것을 구분해 소개합니다.','자동화에서 가장 헷갈린 건 도구보다 연결의 역할이었어요. PC, EC2, 비밀값 보관함, 콘텐츠 채널을 나눠 보니 다음 단계가 보였습니다.','첫 장면: Windows → EC2 루미 → 콘텐츠 채널. 설정 화면의 민감정보를 가리고 연결도를 함께 보여줍니다.'][state.detail.index]}</p>${pill('화면용 샘플','gold')}</div>`:''}`;
  }
  function libraryBody(){
    const examples=[['글 초안','연결 경험 글 · 검토 구조','텍스트'],['시각자료','중앙 본사와 4팀 · 디자인 시안','이미지'],['근거 노트','확인한 것과 아직 남은 것','문서'],['검산 보고','원본·조회 조건·결과 대조','데이터']];
    return `<div class="ws-note ws-note-slim">${pill('서재 구성 예시','gold')}<span>실제 산출물 저장소를 조회하지 않았습니다. 아래 항목은 검토 흐름을 보여 주는 예시입니다.</span></div><div class="ws-grid">${examples.map((row,index)=>({row,index})).filter(({row})=>row.join(' ').includes(state.query)).map(({row:[tag,name,type],index:i})=>`<button type="button" class="ws-card ws-card-button" data-action="artifact" data-value="${i}"><span class="ws-document-mark">${type}</span><h3>${name}</h3><p>${tag} · 미리보기</p><small>열어서 검토 항목 확인</small></button>`).join('')}</div>${state.detail?.type==='artifact'?`<div class="ws-note"><h3>${examples[state.detail.index][1]}</h3><p>원문·버전·입력 자료·검토자의 의견을 같은 작업에 묶습니다. ‘검토 완료’와 ‘공개 승인’은 별도 상태로 유지합니다.</p><ul><li>입력 자료와 출처</li><li>이번 버전의 변경점</li><li>실제로 확인한 결과</li><li>사람이 결정해야 할 항목</li></ul></div>`:''}`;
  }
  function approvalsBody(){
    return `<div class="ws-note ws-note-slim">${pill('실제 승인 현황 미수집','blue')}<span>막힌 카드 ${cards.filter(c=>c.status==='blocked').length}개를 승인 대기로 바꾸어 해석하지 않습니다.</span></div><article class="ws-approval"><div class="ws-card-top">${pill('검토 동작 예시','gold')}<span>운영과 분리된 샘플</span></div><h3>우주도시 오피스 디자인 검토</h3><p>중앙 본사와 4팀 배치, 읽기 순서, 업무 화면 이동을 살펴봅니다.</p><dl class="ws-details-grid"><div><dt>요청 범위</dt><dd>디자인에 대한 피드백</dd></div><div><dt>실제 실행</dt><dd>앱 반영·배포 없음</dd></div><div><dt>게시·메일</dt><dd>하지 않음</dd></div><div><dt>비용</dt><dd>이 버튼은 외부 호출을 하지 않음</dd></div></dl>${state.review?`<div class="ws-local-result">${state.review==='reviewed'?'예시를 검토한 상태로 표시했습니다.':'예시에 수정 의견이 있는 상태로 표시했습니다.'} 실제 승인 기록은 생성하지 않았습니다.</div>`:''}<div class="ws-actions">${button('검토 완료 표시 · 예시','review','reviewed')}${button('수정 요청 표시 · 예시','review','changes')}${state.review?button('예시 초기화','review',''):''}</div></article>`;
  }
  function meetingsBody(){
    return `<div class="ws-note ws-note-slim">${pill('회의 화면 예시','gold')}<span>발언·회의록은 샘플입니다. 동료 모델에게 요청을 보내지 않습니다.</span></div><article class="ws-card"><span class="ws-eyebrow">LUMI COORDINATION ROOM</span><h3>다음 콘텐츠의 방향을 정하는 회의</h3><div class="ws-attendees">${['Lumi','Ethan','Oliver','Noah','Mia'].map(n=>`<span><span class="ws-avatar">${n[0]}</span>${n}</span>`).join('')}</div><label class="ws-field">검토할 주제<input data-meeting-topic maxlength="160" value="${esc(state.meetingTopic)}" placeholder="예: EC2 연결 경험을 초보자에게 설명하기"></label>${button(state.meeting?'회의록 예시 접기':'회의록 예시 열기','meeting')}</article>${state.meeting?`<div class="ws-note"><h3>${esc(state.meetingTopic||'회의록 예시')}</h3><ol class="ws-step-list"><li><span>01</span><div><strong>독자가 얻을 결과</strong><small>전체 연결 구조를 이해하고 다음 설정을 직접 해 보기.</small></div></li><li><span>02</span><div><strong>핵심 근거</strong><small>실제 오류·해결 과정과 아직 검증하지 않은 단계를 구분하기.</small></div></li><li><span>03</span><div><strong>다음 할 일</strong><small>원문 초안 검토 → 민감정보 가림 → 사람 승인 대기.</small></div></li></ol></div>`:''}`;
  }
  function automationBody(){
    return `<div class="ws-note ws-note-slim">${pill('자동화 설계 예시','gold')}<span>스케줄러와 연결하지 않았습니다. 이 화면은 트리거와 검토 지점을 보여 줍니다.</span></div><article class="ws-card"><div class="ws-card-top"><span class="ws-eyebrow">HUMAN-STARTED WORKFLOW</span>${pill(state.routine?'흐름 펼침':'사용자 요청으로 시작')}</div><h3>주제에서 비공개 검토본까지</h3><p>사용자가 주제·경험·자료를 주면 준비를 시작합니다. 실제 발행은 별도 승인 전까지 멈춥니다.</p>${button(state.routine?'흐름 접기':'단계별 흐름 보기','routine')}</article>${state.routine?`<ol class="ws-step-list">${[['Ethan','독자·목표·브리프'],['Oliver','자료와 출처 수집'],['Noah','초안·윤문'],['Mia','시각자료'],['Lumi','최종 취합·사람 검토']].map(([name,job],i)=>`<li><span>${String(i+1).padStart(2,'0')}</span><div><strong>${name} · ${job}</strong><small>산출물과 합격 기준을 다음 작업에 전달</small></div></li>`).join('')}</ol>`:''}<div class="ws-actions">${button('실제 관측 카드 보기','section','tasks')}${button('검토함 예시','section','approvals')}</div>`;
  }
  function researchBody(){
    const tabs=[['dataset','데이터셋'],['model','모델'],['evaluation','평가']];
    const text={dataset:['자료의 권리와 품질부터','수집 목적·출처·누락·제외 기준을 남깁니다. 개인정보나 다른 사람의 저작물을 무분별하게 학습 자료로 옮기지 않습니다.'],model:['실행 환경과 비용을 구분','로컬 모델과 구독/API 모델을 별도로 표시합니다. 이 화면에서는 모델 다운로드·훈련·병합을 실행하지 않습니다.'],evaluation:['같은 입력으로 결과 비교','정확성·재현성·소요 시간·비용 기준을 먼저 정합니다. 시험 실행 없이 점수나 성능 향상을 만들어 내지 않습니다.']}[state.researchTab];
    return `<div class="ws-segment">${tabs.map(([id,name])=>button(name,'research-tab',id,`aria-pressed="${state.researchTab===id}"`)).join('')}</div><div class="ws-note"><span class="ws-eyebrow">RESEARCH WORKSPACE · 화면 예시</span><h3>${text[0]}</h3><p>${text[1]}</p></div><div class="ws-fact-grid"><article><span>훈련 작업</span><strong class="ws-text-value">미실행</strong><small>설계 검토만 가능</small></article><article><span>다운로드</span><strong class="ws-text-value">미실행</strong><small>모델 파일 변경 없음</small></article><article><span>평가 결과</span><strong class="ws-text-value">미확인</strong><small>검증 전 수치 없음</small></article></div>`;
  }
  function mapsBody(){
    const preset=DESK_PRESETS[state.deskPreset];
    return `<div class="ws-note ws-note-slim">${pill('새 디자인 · 독립 미리보기','gold')}<span>현재 우주도시의 네 분위기는 새 디자인 변형입니다. DeskRPG 원본 다섯 맵을 재현한 것으로 표시하지 않습니다.</span></div><div class="ws-grid"><article class="ws-card"><span class="ws-eyebrow">HEOBRAIN WORLD</span><h3>같은 도시, 네 가지 분위기</h3><p>궤도 본사 · 구름 위 캠퍼스 · 가든 테라스 · 미드나잇. 중앙 본사와 4팀 배치를 유지하며 배경과 조명을 바꿉니다.</p>${button('새 도시 테마 선택','open-worlds')}</article><article class="ws-card"><span class="ws-eyebrow">FURNITURE PRESET · 예시</span><h3>오피스 배치 기획</h3><div class="ws-segment">${Object.entries(DESK_PRESETS).map(([id,[name]])=>button(name,'desk-preset',id,`aria-pressed="${state.deskPreset===id}"`)).join('')}</div><p class="ws-layout-note"><strong>${esc(preset[0])}</strong> · ${esc(preset[1])}</p><small>배치 메모만 바뀝니다. 실제 타일·책상·캐릭터 좌표는 변경하지 않습니다.</small></article></div><div class="ws-section-line ws-map-heading"><span>DeskRPG 원본 공간 5종</span><span>소스 기준 참고 목록 · 원본 유지</span></div><div class="ws-map-references">${ORIGINAL_MAPS.map(([id,name,description])=>`<article><span class="ws-eyebrow">${id.toUpperCase()}</span><h3>${name}</h3><p>${description}</p>${pill('기존 앱에 보존')}</article>`).join('')}</div><div class="ws-note"><strong>이 미리보기에서 바꾸는 것</strong><p>카메라·도시 분위기는 직접 조작할 수 있습니다. 원본 맵 편집, 직원 좌석 배정, 초대·권한·자동화 설정은 원본 앱과 분리해 두었습니다.</p></div>`;
  }
  function settingsBody(){
    return `<div class="ws-grid"><article class="ws-card"><span class="ws-eyebrow">COMPANY</span><h3>HeoBrain · 루미 총괄</h3><p>콘텐츠 · 마케팅/상품 · 데이터 · 개발</p><label class="ws-field">회사 원칙 메모<textarea data-config rows="4" maxlength="500" placeholder="이 미리보기에서 검토할 메모">${esc(state.configDraft)}</textarea></label>${button('이 화면에만 적용','config')}</article><article class="ws-card"><span class="ws-eyebrow">PREVIEW BOUNDARY</span><h3>기존 운영은 그대로</h3><ul class="ws-checklist"><li>EC2 프로필·권한·카드 원본 유지</li><li>HeoBrain 회원·상품·결제 유지</li><li>로그인·비밀값 입력 받지 않음</li><li>실행·게시·메일 요청 보내지 않음</li></ul>${button('연결 현황 화면','section','connections')}</article></div><div class="ws-note"><h3>설정은 제자리에서 찾도록</h3><p>맵·카메라는 도시 화면에서, 직원·모델은 동료 상세에서, MCP 권한은 연결 관리에서 확인하도록 나눴습니다. 실제 변경 전에 범위를 보여 줍니다.</p></div>`;
  }
  function featuresBody(){
    if(state.detail?.type==='feature'){
      const f=features.find(f=>f.id===state.detail.id);if(!f)return empty('기능을 찾을 수 없습니다.');const route=featureRoute(f);
      return `<div class="ws-detail">${button('전체 기능으로','back')}<div class="ws-detail-kicker">${pill(f.product,'blue')}${pill(f.id)}${pill(f.category)}</div><h3>${esc(f.name)}</h3><p>${esc(f.description)}</p><dl class="ws-details-grid"><div><dt>원본 대조 상태</dt><dd>${esc(f.statusLabel||'별도 확인 필요')}</dd></div><div><dt>이번 미리보기</dt><dd>화면·동작 예시</dd></div><div><dt>업무상 위치</dt><dd>${esc(SECTIONS[route][0])}</dd></div><div><dt>원본 진입 설명</dt><dd>${esc(f.entryLabel||'원본 기능 목록 참고')}</dd></div></dl><div class="ws-note"><strong>화면과 실제 기능 연결은 구분합니다.</strong><p>관련 화면을 직접 둘러볼 수 있습니다. 서버 실행·설정 저장·외부 서비스 호출은 이 미리보기에 연결하지 않았습니다.</p></div>${button(`${SECTIONS[route][0]} 열기`,'section',route)}</div>`;
    }
    const rows=filtered(features).filter(f=>state.filter==='all'||f.product===state.filter);
    const categories=[...new Set(rows.map(f=>f.category))];
    return `<div class="ws-feature-summary"><div><strong>${features.length}</strong><span>대조한 기능군</span></div><div><strong>${features.filter(f=>f.product==='Connect AI').length}</strong><span>Connect AI</span></div><div><strong>${features.filter(f=>f.product==='DeskRPG').length}</strong><span>DeskRPG 계열 · 맞춤 5개 포함</span></div><p>원본 61개 기능군과 HeoBrain 추가 5개입니다. 목록에 있다는 것은 실제 통합 완료를 의미하지 않습니다. 상세에서 원본 상태와 이번 미리보기 범위를 확인하세요.</p></div><div class="ws-section-line"><span>검색 결과 ${rows.length}개</span><span>모든 기능에 검토 위치 제공</span></div>${categories.map(category=>`<section class="ws-feature-group"><h3>${esc(category)}</h3><div class="ws-feature-list">${rows.filter(f=>f.category===category).map(f=>`<button type="button" class="ws-feature" data-action="feature" data-value="${esc(f.id)}"><span class="ws-feature-id">${esc(f.id)}</span><span><strong>${esc(f.name)}</strong><small>${esc(f.description)}</small></span><span class="ws-feature-meta">${pill(f.product,f.product==='Connect AI'?'gold':'blue')}<small>${esc(f.statusLabel)}</small></span><span aria-hidden="true">→</span></button>`).join('')}</div></section>`).join('')||empty('출처나 검색어를 바꿔 보세요.')}`;
  }
  function renderBody(){
    if(state.detail?.type==='card')return taskBody();
    return ({tasks:taskBody,people:peopleBody,memory:memoryBody,skills:skillsBody,connections:connectionsBody,costs:costsBody,channels:channelsBody,library:libraryBody,settings:settingsBody,features:featuresBody,approvals:approvalsBody,meetings:meetingsBody,automation:automationBody,research:researchBody,maps:mapsBody})[state.section]();
  }
  function open(section,context={}){
    if(!SECTIONS[section])section='features';
    if(!active)returnFocus=document.activeElement;
    active=true;state.section=section;state.context=context||{};state.query=typeof context.query==='string'?context.query:'';state.filter='all';state.detail=null;
    if(section==='tasks'&&context.status)state.filter=context.status;
    if(section==='people'&&context.team)state.filter=context.team;
    if(section==='features'&&context.featureId&&features.some(f=>f.id===context.featureId))state.detail={type:'feature',id:context.featureId};
    if(section==='people'&&context.profileId&&profiles.some(p=>p.id===context.profileId))state.detail={type:'person',id:context.profileId};
    if(section==='memory'&&['all','long','short','growth'].includes(context.type))state.memory=context.type;
    host.hidden=false; render(); host.querySelector('.ws-panel').focus();
    host.dispatchEvent(new CustomEvent('workspace-open',{bubbles:true,detail:{section}}));
  }
  function close(){active=false;host.hidden=true;host.innerHTML='';returnFocus?.focus?.();host.dispatchEvent(new CustomEvent('workspace-close',{bubbles:true}));}
  function click(event){
    if(event.target===host)return close();
    const target=event.target.closest('[data-action]');if(!target||!host.contains(target))return;
    const {action,value}=target.dataset;
    if(action==='close')return close();
    if(action==='open-worlds'){close();return onNavigate('maps');}
    if(action==='section')return onNavigate(value);
    if(action==='view')state.view=value;
    if(action==='back')state.detail=null;
    if(action==='card')state.detail={type:'card',index:Number(value)};
    if(action==='person')state.detail={type:'person',id:value};
    if(action==='person-from-card')return onNavigate('people',{profileId:value});
    if(action==='memory-type')state.memory=value;
    if(action==='pin'){state.pinned.has(value)?state.pinned.delete(value):state.pinned.add(value);notify('이 미리보기에서만 고정 상태를 바꿨습니다.');}
    if(action==='skill')state.detail={type:'skill',id:value};
    if(action==='connection')state.detail={type:'connection',index:Number(value)};
    if(action==='business-rule')state.detail={type:'business'};
    if(action==='budget-note'){const note=host.querySelector('[data-budget]')?.value.trim();notify(note?'예산 메모를 화면에서 확인했습니다. 비용 설정은 변경하지 않았습니다.':'예산 메모를 먼저 입력해 주세요.');return;}
    if(action==='channel')state.detail={type:'channel',index:Number(value)};
    if(action==='artifact')state.detail={type:'artifact',index:Number(value)};
    if(action==='review'){state.review=value||null;notify('예시의 표시 상태만 변경했습니다. 실제 승인 요청은 전송하지 않았습니다.');}
    if(action==='routine')state.routine=!state.routine;
    if(action==='meeting'){state.meetingTopic=host.querySelector('[data-meeting-topic]')?.value||state.meetingTopic;state.meeting=!state.meeting;}
    if(action==='research-tab')state.researchTab=value;
    if(action==='desk-preset')state.deskPreset=value;
    if(action==='appearance'){const split=value.lastIndexOf(':');state.appearance[value.slice(0,split)]=value.slice(split+1);}
    if(action==='config'){state.configDraft=host.querySelector('[data-config]')?.value||'';notify('이 화면의 메모에만 적용했습니다. 회사 설정은 변경하지 않았습니다.');}
    if(action==='feature')state.detail={type:'feature',id:value};
    if(action==='filter-feature'){open('features');state.query=value;}
    render();
    if(['card','person','skill','feature','person-from-card','back'].includes(action)){host.querySelector('.ws-panel').focus();host.querySelector('.ws-content').scrollTop=0;}
    else { [...host.querySelectorAll('[data-action]')].find(el=>el.dataset.action===action&&el.dataset.value===value)?.focus(); }
  }
  function input(event){if(event.target.matches('[data-search]')){state.query=event.target.value;render();}}
  function change(event){if(event.target.matches('[data-filter]')){state.filter=event.target.value;state.detail=null;render();host.querySelector('[data-filter]')?.focus();}}
  function key(event){if(!active)return;if(event.key==='Escape'){event.preventDefault();event.stopPropagation();close();return;}if(event.key==='Tab'){
    const items=[...host.querySelectorAll('button,input,select,textarea,[tabindex="0"]')].filter(e=>!e.disabled&&e.getClientRects().length);if(!items.length)return;
    const first=items[0],last=items[items.length-1];if(event.shiftKey&&(document.activeElement===first||document.activeElement===host.querySelector('.ws-panel'))){event.preventDefault();last.focus();}else if(!event.shiftKey&&(document.activeElement===last||!host.contains(document.activeElement))){event.preventDefault();first.focus();}
  }}
  host.addEventListener('click',click);host.addEventListener('input',input);host.addEventListener('change',change);host.addEventListener('keydown',key);
  return {open,close,destroy(){close();host.removeEventListener('click',click);host.removeEventListener('input',input);host.removeEventListener('change',change);host.removeEventListener('keydown',key);host.classList.remove('ws-host');}};
}
