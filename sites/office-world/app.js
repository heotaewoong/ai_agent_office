/* HeoBrain 오피스 월드 — 콘텐츠 공정 투영을 5개 분야별 팀 공간으로 보여준다.
   모듈: data(읽기·폴링) · world(장면) · hud(오버레이) · controls(입력·카메라). 모두 space 하나를 공유한다. */
(() => {
  'use strict';

  const $ = (id) => document.getElementById(id);
  const SYSTEM_REDUCED = window.matchMedia('(prefers-reduced-motion: reduce)').matches;
  let REDUCED = SYSTEM_REDUCED;
  try { REDUCED ||= localStorage.getItem('heobrain.reduced-motion.v1') === 'true'; } catch (_) { /* 세션 설정 사용 */ }
  const isPhone = () => window.innerWidth <= 720;
  const B = window.BABYLON;
  // ?quality=low 이면 그림자·SSAO·블룸을 끈다(저사양 PC·휴대폰)
  const qualityQuery = new URLSearchParams(location.search).get('quality');
  let savedQuality = null;
  try { savedQuality = localStorage.getItem('heobrain.world-quality.v1'); } catch (_) { /* 기본 화질 사용 */ }
  const QUALITY = [qualityQuery, savedQuality].find(v => ['low', 'high'].includes(v)) || (isPhone() ? 'low' : 'high');

  const notice = (title, text) => {
    $('notice-title').textContent = title;
    $('notice-text').textContent = text;
    $('notice').hidden = false;
  };

  if (!B) {
    notice('3D 라이브러리를 불러오지 못했습니다', '같은 폴더의 vendor/babylon.min.js를 읽지 못했습니다. 페이지를 새로 열거나 파일 구성을 확인해 주세요.');
    return;
  }

  // ======================================================================
  // 공유 상태
  // ======================================================================
  const actionTimers = new Map();
  const space = {
    data: null,            // 정규화된 투영
    stages: [],            // 배치 정보가 붙은 단계 목록
    agents: [],            // 아바타가 붙은 동료 목록
    layer: 'office',      // office=y0 공중 팀 대지, meadow=약 -85m 지상
    view: 'overview',      // 'overview' | 'walk'
    rosterOpen: false,
    buildingOpen: false,
    resultsOpen: false,
    selectedStage: null,
    embedFocus: null,
    embedResult: null,
    pendingActions: new Set(),
  };

  const PALETTE = ['#f2a444', '#4f8df7', '#8b6cf0', '#e65fb8', '#2ec4a6', '#ff7a59', '#59c3ff'];
  const HUB_R = 7;           // 허브 광장 반지름(m)
  const ISLAND_DIST = 23;    // 허브 중심에서 섬 중심까지(다리 길이 약 8m)
  const ISLAND_W = 18;       // 섬 너비(x)
  const ISLAND_D = 16;       // 섬 깊이(z)
  const BRIDGE_W = 2.6;

  // 탐험 XP는 공간을 둘러본 기록이며, 업무 성과나 실제 에이전트 완료를 뜻하지 않는다.
  const explored = new Set();
  const explorationNames = new Map([['hub', '공유 기억 살펴보기']]);
  try {
    const saved = JSON.parse(localStorage.getItem('heobrain.exploration.v1') || '[]');
    if (Array.isArray(saved)) saved.filter((v) => typeof v === 'string').slice(0, 50).forEach((v) => explored.add(v));
  } catch (_) { /* 저장할 수 없는 환경에서도 탐험은 계속한다. */ }
  function exploration(id) {
    if (id) {
      explored.add(id);
      try { localStorage.setItem('heobrain.exploration.v1', JSON.stringify([...explored])); } catch (_) { /* 세션 동안 유지 */ }
    }
    const total = explorationNames.size;
    const done = [...explorationNames.keys()].filter((key) => explored.has(key)).length;
    $('explore-count').textContent = `${done * 20} XP · ${done}/${total}`;
    $('explore-progress').max = total; $('explore-progress').value = done;
    $('explore-list').replaceChildren(...[...explorationNames].map(([key, label]) => {
      const li = document.createElement('li');
      li.textContent = `${explored.has(key) ? '✓' : '○'} ${label}`;
      li.className = explored.has(key) ? 'explored' : '';
      return li;
    }));
  }


  // ======================================================================
  // data — 투영 읽기와 폴링
  // ======================================================================
  const data = {
    apiUrl: null,
    source: 'sample',
    error: null,
    timer: null,
    listeners: [],
    loading: false,
    requestId: 0,
    controller: null,

    init() {
      const q = new URLSearchParams(location.search).get('api');
      this.apiUrl = q || window.OFFICE_WORLD_API || null;
    },

    onChange(fn) { this.listeners.push(fn); },

    async fetchJson(url) {
      const controller = new AbortController();
      this.controller = controller;
      let onAbort;
      const aborted = new Promise((_, reject) => {
        onAbort = () => reject(new Error('조회 시간이 초과되었거나 새 조회로 바뀌었습니다'));
        controller.signal.addEventListener('abort', onAbort, { once: true });
      });
      const timeout = setTimeout(() => controller.abort(), 12000);
      try {
        return await Promise.race([aborted, (async () => {
          const res = await fetch(url, { cache: 'no-store', headers: { Accept: 'application/json' }, signal: controller.signal });
          if (!res.ok) throw new Error(`HTTP ${res.status}`);
          return await res.json();
        })()]);
      } catch (error) {
        if (controller.signal.aborted) throw new Error('조회 시간이 초과되었거나 새 조회로 바뀌었습니다');
        throw error;
      } finally {
        clearTimeout(timeout);
        controller.signal.removeEventListener('abort', onAbort);
        if (this.controller === controller) this.controller = null;
      }
    },

    async load(initial, force = false) {
      if (this.loading && !force) return false;
      const requestId = ++this.requestId;
      this.controller?.abort();
      this.loading = true;
      try {
        let raw = null, source = this.source;
        if (this.apiUrl) {
          try {
            raw = await this.fetchJson(this.apiUrl);
            if (requestId !== this.requestId) return false;
            source = 'live';
            this.error = null;
          } catch (err) {
            if (requestId !== this.requestId) return false;
            this.error = `실시간 읽기 실패: ${err.message}`;
            if (!initial) { this.emit(null); return false; }
          }
        }
        if (!raw) {
          try {
            raw = await this.fetchJson('data/space.json');
            if (requestId !== this.requestId) return false;
            source = this.apiUrl ? 'sample-fallback' : 'sample';
          } catch (err) {
            if (requestId !== this.requestId) return false;
            notice('투영 데이터를 읽을 수 없습니다', `data/space.json 을 불러오지 못했습니다 (${err.message}). 파일을 직접 열지 말고 정적 서버로 여세요. 예: python -m http.server 8080`);
            return false;
          }
        }
        if (requestId !== this.requestId) return false;
        let normalized;
        try { normalized = this.normalize(raw); }
        catch (_) {
          this.error = '투영 데이터 형식을 확인하지 못했습니다';
          if (initial) notice('투영 데이터를 읽을 수 없습니다', '원본 데이터 형식을 확인하지 못했습니다. 연결되면 자동으로 다시 조회합니다.');
          this.emit(null);
          return false;
        }
        this.source = source;
        this.emit(normalized);
        $('notice').hidden = true;
        return true;
      } finally {
        if (requestId === this.requestId) this.loading = false;
      }
    },

    normalize(raw) {
      const out = {
        version: raw.version || 1,
        generatedAt: raw.generatedAt || null,
        office: Object.assign({ name: '콘텐츠 오피스', url: '' }, raw.office || {}),
        brain: Object.assign({ name: '공유 기억', notes: 0, sources: 0, label: '' }, raw.brain || {}),
        stages: [],
        agents: [],
        events: Array.isArray(raw.events) ? raw.events.slice(0, 40) : [],
        flows: Array.isArray(raw.flows) ? raw.flows : [],
        dev: raw.dev && raw.dev.version === 1 ? raw.dev : null,
      };
      const seen = new Set();
      (raw.stages || []).forEach((s, i) => {
        if (!s || !s.id || seen.has(s.id)) return;
        seen.add(s.id);
        out.stages.push({
          id: String(s.id),
          name: s.name || s.id,
          approval: s.approval || '',
          color: /^#[0-9a-f]{6}$/i.test(s.color || '') ? s.color : PALETTE[i % PALETTE.length],
          url: s.url || '',
          view: typeof s.view === 'string' ? s.view : '',
          items: (s.items || []).map((it) => ({
            id: String(it.id || ''),
            title: it.title || '(제목 없음)',
            state: it.state || 'info',
            stateLabel: it.stateLabel || it.state || '',
            needsHuman: !!it.needsHuman,
            agentId: it.agentId || null,
            view: it.view || s.view || '',
            actions: Array.isArray(it.actions) ? it.actions.filter((a) => a && typeof a.id === 'string' && typeof a.label === 'string').map((a) => ({ id: a.id, label: a.label })) : [],
          })),
        });
      });
      if (!out.stages.length) {
        out.stages.push({ id: 'empty', name: '빈 섬', approval: '', color: PALETTE[0], url: '', items: [] });
      }
      const stageIds = new Set(out.stages.map((s) => s.id));
      const statuses = new Set(['running', 'idle', 'waiting', 'error']);
      (raw.agents || []).forEach((a) => {
        if (!a || !a.id) return;
        out.agents.push({
          id: String(a.id),
          name: a.name || a.id,
          engine: a.engine || '',
          model: a.model || '',
          stageId: stageIds.has(a.stageId) ? a.stageId : out.stages[0].id,
          status: statuses.has(a.status) ? a.status : 'unknown',
          task: a.task || '',
        });
      });
      return out;
    },

    emit(normalized) {
      this.listeners.forEach((fn) => fn(normalized, this));
    },

    startPolling() {
      if (!this.apiUrl || this.timer) return;
      this.timer = setInterval(() => { if (!document.hidden) this.load(false); }, 10000);
      document.addEventListener('visibilitychange', () => { if (!document.hidden) this.load(false, true); });
    },
  };

  // 기존 공간 ID는 지리 탐험 기록을 보존하고, 팀과 콘텐츠 공정은 별도로 투영한다.
  const organization = {
    // 개발 팀: GitHub 검증 → 서버 배포 → 확인. 서버의 /api/space가 dev 상태를 줄 때만 연결된 팀으로 바뀐다.
    devTeam(dev) {
      const w = dev.watcher;
      const ci = w && w.ci ? w.ci.state : null;
      const ciLabel = { success:'통과', pending:'진행 중', failure:'실패', unknown:'확인 불가' }[ci] || '기록 없음';
      const when = (iso) => { const t = new Date(iso); return Number.isNaN(t.getTime()) ? '' : t.toLocaleString('ko-KR', { hour12:false, month:'numeric', day:'numeric', hour:'2-digit', minute:'2-digit' }); };
      const toggle = dev.enabled ? { id:'auto-deploy-off', label:'자동 배포 끄기' } : { id:'auto-deploy-on', label:'자동 배포 켜기' };
      const attention = new Set(['needs_dependencies', 'emergency_stop', 'failed']);
      const items = [
        { id:'dev-auto', title: dev.enabled ? '자동 배포 켜짐' : '자동 배포 꺼짐',
          state: dev.enabled ? 'running' : 'info',
          stateLabel: dev.enabled ? 'GitHub 검증을 통과한 main 커밋만 서버에 올립니다' : '검증 결과만 기록하고 서버에는 올리지 않습니다',
          needsHuman:false, actions:[toggle] },
        { id:'dev-main', title: w ? `main ${String(w.origin || '').slice(0, 10)}` : '서버 감시기 설치 전',
          state: ci === 'failure' ? 'failed' : ci === 'pending' ? 'research' : 'info',
          stateLabel: w ? `GitHub 검증 ${ciLabel} · ${w.label || ''}${w.reason ? ' · ' + w.reason : ''}` : '자동 배포 감시기가 아직 한 번도 돌지 않았어요',
          needsHuman: !!(w && attention.has(w.decision)), actions:[] },
        { id:'dev-running', title: dev.running.commit ? `서버 운영 버전 ${dev.running.commit}` : '서버 운영 버전 확인 불가',
          state:'info', stateLabel: `${dev.running.deployed_at ? when(dev.running.deployed_at) + ' 배포 · ' : ''}${dev.running.ci_verified ? 'GitHub에서 검증한 커밋' : '서버에서 검증한 커밋'}`,
          needsHuman:false, actions:[] },
        ...(dev.deployments || []).slice(0, 4).map(r => ({ id:'dev-deploy-' + r.id, title:`배포 ${r.commit}`,
          state: r.status === 'deployed' || r.transient ? 'info' : 'failed',
          stateLabel:`${r.label}${r.ci_verified ? ' · GitHub 검증' : ''} · ${r.id.slice(4, 6)}/${r.id.slice(6, 8)} ${r.id.slice(9, 11)}:${r.id.slice(11, 13)} UTC`,
          needsHuman:false, actions:[] })),
      ];
      return { connection:'dev', items, approval: dev.enabled ? '검증 → 배포 → 확인 자동 진행' : '검증 → 배포 → 확인 · 자동 배포 꺼짐' };
    },

    project(d) {
      const legacy = ['inbox', 'scripts', 'creative', 'outbox', 'ops'];
      if (d.organizationVersion === 1 || d.stages.length !== 5 || !legacy.every(id => d.stages.some(st => st.id === id))) return d;
      const teams = [
        { id:'inbox', teamId:'life', name:'생활 비서 팀', color:'#f2a444', connection:'planned',
          description:'네이버·Gmail의 AI Engineer 채용공고 요약과 답변할 메일 분류',
          goals:['채용공고의 직무·요건·마감일 요약', '내가 답변해야 할 메일 분류'], approval:'메일 연결 준비' },
        { id:'scripts', teamId:'content', name:'콘텐츠 자동화 팀', color:'#4f8df7', connection:'content',
          description:'기존 콘텐츠 파이프라인의 원문·제작·검수·출고 준비',
          goals:['블로그·영상·PPT·카드뉴스·HeoBrain.kr 상세페이지', '채널별 비공개·임시저장까지 준비하되 실제 연결 상태 구분'], approval:'기존 콘텐츠 공정 · 승인 ⓪①②③' },
        { id:'creative', teamId:'dev', name:'개발 팀', color:'#8b6cf0', connection:'planned',
          description:'기존 서비스 개선부터 전체 프로젝트 관리와 새 서비스 개발까지',
          goals:['HeoBrain.kr·AI 오피스 유지보수와 테스트', '전체 개발 프로젝트 관리', '새 아이디어를 서비스로 구현'], approval:'개발 업무 연결 준비' },
        { id:'outbox', teamId:'wiki', name:'옵시디언 팀', color:'#3ecfb2', connection:'planned',
          description:'모든 팀의 결과·결정을 정리하는 공용 위키',
          goals:['팀별 결과·결정·출처를 연결', '대화 보존·자료 수집·검색은 상세 범위 설계 중'], approval:'위키 연결 준비' },
        { id:'ops', teamId:'stocks', name:'주식 팀', color:'#e2c15a', connection:'undecided',
          description:'내 포트폴리오를 바탕으로 할 일을 정할 예정',
          goals:['포트폴리오 활용 방향과 기능은 아직 미정'], approval:'기능 기획 중' },
      ];
      const workflowStages = d.stages;
      const stages = workflowStages.map(st => ({ ...teams.find(team => team.id === st.id), url:'', view:'', items:[], workflowStages:[] }));
      const devTeam = stages.find(team => team.teamId === 'dev');
      if (d.dev) Object.assign(devTeam, organization.devTeam(d.dev));
      const content = stages.find(team => team.teamId === 'content');
      const studio = workflowStages.find(st => st.id === 'scripts');
      content.url = studio.url;
      content.view = studio.view;
      content.workflowStages = workflowStages;
      content.workflowFlows = d.flows;
      content.items = workflowStages.flatMap(st => st.items.map(it => ({ ...it, workflowStageId:st.id, workflowStageName:st.name })));
      return { ...d, organizationVersion:1, office:{ ...d.office, name:'HeoBrain AI 오피스' }, stages,
        agents:d.agents.map(a => ({ ...a, teamId:'content', workflowStageId:a.stageId, stageId:'scripts' })),
        events:d.events.map(ev => ({ ...ev, workflowStageId:ev.stageId, stageId:'scripts' })),
        workflowFlows:d.flows, flows:[] };
    },
  };

  // ======================================================================
  // world — 장면
  // ======================================================================
  const world = {
    engine: null, scene: null, canvas: null, glow: null,
    hub: { rings: [], core: null },
    sky: null,
    flows: [],          // { mesh, bridge, t, speed }
    flowKeys: new Set(),
    matCache: new Map(),
    time: 0,

    mat(key, hex, opts = {}) {
      const k = `${key}:${hex}:${opts.emissive || 0}:${opts.alpha || 1}`;
      if (this.matCache.has(k)) return this.matCache.get(k);
      const m = new B.StandardMaterial(k, this.scene);
      const c = B.Color3.FromHexString(hex);
      m.diffuseColor = opts.emissive ? c.scale(0.2) : c;
      m.specularColor = new B.Color3(0.05, 0.05, 0.08);
      if (opts.emissive) m.emissiveColor = c.scale(opts.emissive);
      if (opts.alpha !== undefined) m.alpha = opts.alpha;
      if (opts.unlit) m.disableLighting = true;
      this.matCache.set(k, m);
      return m;
    },


    // 건축에만 PBR을 사용한다. 아바타/업무 마커의 StandardMaterial 계약은 그대로 둔다.
    pbr(key, hex, metallic = 0, roughness = .6, surface = '') {
      const id=`pbr:${key}:${hex}:${metallic}:${roughness}:${surface}`;
      if(this.matCache.has(id))return this.matCache.get(id);
      const m=new B.PBRMaterial(id,this.scene);m.albedoColor=B.Color3.FromHexString(hex);
      m.metallic=metallic;m.roughness=roughness;m.environmentIntensity=QUALITY==='low'?.55:.8;
      m.directIntensity=1;m.specularIntensity=.7;
      if(surface){
        this.surfaceTextures ||= new Map();
        if(!this.surfaceTextures.has(surface)){
          const size=64,rgba=new Uint8Array(size*size*4);let seed=71;
          for(let y=0;y<size;y++)for(let x=0;x<size;x++){
            seed=seed*16807%2147483647;const grain=(seed/2147483647-.5)*(surface==='metal'?4:10),v=Math.round(248+grain+(surface==='metal'?Math.sin(y*.8)*2:0)),i=(y*size+x)*4;
            rgba.set([v,v,v,255],i);
          }
          const t=B.RawTexture.CreateRGBATexture(rgba,size,size,this.scene,true,false,B.Texture.TRILINEAR_SAMPLINGMODE);
          t.wrapU=t.wrapV=B.Texture.WRAP_ADDRESSMODE;t.uScale=t.vScale=surface==='stone'?5:3;t.anisotropicFilteringLevel=QUALITY==='low'?1:4;
          this.surfaceTextures.set(surface,t);
        }
        m.albedoTexture=this.surfaceTextures.get(surface);
      }
      this.matCache.set(id,m);return m;
    },

    buildReflectionEnvironment() {
      // 자체 생성된 작은 스튜디오 큐브맵: 외부 HDR/사진/네트워크 요청을 사용하지 않는다.
      const size=QUALITY==='low'?32:64,faces=[];
      for(let face=0;face<6;face++){
        const data=new Uint8Array(size*size*4);
        for(let y=0;y<size;y++)for(let x=0;x<size;x++){
          const t=y/(size-1),sky=face===2?1:face===3?0:1-t;
          const strip=face!==3&&x>size*.36&&x<size*.47&&y<size*.78?26:0;
          const i=(y*size+x)*4;
          data.set([Math.round(27+sky*98+strip),Math.round(42+sky*112+strip),Math.round(56+sky*126+strip),255],i);
        }
        faces.push(data);
      }
      const env=new B.RawCubeTexture(this.scene,faces,size,B.Engine.TEXTUREFORMAT_RGBA,B.Engine.TEXTURETYPE_UNSIGNED_BYTE,true,false,B.Texture.TRILINEAR_SAMPLINGMODE);
      env.name='procedural-studio-environment';this.scene.environmentTexture=env;
      this.scene.environmentIntensity=.75;
    },

    deckSurfaceMaterial() {
      const m=this.pbr('team-paved-surface','#b6c8d2',.12,.76);
      const layout=space.stages.map(st=>st.id+':'+st.angle).join('|');
      if(this.deckTexture&&this.deckStageKey===layout){m.albedoTexture=this.deckTexture;return m;}
      if(this.deckTexture)this.deckTexture.dispose();
      this.deckStageKey=layout;
      const size=QUALITY==='low'?512:1024,texture=new B.DynamicTexture('team-paving-plan',{width:size,height:size},this.scene,true),c=texture.getContext(),h=size/2,k=size/136;
      c.fillStyle='#708a9d';c.fillRect(0,0,size,size);
      c.fillStyle='#a8bdcc';c.beginPath();c.arc(h,h,35*k,0,Math.PI*2);c.fill();
      // 포장은 한 표면의 그림이다. 겹친 평면이나 발광 격자를 만들지 않는다.
      c.strokeStyle='#536f84';c.lineWidth=2.7*k;c.beginPath();c.arc(h,h,43*k,0,Math.PI*2);c.stroke();
      c.strokeStyle='#aec8d2';c.lineWidth=.18*k;c.beginPath();c.arc(h,h,44.8*k,0,Math.PI*2);c.stroke();
      space.stages.forEach(st=>{
        c.strokeStyle='#48677f';c.lineWidth=3.6*k;c.beginPath();c.moveTo(h+Math.cos(st.angle)*8*k,h+Math.sin(st.angle)*8*k);c.lineTo(h+Math.cos(st.angle)*64*k,h+Math.sin(st.angle)*64*k);c.stroke();
        c.strokeStyle='#9db7c6';c.lineWidth=.2*k;c.stroke();
      });
      for(let i=0;i<12;i++){
        const a=i*Math.PI/6,x=h+Math.cos(a)*57*k,y=h+Math.sin(a)*57*k;
        c.beginPath();for(let j=0;j<6;j++){const b=j*Math.PI/3;const px=x+Math.cos(b)*5.8*k,py=y+Math.sin(b)*5.8*k;if(j)c.lineTo(px,py);else c.moveTo(px,py);}c.closePath();
        c.fillStyle=i%3?'#8aa4b7':'#506d85';c.fill();c.strokeStyle='#a5bcca';c.lineWidth=.16*k;c.stroke();
      }
      texture.update();texture.anisotropicFilteringLevel=QUALITY==='low'?1:4;m.albedoTexture=texture;this.deckTexture=texture;return m;
    },

    // 그림자: 드리우는 쪽과 받는 쪽
    castShadow(mesh) { if (this.shadows) this.shadows.addShadowCaster(mesh, false); },
    receiveShadow(mesh) { if (this.shadows) (mesh.sourceMesh || mesh).receiveShadows = true; },

    // ---------------- 픽셀 텍스처 (코드로 그린 16×16 블록 질감) ----------------
    pixelTexture(name, tiles, paint) {
      // tiles: 가로로 이어 붙일 타일 수. paint(x, y, tile, rnd) → [r,g,b]
      const S = 16, W = S * tiles, data = new Uint8Array(W * S * 4);
      let seed = name.length * 7919 + 13;
      const rnd = () => { seed = (seed * 48271) % 2147483647; return seed / 2147483647; };
      for (let t = 0; t < tiles; t++) for (let y = 0; y < S; y++) for (let x = 0; x < S; x++) {
        const [r, g, b] = paint(x, y, t, rnd);
        const i = (y * W + t * S + x) * 4; // 행 0이 아래(v=0), 행 15가 위(v=1)
        data[i] = r; data[i + 1] = g; data[i + 2] = b; data[i + 3] = 255;
      }
      const tex = B.RawTexture.CreateRGBATexture(data, W, S, this.scene, false, false, B.Texture.NEAREST_SAMPLINGMODE);
      tex.wrapU = B.Texture.WRAP_ADDRESSMODE; tex.wrapV = B.Texture.WRAP_ADDRESSMODE;
      return tex;
    },

    blockTextures() {
      if (this.blockTex) return this.blockTex;
      const mix = (c, d) => [Math.max(0, Math.min(255, c[0] + d)), Math.max(0, Math.min(255, c[1] + d)), Math.max(0, Math.min(255, c[2] + d))];
      const GRASS = [96, 196, 92], DIRT = [134, 98, 62], STONE = [118, 124, 150], PATH = [182, 190, 214], PLANK = [96, 72, 52], LEAF = [62, 158, 78], TRUNK = [88, 60, 38];
      const noise = (c, rnd, amp) => mix(c, Math.floor((rnd() - 0.5) * amp));
      const grassSide = (x, y, rnd) => {
        const edge = 3 + Math.floor(rnd() * 2);
        if (y >= 16 - edge) return noise(GRASS, rnd, 26);
        return noise(DIRT, rnd, 30);
      };
      const T = {
        // 잔디 블록: 타일 0 윗면, 1 옆면, 2 아랫면(흙)
        grass: this.pixelTexture('grass', 3, (x, y, t, rnd) => t === 0 ? (rnd() < 0.08 ? mix(GRASS, 28) : noise(GRASS, rnd, 30)) : t === 1 ? grassSide(x, y, rnd) : noise(DIRT, rnd, 30)),
        dirt: this.pixelTexture('dirt', 1, (x, y, t, rnd) => rnd() < 0.1 ? mix(DIRT, -34) : noise(DIRT, rnd, 30)),
        stone: this.pixelTexture('stone', 1, (x, y, t, rnd) => ((x + y * 3) % 11 === 0 && rnd() < 0.6) ? mix(STONE, -40) : noise(STONE, rnd, 26)),
        path: this.pixelTexture('path', 1, (x, y, t, rnd) => (x % 8 === 0 || y % 8 === 0 || (x % 8 === 4 && y % 8 < 4)) ? mix(PATH, -48) : noise(PATH, rnd, 18)),
        planks: this.pixelTexture('planks', 1, (x, y, t, rnd) => (y % 4 === 0) ? mix(PLANK, -36) : (x === (y < 8 ? 3 : 11) ? mix(PLANK, -28) : noise(PLANK, rnd, 22))),
        leaves: this.pixelTexture('leaves', 1, (x, y, t, rnd) => rnd() < 0.12 ? mix(LEAF, -46) : noise(LEAF, rnd, 34)),
        // 통나무: 타일 0 옆면(세로 결), 1 윗면(나이테)
        trunk: this.pixelTexture('trunk', 2, (x, y, t, rnd) => t === 0 ? (x % 4 === 0 ? mix(TRUNK, -30) : noise(TRUNK, rnd, 20)) : (Math.hypot(x - 7.5, y - 7.5) % 3 < 1 ? mix(TRUNK, 26) : noise(TRUNK, rnd, 18))),
      };
      this.blockTex = T;
      return T;
    },

    blockMaterial(name, tex) {
      const m = new B.StandardMaterial(`blk-${name}-mat`, this.scene);
      m.diffuseTexture = tex;
      m.specularColor = new B.Color3(0.02, 0.02, 0.03);
      return m;
    },

    // 면별 타일 지정 박스: faces [back, front, right, left, top, bottom] 각각 타일 번호
    blockMesh(name, tex, tiles, faceTiles) {
      const uv = faceTiles.map((t) => new B.Vector4(t / tiles, 0, (t + 1) / tiles, 1));
      const m = B.MeshBuilder.CreateBox(name, { size: 1, faceUV: uv, wrap: true }, this.scene);
      m.material = this.blockMaterial(name, tex);
      m.isPickable = false;
      return m;
    },

    box(name, w, h, d, hex, opts = {}) {
      const mesh = B.MeshBuilder.CreateBox(name, { width: w, height: h, depth: d }, this.scene);
      mesh.material = this.mat('box', hex, opts);
      return mesh;
    },

    init(canvas) {
      this.canvas = canvas;
      this.engine = new B.Engine(canvas, true, { preserveDrawingBuffer: false, stencil: false, antialias: true });
      // 저사양은 CSS 픽셀당 1픽셀, 고화질은 최대 2픽셀로 GPU 작업량을 제한한다.
      const applyDpr = () => this.engine.setHardwareScalingLevel(this.renderScale(window.devicePixelRatio));
      applyDpr();
      const scene = new B.Scene(this.engine);
      this.scene = scene;
      // Hover has no mesh action; clicks and workshop ray picking remain enabled.
      scene.skipPointerMovePicking = true;
      this.applyDpr = applyDpr;
      scene.clearColor = new B.Color4(0.02, 0.03, 0.09, 1);
      scene.ambientColor = new B.Color3(0.31, 0.36, 0.46);
      scene.fogMode = B.Scene.FOGMODE_EXP2;
      scene.fogDensity = 0.00135;
      scene.fogColor = new B.Color3(0.12, 0.21, 0.32);

      const hemi = new B.HemisphericLight('hemi', new B.Vector3(0.2, 1, 0.1), scene);
      hemi.intensity = 0.85;
      hemi.groundColor = new B.Color3(0.12, 0.14, 0.3);
      const sun = new B.DirectionalLight('sun', new B.Vector3(-0.5, -1, 0.35), scene);
      sun.intensity = 1.15;
      sun.diffuse = new B.Color3(1, 0.94, 0.84);
      const fill=new B.HemisphericLight('city-cool-fill',new B.Vector3(-.7,.5,-.3),scene);fill.diffuse=new B.Color3(.54,.75,1);fill.intensity=.16;
      sun.position = new B.Vector3(45, 90, -32);
      sun.shadowMinZ = 20; sun.shadowMaxZ = 220;
      sun.shadowFrustumSize = 125;
      this.sun = sun;

      if (QUALITY !== 'low') {
        // 방향광 그림자: PCF 필터, 블록 면의 줄무늬(acne) 방지 바이어스
        this.shadows = new B.ShadowGenerator(2048, sun);
        this.shadows.usePercentageCloserFiltering = true;
        this.shadows.filteringQuality = B.ShadowGenerator.QUALITY_MEDIUM;
        this.shadows.bias = 0.0012;
        this.shadows.normalBias = 0.035;
        this.shadows.darkness = 0.35;
      }

      this.buildReflectionEnvironment();
      this.buildSky();
      this.buildCosmos();
      this.buildMeadow();
      this.buildGroundCity();
      this.buildTraffic();
      this.buildHub();

      scene.onBeforeRenderObservable.add(() => this.tick());
      window.addEventListener('resize', () => { this.applyDpr(); this.engine.resize(); });
      this.renderFrame = () => scene.render();
      this.renderPaused = true;
      document.addEventListener('visibilitychange', () => this.syncRendering());
      this.syncRendering();
    },

    renderScale(dpr) {
      const density = Number.isFinite(dpr) && dpr > 0 ? dpr : 1;
      return 1 / Math.min(QUALITY === 'low' ? 1 : 2, Math.max(1, density));
    },

    syncMotionUI() {
      const button = $('btn-traffic');
      button.disabled = REDUCED;
      button.textContent = REDUCED ? '동작 줄이기 · 교통 정지' : this.trafficPaused ? '교통 연출 재생' : '교통 연출 멈춤';
      button.setAttribute('aria-pressed', String(REDUCED || this.trafficPaused));
    },

    syncRendering() {
      const paused = document.hidden || space.rosterOpen || space.resultsOpen;
      if (!this.renderFrame || this.renderPaused === paused) return;
      this.renderPaused = paused;
      if (paused) this.engine.stopRenderLoop(this.renderFrame);
      else { this.engine.resize(); this.engine.runRenderLoop(this.renderFrame); }
    },

    buildSky() {
      const size = 1024;
      const tex = new B.DynamicTexture('sky', { width: size * 2, height: size }, this.scene, false);
      const ctx = tex.getContext();
      const dusk = ctx.createLinearGradient(0, 0, 0, size);
      dusk.addColorStop(0, '#060a20'); dusk.addColorStop(0.45, '#172d58'); dusk.addColorStop(0.7, '#3d6378'); dusk.addColorStop(1, '#0b1429');
      ctx.fillStyle = dusk;
      ctx.fillRect(0, 0, size * 2, size);
      const blobs = [
        [300, 420, 560, 'rgba(100, 58, 220, 0.40)'],
        [1500, 300, 580, 'rgba(36, 190, 180, 0.38)'],
        [1050, 760, 300, 'rgba(180, 70, 140, 0.16)'],
      ];
      blobs.forEach(([x, y, r, color]) => {
        const g = ctx.createRadialGradient(x, y, 0, x, y, r);
        g.addColorStop(0, color);
        g.addColorStop(1, 'rgba(0,0,0,0)');
        ctx.fillStyle = g;
        ctx.fillRect(x - r, y - r, r * 2, r * 2);
      });
      let seed = 7;
      const rnd = () => { seed = (seed * 16807) % 2147483647; return seed / 2147483647; };
      for (let i = 0; i < 2200; i++) {
        const x = rnd() * size * 2;
        const y = rnd() * size;
        const r = rnd() < 0.08 ? 1.8 + rnd() * 1.6 : 0.5 + rnd() * 0.9;
        const a = 0.35 + rnd() * 0.65;
        ctx.fillStyle = rnd() < 0.15 ? `rgba(170, 220, 255, ${a})` : `rgba(255, 250, 235, ${a})`;
        ctx.beginPath();
        ctx.arc(x, y, r, 0, Math.PI * 2);
        ctx.fill();
      }
      tex.update();
      const sky = B.MeshBuilder.CreateSphere('skybox', { diameter: 6000, segments: 24, sideOrientation: B.Mesh.BACKSIDE }, this.scene);
      const m = new B.StandardMaterial('skymat', this.scene);
      m.emissiveTexture = tex;
      m.disableLighting = true;
      m.backFaceCulling = false;
      sky.material = m;
      sky.isPickable = false;
      sky.infiniteDistance = true;
      this.sky = sky;
    },


    // 독자 제작 도형으로 만든 궤도 도시. 정적 도형은 재질별 병합해 draw call을 제한한다.
    buildCosmos() {
      const s = this.scene;
      const groups = new Map();
      const metal = this.pbr('orbital-metal','#b9cbd8',.62,.35,'metal');
      const dark = this.pbr('orbital-dark','#294357',.6,.43,'metal');
      const cyan = this.mat('city-cyan', '#66e4ff', { emissive: 1.7, unlit: true });
      const violet = this.mat('city-violet', '#c894ff', { emissive: 1.2, unlit: true });
      const gold = this.mat('city-gold', '#ffe4a4', { emissive: 1.1, unlit: true });
      const add = (m, mat) => {
        m.material = mat; m.isPickable = false;
        if (!groups.has(mat)) groups.set(mat, []);
        groups.get(mat).push(m);
        return m;
      };
      const block = (name, x, y, z, w, h, d, mat) => {
        const m = B.MeshBuilder.CreateBox(name, { width: w, height: h, depth: d }, s);
        m.position.set(x, y, z); return add(m, mat);
      };
      const ring = (name, x, y, z, diameter, thickness, mat, rx = 0, rz = 0) => {
        const m = B.MeshBuilder.CreateTorus(name, { diameter, thickness, tessellation: QUALITY === 'low' ? 64 : 112 }, s);
        m.position.set(x, y, z); m.rotation.x = rx; m.rotation.z = rz;
        return add(m, mat);
      };
      let seed = 7291;
      const rnd = () => { seed = (seed * 16807) % 2147483647; return seed / 2147483647; };
      // 空中 도시: 여러 높이의 독립 플랫폼과 작은 창문, 첨탑, 광학 레일.
      [[-24, 27, 76, 20], [9, 34, 91, 27], [45, 24, 72, 18]].forEach(([x, y, z, size], city) => {
        const disk = B.MeshBuilder.CreateCylinder(`orbit-deck-${city}`, { height: 1.8, diameterTop: size, diameterBottom: size * 0.67, tessellation: 8 }, s);
        disk.position.set(x, y, z); add(disk, dark);
        ring(`orbit-deck-rim-${city}`, x, y + 0.9, z, size - 0.6, 0.24, cyan);
        for (let i = 0; i < 7; i++) {
          const angle = i * Math.PI * 2 / 7;
          const bx = x + Math.cos(angle) * size * 0.28, bz = z + Math.sin(angle) * size * 0.28;
          const h = 5 + rnd() * 13;
          block(`city-tower-${city}-${i}`, bx, y + h / 2 + 1, bz, 2.5 + rnd(), h, 2.7, i % 3 ? metal : dark);
          block(`city-light-${city}-${i}`, bx, y + h / 2 + 1, bz - 1.4, 0.18, h * 0.8, 0.14, i % 2 ? cyan : violet);
          for (let k = 0; k < 3; k++) block(`city-window-${city}-${i}-${k}`, bx + 0.7, y + 3 + k * 2.5, bz - 1.42, 0.45, 0.6, 0.08, gold);
          const spike = B.MeshBuilder.CreateCylinder(`city-spire-${city}-${i}`, { height: 4, diameterBottom: 1.3, diameterTop: 0, tessellation: 4 }, s);
          spike.position.set(bx, y + h + 3, bz); add(spike, cyan);
        }
        const exhaust = B.MeshBuilder.CreateCylinder(`city-thruster-${city}`, { height: 6, diameterTop: size * 0.35, diameterBottom: 0.2, tessellation: 8 }, s);
        exhaust.position.set(x, y - 3.7, z); add(exhaust, cyan);
      });
      ring('great-orbit-dark', 12, 48, 108, 78, 2.1, dark, 1.18, -0.23);
      ring('great-orbit-light', 12, 48, 108, 79.8, 0.3, cyan, 1.18, -0.23);
      ring('great-orbit-inner', 12, 48, 108, 72, 0.15, violet, 1.18, -0.23);
      // 透視 가능한 공중 도로. 하나의 경로가 이어지는 철도처럼 보인다.
      const rail = B.MeshBuilder.CreateTube('sky-rail', { path: [new B.Vector3(-58, 31, 83), new B.Vector3(-24, 32, 76), new B.Vector3(9, 39, 91), new B.Vector3(45, 29, 72), new B.Vector3(67, 34, 108)], radius: 0.22, tessellation: 6 }, s);
      add(rail, cyan);
      // 별빛 행성: 텍스처나 외부 아트 없이 직접 조형.
      const planet = B.MeshBuilder.CreateSphere('distant-planet', { diameter: 47, segments: 32 }, s);
      planet.position.set(-119, 79, 139); add(planet, this.mat('planet', '#8f8dd4', { emissive: 0.35 }));
      ring('planet-ring-outer', -119, 79, 139, 77, 1.5, this.mat('planet-ring', '#e1bff7', { emissive: 0.7, alpha: 0.65, unlit: true }), 0.3, 0.36);
      ring('planet-ring-inner', -119, 79, 139, 69, 0.8, violet, 0.3, 0.36);
      const moon = B.MeshBuilder.CreateSphere('small-moon', { diameter: 11, segments: 16 }, s);
      moon.position.set(117, 64, 158); add(moon, this.mat('moon', '#d9f2ee', { emissive: 0.65 }));
      // 먼 부유 초원: 낮은 수의 큼직한 복셀을 재질별 병합한다.
      [[-79, 4, 51, 10], [83, 9, 28, 9], [-70, 21, 111, 6], [82, 31, 130, 7]].forEach(([x, y, z, r], i) => {
        for (let dx = -r; dx <= r; dx += 2) for (let dz = -r; dz <= r; dz += 2) {
          if (dx * dx + dz * dz > r * r) continue;
          const depth = 2 + Math.floor((1 - Math.hypot(dx, dz) / r) * 4);
          block(`satellite-soil-${i}`, x + dx, y - depth / 2, z + dz, 2, depth, 2, dark);
          block(`satellite-grass-${i}`, x + dx, y + 0.2, z + dz, 2, 0.4, 2, this.mat('satellite-green', '#63b98d'));
        }
      });
      // 모든 고정 조형은 material별 합친 뒤 원본 geometry를 해제한다.
      groups.forEach((meshes) => {
        const merged = B.Mesh.MergeMeshes(meshes, true, true, undefined, false, false);
        if (merged) { merged.isPickable = false; merged.freezeWorldMatrix(); }
      });
      // 적은 수의 움직이는 비행선. reduced motion에서는 정지한다.
      this.airships = [];
      for (let i = 0; i < (QUALITY === 'low' ? 2 : 4); i++) {
        const root = new B.TransformNode(`shuttle-${i}`, s);
        const hull = B.MeshBuilder.CreateBox(`shuttle-hull-${i}`, { width: 3.8, height: 0.65, depth: 1.1 }, s);
        hull.material = metal; hull.parent = root; hull.isPickable = false;
        const cockpit = B.MeshBuilder.CreateBox(`shuttle-glass-${i}`, { width: 1.7, height: 0.5, depth: 0.85 }, s);
        cockpit.position.set(0.4, 0.45, 0); cockpit.material = cyan; cockpit.parent = root; cockpit.isPickable = false;
        const trail = B.MeshBuilder.CreateBox(`shuttle-trail-${i}`, { width: 3.2, height: 0.15, depth: 0.3 }, s);
        trail.position.x = -3.3; trail.material = violet; trail.parent = root; trail.isPickable = false;
        root.position.set(Math.sin(i*1.65)*65,28+i*5,72+Math.cos(i*1.65)*26);
        this.airships.push({ root, phase: i * 1.65, height: 28 + i * 5 });
      }
      // 오로라는 단일 리본 두 개로 구성하며 실시간 변형을 하지 않는다.
      for (let band = 0; band < (QUALITY === 'low' ? 1 : 2); band++) {
        const lower = [], upper = [];
        for (let i = 0; i <= 36; i++) {
          const x = -170 + i * 10, z = 195 + Math.sin(i * 0.18) * 18;
          const y = 85 + band * 17 + Math.sin(i * 0.35 + band) * 13;
          lower.push(new B.Vector3(x, y, z)); upper.push(new B.Vector3(x, y + 17 + Math.sin(i * 0.21) * 7, z));
        }
        const ribbon = B.MeshBuilder.CreateRibbon(`aurora-${band}`, { pathArray: [lower, upper], sideOrientation: B.Mesh.DOUBLESIDE }, s);
        ribbon.material = this.mat('aurora', band ? '#a88cff' : '#5affd5', { emissive: 0.9, alpha: 0.14, unlit: true }); ribbon.isPickable = false;
      }
    },


    // 지상과 공중 팀 대지는 별개의 높이/충돌층이다. 1,600m 지상은 블록 인스턴스로 구성한다.

    groundRoadHeight(x, z, margin = 0) {
      const dz=z+46,r=Math.hypot(x,dz);let height=null;
      if(r<=19.5+margin)height=-82.625;
      for(const ring of [105,235])if(Math.abs(r-ring)<=12.5+margin)height=Math.max(height??-Infinity,-82.81);
      for(const a of [-Math.PI/2,-Math.PI/6,Math.PI/6,Math.PI/2,Math.PI*5/6,Math.PI*7/6]){
        const along=x*Math.cos(a)+dz*Math.sin(a),side=Math.abs(x*Math.sin(a)-dz*Math.cos(a));
        if(along>=16-margin&&along<=414+margin&&side<=13.5+margin)height=Math.max(height??-Infinity,side<=9?-82.71:-82.82);
      }
      return height;
    },

    meadowHeight(x, z) {
      const cell = this.meadowCell || 8;
      const cx = Math.floor((x + 800) / cell) * cell - 796;
      const cz = Math.floor((z + 800) / cell) * cell - 796;
      if(this.groundRoadHeight(cx,cz,12)!==null)return -83;
      const blend = Math.max(0, Math.min(1, (Math.hypot(cx, cz + 46) - 320) / 180));
      return -83 + Math.floor((2 * Math.sin(cx * 0.008) * Math.cos(cz * 0.009) + Math.sin(cz * 0.014) * 0.8) * blend);
    },

    buildMeadow() {
      const scene = this.scene;
      const T = this.blockTextures();
      const blocks = this.blockMesh('mainland-grass', T.grass, 3, [1, 1, 1, 1, 0, 2]);
      const matrices = [];
      const cell = QUALITY === 'low' ? 16 : 8;
      this.meadowCell = cell;
      for (let x = -800; x < 800; x += cell) for (let z = -800; z < 800; z += cell) {
        const y = this.meadowHeight(x + cell / 2, z + cell / 2);
        matrices.push(B.Matrix.Compose(new B.Vector3(cell, 8, cell), B.Quaternion.Identity(), new B.Vector3(x + cell / 2, y - 4, z + cell / 2)));
      }
      const buffer = new Float32Array(matrices.length * 16);
      matrices.forEach((m, i) => m.copyToArray(buffer, i * 16));
      blocks.thinInstanceSetBuffer('matrix', buffer, 16, true); blocks.freezeWorldMatrix(); blocks.isPickable = false;
      // 지상 끝을 공중섬으로 보이게 하지 않도록 연무 속 지평선까지 육지를 연결한다.
      const horizon = B.MeshBuilder.CreateGround('mainland-horizon', { width: 9000, height: 9000 }, scene);
      horizon.position.y = -91; horizon.material = this.mat('horizon-meadow', '#4b8859'); horizon.isPickable = false;
      // 초원의 숲도 소수의 thin-instance 배치로 표현한다.
      const trunks = this.blockMesh('mainland-trunks', T.trunk, 2, [0, 0, 0, 0, 1, 1]);
      const leaves = this.blockMesh('mainland-leaves', T.leaves, 1, [0, 0, 0, 0, 0, 0]);
      const tb = [], lb = [];
      let seed = 431;
      const rnd = () => { seed = seed * 16807 % 2147483647; return seed / 2147483647; };
      for (let i = 0; i < (QUALITY === 'low' ? 180 : 480); i++) {
        const x = (rnd() - 0.5) * 1500, z = (rnd() - 0.5) * 1500;
        if (Math.hypot(x, z + 46) < 350) continue;
        const y = this.meadowHeight(x, z), h = 4 + rnd() * 4;
        tb.push(B.Matrix.Compose(new B.Vector3(1.2, h, 1.2), B.Quaternion.Identity(), new B.Vector3(x, y + h / 2, z)));
        lb.push(B.Matrix.Compose(new B.Vector3(5, 4, 5), B.Quaternion.Identity(), new B.Vector3(x, y + h, z)));
        lb.push(B.Matrix.Compose(new B.Vector3(3, 2, 3), B.Quaternion.Identity(), new B.Vector3(x, y + h + 3, z)));
      }
      [[trunks, tb], [leaves, lb]].forEach(([mesh, items]) => {
        const b = new Float32Array(items.length * 16); items.forEach((m, i) => m.copyToArray(b, i * 16));
        mesh.thinInstanceSetBuffer('matrix', b, 16, true); mesh.freezeWorldMatrix(); mesh.isPickable = false;
      });
      this.mainland = { width: 1600, base: -85, mesh: blocks };
      this.portals = { office: new B.Vector3(0, 0, -46), meadow: new B.Vector3(0, this.meadowHeight(0, -46), -46) };
      Object.entries(this.portals).forEach(([layer, pos]) => {
        const gate = B.MeshBuilder.CreateTorus(`transfer-gate-${layer}`, { diameter: 5.2, thickness: 0.45, tessellation: 48 }, scene);
        gate.position.copyFrom(pos.add(new B.Vector3(0, 3, 0))); gate.rotation.x = Math.PI / 2;
        gate.material = this.mat('transfer-gate', '#5bf5df', { emissive: 1.5, unlit: true });
        gate.metadata = { portal: layer === 'office' ? 'meadow' : 'office' };
        const base = B.MeshBuilder.CreateCylinder(`transfer-base-${layer}`, { height: 0.3, diameter: 8, tessellation: 8 }, scene);
        base.position.copyFrom(pos); base.material = this.mat('transfer-base', '#2b5470'); base.metadata = gate.metadata;
      });
      const campusRing = B.MeshBuilder.CreateTorus('team-land-rim', { diameter: 137, thickness: 0.5, tessellation: 112 }, scene);
      campusRing.position.y = -3; campusRing.material = this.mat('team-land-rim', '#72e5ff', { emissive: 0.8, unlit: true }); campusRing.isPickable = false;
      const liftBeam = B.MeshBuilder.CreateCylinder('team-lift-axis', { height: 82, diameterTop: 6, diameterBottom: 6, tessellation: 12 }, scene);
      liftBeam.position.set(0, -41, -46); liftBeam.material = this.mat('team-lift-axis', '#82f3ff', { emissive: 0.8, alpha: 0.14, unlit: true }); liftBeam.metadata = { elevator: true };
      for (const x of [-3, 3]) for (const z of [-49, -43]) {
        const rail = this.box('orbital-lift-rail', 0.28, 83, 0.28, '#52718e'); rail.position.set(x, -40.5, z); rail.isPickable = false;
      }
    },


    // 도로→광장→기능 지구 순서로 배치한다. 외부 아트 없이 재질별 병합한 독립 건축이다.
    buildGroundCity() {
      const scene = this.scene, groups = new Map(), Y = -82.85, CZ = -46, obstacles=[];
      const M = {
        road: this.pbr('city-asphalt','#243647',.08,.94,'stone'), walk: this.pbr('city-paving','#b7c3c6',.03,.88,'stone'),
        pearl: this.pbr('city-pearl','#c8d5dc',.16,.56,'stone'), navy: this.pbr('city-navy','#294459',.65,.39,'metal'),
        glass: this.pbr('city-glass','#327d91',.32,.18),
        teal: this.mat('city-trace', '#7be8dd', { emissive: 0.75, unlit: true }),
        violet: this.mat('city-violet-trim', '#aaa0e8', { emissive: 0.55, unlit: true }),
        warm: this.mat('city-windows', '#ffe1a6', { emissive: 0.65, unlit: true }),
        green: this.mat('city-garden', '#497b65'), water: this.pbr('city-water','#397f9b',.22,.16),
        solar: this.pbr('city-solar','#214f69',.4,.25),
      };
      const add = (m, mat) => { m.material = mat; m.isPickable = false; if (!groups.has(mat)) groups.set(mat, []); groups.get(mat).push(m); return m; };
      const box = (n,x,y,z,w,h,d,mat,rot=0) => { const m=B.MeshBuilder.CreateBox(n,{width:w,height:h,depth:d},scene);m.position.set(x,y,z);m.rotation.y=rot;return add(m,mat); };
      const cyl = (n,x,y,z,d,h,mat,vertices=12,top=d) => {const m=B.MeshBuilder.CreateCylinder(n,{diameterBottom:d,diameterTop:top,height:h,tessellation:vertices},scene);m.position.set(x,y,z);return add(m,mat);};
      const annulus = (n,r,w,y,mat,cx=0,cz=CZ) => {
        const inner=[],outer=[];for(let i=0;i<=96;i++){const a=i*Math.PI/48;inner.push(new B.Vector3(cx+Math.cos(a)*(r-w/2),y,cz+Math.sin(a)*(r-w/2)));outer.push(new B.Vector3(cx+Math.cos(a)*(r+w/2),y,cz+Math.sin(a)*(r+w/2)));}
        return add(B.MeshBuilder.CreateRibbon(n,{pathArray:[inner,outer],sideOrientation:B.Mesh.DOUBLESIDE},scene),mat);
      };
      // 길은 실제 교차하고, 차도 바깥에 별도 보행로와 식재 띠가 이어진다.
      [105,235].forEach((r,i)=>{
        annulus(`ring-walk-${i}`,r,25,Y,M.walk);annulus(`ring-road-${i}`,r,17,Y+.04,M.road);
        annulus(`ring-median-${i}`,r,.32,Y+.08,M.teal);annulus(`ring-edge-${i}`,r+8.1,.22,Y+.09,M.warm);
      });
      const avenues = [-Math.PI/2, -Math.PI/6, Math.PI/6, Math.PI/2, Math.PI*5/6, Math.PI*7/6];
      avenues.forEach((a,i)=>{
        const mid=215,rot=Math.PI/2-a,x=Math.cos(a)*mid,z=CZ+Math.sin(a)*mid;
        box(`avenue-walk-${i}`,x,Y-.06,z,27,.18,398,M.walk,rot);
        box(`avenue-road-${i}`,x,Y+.06,z,18,.16,398,M.road,rot);
        box(`avenue-median-${i}`,x,Y+.17,z,.3,.035,398,M.teal,rot);
        for(let t=38;t<410;t+=20)for(const side of [-1,1]){
          const dx=Math.cos(a)*t+Math.sin(a)*side*4.3,dz=CZ+Math.sin(a)*t-Math.cos(a)*side*4.3;
          box(`lane-mark-${i}`,dx,Y+.16,dz,.18,.03,6,M.walk,rot);
        }
        for(let t=54;t<390;t+=52)for(const side of [-1,1]){
          const lx=Math.cos(a)*t+Math.sin(a)*side*12,dz=CZ+Math.sin(a)*t-Math.cos(a)*side*12;
          box(`street-lamp-${i}`,lx,Y+3.7,dz,.22,7.4,.22,M.navy);
          box(`street-light-${i}`,lx,Y+7.4,dz,2.2,.2,.8,M.warm,rot);
        }
      });
      cyl('arrival-plaza',0,Y+.1,CZ,39,.25,M.pearl,32);
      annulus('arrival-halo',17,.45,Y+.25,M.teal);
      // 4종 건물 문법. 지구마다 다른 실루엣을 묶고 중앙 승강/기억 시야축은 비운다.
      const building=(x,z,w,h,type)=>{
        obstacles.push({x,z,w:w+8,d:w+6});
        const y=-83;
        box('district-podium',x,y+.6,z,w+8,1.2,w+6,M.walk);
        if(type===0){ // 연구: 유리 팔각 타워와 수직 구조 리브
          cyl('research-glass',x,y+h/2+1,z,w,h,M.glass,8,w*.75);
          for(let k=0;k<8;k++){const a=k*Math.PI/4;box('research-rib',x+Math.cos(a)*w*.43,y+h/2+1,z+Math.sin(a)*w*.43,.55,h,.55,M.pearl);}
          for(let t=5;t<h;t+=7){annulus('research-floor',w*.44,.45,y+t,M.pearl,x,z);annulus('research-recess',w*.435,.3,y+t-.5,M.navy,x,z);}
          cyl('research-crown',x,y+h+1.3,z,w*.85,1.2,M.navy,8);
          annulus('research-crown-light',w*.38,.3,y+h+2,M.teal,x,z);
        }else if(type===1){ // 제작: 계단식 테라스, 긴 작업동과 채광 밴드
          for(let k=0;k<3;k++){
            const ww=w*(1-k*.19),hh=h/3;
            box('studio-terrace',x+k*1.6,y+hh*(k+.5)+1,z+k*1.5,ww,hh,w*(.8-k*.12),k%2?M.navy:M.pearl);
            box('studio-window',x+k*1.6,y+hh*(k+.5)+1,z-w*(.8-k*.12)/2+k*1.5-.1,ww*.88,hh*.47,.2,M.glass);
            box('studio-warm',x+k*1.6,y+hh*(k+.5)-.8,z-w*(.8-k*.12)/2+k*1.5-.24,ww*.75,.35,.1,M.warm);
            box('studio-roof-garden',x+k*1.6,y+hh*(k+1)+1.1,z+k*1.5,ww*.94,.2,w*(.74-k*.12),M.green);
            box('studio-terrace-sill',x+k*1.6,y+hh*(k+1)+1.25,z-w*(.8-k*.12)/2+k*1.5-.2,ww+.6,.28,.65,M.navy);
            box('studio-balustrade',x+k*1.6,y+hh*(k+1)+1.7,z-w*(.8-k*.12)/2+k*1.5-.15,ww*.94,.65,.14,M.glass);
          }
        }else if(type===2){ // 커뮤니티: 아치형 유리 돔과 개방 포디움
          cyl('commons-base',x,y+2,z,w+3,4,M.pearl,24);
          const dome=B.MeshBuilder.CreateSphere('commons-dome',{diameter:w,segments:20},scene);
          dome.scaling.y=.52;dome.position.set(x,y+4,z);add(dome,M.glass);
          annulus('commons-ring',w*.49,.7,y+4,M.pearl,x,z);
          for(let k=0;k<8;k++){const a=k*Math.PI/4;box('commons-portico',x+Math.cos(a)*w*.41,y+3,z+Math.sin(a)*w*.41,.6,6,.6,M.pearl);}
          box('commons-entry',x,y+2,z-w*.54,w*.32,3,.7,M.navy);
        }else{ // 주거/협업: 두 날개를 잇는 스카이브리지
          for(const side of [-1,1]){
            box('collab-wing',x+side*w*.3,y+h/2+1,z,w*.36,h,w*.7,M.pearl);
            box('collab-facade',x+side*w*.3,y+h/2+1,z-w*.36,w*.27,h*.84,.25,M.glass);
            for(let t=5;t<h;t+=6)box('collab-window',x+side*w*.3,y+t,z-w*.37,w*.29,.7,.12,M.warm);
          }
          box('collab-skybridge',x,y+h*.7,z,w*.7,2.6,w*.32,M.navy);
          box('collab-bridge-trim',x,y+h*.7+1.4,z-w*.17,w*.7,.18,.18,M.teal);
        }
      };
      // 東側 연구, 西側 제작, 北側 커뮤니티. 정면은 낮은 환승/에너지 공원이다.
      const plans=[
        [150,-46,24,59,0],[183,-12,18,41,0],[185,-82,21,47,3],[145,0,21,25,1],[285,-46,24,30,1],[318,-14,22,48,0],
        [-150,-46,31,24,1],[-183,-12,26,18,1],[-185,-82,28,29,1],[-145,0,20,38,3],[-285,-46,27,22,1],
        [80,92,26,15,2],[111,98,20,34,3],[60,126,22,22,1],[147,208,32,15,2],[-147,208,25,34,3],[-80,92,29,15,2],
        [-147,-300,25,20,1],[147,-300,24,31,3],[-200,-330,24,26,0],[200,-330,31,14,2],
        [-280,35,27,43,3],[280,35,23,54,0],[-215,220,25,24,1],[215,220,24,31,3],
      ];
      plans.forEach((v)=>building(...v));
      // 區域 지선: 대로와 건물 현관을 연결해 떠 있는 박스 집합을 피한다.
      [[155,-75],[-153,-75],[0,148],[-141,-241],[139,-240]].forEach(([x,z],i)=>{
        const end=new B.Vector3(x,Y+.15,z),start=new B.Vector3(x*.55,Y+.15,CZ+(z-CZ)*.55),v=end.subtract(start),mid=B.Vector3.Center(start,end);
        box(`district-link-${i}`,mid.x,Y+.13,mid.z,7,.1,v.length(),M.walk,Math.atan2(v.x,v.z));
      });
      // 고가 트램: 두 순환선에 접속하는 정류장, 기둥, 구간 경계가 읽힌다.
      const railPath=[];for(let i=0;i<=72;i++){const a=i*Math.PI/36;railPath.push(new B.Vector3(Math.cos(a)*90,-69,CZ+Math.sin(a)*90));}
      add(B.MeshBuilder.CreateTube('civic-tram-guide',{path:railPath,radius:.42,tessellation:6},scene),M.teal);
      add(B.MeshBuilder.CreateTube('civic-tram-deck',{path:railPath.map(v=>v.add(new B.Vector3(0,-.6,0))),radius:1.3,tessellation:6},scene),M.navy);
      for(let i=0;i<18;i++){const a=i*Math.PI/9;cyl('tram-pier',Math.cos(a)*90,-76,CZ+Math.sin(a)*90,1,14,M.pearl,6);}
      [[90,CZ],[-90,CZ],[0,CZ+90],[0,CZ-90]].forEach(([x,z],i)=>{
        box(`station-base-${i}`,x,-68.8,z,22,.8,9,M.pearl);
        box(`station-glass-${i}`,x,-65.8,z+2,18,5,.35,M.glass);
        box(`station-canopy-${i}`,x,-62.8,z,25,.6,12,M.pearl);
        for(const side of [-1,1])box(`station-post-${i}`,x+side*10,-65.8,z,.45,6,.45,M.navy);
        box(`station-sign-${i}`,x,-63.8,z-4,11,.45,.3,M.warm);
      });
      // 랜드마크는 중심 팀 대지 좌우 끝에만 세워 실제 실무 패널/동료의 시야를 비운다.
      obstacles.push({x:-257,z:55,r:14});
      cyl('civic-spire-foot',-257,-80,55,27,6,M.pearl,12);
      cyl('civic-spire',-257,-25,55,15,105,M.glass,8,5);
      for(let k=0;k<4;k++)annulus('spire-observation',12-k*1.5,1,-58+k*22,M.pearl,-257,55);
      const tip=B.MeshBuilder.CreateCylinder('spire-tip',{diameterBottom:4,diameterTop:0,height:27,tessellation:8},scene);tip.position.set(-257,41,55);add(tip,M.teal);
      // 태양광 정원: 정렬된 패널 3열과 제어 파빌리온, 도시 전력 순환을 상징한다.
      for(let row=0;row<3;row++)for(let k=0;k<5;k++){
        const x=-220+k*20,z=-330-row*17;
        box('solar-leg',x,-80,z,.6,5,.6,M.pearl);
        const panel=box('solar-canopy',x,-77,z,15,.4,10,M.solar);panel.rotation.x=-.27;
        box('solar-lane',x,-76.7,z,13,.08,.18,M.teal);
      }
      building(-100,-335,23,12,2);
      // 공원은 건물 사이의 공간을 묶는다. 수면/산책루프/군집 식재를 함께 배치한다.
      [[35,15,14],[-35,15,14],[35,-107,14],[-35,-107,14]].forEach(([x,z,r],i)=>{
        cyl(`park-${i}`,x,-82.7,z,r*2,.3,M.green,24);
        annulus(`park-loop-${i}`,r*.7,2.3,-82.45,M.walk,x,z);
        cyl(`park-water-${i}`,x,-82.38,z,r*.7,.1,M.water,24);
        for(let k=0;k<7;k++){
          const a=k*Math.PI*2/7,px=x+Math.cos(a)*r*.85,pz=z+Math.sin(a)*r*.85;
          cyl('park-trunk',px,-80.5,pz,.7,4,M.navy,6);
          const crown=B.MeshBuilder.CreateSphere('park-crown',{diameter:5,segments:6},scene);crown.position.set(px,-77.8,pz);add(crown,M.green);
        }
        for(const side of [-1,1])box('park-bench',x+side*r*.8,-81.7,z,4,.8,1.2,M.pearl);
      });
      groups.forEach((meshes)=>{const merged=B.Mesh.MergeMeshes(meshes,true,true,undefined,false,false);if(merged){merged.isPickable=false;merged.freezeWorldMatrix();}});
      this.groundCity={districts:5,buildings:plans.length+1,roadRadii:[105,235],landmarkCount:1,obstacles};
      const arrivalY=this.groundRoadHeight(0,-46);this.portals.meadow.y=arrivalY;
      this.scene.getMeshByName('transfer-gate-meadow').position.y=arrivalY+3;
      this.scene.getMeshByName('transfer-base-meadow').position.y=arrivalY+.1;
    },


    // 장식 교통만 움직인다. 실제 에이전트/업무 데이터와 별개인 작은 재사용 차량 풀이다.
    buildTraffic() {
      const scene=this.scene;
      const metal=this.pbr('vehicle-pearl','#c6d4dc',.68,.3,'metal'),dark=this.pbr('vehicle-navy','#243a51',.62,.37,'metal'),glass=this.pbr('vehicle-window','#408f9e',.36,.16),light=this.mat('vehicle-light','#ffe2b2',{emissive:.75,unlit:true}),engine=this.mat('vehicle-engine','#78e3e8',{emissive:.75,unlit:true});
      const master=(kind)=>{
        const groups=new Map();
        const add=(mesh,mat)=>{mesh.material=mat;mesh.isPickable=false;if(!groups.has(mat))groups.set(mat,[]);groups.get(mat).push(mesh);return mesh;};
        const box=(n,x,y,z,w,h,d,mat,rz=0)=>{const m=B.MeshBuilder.CreateBox(n,{width:w,height:h,depth:d},scene);m.position.set(x,y,z);m.rotation.z=rz;return add(m,mat);};
        if(kind==='car'||kind==='fly'){
          const flying=kind==='fly';
          box('hover-chassis',0,0,0,5.8,.65,2.7,metal);box('hover-belly',-.2,-.4,0,4.8,.35,2.2,dark);
          box('hover-cabin',-.35,.62,0,2.8,.75,2.1,glass);box('hover-roof',-.6,1.05,0,2.5,.14,2.15,metal);
          for(const side of [-1,1]){box('hover-headlight',2.94,.12,side*.92,.1,.2,.55,light);box('hover-motor',-2.9,-.15,side*.9,.15,.23,.65,engine);}
          if(flying)for(const side of [-1,1]){box('aircar-wing',-.6,-.12,side*2.0,3.7,.18,1.4,dark);box('aircar-tip',-.6,-.18,side*2.7,2.3,.12,.15,engine);}
        }else if(kind==='plane'){
          box('shuttle-fuselage',0,0,0,14,1.8,2.9,metal);box('shuttle-cockpit',4.7,.7,0,3.4,1.1,2.4,glass);
          for(const side of [-1,1]){box('shuttle-wing',-1,-.2,side*4.2,6.8,.32,6.2,metal);box('shuttle-engine',-3,-.4,side*4.7,4.5,1,1.1,dark);box('shuttle-exhaust',-5.3,-.4,side*4.7,.16,.65,.7,engine);box('shuttle-tail',-5.5,1.6,side*1.2,2.2,3,.25,dark);}
        }else{
          // 독자 설계의 긴 중앙 선체 + 분리된 두 현측 엔진. 특정 게임 자산을 복제하지 않는다.
          box('cruiser-keel',0,0,0,78,5,16,dark);box('cruiser-main-deck',2,3,0,64,3,21,metal);
          box('cruiser-prow',36,1,0,21,3.8,11,metal);box('cruiser-prow-trace',45,1.2,0,.3,1.2,8,engine);
          for(const side of [-1,1]){
            box('cruiser-outrigger',-13,1,side*18,52,5.5,8,metal);box('cruiser-wing',-7,1,side*10,27,2.4,14,dark);
            box('cruiser-side-window',-8,3.1,side*22.1,29,.6,.18,light);box('cruiser-engine-pod',-40,0,side*18,14,6,9,dark);
            box('cruiser-engine-aperture',-47.1,0,side*18,.2,3.5,6,engine);
            box('cruiser-lower-fin',-9,-4.6,side*18,18,3,.65,dark);
          }
          box('cruiser-bridge',-9,8,0,14,7,10,dark);box('cruiser-command-glass',-2,8.5,0,.25,2.8,8.5,glass);
          box('cruiser-bridge-roof',-9,12,0,17,.7,12,metal);box('cruiser-sensor',-12,14.8,0,.7,5,.7,metal);
          for(let i=0;i<5;i++)box('cruiser-deck-panel',-22+i*10,4.65,0,6,.18,8,dark);
        }
        const parts=[];groups.forEach(meshes=>{const m=B.Mesh.MergeMeshes(meshes,true,true,undefined,false,false);if(m){m.isVisible=false;m.isPickable=false;parts.push(m);}});return parts;
      };
      const templates={car:master('car'),fly:master('fly'),plane:master('plane'),cruiser:master('cruiser')};
      this.traffic=[];this.trafficClock=0;this.trafficPaused=false;
      const spawn=(kind,index)=>{
        const root=new B.TransformNode(`traffic-${kind}-${index}`,scene);
        templates[kind].forEach((mesh,i)=>{const instance=mesh.createInstance(`${kind}-${index}-${i}`);instance.parent=root;instance.isVisible=true;instance.isPickable=false;});
        const v={kind,index,root,phase:index*1.83};this.traffic.push(v);return v;
      };
      for(let i=0;i<(QUALITY==='low'?6:10);i++){const v=spawn('car',i);v.radius=(i<6?105:235)+(i%2?3.4:-3.4);v.direction=i%2?-1:1;}
      for(let i=0;i<(QUALITY==='low'?2:4);i++)spawn('fly',i);
      for(let i=0;i<(QUALITY==='low'?1:2);i++)spawn('plane',i);
      spawn('cruiser',0);
      this.stepTraffic(0);
    },

    stepTraffic(dt) {
      if(!this.traffic)return;
      if(!this.trafficPaused&&!REDUCED)this.trafficClock+=dt;
      const time=this.trafficClock;
      this.traffic.forEach(v=>{
        let a;
        if(v.kind==='car'){
          a=v.phase+time*(v.direction*8/v.radius);const x=Math.cos(a)*v.radius,z=-46+Math.sin(a)*v.radius;
          v.root.position.set(x,(this.groundRoadHeight(x,z)??-82.81)+1.4,z);v.root.rotation.y=-a-Math.PI/2+(v.direction<0?Math.PI:0);
        }else if(v.kind==='fly'){
          a=v.phase+time*.045;v.root.position.set(Math.cos(a)*128,12+v.index*6,25+Math.sin(a)*89);v.root.rotation.y=Math.atan2(-89*Math.cos(a),-128*Math.sin(a));
        }else if(v.kind==='plane'){
          a=v.phase+time*.022;v.root.position.set(Math.cos(a)*235,82+v.index*23,45+Math.sin(a)*140);v.root.rotation.y=Math.atan2(-140*Math.cos(a),-235*Math.sin(a));v.root.rotation.z=Math.sin(a)*.06;
        }else{
          v.root.position.set(155,43+Math.sin(time*.12)*.45,86);v.root.rotation.y=.2+Math.sin(time*.035)*.025;
        }
      });
    },

    buildHub() {
      const s = this.scene;
      // 광장: 블록 땅 위에 놓인 밝은 돌 원판. 클릭하면 공유 기억 패널.
      const plaza = B.MeshBuilder.CreateCylinder('hub-plaza', { height: 0.14, diameter: HUB_R * 2 - 1.0, tessellation: 12 }, s);
      plaza.position.y = 0.07;
      plaza.material = this.mat('memory-plaza', '#d1e2e9');
      plaza.metadata = { hub: true };
      this.receiveShadow(plaza);
      [HUB_R * 2 - 2.2, HUB_R * 2 - 4.6].forEach((d, i) => {
        const ring = B.MeshBuilder.CreateTorus(`hub-ring-${i}`, { diameter: d, thickness: 0.14, tessellation: 96 }, s);
        ring.position.y = 0.16;
        ring.material = this.mat('ring', i === 0 ? '#7fe3ff' : '#4f8df7', { emissive: 0.9 - i * 0.2, unlit: true });
        ring.isPickable = false;
        this.hub.rings.push(ring);
      });
      const core = B.MeshBuilder.CreateSphere('brain-core', { diameter: 2.4, segments: 24 }, s);
      core.position.y = 4.2;
      core.material = this.mat('core', '#bff4ff', { emissive: 1.6, unlit: true });
      core.metadata = { hub: true };
      this.hub.core = core;
      const halo = B.MeshBuilder.CreateSphere('brain-halo', { diameter: 3.4, segments: 16 }, s);
      halo.position.y = 4.2;
      halo.material = this.mat('halo', '#7fe3ff', { emissive: 0.9, alpha: 0.14, unlit: true });
      halo.isPickable = false;
      [[2.1, 0.5, 0.2], [2.9, 1.1, -0.4], [3.6, -0.3, 0.9]].forEach((r, i) => {
        const orbit = B.MeshBuilder.CreateTorus(`brain-orbit-${i}`, { diameter: r[0] * 2, thickness: 0.06, tessellation: 64 }, s);
        orbit.position.y = 4.2;
        orbit.rotation.x = r[1];
        orbit.rotation.z = r[2];
        orbit.material = this.mat('orbit', i === 1 ? '#e65fb8' : '#7fe3ff', { emissive: 0.8, unlit: true });
        orbit.isPickable = false;
        this.hub.rings.push(orbit);
      });
      const beam = B.MeshBuilder.CreateCylinder('brain-beam', { height: 60, diameter: 0.5, tessellation: 12 }, s);
      beam.position.y = 30;
      beam.material = this.mat('beam', '#7fe3ff', { emissive: 0.5, alpha: 0.07, unlit: true });
      beam.isPickable = false;
      for (let i = 0; i < 10; i++) {
        const a = (i / 10) * Math.PI * 2;
        const post = this.box(`hub-post-${i}`, 0.18, 1, 0.18, '#7fe3ff', { emissive: 0.6, unlit: true });
        post.position.set(Math.cos(a) * (HUB_R - 0.5), 0.5, Math.sin(a) * (HUB_R - 0.5));
        post.isPickable = false;
        this.castShadow(post);
      }
    },

    // ---------------- 섬 ----------------
    clearStages() {
      if(workshop.ready)workshop.clear();
      space.stages.forEach((st) => st.node.dispose());
      space.stages = [];
      this.flows.forEach((f) => f.mesh.dispose());
      this.flows = [];
      this.flowKeys.clear();
      if (this.terrain) { this.terrain.meshes.forEach((m) => m.dispose()); this.terrain = null; }
    },

    buildStages(stages) {
      this.clearStages();
      const n = stages.length;
      stages.forEach((stage, i) => {
        const angle = -Math.PI / 2 + (i / n) * Math.PI * 2;
        const pos = new B.Vector3(Math.cos(angle) * ISLAND_DIST, 0, Math.sin(angle) * ISLAND_DIST);
        const toHub = pos.scale(-1).normalize();
        const rotY = Math.atan2(toHub.x, toHub.z);
        const node = new B.TransformNode(`island-${stage.id}`, this.scene);
        node.position = pos;
        node.rotation.y = rotY;
        const st = Object.assign({}, stage, { node, pos, rotY, angle, desks: [], screens: [], bridge: null });
        this.buildRoom(st);
        this.buildPath(st);
        space.stages.push(st);
      });
      this.buildTerrain();
    },

    // ---------------- 블록 땅 ----------------
    // 1m 큐브를 쌓아 만든 하나의 땅. 광장·방·길은 높이 0의 평지, 나머지는 0~2칸 높낮이.
    pathDistance(v) {
      let best = Infinity;
      for (const st of space.stages) {
        const b = st.bridge;
        const ab = b.end.subtract(b.start); const ap = v.subtract(b.start);
        const t = Math.max(0, Math.min(1, B.Vector3.Dot(ap, ab) / ab.lengthSquared()));
        const c = b.start.add(ab.scale(t));
        best = Math.min(best, Math.hypot(v.x - c.x, v.z - c.z));
      }
      return best;
    },

    flatZone(x, z) {
      // 'plaza' | 'plot' | 'path' | null
      if (Math.hypot(x, z) <= HUB_R + 0.5) return 'plaza';
      const v = new B.Vector3(x, 0, z);
      for (const st of space.stages) {
        const l = this.toLocal(st, v);
        if (Math.abs(l.x) <= ISLAND_W / 2 + 0.5 && Math.abs(l.z) <= ISLAND_D / 2 + 0.5) return 'plot';
      }
      if (this.pathDistance(v) <= BRIDGE_W / 2 + 0.6) return 'path';
      return null;
    },


    architecturePlan(kind) {
      const parts=[],obstacles=[];
      const box=(name,x,y,z,w,h,d,material,rotationZ=0)=>parts.push({name,position:[x,y,z],size:[w,h,d],material,rotationZ});
      if(kind==='arrival'){
        for(const x of [-5.8,5.8]){
          box('footing',x,.3,-53,1.6,.6,1.6,'frame');
          box('pier',x,3.55,-53,.8,5.9,1.05,'shell');
          box('pier-inset',x,3.55,-53.56,.48,4.8,.12,'glass');
          box('pier-light',x,3.55,-53.64,.08,4.2,.04,'light');
          box('bracket',x*.88,6.05,-53,.36,1.7,.8,'frame',x<0?-.55:.55);
          obstacles.push({x,z:-53,r:1.15});
        }
        box('canopy',0,6.9,-53,15,.5,6,'shell');
        box('canopy-inset',0,6.61,-53,12.8,.08,4.8,'frame');
        box('front-fascia',0,6.92,-56.06,13.6,.23,.1,'glass');
        box('welcome-light',0,6.53,-55.45,10.7,.06,.1,'light');
        box('rear-light',0,6.53,-50.55,10.7,.06,.1,'light');
        for(const x of [-4.5,0,4.5])box('roof-panel',x,7.2,-53,3.8,.1,4.7,'glass');
        const ribs=QUALITY==='low'?5:9;
        for(let i=0;i<ribs;i++)box('roof-rib',-6.3+i*12.6/(ribs-1),7.34,-53,.15,.18,5.5,'frame');
      }else if(kind==='atrium'){
        for(const x of [-6.65,6.65]){
          box('rear-pier',x,3.35,-6.05,.55,6.7,.65,'shell');
          box('rear-light',x,3.5,-6.42,.08,5.8,.06,'light');
        }
        for(const x of [-4.4,0,4.4]){
          box('clerestory',x,5.65,-5.85,4.05,1.7,.16,'glass');
          box('mullion',x-2.13,5.65,-5.99,.16,1.95,.22,'frame');
        }
        box('crown',0,6.8,-5.85,14.4,.35,1.2,'shell');
        box('roof',0,7.06,-5.8,14.4,.18,3.8,'frame');
        box('crown-light',0,6.6,-6.49,13.6,.06,.06,'light');
        for(const z of [-4.6,-1.6,1.4,4.4]){
          box('side-fin',-6.42,2.65,z,.35,5.3,.65,'shell');
          box('side-inset',-6.64,2.7,z,.06,4.2,.3,'glass');
        }
        box('side-beam',-6.4,5.45,.1,.48,.38,12.4,'frame');
        box('front-beam',0,5.45,6.1,13.6,.38,.48,'shell');
        box('front-light',0,5.22,6.13,12.5,.06,.12,'light');
        const ribs=QUALITY==='low'?5:9;
        for(let i=0;i<ribs;i++)box('roof-rib',-6.6+i*13.2/(ribs-1),7.22,-5.8,.13,.15,3.5,'shell');
      }
      if(kind==='build-tower'){
        box('podium',0,.15,0,4,.3,4,'frame');
        box('tower-core',0,3.35,0,3.2,5.5,3.2,'glass');
        for(const x of [-1.72,1.72])for(const z of [-1.72,1.72])box('tower-pier',x,3.3,z,.24,6,.24,'shell');
        for(const y of [.55,2.5,4.45,6.4])box('tower-belt',0,y,0,3.8,.16,3.8,'frame');
        box('tower-crown',0,6.75,0,4,.26,4,'shell');
        for(const x of [-1.2,0,1.2])box('tower-roof-fin',x,7.1,0,.15,.6,2.8,'frame');
        for(const x of [-1.72,1.72])box('tower-guide',x,3.4,-1.86,.06,4.9,.05,'light');
        box('tower-entry',0,.95,-1.93,1.1,1.3,.08,'frame');
      }else if(kind==='build-lab'){
        box('lab-plinth',0,.12,0,6,.24,4,'frame');
        box('lab-back',0,1.9,1.7,5.7,3.3,.4,'shell');
        box('lab-glazing',0,1.9,-1.76,5.3,2.8,.14,'glass');
        for(const x of [-2.7,2.7])box('lab-side',x,1.9,0,.42,3.3,3.7,'shell');
        for(const x of [-1.75,0,1.75])box('lab-mullion',x,1.95,-1.87,.1,2.9,.08,'frame');
        box('lab-door',0,1.2,-1.94,1.1,2.1,.06,'frame');
        box('lab-canopy',0,3.7,-1.1,5.9,.26,1.8,'shell');
        box('lab-roof',0,4.2,0,5.9,.25,3.8,'frame');
        for(const x of [-2,-1,0,1,2])box('lab-fin',x,4.55,0,.14,.5,3.3,'shell');
        box('lab-light',0,3.53,-1.94,5.2,.07,.06,'light');
      }else if(kind==='build-port'){
        box('port-dock',0,.15,0,4,.3,6,'frame');
        box('port-terminal',0,1.65,1.6,3.4,2.7,2.3,'glass');
        for(const x of [-1.7,1.7])for(const z of [-2.6,2.6])box('port-pier',x,2.2,z,.3,4,.3,'shell');
        box('port-roof',0,4.2,0,4,.3,5.9,'shell');
        for(const x of [-1.5,1.5])box('port-roof-edge',x,4.5,0,.3,.2,5.8,'frame');
        box('port-banner',0,4.03,-2.97,3.3,.12,.04,'light');
        box('shuttle-hull',0,.9,-1.25,1.8,.55,2.4,'shell');
        box('shuttle-cabin',0,1.35,-1.05,1.3,.45,1.35,'glass');
        for(const x of [-1.05,1.05])box('shuttle-foil',x,.75,-1.3,.35,.2,2.2,'frame');
        for(const x of [-.65,.65])box('shuttle-headlamp',x,1.02,-2.47,.25,.12,.04,'light');
      }
      return {parts,obstacles};
    },

    buildArchitecture(kind,parent=null) {
      const plan=this.architecturePlan(kind),groups=new Map(),meshes=[];
      const materials={
        shell:this.pbr('architecture-ceramic','#d7e1e7',.2,.4,'stone'),
        frame:this.pbr('architecture-frame','#193345',.65,.31,'metal'),
        glass:this.pbr('architecture-glass','#2f8495',.38,.2),
        light:this.mat('architecture-light','#b9eee5',{emissive:.45,unlit:true}),
      };
      // Parts stay in local coordinates until merged; parenting earlier would bake the stage transform twice.
      for(const part of plan.parts){
        const [width,height,depth]=part.size;
        const mesh=B.MeshBuilder.CreateBox(part.name,{width,height,depth},this.scene);
        mesh.position.set(...part.position);mesh.rotation.z=part.rotationZ;mesh.material=materials[part.material];
        if(!groups.has(part.material))groups.set(part.material,[]);
        groups.get(part.material).push(mesh);
      }
      for(const [material,parts] of groups){
        const mesh=B.Mesh.MergeMeshes(parts,true,true,undefined,false,false);
        if(!mesh)continue;
        mesh.name='architecture-'+kind+'-'+material;mesh.parent=parent;mesh.isPickable=false;
        if(!parent)mesh.freezeWorldMatrix();
        if(material!=='light'){this.castShadow(mesh);this.receiveShadow(mesh);}
        meshes.push(mesh);
      }
      return {meshes,obstacles:plan.obstacles};
    },

    buildTerrain() {
      const scene=this.scene,LAND_R=68,cols=new Map(),key=(x,z)=>`${x},${z}`,meshes=[];
      // 공중 팀은 흙 섬이 아니라 높이 0의 평탄한 세라믹/금속 도시 데크다.
      for(let x=-68;x<=68;x++)for(let z=-68;z<=68;z++)if(Math.hypot(x+.5,z+.5)<=66)cols.set(key(x,z),{x:x+.5,z:z+.5,level:0,depth:4,zone:this.flatZone(x+.5,z+.5)});
      const groups=new Map();
      const pearl=this.pbr('team-ceramic','#bacbd5',.12,.63,'stone'),navy=this.pbr('team-metal','#233d54',.65,.38,'metal'),glass=this.pbr('team-glass','#367e96',.3,.18),cyan=this.mat('team-trim','#81e6ec',{emissive:.65,unlit:true}),warm=this.mat('team-window','#ffe2ab',{emissive:.55,unlit:true});
      const add=(m,mat)=>{m.material=mat;m.isPickable=false;if(!groups.has(mat))groups.set(mat,[]);groups.get(mat).push(m);return m;};
      const box=(n,x,y,z,w,h,d,mat,rot=0)=>{const m=B.MeshBuilder.CreateBox(n,{width:w,height:h,depth:d},scene);m.position.set(x,y,z);m.rotation.y=rot;return add(m,mat);};
      const disk=(n,x,y,z,diameter,h,mat,t=12,lower=diameter)=>{const m=B.MeshBuilder.CreateCylinder(n,{diameterTop:diameter,diameterBottom:lower,height:h,tessellation:t},scene);m.position.set(x,y,z);return add(m,mat);};
      const ring=(n,r,y,thick,mat,t=96)=>{const m=B.MeshBuilder.CreateTorus(n,{diameter:r*2,thickness:thick,tessellation:t},scene);m.position.y=y;return add(m,mat);};
      disk('team-platform-hull',0,-3.3,0,138,6,navy,12,126);
      disk('team-platform-surface',0,-.08,0,136,.16,this.deckSurfaceMaterial(),64);
      ring('team-upper-rim',67,.04,.22,cyan,12);ring('team-lower-rim',64,-5.7,.42,cyan,12);
      ring('team-transit-loop',43,.035,.6,navy);ring('team-transit-trace',43,.07,.12,cyan);
      // 5本 인계로와 외곽 교통 루프: 중심 기억과 실무 건물의 연결을 강조한다.
      space.stages.forEach((st)=>{
        const a=st.angle,x=Math.cos(a)*46,z=Math.sin(a)*46,rot=Math.PI/2-a;
        box('team-outer-spoke',x,.025,z,4,.04,30,navy,rot);
        box('team-outer-guidance',x,.055,z,.12,.04,30,cyan,rot);
      });
      for(let i=0;i<12;i++){
        const a=i*Math.PI/6,x=Math.cos(a)*59,z=Math.sin(a)*59;
        // 패널은 deckTexture에 합쳐 표면 높이 0과 깊이 안정성을 유지한다.
        box('team-radial-rib',Math.cos(a)*64,-2.7,Math.sin(a)*64,1.2,4.5,5.8,pearl,Math.PI/2-a);
      }

      this.landscapeObstacles=[];
      const green=this.pbr('team-pocket-plant','#507f6c',0,.9),soil=this.pbr('team-pocket-soil','#344f47',0,1,'stone');
      for(let i=0;i<5;i++){
        const a=-Math.PI/2+(i+.5)*Math.PI*2/5,x=Math.cos(a)*36,z=Math.sin(a)*36;
        this.landscapeObstacles.push({x,z,r:5.8});
        disk('team-planter-shell',x,.24,z,6.4,.48,navy,12);
        disk('team-planter-bed',x,.51,z,5.8,.08,soil,12);
        for(let j=0;j<3;j++){
          const b=j*Math.PI*2/3,crown=B.MeshBuilder.CreateSphere('team-low-shrub',{diameter:1.75,segments:QUALITY==='low'?6:10},scene);
          crown.position.set(x+Math.cos(b)*1.35,1.15,z+Math.sin(b)*1.35);crown.scaling.y=.7;add(crown,green);
        }
        for(const side of [-1,1]){
          const bx=x+Math.sin(a)*side*4.4,bz=z-Math.cos(a)*side*4.4;
          box('team-pocket-bench',bx,.5,bz,3,.28,.9,pearl,a);
          box('team-bench-leg',bx,.23,bz,1.8,.46,.35,navy,a);
        }
        box('team-pocket-waylight',x,.7,z-3.35,.18,1.4,.18,navy);
        box('team-pocket-light',x,1.42,z-3.35,.3,.12,.3,warm);
      }

      // 下部 반중력 엔진은 실제 팀 플랫폼에 붙는다.
      for(let i=0;i<6;i++){
        const a=i*Math.PI/3,x=Math.cos(a)*45,z=Math.sin(a)*45;
        disk('team-engine',x,-7,z,10,5,navy,12,6);
        const nozzle=B.MeshBuilder.CreateTorus('team-engine-nozzle',{diameter:7.5,thickness:.45,tessellation:32},scene);nozzle.position.set(x,-9.5,z);add(nozzle,cyan);
        disk('team-engine-core',x,-9.9,z,4.8,.3,cyan,12);
      }
      // 北側/左右에만 도시 스카이라인을 두어 남쪽 포털→기억→업무 시야축을 비운다.
      [[-43,31,19],[0,55,32],[43,31,24],[-56,4,14],[56,4,17]].forEach(([x,z,h],i)=>{
        disk(`team-tower-base-${i}`,x,.6,z,13,1.2,navy,8);
        box(`team-tower-${i}`,x,h/2+1.2,z,7,h,7,glass);
        for(const dx of [-3.7,3.7])box(`team-tower-frame-${i}`,x+dx,h/2+1.2,z,.55,h+1,7.8,pearl);
        for(let t=4;t<h;t+=4)box(`team-tower-window-${i}`,x,t+1.2,z-3.6,5,.32,.14,warm);
        disk(`team-tower-crown-${i}`,x,h+2,z,9,1.2,navy,8);
        box(`team-tower-trace-${i}`,x,h/2+1.2,z+3.7,.2,h,.2,cyan);
      });
      // 後方 스카이브리지 두 구간. 인물 활동 영역/출입구와 겹치지 않는다.
      [[-43,31,0,55],[0,55,43,31]].forEach(([x1,z1,x2,z2],i)=>{
        const dx=x2-x1,dz=z2-z1,len=Math.hypot(dx,dz),rot=Math.atan2(dx,dz),x=(x1+x2)/2,z=(z1+z2)/2;
        box(`team-skybridge-${i}`,x,10,z,3.5,.7,len,navy,rot);
        box(`team-skybridge-light-${i}`,x,10.45,z,.18,.12,len,cyan,rot);
      });
      groups.forEach((parts)=>{const mesh=B.Mesh.MergeMeshes(parts,true,true,undefined,false,false);if(mesh){mesh.isPickable=false;mesh.freezeWorldMatrix();this.receiveShadow(mesh);meshes.push(mesh);}});
      const arrival=this.buildArchitecture('arrival');meshes.push(...arrival.meshes);
      this.arrivalArchitecture=arrival;this.arrivalDetail?.sync();
      this.officeObstacles=[...arrival.obstacles,...[[-43,31,6.8],[0,55,6.8],[43,31,6.8],[-56,4,6.8],[56,4,6.8]].map(([x,z,r])=>({x,z,r})),...this.landscapeObstacles];
      this.terrain={cols,key,meshes,landR:LAND_R,kind:'city-platform'};
      this.portals.office.y=0;
      this.scene.getMeshByName('transfer-gate-office').position.y=3;
      this.scene.getMeshByName('transfer-base-office').position.y=.1;
      if(workshop.ready){workshop.rebuild();workshop.sync();}
    },

    heightAt(x, z) {
      if (space.layer === 'meadow') {
        if(Math.abs(x)>=780||Math.abs(z)>=780)return null;
        const ground=this.meadowHeight(x,z),road=this.groundRoadHeight(x,z);
        return road===null?ground:Math.max(ground,road);
      }
      if (!this.terrain) return 0;
      const c = this.terrain.cols.get(this.terrain.key(Math.floor(x), Math.floor(z)));
      return c ? c.level : null;
    },

    local(st, x, y, z) {
      // 섬 로컬 좌표(+Z가 허브 방향)를 월드로
      const c = Math.cos(st.rotY), s = Math.sin(st.rotY);
      return new B.Vector3(st.pos.x + x * c + z * s, y, st.pos.z - x * s + z * c);
    },

    toLocal(st, v) {
      const dx = v.x - st.pos.x, dz = v.z - st.pos.z;
      const c = Math.cos(st.rotY), s = Math.sin(st.rotY);
      return { x: dx * c - dz * s, z: dx * s + dz * c };
    },

    // 단계 색을 어둡게/밝게 섞은 보조색
    tint(hex, mixHex, amount) {
      const a = B.Color3.FromHexString(hex), b = B.Color3.FromHexString(mixHex);
      return B.Color3.Lerp(a, b, amount).toHexString();
    },

    buildRoom(st) {
      const s = this.scene;
      const P = (mesh, x, y, z) => { mesh.parent = st.node; mesh.position.set(x, y, z); mesh.metadata = { stageId: st.id }; return mesh; };
      const deep = this.tint(st.color, '#0b1026', 0.55);   // 벽 안쪽 어두운 톤
      const soft = this.tint(st.color, '#1a2040', 0.35);   // 가구에 쓰는 단계색
      // 바닥: 업무 단지의 세라믹 데크
      const floor = P(B.MeshBuilder.CreateBox('floor', { width: 12.4, height: 0.16, depth: 11.4 }, s), 0, 0.08, 0);
      floor.material = this.pbr(`office-floor-${st.id}`,'#b1c3ce',.08,.78,'stone');
      this.receiveShadow(floor);
      // 러그: 단계색
      P(this.box('rug', 5.2, 0.05, 4.2, soft), 2.4, 0.18, 2.4).isPickable = false;
      // 벽: 바깥은 단계색, 안쪽은 어두운 단계색 패널
      P(this.box('wall-back', 12.6, 3.2, 0.3, '#233e56'), 0, 1.6, -5.75);
      P(this.box('wall-side', 0.3, 3.2, 11.6, '#233e56'), -6.2, 1.6, 0);
      P(this.box('wall-back-in', 12.2, 2.9, 0.06, deep), 0, 1.55, -5.57).isPickable = false;
      P(this.box('wall-side-in', 0.06, 2.9, 11.2, deep), -6.02, 1.55, 0).isPickable = false;
      P(this.box('wall-cap', 12.9, 0.14, 0.5, this.tint(st.color, '#ffffff', 0.35)), 0, 3.27, -5.75);
      P(this.box('wall-cap2', 0.5, 0.14, 11.9, this.tint(st.color, '#ffffff', 0.35)), -6.2, 3.27, 0);
      // 벽 화면(단계 대시보드)
      P(this.box('board', 3.6, 1.7, 0.08, '#0d1326'), -3.2, 2.05, -5.5);
      P(this.box('board-glow', 3.2, 1.3, 0.02, st.color, { emissive: 0.7, unlit: true }), -3.2, 2.05, -5.45).isPickable = false;
      [[-4.3, 2.35, 1.6], [-3.1, 2.1, 0.9], [-2.3, 2.45, 1.2]].forEach(([bx, by, bw], i) => {
        P(this.box(`board-bar-${i}`, bw, 0.12, 0.02, '#0d1326'), bx, by, -5.43).isPickable = false;
      });
      // 책상 3개(뒤 벽을 향해 앉음) + 옆 벽 책상
      [-3.4, 0.2, 3.8].forEach((x, i) => this.buildDesk(st, x, -3.6, 0, i));
      this.buildDesk(st, -4.0, 1.6, Math.PI / 2, 3);
      // 책장
      const shelf = P(this.box('shelf', 1.8, 2.4, 0.5, '#354e65'), 4.9, 1.2, -5.3);
      ['#e65fb8', '#4f8df7', '#f2a444', '#2ec4a6', '#8b6cf0', '#ff7a59'].forEach((hex, i) => {
        const book = this.box(`book-${i}`, 0.22, 0.6, 0.3, hex);
        book.parent = shelf; book.position.set(-0.65 + (i % 5) * 0.3, 0.6 - Math.floor(i / 3) * 0.9, 0.05);
        book.isPickable = false;
      });
      // 소파·탁자·램프·식물
      P(this.box('sofa', 2.4, 0.55, 1.0, soft), 2.6, 0.42, 3.4);
      P(this.box('sofa-back', 2.4, 0.5, 0.25, deep), 2.6, 0.9, 3.9);
      P(this.box('sofa-arm-l', 0.25, 0.4, 1.0, deep), 1.35, 0.75, 3.4).isPickable = false;
      P(this.box('sofa-arm-r', 0.25, 0.4, 1.0, deep), 3.85, 0.75, 3.4).isPickable = false;
      const table = B.MeshBuilder.CreateCylinder('table', { height: 0.45, diameter: 1.1, tessellation: 16 }, s);
      P(table, 2.6, 0.38, 1.9).material = this.mat('table', '#b8cdda');
      const lampPole = B.MeshBuilder.CreateCylinder('lamp', { height: 2.2, diameter: 0.08, tessellation: 8 }, s);
      P(lampPole, 5.2, 1.2, 3.6).material = this.mat('pole', '#8d93ad');
      const bulb = B.MeshBuilder.CreateSphere('bulb', { diameter: 0.55, segments: 10 }, s);
      P(bulb, 5.2, 2.45, 3.6).material = this.mat('bulb', '#ffe9b3', { emissive: 1.0, unlit: true });
      bulb.isPickable = false;
      this.buildPlant(st, -5.0, 4.6);
      this.buildPlant(st, 5.3, -4.4);
      this.buildPlant(st, -5.2, -4.6);
      // 입구 바닥 띠(단계색 발광)
      P(this.box('edge', 12.4, 0.08, 0.25, st.color, { emissive: 0.6, unlit: true }), 0, 0.2, 5.6).isPickable = false;

      // 열린 안쪽과 낮은 유리 캐노피: 실무 동료를 가리지 않는 미래 업무 건물 외피.
      P(this.box('office-back-glass',11.8,1.4,.12,'#4591a6',{alpha:.45}),0,4.0,-5.7).isPickable=false;
      P(this.box('office-upper-beam',13,.23,.5,'#cedce4'),0,4.85,-5.7);
      P(this.box('office-side-canopy',.28,.23,11.8,'#cedce4'),-6.2,4.85,0);
      for(const x of [-6,0,6])P(this.box('office-frame',.24,4.8,.38,'#b9ceda'),x,2.4,-5.7);
      P(this.box('office-roof-trace',12.5,.08,.1,st.color,{emissive:.65,unlit:true}),0,4.97,-5.7).isPickable=false;
      const idx=space.data ? space.data.stages.findIndex(v=>v.id===st.id) : 0;
      if(idx===0){
        const dish=B.MeshBuilder.CreateSphere('news-observatory',{diameter:2.4,segments:12},s);P(dish,4.7,4.4,-4.7).material=this.mat('observatory','#70ccda',{emissive:.25});
      }else if(idx===2){
        const fin=P(this.box('studio-fin',2.8,2.8,.22,'#9fb7ce'),4.7,4.3,-4.8);fin.rotation.z=-.35;
      }else if(idx===3){
        P(this.box('delivery-docking',3.8,.3,2.1,'#203d57'),4.8,3.65,-5.5);
        P(this.box('delivery-beacon',.3,2,.3,st.color,{emissive:.6,unlit:true}),5.7,4.7,-5.5);
      }else if(idx===4){
        const arc=B.MeshBuilder.CreateTorus('operations-antenna',{diameter:3,thickness:.16,tessellation:24},s);P(arc,4.6,4.5,-5).material=this.mat('operations-rim','#8ae3df',{emissive:.55,unlit:true});arc.rotation.x=Math.PI/2;
      }

      st.node.getChildMeshes().forEach(m=>{
        if(/^(wall-back|wall-side)$/.test(m.name))m.material=this.pbr('office-shell','#2a455b',.5,.42,'metal');
        else if(/office-frame|office-upper-beam|office-side-canopy|wall-cap|desk-top/.test(m.name))m.material=this.pbr('office-trim','#bbced9',.45,.4,'metal');
        else if(/office-back-glass/.test(m.name))m.material=this.pbr('office-glazing','#377e95',.3,.19);
      });
      // 방 안 모든 물체가 그림자를 드리우고 받는다
      st.node.getChildMeshes().forEach((m) => { if (m.name !== 'edge' && !/glow|screen|bulb|board-bar/.test(m.name)) this.castShadow(m); this.receiveShadow(m); });
      if(idx===0)st.atriumArchitecture=this.buildArchitecture('atrium',st.node);
    },

    buildDesk(st, x, z, rotY, slot) {
      const g = new B.TransformNode(`desk-${st.id}-${slot}`, this.scene);
      g.parent = st.node;
      g.position.set(x, 0, z);
      g.rotation.y = rotY;
      const add = (mesh, px, py, pz) => { mesh.parent = g; mesh.position.set(px, py, pz); mesh.metadata = { stageId: st.id }; return mesh; };
      add(this.box('desk-top', 2.2, 0.1, 1.0, '#b8cdda'), 0, 0.88, 0);
      add(this.box('desk-front', 2.2, 0.6, 0.06, '#233e56'), 0, 0.52, -0.47);
      [[-1, -0.4], [1, -0.4], [-1, 0.4], [1, 0.4]].forEach(([lx, lz], i) => add(this.box(`leg-${i}`, 0.08, 0.76, 0.08, '#2b2f44'), lx, 0.48, lz));
      add(this.box('monitor', 0.95, 0.6, 0.06, '#1b2036'), 0, 1.28, -0.3);
      add(this.box('monitor-stand', 0.1, 0.25, 0.1, '#2b2f44'), 0, 1.0, -0.3);
      const screen = add(this.box('screen', 0.82, 0.48, 0.02, st.color, { emissive: 0.9, unlit: true }), 0, 1.28, -0.26);
      screen.isPickable = false;
      add(this.box('keyboard', 0.7, 0.04, 0.22, '#3a4060'), 0, 0.95, 0.15);
      add(this.box('mug', 0.14, 0.16, 0.14, st.color), 0.8, 1.0, 0.1).isPickable = false;
      add(this.box('chair-seat', 0.62, 0.1, 0.62, '#1f2440'), 0, 0.6, 1.0);
      add(this.box('chair-back', 0.62, 0.7, 0.1, '#1f2440'), 0, 1.0, 1.3);
      add(this.box('chair-post', 0.08, 0.45, 0.08, '#2b2f44'), 0, 0.35, 1.0);
      // Screens remain independent; desk tops receive a room-specific material below.
      const groups = new Map();
      for (const mesh of g.getChildMeshes()) {
        if (mesh === screen || mesh.name === 'desk-top') continue;
        if (!groups.has(mesh.material)) groups.set(mesh.material, []);
        groups.get(mesh.material).push(mesh);
      }
      this.deskDetailTemplates ||= new Map();
      for (const parts of groups.values()) {
        const name = parts[0].name, pickable = parts.some(mesh => mesh.isPickable);
        const key = name + ':' + parts[0].material.uniqueId;
        parts.forEach(mesh => { mesh.parent = null; });
        let template = this.deskDetailTemplates.get(key);
        if (!template || template.isDisposed()) {
          template = B.Mesh.MergeMeshes(parts, true, true, undefined, false, false);
          template.name = 'desk-template-' + name; template.isVisible = false; template.isPickable = false;
          template.freezeWorldMatrix();
          this.deskDetailTemplates.set(key, template);
        } else parts.forEach(mesh => mesh.dispose());
        const instance = template.createInstance('desk-static-' + name);
        instance.parent = g; instance.isVisible = true;
        instance.metadata = { stageId: st.id }; instance.isPickable = pickable;
        instance.computeWorldMatrix(true); instance.freezeWorldMatrix();
      }
      const sit = this.local(st, x + Math.sin(rotY) * 1.0, 0, z + Math.cos(rotY) * 1.0);
      st.desks.push({ slot, sitPos: sit, faceY: st.rotY + rotY + Math.PI, screen, taken: null, localX: x, localZ: z, rotY });
    },

    buildPlant(st, x, z) {
      const pot = this.box('pot', 0.7, 0.6, 0.7, '#9db9c9');
      pot.parent = st.node; pot.position.set(x, 0.42, z); pot.metadata = { stageId: st.id };
      const leaves = this.box('leaves', 1.0, 1.0, 1.0, '#3f9f4e');
      leaves.parent = st.node; leaves.position.set(x, 1.3, z); leaves.isPickable = false;
      const leaves2 = this.box('leaves2', 0.7, 0.7, 0.7, '#58c46e');
      leaves2.parent = st.node; leaves2.position.set(x + 0.25, 1.95, z - 0.2); leaves2.isPickable = false;
    },

    // 광장에서 방 입구까지의 길. 바닥 블록은 buildTerrain이 깔고, 여기서는 양쪽 발광 띠만 둔다.
    buildPath(st) {
      const dir = st.pos.clone().normalize();
      const start = dir.scale(HUB_R - 0.4);
      const end = this.local(st, 0, 0, ISLAND_D / 2 + 0.2);
      const len = B.Vector3.Distance(start, end);
      const mid = B.Vector3.Center(start, end);
      const holder = new B.TransformNode(`path-${st.id}`, this.scene);
      holder.parent = st.node.parent || null;
      holder.position = mid;
      holder.rotation.y = Math.atan2(end.x - start.x, end.z - start.z);
      [-1, 1].forEach((side) => {
        const rail = this.box(`rail-${st.id}-${side}`, 0.14, 0.06, len, st.color, { emissive: 0.8, unlit: true });
        rail.parent = holder;
        rail.position.set(side * (BRIDGE_W / 2 + 0.2), 0.08, 0);
        rail.isPickable = false;
      });
      st.bridge = { start, end, len, color: st.color, holder };
      st.node.onDisposeObservable.add(() => holder.dispose());
    },

    // ---------------- 아바타 ----------------
    buildAvatar(name, skin, shirt, hair) {
      const s=this.scene,root=new B.TransformNode('avatar-'+name,s),hipY=.78,high=QUALITY!=='low';
      const make=(n,w,h,d,hex)=>{const m=this.box(name+'-'+n,w,h,d,hex);m.parent=root;m.isPickable=false;return m;};
      const body=make('body',.62,.78,.34,shirt);body.position.y=hipY+.39;
      const head=make('head',.58,.58,.58,skin);head.position.y=hipY+.78+.31;
      const limb=(n,w,h,d,hex,px,py)=>{
        const pivot=new B.TransformNode(name+'-'+n+'-pivot',s);pivot.parent=root;pivot.position.set(px,py,0);
        const mesh=this.box(name+'-'+n,w,h,d,hex);mesh.parent=pivot;mesh.position.y=-h/2;mesh.isPickable=false;
        return pivot;
      };
      const legL=limb('legL',.28,hipY,.3,'#2b3350',-.16,hipY),legR=limb('legR',.28,hipY,.3,'#2b3350',.16,hipY);
      const armL=limb('armL',.22,.72,.24,skin,-.44,hipY+.74),armR=limb('armR',.22,.72,.24,skin,.44,hipY+.74);
      const marker=B.MeshBuilder.CreateSphere(name+'-marker',{diameter:.26,segments:8},s);
      marker.parent=root;marker.position.y=hipY+.78+.95;marker.isPickable=false;
      marker.material=this.mat('marker','#4ad994',{emissive:1,unlit:true});
      const trim=this.pbr('avatar-trim','#dbe8ef',.5,.4,'metal'),gear=this.pbr('avatar-gear','#24394c',.6,.35,'metal');
      const accent=this.mat('avatar-badge','#8cfff1',{emissive:.3,unlit:true}),hairMat=this.mat('avatar-hair',hair),ink=this.mat('avatar-face','#1a1e2e');
      const whites=this.mat('avatar-eye-white','#f4f7ed'),groups=new Map();
      const detail=(part,w,h,d,material,x,y,z,parent=root)=>{
        const mesh=B.MeshBuilder.CreateBox(name+'-'+part,{width:w,height:h,depth:d},s);
        mesh.position.set(x,y,z);mesh.material=material;
        if(!groups.has(parent))groups.set(parent,new Map());
        const byMaterial=groups.get(parent);if(!byMaterial.has(material))byMaterial.set(material,[]);byMaterial.get(material).push(mesh);
      };
      detail('hair-cap',.62,.17,.62,hairMat,0,2.135,0);
      detail('hair-back',.62,.31,.13,hairMat,0,1.98,-.27);
      for(const side of [-1,1]){
        detail('hair-temple',.075,.24,.38,hairMat,side*.275,2.02,-.07);
        if(high)detail('brow',.13,.025,.022,hairMat,side*.13,1.995,.307);
        detail('eye',high?.065:.1,.095,.018,ink,side*.13,1.9,high?.328:.31);
        if(high){
          detail('eye-white',.13,.105,.026,whites,side*.13,1.9,.307);
          detail('eye-glint',.018,.023,.01,accent,side*.13-.012,1.92,.344);
        }
        detail('earpiece',.12,.22,.26,trim,side*.345,hipY+1.09,0);
      }
      for(const x of high?[-.2,0,.2]:[-.16,.16])detail('fringe',high?.2:.31,.13+(x<0?.06:0),.11,hairMat,x,2.065,.27);
      detail('mouth',.12,.025,.015,ink,0,1.735,.31);
      if(high)detail('nose',.075,.085,.08,head.material,0,1.815,.327);
      detail('collar',.66,.1,.38,trim,0,hipY+.72,0);
      detail('chest-plate',.39,.34,.055,trim,0,hipY+.47,.1975);
      detail('belt',.66,.1,.38,trim,0,hipY+.09,0);
      detail('badge',.1,.075,.018,accent,-.095,hipY+.53,.237);
      detail('pack',.45,.5,.13,trim,0,hipY+.42,-.235);
      detail('pack-inset',.27,.31,.03,ink,0,hipY+.42,-.33);
      [armL,armR].forEach(arm=>{
        detail('sleeve',.24,.26,.26,body.material,0,-.13,0,arm);
        detail('shoulder',.28,.085,.29,trim,0,-.045,0,arm);
        detail('glove',.245,.2,.27,gear,0,-.64,.015,arm);
        detail('glove-cuff',.255,.065,.28,gear,0,-.53,.015,arm);
      });
      [legL,legR].forEach(leg=>{
        detail('boot',.305,.22,.38,gear,0,-hipY+.11,.025,leg);
        detail('boot-toe',.31,.1,.15,gear,0,-hipY+.065,.17,leg);
      });
      // Hidden templates outlive individual avatars; instances share each rigid part's draw call.
      this.avatarDetailTemplates ||= new Map();
      for(const [parent,materials] of groups)for(const parts of materials.values()){
        const detailName=parts[0].name;
        const limb=parent===root?'root':parent===armL||parent===armR?'arm':'leg';
        const key=QUALITY+':'+limb+':'+parts[0].material.uniqueId;
        let template=this.avatarDetailTemplates.get(key);
        if(!template||template.isDisposed()){
          template=B.Mesh.MergeMeshes(parts,true,true,undefined,false,false);
          if(!template)continue;
          template.name='avatar-template-'+key;template.isVisible=false;template.isPickable=false;
          this.avatarDetailTemplates.set(key,template);
        }else parts.forEach(mesh=>mesh.dispose());
        const mesh=template.createInstance(detailName+'-detail');
        mesh.parent=parent;mesh.isVisible=true;mesh.isPickable=false;
      }
      root.getChildMeshes().forEach(mesh=>{if(mesh!==marker&&!mesh.material?.disableLighting){this.castShadow(mesh);this.receiveShadow(mesh.sourceMesh||mesh);}});
      return {root,legL,legR,armL,armR,head,body,marker,hipY,phase:Math.random()*6};
    },

    setPose(av, pose) {
      if (pose === 'sit') {
        av.root.position.y = 0.5 - av.hipY + 0.02;
        av.legL.rotation.x = -Math.PI / 2; av.legR.rotation.x = -Math.PI / 2;
        av.armL.rotation.x = -0.9; av.armR.rotation.x = -0.9;
      } else {
        av.legL.rotation.x = 0; av.legR.rotation.x = 0; av.armL.rotation.x = 0; av.armR.rotation.x = 0;
      }
    },

    animateWalk(av, t, speed) {
      const k = Math.sin(t * 9 + av.phase) * Math.min(0.9, speed * 0.3);
      av.legL.rotation.x = k; av.legR.rotation.x = -k;
      av.armL.rotation.x = -k * 0.8; av.armR.rotation.x = k * 0.8;
    },

    markerColor(status) {
      return { running: '#4ad994', waiting: '#f5c451', error: '#ff6b7a', idle: '#6b7390' }[status] || '#6b7390';
    },

    clearAgents() {
      space.agents.forEach((a) => a.av.root.dispose());
      space.agents = [];
      space.stages.forEach((st) => st.desks.forEach((d) => { d.taken = null; }));
    },

    standingSpot(index) {
      // shortcut: 현재 콘텐츠 9개 역할 기준. 역할이 늘면 좌석·회의 구역을 확장한다.
      return { x:-0.8 + (index % 3) * 1.8, z:-0.4 + Math.floor(index / 3) * 1.5 };
    },

    buildAgents(agents) {
      this.clearAgents();
      const standing = new Map();
      const skins = ['#f1c9a5', '#d9a57c', '#a9774f', '#f5d6b8', '#7a4a2e'];
      const shirts = ['#ff7a59', '#4f8df7', '#2ec4a6', '#f2a444', '#8b6cf0', '#e65fb8', '#59c3ff', '#c9d1ff'];
      const hairs = ['#2b1d14', '#5a3a22', '#1a1a1a', '#b56b3a', '#d8c7a8', '#3a2a5a'];
      agents.forEach((a, i) => {
        const st = space.stages.find((s) => s.id === a.stageId) || space.stages[0];
        const desk = st.desks.find((d) => !d.taken) || null;
        const av = this.buildAvatar(a.id, skins[i % skins.length], shirts[i % shirts.length], hairs[i % hairs.length]);
        const agent = Object.assign({}, a, { av, stage: st, desk, mode: 'seated', path: null, pathIdx: 0, pos: null, walkT: 0 });
        if (desk) {
          desk.taken = agent;
          agent.pos = desk.sitPos.clone();
          av.root.position.copyFrom(agent.pos);
          av.root.rotation.y = desk.faceY;
          this.setPose(av, 'sit');
        } else {
          const index = standing.get(st.id) || 0;
          standing.set(st.id, index + 1);
          const p = this.standingSpot(index);
          const spot = this.local(st, p.x, 0, p.z);
          agent.pos = spot; agent.mode = 'standing';
          av.root.position.copyFrom(spot);
          av.root.rotation.y = st.rotY + Math.PI;
          this.setPose(av, 'stand');
        }
        this.applyStatus(agent);
        space.agents.push(agent);
      });
    },

    applyStatus(agent) {
      agent.av.marker.material = this.mat('marker', this.markerColor(agent.status), { emissive: 1.0, unlit: true });
      if (agent.desk) {
        const on = agent.status === 'running' || agent.status === 'waiting';
        agent.desk.screen.material = this.mat('screen', on ? agent.stage.color : '#1b2036', { emissive: on ? 0.9 : 0.05, unlit: true });
      }
    },

    updateAgentStatuses(agents) {
      const byId = new Map(agents.map((a) => [a.id, a]));
      space.agents.forEach((agent) => {
        const next = byId.get(agent.id);
        if (!next) return;
        agent.status = next.status; agent.task = next.task; agent.name = next.name; agent.engine = next.engine; agent.model = next.model;
        this.applyStatus(agent);
      });
    },

    // 동료가 허브(기억)까지 걸어갔다 돌아오는 경로
    memoryTrip(agent) {
      if (REDUCED || document.hidden || space.rosterOpen) return;
      if (!agent.desk || agent.mode !== 'seated') return;
      const st = agent.stage;
      const d = agent.desk;
      const standLocal = d.rotY === 0 ? [d.localX, d.localZ + 2.0] : [d.localX + 2.0, d.localZ];
      const out = [
        this.local(st, standLocal[0], 0, standLocal[1]),
        this.local(st, 0.6, 0, 2.6),
        this.local(st, 0, 0, ISLAND_D / 2 - 0.8),
        st.bridge.start.clone().add(st.pos.clone().normalize().scale(0.6)),
        st.pos.clone().normalize().scale(3.6),
      ];
      const back = out.slice().reverse();
      agent.path = out.concat([null], back); // null = 허브에서 잠시 멈춤
      agent.pathIdx = 0; agent.mode = 'walking'; agent.pause = 0;
      agent.av.root.position.y = 0;
      this.setPose(agent.av, 'stand');
    },

    stepAgents(dt) {
      space.agents.forEach((agent) => {
        if (agent.mode !== 'walking') return;
        if (agent.pause > 0) { agent.pause -= dt; return; }
        const target = agent.path[agent.pathIdx];
        if (target === null) { agent.pause = 2.2 + Math.random() * 1.5; agent.pathIdx++; agent.av.root.rotation.y = Math.atan2(-agent.pos.x, -agent.pos.z); this.setPose(agent.av, 'stand'); return; }
        if (!target) {
          // 끝: 자리에 앉기
          agent.mode = 'seated'; agent.path = null;
          agent.pos.copyFrom(agent.desk.sitPos);
          agent.av.root.position.copyFrom(agent.pos);
          agent.av.root.rotation.y = agent.desk.faceY;
          this.setPose(agent.av, 'sit');
          return;
        }
        const diff = target.subtract(agent.pos); diff.y = 0;
        const dist = diff.length();
        const speed = 2.6;
        if (dist < 0.15) { agent.pathIdx++; return; }
        const step = diff.scale(Math.min(1, (speed * dt) / dist));
        agent.pos.addInPlace(step);
        agent.av.root.position.copyFrom(agent.pos);
        agent.av.root.rotation.y = Math.atan2(diff.x, diff.z);
        agent.walkT += dt;
        this.animateWalk(agent.av, agent.walkT, speed);
      });
    },

    // ---------------- 흐름 점 ----------------
    spawnFlow(flow) {
      if (REDUCED || document.hidden || space.rosterOpen) return;
      const from = space.stages.find((s) => s.id === flow.from);
      const to = space.stages.find((s) => s.id === flow.to);
      if (!from || !to || from === to) return;
      const key = `${flow.from}>${flow.to}:${flow.itemId}`;
      if (this.flowKeys.has(key)) return;
      this.flowKeys.add(key);
      setTimeout(() => this.flowKeys.delete(key), 60000);
      const mesh = B.MeshBuilder.CreateSphere('flow', { diameter: 0.5, segments: 8 }, this.scene);
      mesh.material = this.mat('flow', to.color, { emissive: 1.2, unlit: true });
      mesh.isPickable = false;
      this.flows.push({ mesh, legs: [[from.bridge.end, from.bridge.start], [to.bridge.start, to.bridge.end]], leg: 0, t: 0, speed: 0.28 });
    },

    stepFlows(dt) {
      for (let i = this.flows.length - 1; i >= 0; i--) {
        const f = this.flows[i];
        f.t += dt * f.speed;
        if (f.t >= 1) { f.t = 0; f.leg++; }
        if (f.leg >= f.legs.length) { f.mesh.dispose(); this.flows.splice(i, 1); continue; }
        const [a, b] = f.legs[f.leg];
        const p = B.Vector3.Lerp(a, b, f.t);
        p.y = 0.45 + Math.sin(f.t * Math.PI) * 0.6;
        f.mesh.position.copyFrom(p);
      }
    },

    // ---------------- 이동 가능 영역 ----------------
    // 블록 땅 위이고, 현재 높이에서 한 칸 이내로만 오르내릴 수 있다. 벽과 책상은 통과하지 않는다.
    walkable(v, fromY, clearance = .4) {
      if (space.layer === 'meadow') {
        if(Math.abs(v.x)>=780-clearance||Math.abs(v.z)>=780-clearance)return false;
        return !(this.groundCity?.obstacles||[]).some(o=>o.r?Math.hypot(v.x-o.x,v.z-o.z)<o.r+clearance:Math.abs(v.x-o.x)<o.w/2+clearance&&Math.abs(v.z-o.z)<o.d/2+clearance);
      }
      const h = this.heightAt(v.x, v.z);
      if(workshop.collides(v,clearance))return false;
      if((this.officeObstacles||[]).some(o=>Math.hypot(v.x-o.x,v.z-o.z)<o.r+clearance))return false;
      if (h === null) return false;
      if (fromY !== undefined && h - fromY > 1.01) return false;
      for (const st of space.stages) {
        const l = this.toLocal(st, v);
        if (Math.abs(l.x) > ISLAND_W / 2 || Math.abs(l.z) > ISLAND_D / 2) continue;
        if (l.z < -5.3 || l.x < -5.8) return false;                                  // 뒤 벽·옆 벽
        if (l.z > -4.5 && l.z < -2.6 && l.x > -4.6 && l.x < 5.0) return false;        // 책상 줄
        if (l.x > -5.2 && l.x < -3.0 && l.z > 0.4 && l.z < 2.8) return false;          // 옆 책상
      }
      return true;
    },

    tick() {
      const dt = Math.min(0.1, this.engine.getDeltaTime() / 1000);
      this.time += dt;
      this.stepTraffic(dt);
      if (!REDUCED) {
        this.hub.rings.forEach((r, i) => { r.rotation.y += dt * (0.08 + i * 0.05) * (i % 2 ? -1 : 1); });
        if (this.sky) this.sky.rotation.y += dt * 0.001;
        (!this.trafficPaused ? this.airships || [] : []).forEach((a) => { const t = this.trafficClock * 0.045 + a.phase; a.root.position.set(Math.sin(t) * 65, a.height + Math.sin(t * 2) * 1.5, 72 + Math.cos(t) * 26); a.root.rotation.y = -t; });
        const pulse = 1 + Math.sin(this.time * 1.6) * 0.06;
        this.hub.core.scaling.set(pulse, pulse, pulse);
        this.stepAgents(dt);
        this.stepFlows(dt);

      }
      space.agents.forEach((a) => { a.av.marker.isVisible = true; });
      controls.tick(dt);
      document.body.classList.toggle('wide-overview', space.view === 'overview' && controls.overview.radius > 105);
      this.hudElapsed = (this.hudElapsed || 0) + dt;
      if (this.hudElapsed >= 1 / 15) { this.hudElapsed = 0; hud.tick(); }
    },
  };

  // ======================================================================
  // controls — 카메라와 입력
  // ======================================================================
  const OVERVIEW_HOME = { alpha: -Math.PI / 2.35, beta: 1.15, radius: 210, target: new B.Vector3(0, -18, 0) };

  const controls = {
    overview: null, walk: null, player: null, keys: new Set(),
    yaw: Math.PI, pitch: 0.18, vy: 0, dragging: false, lastX: 0, lastY: 0,
    focused: null,   // 확대해서 보고 있는 방 ID 또는 'hub'
    vehicleSpeed: 0, touchWalkEnabled: false,



    setVehicleSpeed(speed) {
      if(typeof speed!=='number'||!Number.isFinite(speed)||speed<0||speed>36)return false;
      if(speed>0&&space.layer!=='meadow')return false;
      this.vehicleSpeed=speed;this.vy=0;this.keys.delete(' ');
      if(this.player){this.player.grounded=true;this.player.pos.y=world.heightAt(this.player.pos.x,this.player.pos.z)??this.player.pos.y;}
      return true;
    },

    enableTouchWalk(enabled) {
      this.touchWalkEnabled=enabled===true;this.keys.clear();
      if(!this.touchWalkEnabled&&isPhone()&&space.view==='walk')this.setView('overview');
      return this.touchWalkEnabled;
    },

    setLayer(layer, walk = false) {
      if (!['office', 'meadow'].includes(layer)) return;
      hud.closePanel(); this.keys.clear(); this.vy = 0; this.focused = null;
      space.layer = layer;
      if(layer==='office')this.setVehicleSpeed(0);
      const p = this.player, point = world.portals[layer];
      p.pos.copyFrom(point.add(new B.Vector3(0, 0, layer === 'meadow' ? -18 : -6))); p.pos.y = world.heightAt(p.pos.x, p.pos.z) ?? point.y;
      p.grounded = true; p.av.root.position.copyFrom(p.pos);
      this.yaw = 0; this.pitch = 0.18;
      this.walk.position.copyFrom(p.pos.add(new B.Vector3(0, 4, -7)));
      this.walk.setTarget(p.pos.add(new B.Vector3(0, 1.5, 0)));
      this.setView(walk && (!isPhone() || this.touchWalkEnabled) ? 'walk' : 'overview');
      const home = layer === 'office' ? OVERVIEW_HOME : { alpha: -Math.PI / 2, beta: 1.15, radius: 430, target: new B.Vector3(0, -18, 0) };
      this.animateCamera(home, 1400);
      $('layer-label').textContent = layer === 'office' ? '공중 팀 대지 · 지상 위 약 85m' : '지상 미래도시 · 폭 1,600m';
      $('btn-layer').textContent = layer === 'office' ? '↓ 지상 미래도시로' : '↑ 우리 팀 오피스로';
      document.body.classList.toggle('meadow-layer', layer === 'meadow');
    },

    // 관제 카메라를 부드럽게 이동
    animateCamera(to, ms = 900) {
      const cam=this.overview;
      const from={alpha:cam.alpha,beta:cam.beta,radius:cam.radius,target:cam.target.clone()};
      const end={alpha:to.alpha??from.alpha,beta:to.beta??from.beta,radius:to.radius??from.radius,target:to.target?to.target.clone():from.target.clone()};
      this.cameraTween={from,to:end,elapsed:0,duration:REDUCED?0:ms/1000};
      if(REDUCED||ms===0){cam.setTarget(end.target.clone());cam.alpha=end.alpha;cam.beta=end.beta;cam.radius=end.radius;this.cameraTween=null;cam.getViewMatrix(true);}
    },

    // 방으로 확대: 광장 쪽에서 열린 면을 바라본다
    focusStage(st) {
      if (space.view !== 'overview') return;
      this.focused = st.id;
      const dir = st.pos.scale(-1).normalize();
      this.animateCamera({ alpha: Math.atan2(dir.z, dir.x), beta: 0.98, radius: 21, target: world.local(st, 0, 1.2, -1.5) });
      $('btn-reset').hidden = false;
    },

    focusHub() {
      if (space.view !== 'overview') return;
      this.focused = 'hub';
      this.animateCamera({ beta: 0.9, radius: 26, target: new B.Vector3(0, 2.5, 0) });
      $('btn-reset').hidden = false;
    },

    resetOverview() {
      this.focused = null;
      $('btn-reset').hidden = true;
      if (space.view === 'overview') this.animateCamera(space.layer === 'office' ? Object.assign({}, OVERVIEW_HOME, { target: OVERVIEW_HOME.target.clone() }) : { alpha: -Math.PI / 2, beta: 1.15, radius: 430, target: new B.Vector3(0, -18, 0) }, 1000);
    },

    // 걷기 시점으로 바꾸고 방 입구에 세운다
    enterStage(st) {
      if (isPhone() && !this.touchWalkEnabled) return;
      if (space.layer !== 'office') this.setLayer('office');
      const p = this.player;
      const entrance = world.local(st, 0, 0, ISLAND_D / 2 + 1.2);
      p.pos.set(entrance.x, world.heightAt(entrance.x, entrance.z) ?? 0, entrance.z);
      this.yaw = st.rotY + Math.PI;
      this.pitch = 0.18;
      p.av.root.position.copyFrom(p.pos);
      p.av.root.rotation.y = this.yaw;
      const fwd = new B.Vector3(Math.sin(this.yaw), 0, Math.cos(this.yaw));
      this.walk.position = p.pos.add(fwd.scale(-6.8)).add(new B.Vector3(0, 2.9 + this.pitch * 3.2, 0));
      this.setView('walk');
      hud.closePanel();
    },

    init() {
      const s = world.scene, canvas = world.canvas;
      this.overview = new B.ArcRotateCamera('overview', -Math.PI / 2, 1.15, 430, new B.Vector3(0, -18, 0), s);
      this.overview.lowerRadiusLimit = 26; this.overview.upperRadiusLimit = 800;
      this.overview.lowerBetaLimit = 0.45; this.overview.upperBetaLimit = 1.38;
      this.overview.wheelPrecision = 12; this.overview.panningSensibility = 60;
      this.overview.pinchPrecision = 60;
      this.overview.minZ = 0.5; this.overview.maxZ = 4500;
      this.overview.attachControl(canvas, true);
      s.activeCamera = this.overview;

      this.walk = new B.UniversalCamera('walk', new B.Vector3(0, 3, -8), s);
      this.walk.inputs.clear();
      this.walk.minZ = 0.3; this.walk.maxZ = 4500;

      if (QUALITY !== 'low') {
        // 화면 공간 주변광 차폐: 블록 틈과 가구 밑을 어둡게 (톤 매핑보다 먼저 적용되도록 먼저 만든다)
        const ssao = new B.SSAO2RenderingPipeline('ssao', s, { ssaoRatio: 0.5, blurRatio: 0.5 }, [this.overview, this.walk]);
        ssao.radius = 1.6;
        ssao.totalStrength = 1.1;
        ssao.base = 0.08;
        ssao.samples = 16;
        ssao.maxZ = 160;
        ssao.expensiveBlur = false;
        this.ssao = ssao;
      }

      // FXAA handles edges once; avoid a second 4x multisampled post-process buffer.
      const pipeline = new B.DefaultRenderingPipeline('post', true, s, [this.overview, this.walk]);
      pipeline.samples = 1;
      pipeline.fxaaEnabled = true;
      if (QUALITY !== 'low') {
        pipeline.bloomEnabled = true;
        pipeline.bloomThreshold = 0.85;
        pipeline.bloomWeight = 0.18;
        pipeline.bloomKernel = 64;
        pipeline.bloomScale = 0.5;
      }
      pipeline.imageProcessingEnabled = true;
      pipeline.imageProcessing.toneMappingEnabled = true;
      pipeline.imageProcessing.toneMappingType = B.ImageProcessingConfiguration.TONEMAPPING_ACES;
      pipeline.imageProcessing.exposure = 1.0;
      pipeline.imageProcessing.contrast = 1.12;
      pipeline.imageProcessing.vignetteEnabled = true;
      pipeline.imageProcessing.vignetteWeight = 1.6;
      pipeline.imageProcessing.vignetteColor = new B.Color4(0.02, 0.03, 0.08, 0);
      this.pipeline = pipeline;

      const av = world.buildAvatar('player', '#f5d6b8', '#f4f1ea', '#7fe3ff');
      av.marker.isVisible = false;
      av.root.position.set(0, 0, -5.2);
      av.root.rotation.y = Math.PI;
      this.player = { av, pos: new B.Vector3(0, 0, -5.2), grounded: true, walkT: 0 };
      this.setView('overview');

      window.addEventListener('keydown', (e) => this.onKey(e, true));
      window.addEventListener('keyup', (e) => this.onKey(e, false));
      window.addEventListener('blur', () => { this.keys.clear(); this.dragging=false; });
      document.addEventListener('visibilitychange', () => { if(document.hidden){this.keys.clear();this.dragging=false;} });
      canvas.addEventListener('pointerdown', (e) => { if (space.view === 'walk') { this.dragging = true; this.lastX = e.clientX; this.lastY = e.clientY; canvas.setPointerCapture(e.pointerId); } });
      canvas.addEventListener('pointermove', (e) => {
        if (!this.dragging || space.view !== 'walk') return;
        this.yaw -= (e.clientX - this.lastX) * 0.006;
        this.pitch = Math.max(-0.25, Math.min(0.8, this.pitch + (e.clientY - this.lastY) * 0.004));
        this.lastX = e.clientX; this.lastY = e.clientY;
      });
      const stop = () => { this.dragging = false; };
      canvas.addEventListener('pointerup', stop); canvas.addEventListener('pointercancel', stop);
      s.onPointerObservable.add((info) => {
        if (info.type !== B.PointerEventTypes.POINTERTAP || space.view !== 'overview' || workshop.opened) return;
        const pick = info.pickInfo;
        if (!pick || !pick.hit || !pick.pickedMesh) return;
        const meta = pick.pickedMesh.metadata || {};
        if (meta.elevator) this.setLayer(space.layer === 'office' ? 'meadow' : 'office');
        else if (meta.portal) this.setLayer(meta.portal);
        else if (meta.stageId) hud.openStage(meta.stageId);
        else if (meta.hub) hud.openBrain();
      });
      world.syncMotionUI();
      $('btn-traffic').addEventListener('click', () => { if (REDUCED) return; world.trafficPaused = !world.trafficPaused; world.syncMotionUI(); });
      $('btn-rooms').addEventListener('click', () => { const open = $('cards').classList.toggle('mobile-open'); $('btn-rooms').setAttribute('aria-expanded', String(open)); });
      $('btn-layer').addEventListener('click', () => this.setLayer(space.layer === 'office' ? 'meadow' : 'office', space.view === 'walk'));
      $('btn-overview').addEventListener('click', () => this.setView('overview'));
      $('btn-walk').addEventListener('click', () => this.setView('walk'));
      $('btn-reset').addEventListener('click', () => { hud.closePanel(); this.resetOverview(); });
      $('btn-exit').addEventListener('click', () => this.exitSpace());
    },

    // 걷기 시점에서 나가기: 전체 조망으로 복귀
    exitSpace() {
      hud.closePanel();
      this.focused = null;
      this.setView('overview');
      this.resetOverview();
    },

    setView(view) {
      if (view === 'walk' && isPhone() && !this.touchWalkEnabled) view = 'overview';
      space.view = view;
      document.body.classList.toggle('walking-view', view === 'walk');
      const s = world.scene;
      if (view === 'walk') {
        this.overview.detachControl();
        s.activeCamera = this.walk;
        this.player.av.root.setEnabled(true);
        $('help').hidden = false;
        $('btn-reset').hidden = true;
        $('btn-exit').hidden = false;
      } else {
        s.activeCamera = this.overview;
        this.overview.attachControl(world.canvas, true);
        this.player.av.root.setEnabled(false);
        $('help').hidden = true;
        $('btn-exit').hidden = true;
        $('btn-reset').hidden = !this.focused;
        hud.hideAgentCard();
      }
      $('btn-overview').setAttribute('aria-pressed', String(view === 'overview'));
      $('btn-walk').setAttribute('aria-pressed', String(view === 'walk'));
      try { localStorage.setItem('office-world.view', view); } catch (_) { /* 저장 불가 환경 */ }
    },

    onKey(e, down) {
      const k = e.key.toLowerCase();
      if (!down) this.keys.delete(k);
      if (space.rosterOpen || space.buildingOpen || space.resultsOpen || space.playHubOpen) return;
      if (e.target?.closest?.('input, textarea, select, [contenteditable]:not([contenteditable="false"])')) return;
      if (down && k === 'escape') {
        if (space.view === 'walk') { this.exitSpace(); return; }
        hud.closePanel(); this.resetOverview(); return;
      }
      if (e.target?.closest?.('button, summary, a[href]')) return;
      if (down && k === 'm') { this.setView(space.view === 'walk' ? 'overview' : 'walk'); return; }
      if (space.view !== 'walk') return;
      if (down && k === 'r') { this.yaw = this.player.av.root.rotation.y + Math.PI; this.pitch = 0.18; return; }
      if (down && k === 'e') {
        const gate = world.portals[space.layer];
        if (Math.hypot(this.player.pos.x - gate.x, this.player.pos.z - gate.z) < 9) this.setLayer(space.layer === 'office' ? 'meadow' : 'office', true);
        else hud.toggleNearestAgent();
        return;
      }
      if ([' ', 'w', 'a', 's', 'd', 'shift', 'arrowup', 'arrowdown', 'arrowleft', 'arrowright'].includes(k)) {
        e.preventDefault();
        if (down) this.keys.add(k); else this.keys.delete(k);
      }
    },

    tick(dt) {
      if(this.cameraTween){
        const t=this.cameraTween;t.elapsed+=dt;const q=Math.min(1,t.duration?t.elapsed/t.duration:1),u=q*q*(3-2*q),cam=this.overview;
        cam.setTarget(B.Vector3.Lerp(t.from.target,t.to.target,u));
        cam.alpha=t.from.alpha+(t.to.alpha-t.from.alpha)*u;cam.beta=t.from.beta+(t.to.beta-t.from.beta)*u;cam.radius=t.from.radius+(t.to.radius-t.from.radius)*u;
        if(q===1)this.cameraTween=null;
      }
      if (space.view !== 'walk') return;
      const p = this.player;
      const keys = this.keys;
      const fwd = new B.Vector3(Math.sin(this.yaw), 0, Math.cos(this.yaw));
      const right = new B.Vector3(fwd.z, 0, -fwd.x);
      let move = B.Vector3.Zero();
      if (keys.has('w') || keys.has('arrowup')) move.addInPlace(fwd);
      if (keys.has('s') || keys.has('arrowdown')) move.subtractInPlace(fwd);
      if (keys.has('d') || keys.has('arrowright')) move.addInPlace(right);
      if (keys.has('a') || keys.has('arrowleft')) move.subtractInPlace(right);
      const moving = move.lengthSquared() > 0;
      const speed = this.vehicleSpeed>0 ? this.vehicleSpeed : (keys.has('shift') ? 6.2 : 3.3) * (space.layer === 'meadow' ? 3 : 1);
      const groundNow = world.heightAt(p.pos.x, p.pos.z) ?? 0;
      if (moving) {
        move.normalize().scaleInPlace(speed * dt);
        const steps=Math.max(1,Math.ceil(move.length()/.35)),sub=move.scale(1/steps),clearance=this.vehicleSpeed>0?2.2:.4;
        const tryMove=(cand)=>{if(world.walkable(cand,groundNow,clearance)){p.pos.x=cand.x;p.pos.z=cand.z;return true;}return false;};
        for(let i=0;i<steps;i++)if(!tryMove(p.pos.add(sub))){
          if(!tryMove(p.pos.add(new B.Vector3(sub.x,0,0))))tryMove(p.pos.add(new B.Vector3(0,0,sub.z)));
        }
        p.av.root.rotation.y = Math.atan2(move.x, move.z);
        p.walkT += dt;
        if(this.vehicleSpeed>0)world.setPose(p.av,'sit');else world.animateWalk(p.av,p.walkT,speed);
      } else if (p.grounded) {
        world.setPose(p.av,this.vehicleSpeed>0?'sit':'stand');
      }
      const ground = world.heightAt(p.pos.x, p.pos.z) ?? groundNow;
      if (keys.has(' ') && p.grounded && this.vehicleSpeed===0) { this.vy = 6.2; p.grounded = false; }
      if (!p.grounded) {
        this.vy -= 16 * dt;
        p.pos.y += this.vy * dt;
        if (p.pos.y <= ground) { p.pos.y = ground; p.grounded = true; this.vy = 0; }
      } else {
        // 한 칸 계단은 자동으로 오르내린다
        p.pos.y += (ground - p.pos.y) * Math.min(1, dt * 14);
      }
      p.av.root.position.copyFrom(p.pos);
      const camBack = fwd.scale(this.vehicleSpeed>0?-10:-6.8);
      const desired = p.pos.add(camBack).add(new B.Vector3(0,this.vehicleSpeed>0?4.8:2.9+this.pitch*3.2,0));
      this.walk.position = B.Vector3.Lerp(this.walk.position, desired, Math.min(1, dt * 9));
      this.walk.setTarget(p.pos.add(new B.Vector3(0, 1.5, 0)));
    },
  };

  // ======================================================================
  // hud — 오버레이
  // ======================================================================
  const hud = {
    cards: new Map(), brainCard: null, agentCard: null, agentCardTarget: null,
    tickerQueue: [], tickerIdx: 0, tickerTimer: null, seenEvents: new Set(),
    mini: null, miniCtx: null, miniT: 0,
    renderedContent: new WeakMap(),

    replaceContent(element, signature, render, scrollRoot = element) {
      const previous = this.renderedContent.get(element);
      // 결과함도 같은 패널을 쓰므로 다른 화면이 바꾼 DOM은 캐시로 건너뛰지 않는다.
      if (previous?.signature === signature && previous.content === element.innerHTML) return false;
      const active = document.activeElement;
      const focusKey = element.contains(active) ? active?.dataset?.focusKey : null;
      const scrollTop = scrollRoot.scrollTop;
      render();
      this.renderedContent.set(element, { signature, content: element.innerHTML });
      if (focusKey) {
        const matches = [...element.querySelectorAll('[data-focus-key]')].filter(node => node.dataset.focusKey === focusKey);
        if (matches.length === 1 && !matches[0].disabled && !matches[0].hidden) matches[0].focus({ preventScroll: true });
      }
      scrollRoot.scrollTop = scrollTop;
      return true;
    },

    init() {
      $('panel-close').addEventListener('click', () => this.closePanel());
      $('btn-command')?.addEventListener('click', () => this.openBrain());
      $('panel-body').addEventListener('click', (e) => {
        const team = e.target.closest('[data-team]');
        if (team) { this.openStage(team.dataset.team); return; }
        if (!embed.enabled) return;
        const act = e.target.closest('[data-action]');
        if (act) {
          if (data.source !== 'live' || data.error) return;
          const key = `${act.dataset.item}:${act.dataset.action}`;
          if (space.pendingActions.has(key)) return;
          clearTimeout(actionTimers.get(key));
          embed.post({ type: 'action', action: act.dataset.action, itemId: act.dataset.item });
          space.pendingActions.add(key);
          space.embedResult = null;
          act.disabled = true;
          actionTimers.set(key, setTimeout(() => {
            actionTimers.delete(key);
            if (!space.pendingActions.delete(key)) return;
            space.embedResult = { ok: false, message: '응답이 없습니다' };
            if (space.selectedStage) hud.openStage(space.selectedStage, true);
          }, 15000));
          return;
        }
        const op = e.target.closest('[data-open]');
        if (op) embed.post({ type: 'open', view: op.dataset.open, itemId: op.dataset.item });
      });
      $('panel-foot').addEventListener('click', (e) => {
        const btn = e.target.closest('[data-enter]');
        if (!btn) return;
        const st = space.stages.find((s) => s.id === btn.dataset.enter);
        if (st) controls.enterStage(st);
      });
      this.mini = $('minimap'); this.miniCtx = this.mini.getContext('2d');
      this.brainCard = document.createElement('button');
      this.brainCard.type = 'button';
      this.brainCard.className = 'card brain';
      this.brainCard.addEventListener('click', () => this.openBrain());
      $('cards').appendChild(this.brainCard);
      this.agentCard = document.createElement('div');
      this.agentCard.className = 'card agent';
      this.agentCard.hidden = true;
      $('cards').appendChild(this.agentCard);
    },

    project(v) {
      // 렌더 해상도(장치 픽셀)로 투영한 뒤 CSS 픽셀로 환산한다.
      const s = world.scene, e = world.engine;
      const scale = e.getHardwareScalingLevel();
      const p = B.Vector3.Project(v, B.Matrix.Identity(), s.getTransformMatrix(), s.activeCamera.viewport.toGlobal(e.getRenderWidth(), e.getRenderHeight()));
      return { x: p.x * scale, y: p.y * scale, visible: p.z > 0 && p.z < 1 };
    },

    rebuild(d) {
      $('office-name').textContent = `${d.office.name} · 오피스 월드`;
      explorationNames.clear(); explorationNames.set('hub', '중앙 관제 구역 둘러보기');
      space.stages.forEach((st, i) => explorationNames.set(st.id, `공중 ${i + 1}구역 · ${st.name} 둘러보기`));
      exploration();
      $('cards').querySelectorAll('.card.stage').forEach((el) => el.remove());
      this.cards.clear();
      const departments = $('department-nav');
      departments.replaceChildren();
      space.stages.forEach((st, index) => {
        const el = document.createElement('button');
        el.type = 'button';
        el.className = 'card stage';
        el.style.setProperty('--stage', st.color);
        el.addEventListener('click', () => this.openStage(st.id));
        $('cards').appendChild(el);
        this.cards.set(st.id, el);
        const shortcut = document.createElement('button');
        shortcut.type = 'button';
        shortcut.dataset.department = st.id;
        shortcut.style.setProperty('--stage', st.color);
        shortcut.textContent = `${index + 1} · ${st.name}`;
        shortcut.title = `${st.name} 위치와 맡은 업무 보기`;
        shortcut.setAttribute('aria-controls', 'panel');
        shortcut.addEventListener('click', () => this.openStage(st.id));
        departments.appendChild(shortcut);
      });
      this.refresh(d);
    },

    refresh(d) {
      const command = $('btn-command');
      if (command) command.disabled = false;
      space.stages.forEach((st, index) => {
        const el = this.cards.get(st.id);
        if (!el) return;
        const agents = space.agents.filter((a) => a.stageId === st.id);
        const running = agents.filter((a) => a.status === 'running').length;
        const human = st.items.filter((it) => it.needsHuman).length;
        const meta = st.teamId && st.connection !== 'content' ? esc(st.approval) : `<span>${st.items.length}건</span><span class="running">앱 역할 ${agents.length}개 · ${running} 실행</span>${human ? `<span class="human">사람 ${human}</span>` : ''}`;
        el.innerHTML = `<span class="card-dot" aria-hidden="true">${index + 1}</span><span class="card-body"><span class="card-title">${esc(st.name)}</span><span class="card-meta">${meta}</span></span><span class="card-faces">${agents.map((a) => `<span class="face ${a.status}" style="--face:${a.av ? faceColor(a) : '#c9a'}" title="${esc(a.name)}"></span>`).join('')}</span>`;
        el.classList.toggle('active', space.selectedStage === st.id);
      });
      const b = d.brain;
      this.brainCard.innerHTML = d.organizationVersion === 1 ? '<span class="card-title">오비서 중앙 관제</span><span class="card-meta">5팀 업무 보기 · 팀별 직접 진입</span>' : `<span class="card-title">${esc(b.name)}</span><span class="card-meta"><span>${fmt(b.notes)} 절</span><span>원본 ${fmt(b.sources)}편</span></span><span class="card-meta"><span>${esc(b.label)}</span></span>`;
      $('tags').innerHTML = [...new Set(space.agents.map((a) => `${a.engine} · ${a.model}`.trim()))].filter((t) => t !== '·').map((t) => `<span class="tag">${esc(t)}</span>`).join('');
      const pill = $('source-pill');
      pill.className = `source-pill ${data.source === 'live' ? 'live' : ''} ${data.error ? 'error' : ''}`.trim();
      pill.textContent = workbench.sourceLabel(data.source, Boolean(data.error));
      pill.setAttribute('role', 'status');
      pill.title = data.error || '';
      $('updated-at').textContent = d.generatedAt ? `갱신 ${fmtTime(d.generatedAt)}` : '갱신 시각 없음';
      if (!results.opened&&space.selectedStage) this.openStage(space.selectedStage, true);
      this.pushEvents(d.events);
    },

    pushEvents(events) {
      const fresh = [];
      events.forEach((ev) => {
        const key = `${ev.time}|${ev.text}`;
        if (this.seenEvents.has(key)) return;
        this.seenEvents.add(key); fresh.push(ev);
      });
      if (!fresh.length && this.tickerQueue.length) return;
      this.tickerQueue = fresh.concat(this.tickerQueue).slice(0, 30);
      this.tickerIdx = 0;
      this.showTicker();
      if (!this.tickerTimer) this.tickerTimer = setInterval(() => { this.tickerIdx = (this.tickerIdx + 1) % Math.max(1, this.tickerQueue.length); this.showTicker(); }, 5200);
    },

    showTicker() {
      const ev = this.tickerQueue[this.tickerIdx];
      const el = $('ticker');
      if (!ev) { $('ticker-text').textContent = '아직 기록된 이벤트가 없습니다.'; return; }
      const st = space.stages.find((s) => s.id === ev.stageId);
      const apply = () => {
        $('ticker-stage').textContent = st ? st.name : '오피스';
        $('ticker-stage').style.setProperty('--stage', st ? st.color : '#7fe3ff');
        $('ticker-time').textContent = ev.time || '';
        $('ticker-text').textContent = ev.text || '';
        el.classList.remove('fade');
      };
      if (REDUCED) { apply(); return; }
      el.classList.add('fade');
      setTimeout(apply, 380);
    },

    openStage(id, silent) {
      if(results.opened)results.close();
      if (space.layer !== 'office') controls.setLayer('office');
      exploration(id);
      const st = space.stages.find((s) => s.id === id);
      if (!st) return;
      if (!silent && id !== space.selectedStage) space.embedResult = null;
      space.selectedStage = id;
      const panel = $('panel');
      panel.style.setProperty('--stage', st.color);
      $('panel-title').textContent = st.name;
      $('panel-sub').textContent = `${st.approval ? st.approval + ' · ' : ''}작업 ${st.items.length}건`;
      const agentName = (aid) => { const a = space.agents.find((x) => x.id === aid); return a ? `${a.name} (${a.engine})` : ''; };
      const bodyHtml = st.items.length ? st.items.map((it) => {
        const cls = it.needsHuman ? 'human' : /fail|error/.test(it.state) ? 'failed' : /writing|producing|research|measuring/.test(it.state) ? 'running' : '';
        const acts = embed.enabled ? `<div class="item-actions">${(data.source === 'live' ? it.actions : []).map((a) => `<button type="button" class="item-action" data-action="${esc(a.id)}" data-item="${esc(it.id)}" data-focus-key="${esc(JSON.stringify(['action', it.id, a.id]))}"${data.error || space.pendingActions.has(it.id + ':' + a.id) ? ' disabled' : ''}>${esc(a.label)}</button>`).join('')}${it.view ? `<button type="button" class="item-link" data-open="${esc(it.view)}" data-item="${esc(it.id)}" data-focus-key="${esc(JSON.stringify(['open', it.id, it.view]))}">오피스에서 열기</button>` : ''}</div>` : '';
        return `<div class="item${space.embedFocus === it.id ? ' active' : ''}" data-item-id="${esc(it.id)}"><span class="item-stripe ${cls}"></span><div>${it.workflowStageName ? `<div class="item-agent">${esc(it.workflowStageName)}</div>` : ''}<div class="item-title">${esc(it.title)}</div><div class="item-state">${esc(it.stateLabel)}</div>${it.agentId ? `<div class="item-agent">담당 ${esc(agentName(it.agentId))}</div>` : ''}${acts}</div></div>`;
      }).join('') : `<p class="panel-note">${st.teamId ? '실제 업무 연결 전입니다. 등록된 실행 작업은 없습니다.' : '이 단계에 등록된 작업이 없습니다.'}</p>`;
      const goals = st.teamId ? `<section class="team-goals"><p>${esc(st.description)}</p><ul>${st.goals.map(goal => `<li>${esc(goal)}</li>`).join('')}</ul>${st.connection === 'content' ? '<p class="panel-note">아래 상태는 기존 콘텐츠 앱의 기록입니다. Hermes 비서 연결이나 모든 채널 업로드 완료를 뜻하지 않습니다.</p>' : st.connection === 'dev' ? '<p class="panel-note">검증은 GitHub에서 하고, 검증을 통과한 커밋만 서버 감시기가 10분마다 배포합니다. 실패하면 이전 버전으로 되돌립니다.</p>' : '<p class="panel-note">메일·파일 조회나 비서 실행을 이 화면에서 시작하지 않습니다.</p>'}</section>` : '';
      const workflow = st.workflowStages?.length ? `<section class="workflow-map"><h3>콘텐츠 팀 내부 공정</h3>${st.workflowStages.map(step => {
        const safeUrl = /^(https?:\/\/|\/(?!\/))/.test(step.url || '') ? step.url : '';
        const key = esc(JSON.stringify(['workflow', step.id]));
        const link = embed.enabled && step.view ? `<button type="button" class="item-link" data-open="${esc(step.view)}" data-item="" data-focus-key="${key}">공정 열기</button>` : safeUrl ? `<a class="item-link" href="${esc(safeUrl)}" target="_blank" rel="noopener" data-focus-key="${key}">공정 열기</a>` : '';
        return `<div><span>${esc(step.name)} · ${step.items.length}건</span>${link}</div>`;
      }).join('')}</section>` : '';
      const stageNote = st.connection === 'dev' ? '이 화면에서는 자동 배포를 켜고 끄기만 합니다. 콘텐츠 승인(⓪·①·②·③)과는 별개입니다.' : st.teamId && st.connection !== 'content' ? '팀의 업무 범위만 정리한 상태입니다. 실제 비서 연결·실행 전입니다.' : embed.enabled ? '승인(⓪·①·②·③)은 오피스 화면에서 합니다. 여기서는 열기와 생성·제작 요청만 보냅니다.' : '승인(⓪·①·②·③)은 오피스 앱에서 사람이 합니다. 이 공간은 상태를 보여주기만 합니다.';
      const footHtml = `<button type="button" class="item-link walk-only" data-enter="${esc(st.id)}" data-focus-key="${esc(JSON.stringify(['enter', st.id]))}">걸어서 들어가기</button>${!embed.enabled && st.url ? `<a class="item-link" href="${esc(st.url)}" target="_blank" rel="noopener" data-focus-key="${esc(JSON.stringify(['stage-link', st.id]))}">${data.source === 'live' ? '오피스에서 열기' : '플레이북에서 보기'}</a>` : ''}<span class="panel-note">${esc(stageNote)}</span>${embed.enabled ? `<span class="${space.embedResult && space.embedResult.ok ? 'panel-result ok' : 'panel-result'}" role="status">${space.embedResult ? esc(space.embedResult.message) : ''}</span>` : ''}`;
      const teamBody = goals + workflow + bodyHtml;
      this.replaceContent($('panel-body'), teamBody, () => { $('panel-body').innerHTML = teamBody; });
      this.replaceContent($('panel-foot'), footHtml, () => { $('panel-foot').innerHTML = footHtml; });
      panel.hidden = false;
      if (!silent) {
        this.cards.forEach((el, sid) => el.classList.toggle('active', sid === id));
        controls.focusStage(st);
      }
    },

    openBrain() {
      if (!space.data) return;
      if(results.opened)results.close();
      if(workshop.opened)workshop.setOpen(false);
      if(space.rosterOpen)workbench.setRoster(false);
      if (space.layer !== 'office') controls.setLayer('office');
      exploration('hub');
      const b = space.data.brain;
      space.selectedStage = null;
      const panel = $('panel');
      panel.style.setProperty('--stage', '#7fe3ff');
      $('panel-title').textContent = b.name;
      $('panel-sub').textContent = `${fmt(b.notes)}절 · 원본 ${fmt(b.sources)}편`;
      $('panel-body').innerHTML = `<p class="panel-note">${esc(b.label)}. 검색 결과는 과거 계획과 근거이며 현재 지시나 실행 권한이 아닙니다.</p>` + space.agents.map((a) => `<div class="item"><span class="item-stripe ${a.status === 'running' ? 'running' : a.status === 'waiting' ? 'human' : a.status === 'error' ? 'failed' : ''}"></span><div><div class="item-title">${esc(a.name)}</div><div class="item-state">${esc(a.engine)} · ${esc(a.model)} · ${statusLabel(a.status)}</div><div class="item-agent">${esc(a.task)}</div></div></div>`).join('');
      $('panel-foot').innerHTML = '<span class="panel-note">동료 상태는 투영 데이터의 값 그대로입니다. 공간이 진행률을 추정하지 않습니다.</span>';
      if (space.data.organizationVersion === 1) {
        $('panel-title').textContent = '오비서 중앙 관제';
        $('panel-sub').textContent = '중앙 접수와 팀별 직접 지시를 위한 5팀 구성';
        $('panel-body').innerHTML = '<p class="panel-note">먼저 팀을 선택해 맡길 업무와 연결 상태를 확인하세요. 실제 비서 배정·업무 전달은 EC2 이전 후 연결할 예정입니다.</p>' + space.stages.map(st => `<button type="button" class="team-choice" data-team="${esc(st.id)}"><strong>${esc(st.name)}</strong><span>${esc(st.description)}</span><small>${esc(st.approval)}</small></button>`).join('') + `<details class="team-memory"><summary>현재 콘텐츠 앱의 참고 기억</summary><p class="panel-note">${esc(b.name)} · ${fmt(b.notes)}절 · 원본 ${fmt(b.sources)}편. ${esc(b.label)}. 전 팀 공용 위키·전체 대화 자동 보존과는 별개입니다.</p></details>`;
        $('panel-foot').innerHTML = '<span class="panel-note">팀 구성을 바꿔도 기존 콘텐츠 작업·승인·결과 ID와 지리 탐험 기록은 보존합니다.</span>';
      }
      panel.hidden = false;
      this.cards.forEach((el) => el.classList.remove('active'));
      controls.focusHub();
      if (space.data.organizationVersion === 1) {
        $('panel-body').scrollTop = 0;
        $('panel-body').querySelector('.team-choice')?.focus({ preventScroll:true });
      }
    },

    closePanel() {
      if(results.opened)results.close();
      $('panel').hidden = true;
      space.selectedStage = null;
      this.cards.forEach((el) => el.classList.remove('active'));
    },

    toggleNearestAgent() {
      const p = controls.player.pos;
      let best = null, bestD = 3.2;
      space.agents.forEach((a) => { const d = B.Vector3.Distance(a.pos, p); if (d < bestD) { best = a; bestD = d; } });
      if (best) this.openStage(best.stageId);
    },

    hideAgentCard() { if (this.agentCard) this.agentCard.hidden = true; },

    tick() {
      const now = performance.now(), redrawMini = now - this.miniT >= 200;
      if (redrawMini) this.miniT = now;
      if (isPhone() || space.layer === 'meadow') { this.cards.forEach((el) => { el.hidden = false; }); this.brainCard.hidden = false; this.agentCard.hidden = true; if (!isPhone() && redrawMini) this.drawMinimap(); return; }
      const w = world.canvas.clientWidth, h = world.canvas.clientHeight;
      const nameTop = $('department-nav').getBoundingClientRect().bottom + 12;
      const walk = space.view === 'walk';
      const ppos = controls.player.pos;
      space.stages.forEach((st) => {
        const el = this.cards.get(st.id);
        if (!el) return;
        if (!walk && controls.focused && controls.focused !== st.id) { el.hidden = true; return; }
        if ((space.layer === 'meadow' && walk) || (walk && B.Vector3.Distance(st.pos, ppos) > 30)) { el.hidden = true; return; }
        const pr = this.project(st.pos.add(new B.Vector3(0, 5.6, 0)));
        if (!pr.visible || pr.x < -200 || pr.x > w + 200 || pr.y < -100 || pr.y > h + 100) { el.hidden = true; return; }
        el.hidden = false;
        const half = el.offsetWidth / 2 + 8;
        el.style.left = `${Math.max(half, Math.min(w - half, pr.x))}px`; el.style.top = `${Math.max(nameTop + el.offsetHeight, pr.y)}px`;
      });
      const bp = this.project(new B.Vector3(0, 7.4, 0));
      this.brainCard.hidden = !bp.visible || (space.layer === 'meadow' && walk) || (walk && Math.hypot(ppos.x, ppos.z) > 26);
      this.brainCard.style.left = `${bp.x}px`; this.brainCard.style.top = `${bp.y}px`;
      if (walk) {
        // 지금 서 있는 방 이름을 나가기 버튼에 표시
        const inside = space.layer === 'office' && space.stages.find((st) => { const l = world.toLocal(st, ppos); return Math.abs(l.x) <= ISLAND_W / 2 && Math.abs(l.z) <= ISLAND_D / 2; }) || null;
        if (this.insideStage !== inside) {
          this.insideStage = inside;
          const btn = $('btn-exit');
          btn.innerHTML = inside ? `↩ <span class="room">${esc(inside.name)}</span>에서 나가기<span class="kbd">Esc</span>` : '↩ 공간에서 나가기<span class="kbd">Esc</span>';
          btn.style.setProperty('--stage', inside ? inside.color : '#7fe3ff');
        }
        let best = null, bestD = 4.5;
        space.agents.forEach((a) => { const d = B.Vector3.Distance(a.pos, ppos); if (d < bestD) { best = a; bestD = d; } });
        if (best) {
          if (this.agentCardTarget !== best) {
            this.agentCardTarget = best;
            this.agentCard.innerHTML = `<span class="card-body"><span class="card-title">${esc(best.name)}</span><span class="card-meta"><span>${esc(best.engine)}</span><span class="${best.status}">${statusLabel(best.status)}</span></span><span class="card-meta"><span>${esc(best.task)}</span></span><span class="card-meta"><span>E 자세히</span></span></span>`;
          }
          const ap = this.project(best.pos.add(new B.Vector3(0, 2.6, 0)));
          this.agentCard.hidden = !ap.visible;
          this.agentCard.style.left = `${ap.x}px`; this.agentCard.style.top = `${ap.y}px`;
        } else { this.agentCard.hidden = true; this.agentCardTarget = null; }
      }
      if (redrawMini) this.drawMinimap();
    },

    drawMinimap() {
      const c = this.miniCtx, W = this.mini.width, H = this.mini.height;
      const R = space.layer === 'meadow' ? 800 : world.terrain ? world.terrain.landR + 7 : 72;
      const sx = (x) => W / 2 + (x / R) * (W / 2 - 8);
      const sz = (z) => H / 2 + (z / R) * (H / 2 - 8);
      c.clearRect(0, 0, W, H);
      c.fillStyle = '#03050f'; c.fillRect(0, 0, W, H);
      if (space.layer === 'meadow') {
        c.fillStyle = '#458456'; c.fillRect(8, 8, W - 16, H - 16);
        c.strokeStyle = '#5c9a6b'; c.lineWidth = 0.5;
        for (let g = 1; g < 8; g++) { c.beginPath(); c.moveTo(g * W / 8, 8); c.lineTo(g * W / 8, H - 8); c.stroke(); c.beginPath(); c.moveTo(8, g * H / 8); c.lineTo(W - 8, g * H / 8); c.stroke(); }
        c.fillStyle = '#b5fff0'; c.font = '11px sans-serif'; c.fillText('↑ 공중 팀 대지', sx(0) + 8, sz(0));
      } else if (world.terrain) {
        if (!this.landLayer || this.landLayer.terrain !== world.terrain) {
          const off = document.createElement('canvas'); off.width = W; off.height = H;
          const oc = off.getContext('2d');
          const cw = (1 / R) * (W / 2 - 8), ch = (1 / R) * (H / 2 - 8);
          world.terrain.cols.forEach((col) => {
            oc.fillStyle = col.zone === 'path' ? '#4e8c9e' : '#a2b9c9';
            oc.fillRect(sx(col.x) - cw / 2, sz(col.z) - ch / 2, cw + 0.6, ch + 0.6);
          });
          this.landLayer = { canvas: off, terrain: world.terrain };
        }
        c.drawImage(this.landLayer.canvas, 0, 0);
      }
      space.stages.forEach((st) => {
        c.save();
        c.translate(sx(st.pos.x), sz(st.pos.z));
        c.rotate(-st.rotY);
        c.fillStyle = st.color;
        const w = (ISLAND_W / R) * (W / 2 - 8), d = (ISLAND_D / R) * (H / 2 - 8);
        c.fillRect(-w / 2, -d / 2, w, d);
        c.restore();
      });
      c.fillStyle = '#7fe3ff'; c.beginPath(); c.arc(sx(0), sz(0), (HUB_R / R) * (W / 2 - 8), 0, Math.PI * 2); c.fill();
      space.agents.forEach((a) => {
        c.fillStyle = world.markerColor(a.status);
        c.beginPath(); c.arc(sx(a.pos.x), sz(a.pos.z), 3, 0, Math.PI * 2); c.fill();
      });
      if (space.view === 'walk') {
        const p = controls.player.pos;
        c.fillStyle = '#ffffff'; c.beginPath(); c.arc(sx(p.x), sz(p.z), 4, 0, Math.PI * 2); c.fill();
        $('minimap-zoom').textContent = 'WALK';
      } else {
        $('minimap-zoom').textContent = `${Math.round((210 / controls.overview.radius) * 100)}%`;
      }
    },
  };

  // ======================================================================
  // 보조
  // ======================================================================
  // 같은 투영을 읽는 간편 관제. 보기/초점 변경은 업무를 실행하지 않는다.
  const workshop = {
    key:'heobrain.buildings.v1',
    catalog:{tower:{name:'오로라 관측 타워',w:4,d:4,h:7.4},lab:{name:'프리즘 연구소',w:6,d:4,h:4.8},port:{name:'오비탈 모빌리티 허브',w:4,d:6,h:4.6}},
    plot:{x:32,z:-46,cols:8,rows:5,step:2},items:[],history:[],visibleItems:[],storedRaw:null,storageBlocked:false,
    selectedId:null,draft:{kind:'tower',col:1,row:1,turn:0},opened:false,ready:false,root:null,preview:null,message:'',

    bounds(item) {
      const model=this.catalog[item.kind],p=this.plot;
      const w=item.turn%2?model.d:model.w,d=item.turn%2?model.w:model.d;
      const minX=p.x-p.cols*p.step/2+item.col*p.step,minZ=p.z-p.rows*p.step/2+item.row*p.step;
      return {minX,minZ,maxX:minX+w,maxZ:minZ+d,w,d};
    },

    validateLayout(items) {
      if(!Array.isArray(items)||items.length>8)return '건물은 최대 8개까지 배치할 수 있어요.';
      const ids=new Set(),p=this.plot;
      for(const item of items){
        if(!item||typeof item!=='object'||typeof item.id!=='string'||!/^b[1-9][0-9]{0,5}$/.test(item.id)||ids.has(item.id))return '건물 기록의 식별자가 올바르지 않아요.';
        ids.add(item.id);
        if(typeof item.kind!=='string'||!Object.hasOwn(this.catalog,item.kind)||!['col','row','turn'].every(k=>Number.isInteger(item[k]))||item.turn<0||item.turn>3)return '건물 종류나 위치·회전 기록이 올바르지 않아요.';
        const b=this.bounds(item);
        if(item.col<0||item.row<0||b.maxX>p.x+p.cols*p.step/2||b.maxZ>p.z+p.rows*p.step/2)return '건물 전체가 보호 부지 안에 들어와야 해요.';
      }
      for(let i=0;i<items.length;i++)for(let j=i+1;j<items.length;j++){
        const a=this.bounds(items[i]),b=this.bounds(items[j]);
        if(a.minX<b.maxX&&a.maxX>b.minX&&a.minZ<b.maxZ&&a.maxZ>b.minZ)return '다른 건물과 겹쳐요. 빈 칸을 선택하세요.';
      }
      return '';
    },

    obstruction(item) {
      const b=this.bounds(item),x=(b.minX+b.maxX)/2,z=(b.minZ+b.maxZ)/2;
      if((world.officeObstacles||[]).some(o=>Math.hypot(Math.max(b.minX-o.x,0,o.x-b.maxX),Math.max(b.minZ-o.z,0,o.z-b.maxZ))<o.r+.4))return '기존 도시 시설과 겹쳐요.';
      for(const st of space.stages){
        const c=Math.cos(st.angle),s=Math.sin(st.angle),dx=x-c*46,dz=z-s*46;
        const intersects=[[1,0],[0,1],[c,s],[-s,c]].every(([ax,az])=>Math.abs(dx*ax+dz*az)<b.w/2*Math.abs(ax)+b.d/2*Math.abs(az)+15*Math.abs(c*ax+s*az)+2*Math.abs(-s*ax+c*az)+.4);
        if(intersects)return '부서로 이어지는 도로는 비워 두세요.';
      }
      const player=controls.player?.pos;
      if(space.layer==='office'&&player&&player.x>b.minX-.45&&player.x<b.maxX+.45&&player.z>b.minZ-.45&&player.z<b.maxZ+.45)return '캐릭터가 있는 칸은 비워 두세요.';
      return '';
    },

    restore() {
      this.history=[];this.selectedId=null;this.items=[];this.storageBlocked=false;this.message='';
      try{
        this.storedRaw=localStorage.getItem(this.key);
        if(this.storedRaw===null)return;
        if(this.storedRaw.length>32768)throw new Error('size');
        const saved=JSON.parse(this.storedRaw);
        if(saved?.version!==1||this.validateLayout(saved.items))throw new Error('layout');
        this.items=saved.items.map(({id,kind,col,row,turn})=>({id,kind,col,row,turn}));
      }catch(_){this.storageBlocked=true;this.message='건축 기록을 읽지 못했어요. 기존 저장은 보존했으며 덮어쓰지 않아요.';}
    },

    persist(next,selectedId=null,undo=false) {
      const reason=this.validateLayout(next);
      if(reason){this.message=reason;return false;}
      if(this.storageBlocked){this.message='기존 건축 기록을 보호하고 있어요. 브라우저 저장 상태를 확인해 주세요.';return false;}
      const clean=next.map(({id,kind,col,row,turn})=>({id,kind,col,row,turn})),raw=JSON.stringify({version:1,items:clean});
      try{
        if(localStorage.getItem(this.key)!==this.storedRaw){this.message='다른 탭에서 건축 기록이 바뀌었어요. 건축 창을 닫았다 다시 열어 주세요.';return false;}
        localStorage.setItem(this.key,raw);
      }catch(_){this.message='저장하지 못해 변경을 적용하지 않았어요. 브라우저의 저장 허용·여유 공간을 확인하세요.';return false;}
      if(!undo){this.history.push(this.items.map(i=>({...i})));if(this.history.length>20)this.history.shift();}
      this.items=clean;this.storedRaw=raw;this.selectedId=selectedId;
      return true;
    },

    applyDraft() {
      const id=this.selectedId||'b'+(Math.max(0,...this.items.map(i=>Number(i.id.slice(1))))+1);
      const item={id,...this.draft},next=this.selectedId?this.items.map(i=>i.id===id?item:i):[...this.items,item];
      const reason=this.validateLayout(next)||this.obstruction(item);
      if(reason){this.message=reason;this.sync();return false;}
      if(JSON.stringify(next)===JSON.stringify(this.items)){this.message='위치나 회전을 바꾼 뒤 적용하세요.';this.sync();return false;}
      if(!this.persist(next,id)){this.sync();return false;}
      this.message='건물을 배치했어요. 이 브라우저에 저장됐어요.';this.rebuild();this.sync();return true;
    },

    remove() {
      if(!this.selectedId)return false;
      if(!this.persist(this.items.filter(i=>i.id!==this.selectedId))) {this.sync();return false;}
      this.message='선택한 건물을 삭제했어요. 되돌리기로 복원할 수 있어요.';this.rebuild();this.sync();return true;
    },

    undo() {
      if(!this.history.length)return false;
      if(!this.persist(this.history[this.history.length-1],null,true)){this.sync();return false;}
      this.history.pop();this.message='직전 변경을 되돌렸어요.';this.rebuild();this.sync();return true;
    },

    collides(v,clearance=.4) {
      return this.visibleItems.some(i=>{const b=this.bounds(i);return v.x>b.minX-clearance&&v.x<b.maxX+clearance&&v.z>b.minZ-clearance&&v.z<b.maxZ+clearance;});
    },

    clear() {
      this.preview?.dispose();this.preview=null;this.root?.dispose();this.root=null;this.visibleItems=[];this.models=new Map();this.pickPlane=null;
    },

    model(item,parent,ghost=false) {
      const b=this.bounds(item),node=new B.TransformNode('build-'+item.id,world.scene);
      node.parent=parent;node.position.set((b.minX+b.maxX)/2,0,(b.minZ+b.maxZ)/2);node.rotation.y=item.turn*Math.PI/2;
      const built=world.buildArchitecture('build-'+item.kind,node);
      if(ghost){
        const reason=this.validateLayout([...this.items.filter(i=>i.id!==item.id),item])||this.obstruction(item);
        const material=world.mat('building-preview',reason?'#ff817c':'#8aecd7',{emissive:.7,alpha:.45,unlit:true});
        built.meshes.forEach(m=>{world.shadows?.removeShadowCaster(m);m.material=material;});
      }
      return node;
    },

    rebuild() {
      if(!this.ready)return;
      this.clear();this.root=new B.TransformNode('protected-building-plot',world.scene);
      this.visibleItems=this.items.filter(i=>!this.obstruction(i));
      this.models=new Map();this.visibleItems.forEach(i=>this.models.set(i.id,this.model(i,this.root)));
      const p=this.plot,x=p.x-p.cols*p.step/2,z=p.z-p.rows*p.step/2,lines=[];
      for(let c=0;c<=p.cols;c++)lines.push([new B.Vector3(x+c*p.step,.045,z),new B.Vector3(x+c*p.step,.045,z+p.rows*p.step)]);
      for(let r=0;r<=p.rows;r++)lines.push([new B.Vector3(x,.045,z+r*p.step),new B.Vector3(x+p.cols*p.step,.045,z+r*p.step)]);
      const grid=B.MeshBuilder.CreateLineSystem('protected-plot-grid',{lines},world.scene);grid.parent=this.root;grid.color=B.Color3.FromHexString('#75d7cb');grid.alpha=.65;grid.isPickable=false;
      if(this.opened){
        this.pickPlane=B.MeshBuilder.CreateGround('building-pick-plane',{width:p.cols*p.step,height:p.rows*p.step},world.scene);
        this.pickPlane.position.set(p.x,.02,p.z);this.pickPlane.parent=this.root;this.pickPlane.visibility=0;
      }
      this.updatePreview();
    },

    draftMatchesSelection() {
      const item=this.items.find(i=>i.id===this.selectedId);
      return !!item&&['kind','col','row','turn'].every(k=>item[k]===this.draft[k]);
    },

    updatePreview() {
      this.preview?.dispose();this.preview=null;
      const unchanged=this.draftMatchesSelection();
      this.models?.forEach((node,id)=>node.setEnabled(!this.opened||id!==this.selectedId||unchanged));
      if(this.pickPlane)this.pickPlane.isPickable=this.opened;
      if(this.opened&&this.root&&!unchanged)this.preview=this.model({id:this.selectedId||'b999999',...this.draft},this.root,true);
    },

    sync() {
      if(!this.ready)return;
      const target=$('build-target');target.replaceChildren(new Option('새 건물', ''));
      this.items.forEach(i=>target.add(new Option(this.catalog[i.kind].name+' · '+(i.col+1)+','+(i.row+1)+' · '+i.turn*90+'°',i.id)));
      target.value=this.selectedId||'';
      $('build-kind').value=this.draft.kind;$('build-col').value=String(this.draft.col);$('build-row').value=String(this.draft.row);
      const model=this.catalog[this.draft.kind],item={id:this.selectedId||'b999999',...this.draft};
      const invalid=this.validateLayout([...this.items.filter(i=>i.id!==item.id),item])||this.obstruction(item);
      const held=this.items.length-this.visibleItems.length;
      $('build-spec').textContent=model.w+'×'+model.d+'m · '+this.draft.turn*90+'° · 높이 '+model.h+'m';
      $('build-preview-status').textContent=invalid||(this.draftMatchesSelection()?'배치 완료 · 위치나 회전을 바꾸면 미리보기가 나타나요.':'민트색 미리보기 위치에 배치할 수 있어요.');
      $('build-preview-status').classList.toggle('invalid',!!invalid);
      $('build-apply').textContent=this.selectedId?'위치·회전 적용':'배치 확정';$('build-apply').disabled=!!invalid||this.storageBlocked||this.draftMatchesSelection();
      $('build-delete').disabled=!this.selectedId||this.storageBlocked;$('build-undo').disabled=!this.history.length||this.storageBlocked;
      $('build-count').textContent=this.items.length+'/8 건물 · 되돌리기 '+this.history.length+'/20';
      $('btn-build').disabled=!world.terrain;
      $('build-message').textContent=(held?held+'개 건물은 현재 도로·캐릭터와 겹쳐 표시를 보류했어요. 저장 원본은 유지돼요. ':'')+(this.message||'건축 기록은 이 브라우저에 저장돼요. 차량·업무 기록과 별개예요.');
      this.updatePreview();
    },

    frame() {
      controls.animateCamera({alpha:-1.1,beta:.9,radius:isPhone()?46:34,target:new B.Vector3(32,isPhone()?-5:2,-46)});
    },

    setOpen(open) {
      if(open){
        if(!world.terrain)return;
        try{if(localStorage.getItem(this.key)!==this.storedRaw)this.restore();}catch(_){this.storageBlocked=true;}
        workbench.setRoster(false);hud.closePanel();controls.keys.clear();controls.dragging=false;controls.setVehicleSpeed(0);
        controls.setLayer('office');controls.setView('overview');controls.overview.detachControl();
        $('world-tools').open=false;this.opened=true;space.buildingOpen=true;document.body.classList.add('building-view');
        $('build-panel').hidden=false;$('btn-build').setAttribute('aria-pressed','true');
        this.frame();
        this.rebuild();this.sync();$('build-kind').focus({preventScroll:true});$('build-panel').scrollTop=0;
      }else{
        this.opened=false;space.buildingOpen=false;this.preview?.dispose();this.preview=null;controls.keys.clear();controls.dragging=false;
        document.body.classList.remove('building-view');$('build-panel').hidden=true;$('btn-build').setAttribute('aria-pressed','false');
        controls.overview.attachControl(world.canvas,true);this.updatePreview();$('btn-build').focus();
      }
    },

    init() {
      this.restore();this.ready=true;$('btn-build').disabled=!world.terrain;
      for(const [kind,model]of Object.entries(this.catalog))$('build-kind').add(new Option(model.name,kind));
      for(let c=0;c<this.plot.cols;c++)$('build-col').add(new Option(String(c+1),String(c)));
      for(let r=0;r<this.plot.rows;r++)$('build-row').add(new Option(String(r+1),String(r)));
      window.addEventListener('resize',()=>{if(this.opened)this.frame();});
      $('btn-build').onclick=()=>this.setOpen(!this.opened);$('build-close').onclick=()=>this.setOpen(false);
      const update=()=>{this.draft={kind:$('build-kind').value,col:Number($('build-col').value),row:Number($('build-row').value),turn:this.draft.turn};this.message='';this.sync();};
      ['build-kind','build-col','build-row'].forEach(id=>$(id).onchange=update);
      world.scene.onPointerObservable.add(info=>{
        if(!this.opened||info.type!==B.PointerEventTypes.POINTERTAP||!this.pickPlane)return;
        const rect=world.canvas.getBoundingClientRect(),hit=world.scene.pick(info.event.clientX-rect.left,info.event.clientY-rect.top,m=>m===this.pickPlane);
        if(!hit?.hit||!hit.pickedPoint)return;
        const p=this.plot;this.draft.col=Math.min(p.cols-1,Math.max(0,Math.floor((hit.pickedPoint.x-p.x+p.cols*p.step/2)/p.step)));
        this.draft.row=Math.min(p.rows-1,Math.max(0,Math.floor((hit.pickedPoint.z-p.z+p.rows*p.step/2)/p.step)));
        this.message='';this.sync();
      });
      $('build-target').onchange=()=>{this.selectedId=$('build-target').value||null;const item=this.items.find(i=>i.id===this.selectedId);this.draft=item?{kind:item.kind,col:item.col,row:item.row,turn:item.turn}:{kind:'tower',col:1,row:1,turn:0};this.message='';this.sync();};
      $('build-rotate').onclick=()=>{this.draft.turn=(this.draft.turn+1)%4;this.message='';this.sync();};
      $('build-apply').onclick=()=>this.applyDraft();$('build-delete').onclick=()=>this.remove();$('build-undo').onclick=()=>this.undo();
      document.addEventListener('keydown',e=>{
        if(!this.opened)return;
        if(e.key==='Escape'){e.preventDefault();e.stopPropagation();this.setOpen(false);return;}
        if((e.ctrlKey||e.metaKey)&&e.key.toLowerCase()==='z'&&!e.target.closest('input,select,textarea')){e.preventDefault();e.stopPropagation();this.undo();}
      });
    },
  };

  const results = {
    opened:false,loading:false,error:'',jobs:[],current:null,selectedId:null,listAt:null,detailAt:null,serial:0,controller:null,

    safeId(value) { return typeof value==='string'&&/^[A-Za-z0-9_-]{1,128}$/.test(value); },
    text(value,max=200) { return typeof value==='string'?value.slice(0,max):''; },
    hash(value) { return typeof value==='string'&&/^[a-f0-9]{64}$/i.test(value)?value.toLowerCase():null; },

    endpoint(kind,id,child) {
      try{
        if(!data.apiUrl)return null;
        const base=new URL(data.apiUrl,location.href);
        if(base.origin!==location.origin||base.username||base.password||base.pathname!=='/api/space'||!['http:','https:'].includes(base.protocol))return null;
        const paths={list:'/api/jobs/summaries?limit=80'};
        if(kind==='list')return base.origin+paths.list;
        if(!this.safeId(id))return null;
        if(kind==='job')return base.origin+'/api/jobs/'+encodeURIComponent(id);
        if(kind==='deliveries')return base.origin+'/api/jobs/'+encodeURIComponent(id)+'/deliveries';
        if(kind==='draft'&&this.safeId(child))return base.origin+'/api/jobs/'+encodeURIComponent(id)+'/drafts/'+encodeURIComponent(child)+'/preview';
      }catch(_){ /* 연결 주소가 확인될 때만 조회한다. */ }
      return null;
    },

    summary(job) {
      if(!job||!this.safeId(job.id))return null;
      const approval=(record,release=false)=>{
        if(!record||typeof record!=='object')return null;
        return {id:release?null:(this.safeId(record.id)?record.id:null),version:this.hash(record.version),decision:this.text(record.decision,40),createdAt:this.text(record.created_at,60),outputs:release&&Array.isArray(record.outputs)?record.outputs.filter(v=>typeof v==='string').slice(0,20).map(v=>v.slice(0,60)):[]};
      };
      const manifest=job.manifest&&typeof job.manifest==='object'?job.manifest:{};
      return {id:job.id,title:this.text(job.title)||job.id,state:this.text(job.state,60)||'unknown',sourceHash:this.hash(job.source_hash),manifestHash:this.hash(manifest.hash),manifestSourceHash:this.hash(manifest.source_hash),sourceApproval:approval(job.source_approval),releaseApproval:approval(job.release_approval,true),
        files:(Array.isArray(manifest.files)?manifest.files:[]).slice(0,80).map(f=>({id:this.safeId(f?.id)?f.id:null,kind:this.text(f?.kind,60)||'형식 미제공',sha256:this.hash(f?.sha256),outputs:Array.isArray(f?.outputs)?f.outputs.filter(v=>typeof v==='string').slice(0,20).map(v=>v.slice(0,60)):[]}))};
    },

    detail(raw,ledger) {
      const job=this.summary(raw);
      if(!job)throw new Error('작업 기록 형식을 확인하지 못했습니다.');
      const tasks=(Array.isArray(raw.tasks)?raw.tasks:[]).filter(t=>this.safeId(t?.id)).slice(0,100).map(t=>({id:t.id,kind:this.text(t.kind,60),state:this.text(t.state,60)||'unknown',createdAt:this.text(t.created_at,60),updatedAt:this.text(t.updated_at,60)}));
      const drafts=(Array.isArray(raw.drafts)?raw.drafts:[]).filter(d=>this.safeId(d?.id)).slice(0,30).map(d=>({id:d.id,title:this.text(d.title),version:Number.isInteger(d.version)&&d.version>=0?d.version:null,createdAt:this.text(d.created_at,60)}));
      const deliveries=(Array.isArray(ledger?.deliveries)?ledger.deliveries:[]).slice(0,30).map(d=>({state:this.text(d?.state,60)||'unknown',visibility:this.text(d?.visibility,40),privacyStatus:this.text(d?.privacy_status,40),updatedAt:this.text(d?.updated_at,60)}));
      return {job,tasks,drafts,deliveries,deliveryError:!Array.isArray(ledger?.deliveries)};
    },

    async read(url,signal) {
      const response=await fetch(url,{method:'GET',credentials:'same-origin',cache:'no-store',redirect:'error',signal});
      if(response.status===404&&url===this.endpoint('list'))throw new Error('작업 요약 목록을 지원하지 않는 서버입니다 (HTTP 404). 서버 판본을 확인해 주세요.');
      if(!response.ok)throw new Error('조회 실패 · HTTP '+response.status);
      if(!response.headers.get('content-type')?.includes('application/json'))throw new Error('조회 데이터 형식을 확인하지 못했습니다.');
      try{return await response.json();}catch(_){throw new Error('조회 데이터 형식을 확인하지 못했습니다.');}
    },

    async load(kind='list',id=null) {
      if(!['list','job'].includes(kind)){this.error='지원하지 않는 조회입니다.';this.render();return false;}
      const url=this.endpoint(kind,id);
      if(!url){this.error='실제 결과 연결이 없습니다. 같은 주소의 오피스 앱에서 월드를 열어 주세요.';this.render();return false;}
      this.controller?.abort();const token=++this.serial,controller=new AbortController();this.controller=controller;
      this.loading=true;this.error='';
      if(kind==='job'){this.selectedId=id;this.current=null;this.detailAt=null;}else{this.selectedId=null;this.current=null;}
      this.render();const timeout=setTimeout(()=>controller.abort(),12000);
      try{
        let value;
        if(kind==='list'){
          const raw=await this.read(url,controller.signal);
          if(!Array.isArray(raw.jobs))throw new Error('작업 목록 형식을 확인하지 못했습니다.');
          const seen=new Set();value=raw.jobs.slice(0,80).map(j=>this.summary(j)).filter(j=>j&&!seen.has(j.id)&&seen.add(j.id));
        }else{
          const [job,ledger]=await Promise.allSettled([this.read(url,controller.signal),this.read(this.endpoint('deliveries',id),controller.signal)]);
          if(job.status!=='fulfilled')throw job.reason;
          value=this.detail(job.value,ledger.status==='fulfilled'?ledger.value:null);
          if(value.job.id!==id)throw new Error('요청한 작업과 결과 식별자가 다릅니다.');
        }
        if(!this.opened||token!==this.serial)return false;
        if(kind==='list'){this.jobs=value;this.listAt=new Date().toISOString();}else{this.current=value;this.detailAt=new Date().toISOString();}
        return true;
      }catch(error){
        if(this.opened&&token===this.serial)this.error=controller.signal.aborted?'조회 시간이 초과됐습니다. 다시 조회해 주세요.':this.text(error?.message)||'조회하지 못했습니다.';
        return false;
      }finally{
        clearTimeout(timeout);
        if(this.opened&&token===this.serial){this.loading=false;this.controller=null;this.render();}
      }
    },

    match(a,b) { return a&&b?(a===b?'기록 버전 일치':'기록 버전 다름'):'버전 미제공'; },

    reviewStep(state) {
      const steps={
        research_ready:['근거 준비','studio','검토 앱에서 근거와 원고 작성 방향을 확인하세요.'],
        drafting:['원고·검수 중','studio','검토 앱에서 원고와 검수 작업의 진행·오류 기록을 확인하세요.'],
        source_review:['사람 승인 대기 ①','studio','검토 앱에서 현재 원고·근거·검수 결과를 읽고 판단하세요.'],
        source_rejected:['원고 거절','studio','검토 앱에서 반려 사유와 수정할 원고를 확인하세요.'],
        source_approved:['원고 승인','delivery','검토 앱에서 원고 승인 기록과 제작 선택·예산을 확인하세요.'],
        production_queued:['제작 대기','delivery','검토 앱에서 선택한 제작물과 작업자 대기 상태를 확인하세요.'],
        producing:['제작 중','delivery','검토 앱에서 제작 진행과 출력별 오류를 확인하세요.'],
        release_review:['사람 승인 대기 ②','delivery','검토 앱에서 실제 최종 파일과 출고 조건을 확인하세요.'],
        partial_release_review:['일부 제작 완료','delivery','검토 앱에서 완료한 출력과 실패한 출력을 구분해 확인하세요.'],
        release_approved:['출고 승인 ② 완료 · 채널별 전달 기록 확인','delivery','검토 앱에서 ②의 파일·대상 조건과 실제 전달 결과를 확인하세요.'],
        blocked:['확인 필요','activity','운영 기록에서 중단 사유와 필요한 확인을 살펴보세요.'],
        needs_reconciliation:['호출 결과 확인 필요','activity','운영 기록에서 결과 불명 호출을 대조하고 다음 행동을 결정하세요.'],
        failed:['실패','activity','운영 기록에서 실패 원인과 다음 조치를 확인하세요.'],
      };
      const [label,view,next]=Object.hasOwn(steps,state)?steps[state]:['상태 미확인','activity','상태가 확인되지 않았으므로 운영 기록에서 원본 작업을 확인하세요.'];
      return {label,view,next};
    },

    openReview(id) {
      const job=this.current?.job;
      if(!embed.enabled||!this.opened||this.loading||!this.safeId(id)||id!==this.selectedId||job?.id!==id||!this.endpoint('job',id))return false;
      embed.post({type:'open',view:this.reviewStep(job.state).view,itemId:id});
      return true;
    },

    render() {
      if(!this.opened)return;
      const body=$('panel-body'),stamp=this.listAt?new Date(this.listAt).toLocaleString('ko-KR'):'아직 조회하지 않음';
      let openJobId=null;
      $('panel-title').textContent='내 작업 결과 전시장';$('panel-sub').textContent='읽기 전용 · 목록 조회 '+stamp;
      const row=(label,value)=>'<div class="result-meta"><dt>'+esc(label)+'</dt><dd>'+esc(value||'미제공')+'</dd></div>';
      const approval=(label,record,currentHash)=>'<section class="result-block"><h3>'+label+'</h3><dl>'+row('기록된 판정',record?.decision||'기록 미제공')+row('기록 ID',record?.id)+row('승인 대상 버전',record?.version)+row('버전 비교',this.match(record?.version,currentHash))+row('기록 시각',record?.createdAt)+(record?.outputs?.length?row('대상 출력',record.outputs.join(', ')):'')+'</dl></section>';
      const options=this.jobs.map(j=>'<option value="'+esc(j.id)+'"'+(j.id===this.selectedId?' selected':'')+'>'+esc(j.title.slice(0,70))+' · '+esc(this.reviewStep(j.state).label)+'</option>').join('');
      let html='<p class="results-source" role="status">'+(this.error?esc(this.error)+(this.listAt?' · 목록은 마지막 조회 기록입니다.':''):this.loading?'원본 기록을 조회하고 있습니다.':this.listAt?'연결된 오피스의 조회 기록 · 예시 결과로 대체하지 않습니다.':'제작·승인·게시 요청을 보내지 않는 조회 화면입니다.')+'</p>';
      html+='<label class="result-picker">확인할 작업<select id="result-job"'+(this.loading?' disabled':'')+'><option value="">작업을 선택하세요</option>'+options+'</select></label>';
      if(this.current){
        const d=this.current,j=d.job,step=this.reviewStep(j.state);
        if(embed.enabled&&!this.loading&&this.safeId(j.id)&&j.id===this.selectedId&&this.endpoint('job',j.id))openJobId=j.id;
        html+='<article class="result-detail"><h3>'+esc(j.title)+'</h3><p class="result-caution"><strong>다음 검토</strong> · '+esc(step.next)+'</p>'+(openJobId?'<button type="button" class="item-link" id="results-open-review">선택 작업 검토 화면 열기</button>':'')+'<dl>'+row('원본 작업 ID',j.id)+row('기록된 작업 상태',step.label)+row('상세 조회 시각',this.detailAt)+row('현재 원고 버전',j.sourceHash)+row('산출물 묶음 버전',j.manifestHash)+row('묶음의 원고 버전',j.manifestSourceHash)+row('원고/묶음 비교',this.match(j.sourceHash,j.manifestSourceHash))+'</dl>';
        html+=approval('① 원고 승인 기록',j.sourceApproval,j.sourceHash)+approval('② 출력 승인 기록',j.releaseApproval,j.manifestHash);
        html+='<p class="result-caution">기록 판정과 버전 비교만 표시합니다. 선택값·출력별 승인 유효성, 실파일 해시 검증은 검토 앱에서 확인하세요.</p>';
        html+='<section class="result-block"><h3>생성초안 기록</h3><p class="result-caution">별도로 저장된 생성초안 목록이며 현재 검토·승인 원고와 다를 수 있습니다.</p>'+(d.drafts.length?d.drafts.map(v=>'<div class="result-entry"><strong>'+esc(v.title||'생성초안')+'</strong><span>'+esc(v.id)+' · 버전 '+esc(v.version===null?'미제공':String(v.version))+'</span><a class="item-link" target="_blank" rel="noopener" href="'+esc(this.endpoint('draft',j.id,v.id))+'">생성초안 읽기</a></div>').join(''):'<p>이 조회에 별도로 저장된 생성초안 기록이 없습니다. 현재 원고가 없다는 뜻은 아닙니다. 현재 원고는 검토 앱에서 원본 작업 ID로 확인하세요.</p>')+'</section>';
        html+='<section class="result-block"><h3>산출물 파일 · '+j.files.length+'개 조회</h3>'+(j.files.length?j.files.map(f=>'<dl class="result-entry">'+row('파일 ID',f.id)+row('형식',f.kind)+row('기록된 SHA-256',f.sha256)+row('대상 출력',f.outputs.join(', '))+'</dl>').join(''):'<p>이 조회에서 산출물 파일을 받지 못했습니다.</p>')+'<p class="result-caution">파일 내용은 자동으로 열지 않습니다. 파일 저장·전체 검토는 오피스 앱에서 진행하세요.</p></section>';
        html+='<section class="result-block"><h3>조회된 실행 기록 · '+d.tasks.length+'건</h3><p class="result-caution">원본 task ID입니다. 별도 run/attempt ID는 미제공입니다. 최근 조회 범위이므로 전체 이력 수가 아닙니다.</p>'+d.tasks.map(t=>'<dl class="result-entry">'+row('task ID',t.id)+row('종류 / 상태',t.kind+' / '+t.state)+row('생성 / 갱신',t.createdAt+' / '+t.updatedAt)+'</dl>').join('')+(d.tasks.length?'':'<p>이 조회 범위에 실행 기록이 없습니다.</p>')+'</section>';
        html+='<section class="result-block"><h3>YouTube 전송 원장</h3>'+(d.deliveryError?'<p>전송 원장을 조회하지 못했습니다. 미게시로 판단하지 않습니다.</p>':d.deliveries.length?d.deliveries.map(v=>'<dl class="result-entry">'+row('전송 상태',v.state)+row('공개 설정',v.privacyStatus||v.visibility||'미제공')+row('갱신 시각',v.updatedAt)+'</dl>').join(''):'<p>이 조회에 YouTube 전송 기록이 없습니다. 다른 채널의 게시 여부는 확인하지 않습니다.</p>')+'</section></article>';
      }else if(!this.selectedId&&!this.loading){
        html+=this.jobs.length?'<p class="result-caution">조회된 작업 '+this.jobs.length+'건(최대80건). 완료 상태만으로 산출물·승인·공개 게시를 추정하지 않습니다.</p><div class="result-grid">'+this.jobs.slice(0,6).map(j=>'<button type="button" class="result-card" data-result-job="'+esc(j.id)+'"><strong>'+esc(j.title)+'</strong><span>'+esc(this.reviewStep(j.state).label)+'</span><small>'+esc(j.id)+'</small></button>').join('')+'</div>':'<p class="result-empty">표시할 작업이 없습니다. 연결된 오피스에서 작업 기록을 만든 뒤 다시 조회하세요.</p>';
      }
      body.innerHTML=html;
      if(openJobId)$('results-open-review').onclick=()=>this.openReview(openJobId);
      $('result-job').onchange=e=>{if(e.target.value)this.load('job',e.target.value);else{this.selectedId=null;this.current=null;this.render();}};
      body.querySelectorAll('[data-result-job]').forEach(button=>button.onclick=()=>this.load('job',button.dataset.resultJob));
      $('panel-foot').innerHTML='<button type="button" class="item-link" id="results-refresh"'+(this.loading?' disabled':'')+'>다시 조회</button>'+(this.endpoint('list')?'<a class="item-link" href="'+esc(location.origin+'/')+'" target="_blank" rel="noopener">오피스 검토 앱 열기</a>':'')+'<span class="panel-note">승인·제작·게시·재시도·ZIP 생성은 이 화면에서 실행하지 않습니다.</span>';
      $('results-refresh').onclick=()=>this.load(this.selectedId?'job':'list',this.selectedId);
    },

    open() {
      if(workshop.opened)workshop.setOpen(false);workbench.setRoster(false);hud.closePanel();
      controls.keys.clear();controls.dragging=false;controls.setVehicleSpeed(0);controls.setView('overview');
      this.opened=true;space.resultsOpen=true;document.body.classList.add('results-view');
      $('btn-results').setAttribute('aria-pressed','true');$('btn-results').textContent='작업·결과 닫기';$('panel').hidden=false;
      this.render();world.syncRendering();this.load();
    },

    close() {
      if(!this.opened)return;
      this.opened=false;space.resultsOpen=false;this.serial++;this.controller?.abort();this.controller=null;this.loading=false;
      document.body.classList.remove('results-view');$('panel').hidden=true;$('btn-results').setAttribute('aria-pressed','false');$('btn-results').textContent='작업·결과';
      controls.keys.clear();controls.dragging=false;world.syncRendering();
    },

    init() {
      $('btn-results').onclick=()=>this.opened?hud.closePanel():this.open();
      document.addEventListener('keydown',e=>{if(this.opened&&e.key==='Escape'){e.preventDefault();e.stopPropagation();hud.closePanel();$('btn-results').focus();}});
    },
  };

  const workbench = {
    attentionId: null,

    sourceLabel(source, failed) {
      if (source === 'sample-fallback') return '실시간 연결 실패 · 예시 데이터';
      if (source !== 'live') return '예시 데이터 · 실행 연결 전';
      return failed ? '연결 지연 · 마지막 API 데이터' : '실시간 API';
    },

    filteredAgents(agents, query = '', attention = false) {
      const needle = query.trim().toLocaleLowerCase();
      const rank = { error: 0, unknown: 1, waiting: 2 };
      return agents.filter(a => (!attention || Object.hasOwn(rank, a.status)) &&
        [a.name, a.engine, a.model, a.task].some(v => String(v || '').toLocaleLowerCase().includes(needle)))
        .sort((a, b) => (rank[a.status] ?? 3) - (rank[b.status] ?? 3));
    },

    nextAttentionId(agents, current) {
      const targets = this.filteredAgents(agents, '', true);
      if (!targets.length) return null;
      return targets[(targets.findIndex(a => a.id === current) + 1) % targets.length].id;
    },

    setRoster(open) {
      if(open&&space.resultsOpen)hud.closePanel();
      space.rosterOpen = open === true;
      controls.keys.clear(); controls.dragging = false;
      $('roster-panel').hidden = !space.rosterOpen;
      $('btn-roster').textContent = space.rosterOpen ? '3D 도시로' : '동료 목록';
      $('btn-roster').setAttribute('aria-pressed', String(space.rosterOpen));
      document.body.classList.toggle('roster-view', space.rosterOpen);
      world.syncRendering();
      if (space.rosterOpen) { $('world-tools').open = false; $('roster-search').focus(); }
      else $('btn-roster').focus();
    },

    focusAttention() {
      const agents = space.data?.agents || [];
      this.attentionId = this.nextAttentionId(agents, this.attentionId);
      const agent = agents.find(a => a.id === this.attentionId);
      if (!agent) return;
      this.setRoster(false);
      controls.setVehicleSpeed(0); controls.setLayer('office');
      hud.openStage(agent.stageId);
    },

    refresh(d) {
      const agents = d?.agents || [], targets = this.filteredAgents(agents, '', true);
      $('btn-attention').disabled = !targets.length;
      $('btn-attention').textContent = '도움 ' + targets.length;
      $('roster-summary').textContent = agents.length + '명 · 도움/오류 ' + targets.length + '명';
      const source = this.sourceLabel(data.source, Boolean(data.error));
      const stamp = d?.generatedAt && Number.isFinite(Date.parse(d.generatedAt)) ? fmtTime(d.generatedAt) : '시각 미확인';
      $('roster-source').textContent = source + ' · 원본 갱신 ' + stamp;
      const visible = this.filteredAgents(agents, $('roster-search').value, $('roster-attention').checked);
      const signature = JSON.stringify([Boolean(d), visible.map(a => [a.id, a.name, a.status, a.engine, a.model, a.task, a.stageId, d.stages.find(s => s.id === a.stageId)?.name])]);
      hud.replaceContent($('roster-list'), signature, () => {
        const cards = visible.map(a => {
          const card = document.createElement('article'); card.className = 'roster-agent';
          const title = document.createElement('h2'); title.textContent = a.name;
          const badge = document.createElement('span'); badge.className = 'roster-state ' + a.status; badge.textContent = statusLabel(a.status);
          const stage = d.stages.find(s => s.id === a.stageId);
          const meta = document.createElement('p'); meta.className = 'roster-meta'; meta.textContent = [stage?.name, a.engine, a.model].filter(Boolean).join(' · ');
          const task = document.createElement('p'); task.textContent = a.task || '표시할 업무 설명이 없습니다.';
          const visit = document.createElement('button'); visit.type = 'button'; visit.textContent = '부서 보기';
          visit.dataset.focusKey = JSON.stringify(['agent', a.id, 'visit']);
          visit.onclick = () => { this.setRoster(false); controls.setVehicleSpeed(0); controls.setLayer('office'); hud.openStage(a.stageId); };
          card.append(title, badge, meta, task, visit); return card;
        });
        if (!cards.length) { const empty = document.createElement('p'); empty.textContent = d ? '조건에 맞는 동료가 없습니다.' : '동료 데이터를 읽는 중입니다.'; cards.push(empty); }
        $('roster-list').replaceChildren(...cards);
      }, $('roster-panel'));
    },

    init() {
      $('world-quality').value = QUALITY;
      $('world-motion').checked = REDUCED; $('world-motion').disabled = SYSTEM_REDUCED;
      $('world-quality-apply').onclick = () => {
        const quality = $('world-quality').value;
        if (!['low', 'high'].includes(quality)) return;
        try { localStorage.setItem('heobrain.world-quality.v1', quality); } catch (_) { /* URL 설정 사용 */ }
        if (quality === QUALITY) { $('world-setting-status').textContent = '현재 화질을 저장했습니다.'; return; }
        const url = new URL(location.href); url.searchParams.set('quality', quality); url.searchParams.set('layer', space.layer);
        location.assign(url.href);
      };
      $('world-motion').onchange = () => {
        REDUCED = SYSTEM_REDUCED || $('world-motion').checked;
        world.syncMotionUI();
        try { localStorage.setItem('heobrain.reduced-motion.v1', String(REDUCED)); } catch (_) { /* 세션 설정 사용 */ }
        $('world-setting-status').textContent = REDUCED ? '도시의 배경 움직임을 줄였습니다.' : '도시의 배경 움직임을 켰습니다.';
      };
      $('btn-roster').onclick = () => this.setRoster(!space.rosterOpen);
      $('btn-attention').onclick = () => this.focusAttention();
      $('roster-search').oninput = $('roster-attention').onchange = () => this.refresh(space.data);
      $('world-tools').addEventListener('toggle', () => { if ($('world-tools').open) { controls.keys.clear(); controls.dragging = false; } });
      document.addEventListener('keydown', e => { if (e.key === 'Escape' && space.rosterOpen) this.setRoster(false); });
      document.querySelectorAll('[data-world-view]').forEach(button => {
        button.onclick = () => {
          this.setRoster(false); controls.setVehicleSpeed(0);
          const view=button.dataset.worldView;
          const office=['office','arrival','atrium'].includes(view);
          controls.setLayer(office ? 'office' : 'meadow');
          if(view==='arrival')controls.animateCamera({alpha:-1.05,beta:1.04,radius:32,target:new B.Vector3(0,3.2,-51)});
          if(view==='atrium' && space.stages.length){
            const st=space.stages[0];
            controls.animateCamera({alpha:Math.atan2(Math.cos(st.rotY),Math.sin(st.rotY))-.5,beta:1.03,radius:28,target:world.local(st,0,3,0)});
          }
          if (view === 'cruiser') controls.animateCamera({ alpha: -.7, beta: 1.1, radius: 125, target: new B.Vector3(155, 46, 86) });
          $('world-tools').open = false;
        };
      });
      data.onChange(d => this.refresh(d || space.data)); this.refresh(space.data);
    },
  };

  const esc = (s) => String(s).replace(/[&<>"']/g, (ch) => ({ '&': '&amp;', '<': '&lt;', '>': '&gt;', '"': '&quot;', "'": '&#39;' }[ch]));
  const fmt = (n) => Number(n || 0).toLocaleString('ko-KR');
  const fmtTime = (iso) => { const d = new Date(iso); return Number.isNaN(d.getTime()) ? iso : d.toLocaleString('ko-KR', { hour12: false, month: 'numeric', day: 'numeric', hour: '2-digit', minute: '2-digit' }); };
  const statusLabel = (s) => ({ running: '실행 중', idle: '대기', waiting: '사람 답 대기', error: '오류', unknown: '상태 미확인' }[s] || '상태 미확인');
  const faceColor = (a) => a.av.body.material.diffuseColor.toHexString();

  // ======================================================================
  // embed — 오피스 앱 iframe 안에서의 postMessage 연동 (설계 12장)
  // ======================================================================
  const embed = {
    enabled: new URLSearchParams(location.search).get('embed') === '1' && window.parent !== window,
    handler: null,

    post(msg) {
      if (!this.enabled) return;
      window.parent.postMessage({ source: 'office-world', ...msg }, location.origin);
    },

    onMessage(fn) { this.handler = fn; },

    init() {
      if (!this.enabled) return;
      window.addEventListener('message', (event) => {
        if (event.origin !== location.origin || event.source !== window.parent) return;
        const m = event.data;
        if (!m || m.source !== 'content-office') return;
        if (this.handler) this.handler(m);
      });
      this.onMessage((m) => {
        if (m.type === 'focus') {
          const st = space.stages.find((s) => s.items.some((it) => it.id === m.itemId));
          if (!st) return;
          space.embedFocus = m.itemId;
          hud.openStage(st.id);
        } else if (m.type === 'refresh') {
          data.load(false);
        } else if (m.type === 'result') {
          space.embedResult = { ok: !!m.ok, message: String(m.message || '') };
          space.pendingActions.clear();
          actionTimers.forEach((t) => clearTimeout(t));
          actionTimers.clear();
          if (space.selectedStage) hud.openStage(space.selectedStage, true);
        }
      });
    },
  };

  // ======================================================================
  // 시작
  // ======================================================================
  function start() {
    world.init($('scene'));
    hud.init();
    controls.init();
    data.init();
    embed.init();
    workbench.init();
    workshop.init();
    results.init();
    // Optional appearance code must not delay base-world initialization or load in low mode.
    if (QUALITY === 'high') void Promise.allSettled([
      import('./arrival-detail.js?v=20261030'),
      import('./atrium-detail.js?v=20261031'),
      import('./guide-avatar.js?v=20261031'),
    ]);

    let simTimer = null;
    data.onChange((d) => {
      if (!d) { if (space.data) hud.refresh(space.data); return; } // 폴링 실패: 마지막 상태 유지, 상태 표시만 갱신
      d = organization.project(d);
      const first = !space.data;
      const stageKey = d.stages.map((s) => s.id).join('|');
      const agentKey = d.agents.map((a) => a.id).join('|');
      const prevStageKey = space.data ? space.data.stages.map((s) => s.id).join('|') : null;
      const prevAgentKey = space.data ? space.data.agents.map((a) => a.id).join('|') : null;
      space.data = d;
      if (first || stageKey !== prevStageKey) {
        world.buildStages(d.stages);
        world.buildAgents(d.agents);
        hud.rebuild(d);
      } else {
        space.stages.forEach((st) => { const nx = d.stages.find((s) => s.id === st.id); if (nx) Object.assign(st, { items: nx.items, name: nx.name, approval: nx.approval, url: nx.url, view: nx.view, teamId:nx.teamId, description:nx.description, goals:nx.goals, connection:nx.connection, workflowStages:nx.workflowStages }); });
        if (agentKey !== prevAgentKey) world.buildAgents(d.agents); else world.updateAgentStatuses(d.agents);
        hud.refresh(d);
      }
      const projectionSource = data.source;
      if (!REDUCED) d.flows.forEach((f, i) => setTimeout(() => { if (data.source === projectionSource) world.spawnFlow(f); }, 600 + i * 1800));
      if (data.source === 'live' && simTimer) { clearInterval(simTimer); simTimer = null; }
      if (!REDUCED && data.source !== 'live' && !simTimer) {
        simTimer = setInterval(() => {
          if (data.source === 'live' || REDUCED || document.hidden || space.rosterOpen) return;
          const seated = space.agents.filter((a) => a.mode === 'seated' && a.status !== 'waiting');
          if (seated.length) world.memoryTrip(seated[Math.floor(Math.random() * seated.length)]);
          const f = d.flows[Math.floor(Math.random() * d.flows.length)];
          if (f) world.spawnFlow({ from: f.from, to: f.to, itemId: `${f.itemId}-${Date.now()}` });
        }, 11000);
      }
      if (!REDUCED && data.source === 'live' && !first) {
        if (d.events.some((ev) => /기억/.test(ev.text || ''))) {
          const seated = space.agents.filter((a) => a.mode === 'seated');
          if (seated.length) world.memoryTrip(seated[Math.floor(Math.random() * seated.length)]);
        }
      }
    });
    data.load(true).then(() => {
      if(space.data){
        const layer=new URLSearchParams(location.search).get('layer')==='office'?'office':'meadow';
        controls.setLayer(layer);controls.cameraTween=null;
        const home=layer==='office'?OVERVIEW_HOME:{alpha:-Math.PI/2,beta:1.15,radius:430,target:new B.Vector3(0,-18,0)};
        controls.animateCamera(home,0);
      }
    }).catch((error) => {
      data.error = '투영 초기화 실패: ' + error.message;
      notice('투영 데이터를 읽을 수 없습니다', '연결되면 자동으로 다시 조회합니다.');
    }).finally(() => { data.startPolling(); embed.post({ type: 'ready' }); });

    try {
      const saved = localStorage.getItem('office-world.view');
      if (new URLSearchParams(location.search).has('resume') && saved === 'walk' && !isPhone()) controls.setView('walk');
    } catch (_) { /* 저장 불가 환경 */ }
  }

  // 디버그·검사용 접근 (비밀값 없음)
  window.__officeWorld = { space, world, controls, hud, data, embed, workbench, quality: QUALITY };

  if (document.readyState === 'loading') document.addEventListener('DOMContentLoaded', start);
  else start();
})();
