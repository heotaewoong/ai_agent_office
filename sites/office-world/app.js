/* HeoBrain 오피스 월드 — 공간 투영 v1을 읽어 우주 위 잔디 섬 마을로 그린다.
   모듈: data(읽기·폴링) · world(장면) · hud(오버레이) · controls(입력·카메라). 모두 space 하나를 공유한다. */
(() => {
  'use strict';

  const $ = (id) => document.getElementById(id);
  const REDUCED = window.matchMedia('(prefers-reduced-motion: reduce)').matches;
  const isPhone = () => window.innerWidth < 720;
  const B = window.BABYLON;
  // ?quality=low 이면 그림자·SSAO·블룸을 끈다(저사양 PC·휴대폰)
  const QUALITY = new URLSearchParams(location.search).get('quality') || (isPhone() ? 'low' : 'high');

  const notice = (title, text) => {
    $('notice-title').textContent = title;
    $('notice-text').textContent = text;
    $('notice').hidden = false;
  };

  if (!B) {
    notice('3D 라이브러리를 불러오지 못했습니다', 'cdnjs.cloudflare.com 접근이 막혀 있으면 babylon.min.js를 같은 폴더에 두고 index.html의 script 주소를 바꿔 주세요.');
    return;
  }

  // ======================================================================
  // 공유 상태
  // ======================================================================
  const space = {
    data: null,            // 정규화된 투영
    stages: [],            // 배치 정보가 붙은 단계 목록
    agents: [],            // 아바타가 붙은 동료 목록
    view: 'overview',      // 'overview' | 'walk'
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

  // ======================================================================
  // data — 투영 읽기와 폴링
  // ======================================================================
  const data = {
    apiUrl: null,
    source: 'sample',
    error: null,
    timer: null,
    listeners: [],

    init() {
      const q = new URLSearchParams(location.search).get('api');
      this.apiUrl = q || window.OFFICE_WORLD_API || null;
    },

    onChange(fn) { this.listeners.push(fn); },

    async fetchJson(url) {
      const res = await fetch(url, { cache: 'no-store', headers: { Accept: 'application/json' } });
      if (!res.ok) throw new Error(`HTTP ${res.status}`);
      return res.json();
    },

    async load(initial) {
      let raw = null;
      if (this.apiUrl) {
        try {
          raw = await this.fetchJson(this.apiUrl);
          this.source = 'live';
          this.error = null;
        } catch (err) {
          this.error = `실시간 읽기 실패: ${err.message}`;
          if (!initial) { this.emit(null); return; }
        }
      }
      if (!raw) {
        try {
          raw = await this.fetchJson('data/space.json');
          this.source = this.apiUrl ? 'sample-fallback' : 'sample';
        } catch (err) {
          notice('투영 데이터를 읽을 수 없습니다', `data/space.json 을 불러오지 못했습니다 (${err.message}). 파일을 직접 열지 말고 정적 서버로 여세요. 예: python -m http.server 8080`);
          return;
        }
      }
      this.emit(this.normalize(raw));
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
          status: statuses.has(a.status) ? a.status : 'idle',
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
      this.timer = setInterval(() => this.load(false), 10000);
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

    // 그림자: 드리우는 쪽과 받는 쪽
    castShadow(mesh) { if (this.shadows) this.shadows.addShadowCaster(mesh, false); },
    receiveShadow(mesh) { if (this.shadows) mesh.receiveShadows = true; },

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
      // 고해상도 화면에서도 선명하게: 장치 픽셀 비율만큼 실제 렌더 해상도를 올린다(최대 2배).
      const applyDpr = () => this.engine.setHardwareScalingLevel(1 / Math.min(2, window.devicePixelRatio || 1));
      applyDpr();
      const scene = new B.Scene(this.engine);
      this.scene = scene;
      this.applyDpr = applyDpr;
      scene.clearColor = new B.Color4(0.02, 0.03, 0.09, 1);
      scene.ambientColor = new B.Color3(0.25, 0.28, 0.4);

      const hemi = new B.HemisphericLight('hemi', new B.Vector3(0.2, 1, 0.1), scene);
      hemi.intensity = 0.85;
      hemi.groundColor = new B.Color3(0.12, 0.14, 0.3);
      const sun = new B.DirectionalLight('sun', new B.Vector3(-0.5, -1, 0.35), scene);
      sun.intensity = 1.15;
      sun.diffuse = new B.Color3(1, 0.95, 0.86);
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

      this.buildSky();
      this.buildHub();

      scene.onBeforeRenderObservable.add(() => this.tick());
      window.addEventListener('resize', () => { this.applyDpr(); this.engine.resize(); });
      this.engine.runRenderLoop(() => scene.render());
    },

    buildSky() {
      const size = 1024;
      const tex = new B.DynamicTexture('sky', { width: size * 2, height: size }, this.scene, false);
      const ctx = tex.getContext();
      ctx.fillStyle = '#05081c';
      ctx.fillRect(0, 0, size * 2, size);
      const blobs = [
        [300, 420, 420, 'rgba(96, 58, 170, 0.28)'],
        [1500, 300, 380, 'rgba(36, 120, 150, 0.22)'],
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
      const sky = B.MeshBuilder.CreateSphere('skybox', { diameter: 700, segments: 24, sideOrientation: B.Mesh.BACKSIDE }, this.scene);
      const m = new B.StandardMaterial('skymat', this.scene);
      m.emissiveTexture = tex;
      m.disableLighting = true;
      m.backFaceCulling = false;
      sky.material = m;
      sky.isPickable = false;
      sky.infiniteDistance = true;
      this.sky = sky;
    },

    buildHub() {
      const s = this.scene;
      // 광장: 블록 땅 위에 놓인 밝은 돌 원판. 클릭하면 공유 기억 패널.
      const plaza = B.MeshBuilder.CreateCylinder('hub-plaza', { height: 0.14, diameter: HUB_R * 2 - 1.0, tessellation: 12 }, s);
      plaza.position.y = 0.07;
      plaza.material = this.blockMaterial('plaza', this.blockTextures().path);
      plaza.material.diffuseTexture.uScale = 7; plaza.material.diffuseTexture.vScale = 7;
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

    buildTerrain() {
      const s = this.scene;
      const LAND_R = ISLAND_DIST + ISLAND_D / 2 + 6;
      const noise = (x, z) => 0.5 + 0.5 * Math.sin(x * 0.23 + Math.sin(z * 0.19) * 1.7) * Math.cos(z * 0.21 + Math.sin(x * 0.13) * 1.3);
      const cols = new Map();
      const key = (x, z) => `${x},${z}`;
      const R = Math.ceil(LAND_R + 6);
      for (let x = -R; x <= R; x++) {
        for (let z = -R; z <= R; z++) {
          const cx = x + 0.5, cz = z + 0.5;
          const r = Math.hypot(cx, cz);
          const a = Math.atan2(cz, cx);
          const edge = LAND_R + 3.2 * Math.sin(a * 3 + 0.7) + 2.1 * Math.sin(a * 7 + 2.3) + 1.2 * Math.sin(a * 13);
          if (r > edge) continue;
          const zone = this.flatZone(cx, cz);
          let level = zone ? 0 : Math.min(2, Math.floor(noise(cx, cz) * 2.6 + (r > edge - 4 ? -0.5 : 0)));
          if (level < 0) level = 0;
          const depth = 1 + Math.floor((1 - r / edge) * 5 + noise(cz * 0.7, cx * 0.7) * 1.5);
          cols.set(key(x, z), { x: cx, z: cz, level, depth, zone });
        }
      }
      // 블록 종류별 thin instance (픽셀 텍스처)
      const T = this.blockTextures();
      void s;
      const grass = this.blockMesh('grass', T.grass, 3, [1, 1, 1, 1, 0, 2]);
      const dirt = this.blockMesh('dirt', T.dirt, 1, [0, 0, 0, 0, 0, 0]);
      const stone = this.blockMesh('stone', T.stone, 1, [0, 0, 0, 0, 0, 0]);
      const path = this.blockMesh('path', T.path, 1, [0, 0, 0, 0, 0, 0]);
      const trunk = this.blockMesh('trunk', T.trunk, 2, [0, 0, 0, 0, 1, 1]);
      const leaf = this.blockMesh('leaf', T.leaves, 1, [0, 0, 0, 0, 0, 0]);
      const bufs = { grass: [], dirt: [], stone: [], path: [], trunk: [], leaf: [] };
      const put = (kind, x, y, z) => bufs[kind].push(B.Matrix.Translation(x, y, z));
      let seed = 11;
      const rnd = () => { seed = (seed * 48271) % 2147483647; return seed / 2147483647; };
      cols.forEach((c) => {
        const topKind = c.zone === 'path' ? 'path' : 'grass';
        put(topKind, c.x, c.level - 0.5, c.z);
        for (let y = c.level - 1; y >= -c.depth; y--) put(y <= -c.depth + 1 ? 'stone' : 'dirt', c.x, y - 0.5, c.z);
        // 나무: 평지 밖의 일부 칸
        if (!c.zone && rnd() < 0.018 && this.pathDistance(new B.Vector3(c.x, 0, c.z)) > 3) {
          const h = 3 + Math.floor(rnd() * 2);
          for (let y = 0; y < h; y++) put('trunk', c.x, c.level + y + 0.5, c.z);
          for (let dx = -1; dx <= 1; dx++) for (let dz = -1; dz <= 1; dz++) for (let dy = 0; dy < 2; dy++) {
            if (Math.abs(dx) + Math.abs(dz) === 2 && dy === 1) continue;
            put('leaf', c.x + dx, c.level + h - 1 + dy + 0.5, c.z + dz);
          }
          put('leaf', c.x, c.level + h + 1.5, c.z);
        }
      });
      const meshes = { grass, dirt, stone, path, trunk, leaf };
      Object.keys(bufs).forEach((k) => {
        if (!bufs[k].length) { meshes[k].setEnabled(false); return; }
        const arr = new Float32Array(bufs[k].length * 16);
        bufs[k].forEach((mtx, i) => mtx.copyToArray(arr, i * 16));
        meshes[k].thinInstanceSetBuffer('matrix', arr, 16, true);
        meshes[k].freezeWorldMatrix();
        this.receiveShadow(meshes[k]);
        if (k !== 'dirt' && k !== 'stone') this.castShadow(meshes[k]);
      });
      this.terrain = { cols, key, meshes: Object.values(meshes), landR: LAND_R };
    },

    heightAt(x, z) {
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
      // 바닥: 나무 판자 픽셀 텍스처
      const floor = P(B.MeshBuilder.CreateBox('floor', { width: 12.4, height: 0.16, depth: 11.4 }, s), 0, 0.08, 0);
      floor.material = this.blockMaterial(`floor-${st.id}`, this.blockTextures().planks);
      floor.material.diffuseTexture.uScale = 12; floor.material.diffuseTexture.vScale = 11;
      floor.material.diffuseColor = B.Color3.FromHexString(this.tint(st.color, '#ffffff', 0.75));
      this.receiveShadow(floor);
      // 러그: 단계색
      P(this.box('rug', 5.2, 0.05, 4.2, soft), 2.4, 0.18, 2.4).isPickable = false;
      // 벽: 바깥은 단계색, 안쪽은 어두운 단계색 패널
      P(this.box('wall-back', 12.6, 3.2, 0.3, st.color), 0, 1.6, -5.75);
      P(this.box('wall-side', 0.3, 3.2, 11.6, st.color), -6.2, 1.6, 0);
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
      const shelf = P(this.box('shelf', 1.8, 2.4, 0.5, '#3f3048'), 4.9, 1.2, -5.3);
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
      P(table, 2.6, 0.38, 1.9).material = this.mat('table', '#6b5440');
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
      // 방 안 모든 물체가 그림자를 드리우고 받는다
      st.node.getChildMeshes().forEach((m) => { if (m.name !== 'edge' && !/glow|screen|bulb|board-bar/.test(m.name)) this.castShadow(m); this.receiveShadow(m); });
    },

    buildDesk(st, x, z, rotY, slot) {
      const g = new B.TransformNode(`desk-${st.id}-${slot}`, this.scene);
      g.parent = st.node;
      g.position.set(x, 0, z);
      g.rotation.y = rotY;
      const add = (mesh, px, py, pz) => { mesh.parent = g; mesh.position.set(px, py, pz); mesh.metadata = { stageId: st.id }; return mesh; };
      add(this.box('desk-top', 2.2, 0.1, 1.0, '#6b4f3a'), 0, 0.88, 0);
      add(this.box('desk-front', 2.2, 0.6, 0.06, '#523b2b'), 0, 0.52, -0.47);
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
      const sit = this.local(st, x + Math.sin(rotY) * 1.0, 0, z + Math.cos(rotY) * 1.0);
      st.desks.push({ slot, sitPos: sit, faceY: st.rotY + rotY + Math.PI, screen, taken: null, localX: x, localZ: z, rotY });
    },

    buildPlant(st, x, z) {
      const pot = this.box('pot', 0.7, 0.6, 0.7, '#6b4a2e');
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
      const s = this.scene;
      const root = new B.TransformNode(`avatar-${name}`, s);
      const hipY = 0.78;
      const make = (n, w, h, d, hex) => { const m = this.box(`${name}-${n}`, w, h, d, hex); m.parent = root; m.isPickable = false; return m; };
      const body = make('body', 0.62, 0.78, 0.34, shirt); body.position.y = hipY + 0.39;
      const head = make('head', 0.58, 0.58, 0.58, skin); head.position.y = hipY + 0.78 + 0.31;
      const cap = make('hair', 0.62, 0.2, 0.62, hair); cap.position.y = hipY + 0.78 + 0.56;
      const hairBack = make('hair-back', 0.62, 0.3, 0.14, hair); hairBack.position.set(0, hipY + 0.78 + 0.34, -0.26);
      [-0.13, 0.13].forEach((ex, i) => { const eye = make(`eye-${i}`, 0.1, 0.1, 0.04, '#1a1e2e'); eye.position.set(ex, hipY + 0.78 + 0.34, 0.3); });
      const limb = (n, w, h, d, hex, px, py) => {
        const pivot = new B.TransformNode(`${name}-${n}-pivot`, s);
        pivot.parent = root; pivot.position.set(px, py, 0);
        const m = this.box(`${name}-${n}`, w, h, d, hex); m.parent = pivot; m.position.y = -h / 2; m.isPickable = false;
        return pivot;
      };
      const legL = limb('legL', 0.28, hipY, 0.3, '#2b3350', -0.16, hipY);
      const legR = limb('legR', 0.28, hipY, 0.3, '#2b3350', 0.16, hipY);
      const armL = limb('armL', 0.22, 0.72, 0.24, skin, -0.44, hipY + 0.74);
      const armR = limb('armR', 0.22, 0.72, 0.24, skin, 0.44, hipY + 0.74);
      const marker = B.MeshBuilder.CreateSphere(`${name}-marker`, { diameter: 0.26, segments: 8 }, s);
      marker.parent = root; marker.position.y = hipY + 0.78 + 0.95; marker.isPickable = false;
      marker.material = this.mat('marker', '#4ad994', { emissive: 1.0, unlit: true });
      root.getChildMeshes().forEach((m) => { if (m !== marker) { this.castShadow(m); this.receiveShadow(m); } });
      return { root, legL, legR, armL, armR, head, body, marker, hipY, phase: Math.random() * 6 };
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

    buildAgents(agents) {
      this.clearAgents();
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
          const spot = this.local(st, 1.0 + (i % 3) * 1.2, 0, 1.5);
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
    walkable(v, fromY) {
      const h = this.heightAt(v.x, v.z);
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
      if (!REDUCED) {
        this.hub.rings.forEach((r, i) => { r.rotation.y += dt * (0.08 + i * 0.05) * (i % 2 ? -1 : 1); });
        if (this.sky) this.sky.rotation.y += dt * 0.004;
        const pulse = 1 + Math.sin(this.time * 1.6) * 0.06;
        this.hub.core.scaling.set(pulse, pulse, pulse);
        this.stepAgents(dt);
        this.stepFlows(dt);
        space.agents.forEach((a) => { a.av.marker.isVisible = a.status !== 'running' || Math.sin(this.time * 5 + a.av.phase) > -0.4; });
      }
      controls.tick(dt);
      hud.tick();
    },
  };

  // ======================================================================
  // controls — 카메라와 입력
  // ======================================================================
  const OVERVIEW_HOME = { alpha: -Math.PI / 2.35, beta: 1.02, radius: 66, target: new B.Vector3(0, 1.5, 0) };

  const controls = {
    overview: null, walk: null, player: null, keys: new Set(),
    yaw: Math.PI, pitch: 0.18, vy: 0, dragging: false, lastX: 0, lastY: 0,
    focused: null,   // 확대해서 보고 있는 방 ID 또는 'hub'

    // 관제 카메라를 부드럽게 이동
    animateCamera(to, ms = 900) {
      const cam = this.overview;
      const keys = ['alpha', 'beta', 'radius', 'target'];
      if (REDUCED) { keys.forEach((k) => { if (to[k] !== undefined) cam[k] = to[k]; }); return; }
      const ease = new B.CubicEase(); ease.setEasingMode(B.EasingFunction.EASINGMODE_EASEINOUT);
      const frames = Math.round((ms / 1000) * 60);
      keys.forEach((k) => {
        if (to[k] === undefined) return;
        const from = k === 'target' ? cam.target.clone() : cam[k];
        B.Animation.CreateAndStartAnimation(`cam-${k}`, cam, k, 60, frames, from, to[k], B.Animation.ANIMATIONLOOPMODE_CONSTANT, ease);
      });
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
      if (space.view === 'overview') this.animateCamera(Object.assign({}, OVERVIEW_HOME, { target: OVERVIEW_HOME.target.clone() }), 1000);
    },

    // 걷기 시점으로 바꾸고 방 입구에 세운다
    enterStage(st) {
      if (isPhone()) return;
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
      this.overview = new B.ArcRotateCamera('overview', -Math.PI / 2.35, 1.02, 66, new B.Vector3(0, 1.5, 0), s);
      this.overview.lowerRadiusLimit = 26; this.overview.upperRadiusLimit = 120;
      this.overview.lowerBetaLimit = 0.45; this.overview.upperBetaLimit = 1.38;
      this.overview.wheelPrecision = 12; this.overview.panningSensibility = 60;
      this.overview.pinchPrecision = 60;
      this.overview.minZ = 0.5; this.overview.maxZ = 900;
      this.overview.attachControl(canvas, true);
      s.activeCamera = this.overview;

      this.walk = new B.UniversalCamera('walk', new B.Vector3(0, 3, -8), s);
      this.walk.inputs.clear();
      this.walk.minZ = 0.3; this.walk.maxZ = 900;

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

      // 후처리: MSAA 4배 + FXAA, 블룸, ACES 톤 매핑, 약한 비네트
      const pipeline = new B.DefaultRenderingPipeline('post', true, s, [this.overview, this.walk]);
      pipeline.samples = 4;
      pipeline.fxaaEnabled = true;
      if (QUALITY !== 'low') {
        pipeline.bloomEnabled = true;
        pipeline.bloomThreshold = 0.62;
        pipeline.bloomWeight = 0.42;
        pipeline.bloomKernel = 64;
        pipeline.bloomScale = 0.5;
      }
      pipeline.imageProcessingEnabled = true;
      pipeline.imageProcessing.toneMappingEnabled = true;
      pipeline.imageProcessing.toneMappingType = B.ImageProcessingConfiguration.TONEMAPPING_ACES;
      pipeline.imageProcessing.exposure = 1.38;
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
        if (info.type !== B.PointerEventTypes.POINTERTAP || space.view !== 'overview') return;
        const pick = info.pickInfo;
        if (!pick || !pick.hit || !pick.pickedMesh) return;
        const meta = pick.pickedMesh.metadata || {};
        if (meta.stageId) hud.openStage(meta.stageId);
        else if (meta.hub) hud.openBrain();
      });
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
      if (view === 'walk' && isPhone()) view = 'overview';
      space.view = view;
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
      if (e.target && /^(INPUT|TEXTAREA)$/.test(e.target.tagName)) return;
      const k = e.key.toLowerCase();
      if (down && k === 'm') { this.setView(space.view === 'walk' ? 'overview' : 'walk'); return; }
      if (down && k === 'escape') {
        if (space.view === 'walk') { this.exitSpace(); return; }
        hud.closePanel(); this.resetOverview(); return;
      }
      if (space.view !== 'walk') return;
      if (down && k === 'r') { this.yaw = this.player.av.root.rotation.y + Math.PI; this.pitch = 0.18; return; }
      if (down && k === 'e') { hud.toggleNearestAgent(); return; }
      if ([' ', 'w', 'a', 's', 'd', 'shift', 'arrowup', 'arrowdown', 'arrowleft', 'arrowright'].includes(k)) {
        e.preventDefault();
        if (down) this.keys.add(k); else this.keys.delete(k);
      }
    },

    tick(dt) {
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
      const speed = keys.has('shift') ? 6.2 : 3.3;
      const groundNow = world.heightAt(p.pos.x, p.pos.z) ?? 0;
      if (moving) {
        move.normalize().scaleInPlace(speed * dt);
        const next = p.pos.add(move);
        const tryMove = (cand) => { if (world.walkable(cand, groundNow)) { p.pos.x = cand.x; p.pos.z = cand.z; return true; } return false; };
        if (!tryMove(next)) {
          if (!tryMove(p.pos.add(new B.Vector3(move.x, 0, 0)))) tryMove(p.pos.add(new B.Vector3(0, 0, move.z)));
        }
        p.av.root.rotation.y = Math.atan2(move.x, move.z);
        p.walkT += dt;
        world.animateWalk(p.av, p.walkT, speed);
      } else if (p.grounded) {
        world.setPose(p.av, 'stand');
      }
      const ground = world.heightAt(p.pos.x, p.pos.z) ?? groundNow;
      if (keys.has(' ') && p.grounded) { this.vy = 6.2; p.grounded = false; }
      if (!p.grounded) {
        this.vy -= 16 * dt;
        p.pos.y += this.vy * dt;
        if (p.pos.y <= ground) { p.pos.y = ground; p.grounded = true; this.vy = 0; }
      } else {
        // 한 칸 계단은 자동으로 오르내린다
        p.pos.y += (ground - p.pos.y) * Math.min(1, dt * 14);
      }
      p.av.root.position.copyFrom(p.pos);
      const camBack = fwd.scale(-6.8);
      const desired = p.pos.add(camBack).add(new B.Vector3(0, 2.9 + this.pitch * 3.2, 0));
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

    init() {
      $('panel-close').addEventListener('click', () => this.closePanel());
      $('panel-body').addEventListener('click', (e) => {
        if (!embed.enabled) return;
        const act = e.target.closest('[data-action]');
        if (act) {
          const key = `${act.dataset.item}:${act.dataset.action}`;
          if (space.pendingActions.has(key)) return;
          embed.post({ type: 'action', action: act.dataset.action, itemId: act.dataset.item });
          space.pendingActions.add(key);
          space.embedResult = null;
          act.disabled = true;
          setTimeout(() => {
            if (!space.pendingActions.delete(key)) return;
            space.embedResult = { ok: false, message: '응답이 없습니다' };
            if (space.selectedStage) hud.openStage(space.selectedStage, true);
          }, 15000);
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
      $('cards').querySelectorAll('.card.stage').forEach((el) => el.remove());
      this.cards.clear();
      space.stages.forEach((st) => {
        const el = document.createElement('button');
        el.type = 'button';
        el.className = 'card stage';
        el.style.setProperty('--stage', st.color);
        el.addEventListener('click', () => this.openStage(st.id));
        $('cards').appendChild(el);
        this.cards.set(st.id, el);
      });
      this.refresh(d);
    },

    refresh(d) {
      space.stages.forEach((st) => {
        const el = this.cards.get(st.id);
        if (!el) return;
        const agents = space.agents.filter((a) => a.stageId === st.id);
        const running = agents.filter((a) => a.status === 'running').length;
        const human = st.items.filter((it) => it.needsHuman).length;
        el.innerHTML = `<span class="card-dot"></span><span class="card-body"><span class="card-title">${esc(st.name)}</span><span class="card-meta"><span>${st.items.length}건</span><span class="running">${agents.length}명 · ${running} 실행</span>${human ? `<span class="human">사람 ${human}</span>` : ''}</span></span><span class="card-faces">${agents.map((a) => `<span class="face ${a.status}" style="--face:${a.av ? faceColor(a) : '#c9a'}" title="${esc(a.name)}"></span>`).join('')}</span>`;
        el.classList.toggle('active', space.selectedStage === st.id);
      });
      const b = d.brain;
      this.brainCard.innerHTML = `<span class="card-title">${esc(b.name)}</span><span class="card-meta"><span>${fmt(b.notes)} 절</span><span>원본 ${fmt(b.sources)}편</span></span><span class="card-meta"><span>${esc(b.label)}</span></span>`;
      $('tags').innerHTML = [...new Set(space.agents.map((a) => `${a.engine} · ${a.model}`.trim()))].filter((t) => t !== '·').map((t) => `<span class="tag">${esc(t)}</span>`).join('');
      const pill = $('source-pill');
      pill.className = `source-pill ${data.source === 'live' ? 'live' : ''} ${data.error ? 'error' : ''}`.trim();
      pill.textContent = data.source === 'live' ? '실시간' : data.source === 'sample-fallback' ? '예시 데이터 (실시간 실패)' : '예시 데이터';
      pill.title = data.error || '';
      $('updated-at').textContent = d.generatedAt ? `갱신 ${fmtTime(d.generatedAt)}` : '갱신 시각 없음';
      if (space.selectedStage) this.openStage(space.selectedStage, true);
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
      const st = space.stages.find((s) => s.id === id);
      if (!st) return;
      space.selectedStage = id;
      const panel = $('panel');
      panel.style.setProperty('--stage', st.color);
      $('panel-title').textContent = st.name;
      $('panel-sub').textContent = `${st.approval ? st.approval + ' · ' : ''}작업 ${st.items.length}건`;
      const agentName = (aid) => { const a = space.agents.find((x) => x.id === aid); return a ? `${a.name} (${a.engine})` : ''; };
      $('panel-body').innerHTML = st.items.length ? st.items.map((it) => {
        const cls = it.needsHuman ? 'human' : /fail|error/.test(it.state) ? 'failed' : /writing|producing|research|measuring/.test(it.state) ? 'running' : '';
        const acts = embed.enabled ? `<div class="item-actions">${(data.source === 'live' ? it.actions : []).map((a) => `<button type="button" class="item-action" data-action="${esc(a.id)}" data-item="${esc(it.id)}"${space.pendingActions.has(it.id + ':' + a.id) ? ' disabled' : ''}>${esc(a.label)}</button>`).join('')}${it.view ? `<button type="button" class="item-link" data-open="${esc(it.view)}" data-item="${esc(it.id)}">오피스에서 열기</button>` : ''}</div>` : '';
        return `<div class="item${space.embedFocus === it.id ? ' active' : ''}" data-item-id="${esc(it.id)}"><span class="item-stripe ${cls}"></span><div><div class="item-title">${esc(it.title)}</div><div class="item-state">${esc(it.stateLabel)}</div>${it.agentId ? `<div class="item-agent">담당 ${esc(agentName(it.agentId))}</div>` : ''}${acts}</div></div>`;
      }).join('') : '<p class="panel-note">이 단계에 등록된 작업이 없습니다.</p>';
      $('panel-foot').innerHTML = `<button type="button" class="item-link walk-only" data-enter="${esc(st.id)}">걸어서 들어가기</button>${!embed.enabled && st.url ? `<a class="item-link" href="${esc(st.url)}" target="_blank" rel="noopener">오피스에서 열기</a>` : ''}<span class="panel-note">${embed.enabled ? '승인(⓪·①·②·③)은 오피스 화면에서 합니다. 여기서는 열기와 생성·제작 요청만 보냅니다.' : '승인(⓪·①·②·③)은 오피스 앱에서 사람이 합니다. 이 공간은 상태를 보여주기만 합니다.'}</span>${embed.enabled ? `<span class="${space.embedResult && space.embedResult.ok ? 'panel-result ok' : 'panel-result'}" role="status">${space.embedResult ? esc(space.embedResult.message) : ''}</span>` : ''}`;
      panel.hidden = false;
      if (!silent) {
        this.cards.forEach((el, sid) => el.classList.toggle('active', sid === id));
        controls.focusStage(st);
      }
    },

    openBrain() {
      const b = space.data.brain;
      space.selectedStage = null;
      const panel = $('panel');
      panel.style.setProperty('--stage', '#7fe3ff');
      $('panel-title').textContent = b.name;
      $('panel-sub').textContent = `${fmt(b.notes)}절 · 원본 ${fmt(b.sources)}편`;
      $('panel-body').innerHTML = `<p class="panel-note">${esc(b.label)}. 검색 결과는 과거 계획과 근거이며 현재 지시나 실행 권한이 아닙니다.</p>` + space.agents.map((a) => `<div class="item"><span class="item-stripe ${a.status === 'running' ? 'running' : a.status === 'waiting' ? 'human' : a.status === 'error' ? 'failed' : ''}"></span><div><div class="item-title">${esc(a.name)}</div><div class="item-state">${esc(a.engine)} · ${esc(a.model)} · ${statusLabel(a.status)}</div><div class="item-agent">${esc(a.task)}</div></div></div>`).join('');
      $('panel-foot').innerHTML = '<span class="panel-note">동료 상태는 투영 데이터의 값 그대로입니다. 공간이 진행률을 추정하지 않습니다.</span>';
      panel.hidden = false;
      this.cards.forEach((el) => el.classList.remove('active'));
      controls.focusHub();
    },

    closePanel() {
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
      const w = world.canvas.clientWidth, h = world.canvas.clientHeight;
      const walk = space.view === 'walk';
      const ppos = controls.player.pos;
      space.stages.forEach((st) => {
        const el = this.cards.get(st.id);
        if (!el) return;
        if (walk && B.Vector3.Distance(st.pos, ppos) > 30) { el.hidden = true; return; }
        const pr = this.project(st.pos.add(new B.Vector3(0, 5.6, 0)));
        if (!pr.visible || pr.x < -200 || pr.x > w + 200 || pr.y < -100 || pr.y > h + 100) { el.hidden = true; return; }
        el.hidden = false;
        const half = el.offsetWidth / 2 + 8;
        el.style.left = `${Math.max(half, Math.min(w - half, pr.x))}px`; el.style.top = `${Math.max(90, pr.y)}px`;
      });
      const bp = this.project(new B.Vector3(0, 7.4, 0));
      this.brainCard.hidden = !bp.visible || (walk && Math.hypot(ppos.x, ppos.z) > 26);
      this.brainCard.style.left = `${bp.x}px`; this.brainCard.style.top = `${bp.y}px`;
      if (walk) {
        // 지금 서 있는 방 이름을 나가기 버튼에 표시
        const inside = space.stages.find((st) => { const l = world.toLocal(st, ppos); return Math.abs(l.x) <= ISLAND_W / 2 && Math.abs(l.z) <= ISLAND_D / 2; }) || null;
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
      this.miniT += 1;
      if (this.miniT % 4 === 0) this.drawMinimap();
    },

    drawMinimap() {
      const c = this.miniCtx, W = this.mini.width, H = this.mini.height;
      const R = ISLAND_DIST + ISLAND_D / 2 + 12;
      const sx = (x) => W / 2 + (x / R) * (W / 2 - 8);
      const sz = (z) => H / 2 + (z / R) * (H / 2 - 8);
      c.clearRect(0, 0, W, H);
      c.fillStyle = '#03050f'; c.fillRect(0, 0, W, H);
      if (world.terrain) {
        if (!this.landLayer || this.landLayer.terrain !== world.terrain) {
          const off = document.createElement('canvas'); off.width = W; off.height = H;
          const oc = off.getContext('2d');
          const cw = (1 / R) * (W / 2 - 8), ch = (1 / R) * (H / 2 - 8);
          world.terrain.cols.forEach((col) => {
            oc.fillStyle = col.zone === 'path' ? '#8e97b8' : col.level === 0 ? '#3f8f49' : col.level === 1 ? '#4faa58' : '#62c46a';
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
        $('minimap-zoom').textContent = `${Math.round((66 / controls.overview.radius) * 100)}%`;
      }
    },
  };

  // ======================================================================
  // 보조
  // ======================================================================
  const esc = (s) => String(s).replace(/[&<>"']/g, (ch) => ({ '&': '&amp;', '<': '&lt;', '>': '&gt;', '"': '&quot;', "'": '&#39;' }[ch]));
  const fmt = (n) => Number(n || 0).toLocaleString('ko-KR');
  const fmtTime = (iso) => { const d = new Date(iso); return Number.isNaN(d.getTime()) ? iso : d.toLocaleString('ko-KR', { hour12: false, month: 'numeric', day: 'numeric', hour: '2-digit', minute: '2-digit' }); };
  const statusLabel = (s) => ({ running: '실행 중', idle: '대기', waiting: '사람 답 대기', error: '오류' }[s] || s);
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

    let simTimer = null;
    data.onChange((d) => {
      if (!d) { hud.refresh(space.data); return; } // 폴링 실패: 마지막 상태 유지, 상태 표시만 갱신
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
        space.stages.forEach((st) => { const nx = d.stages.find((s) => s.id === st.id); if (nx) Object.assign(st, { items: nx.items, name: nx.name, approval: nx.approval, url: nx.url, view: nx.view }); });
        if (agentKey !== prevAgentKey) world.buildAgents(d.agents); else world.updateAgentStatuses(d.agents);
        hud.refresh(d);
      }
      if (!REDUCED) d.flows.forEach((f, i) => setTimeout(() => world.spawnFlow(f), 600 + i * 1800));
      if (!REDUCED && data.source !== 'live' && !simTimer) {
        simTimer = setInterval(() => {
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
    data.load(true).then(() => { data.startPolling(); embed.post({ type: 'ready' }); });

    try {
      const saved = localStorage.getItem('office-world.view');
      if (saved === 'walk' && !isPhone()) controls.setView('walk');
    } catch (_) { /* 저장 불가 환경 */ }
  }

  // 디버그·검사용 접근 (비밀값 없음)
  window.__officeWorld = { space, world, controls, hud, data, embed };

  if (document.readyState === 'loading') document.addEventListener('DOMContentLoaded', start);
  else start();
})();
