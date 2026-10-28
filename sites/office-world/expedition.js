export const ALIENS = [
  { id: 'mint', name: '민트 탐사자', x: 0, z: -52 },
  { id: 'violet', name: '보랏빛 탐사자', x: 0, z: -24 },
  { id: 'amber', name: '호박빛 탐사자', x: 58, z: -46 },
  { id: 'azure', name: '푸른 탐사자', x: -58, z: -46 },
  { id: 'pearl', name: '진주 탐사자', x: 0, z: 25 },
  { id: 'coral', name: '산호 탐사자', x: 104, z: -46 },
  { id: 'lime', name: '라임 탐사자', x: -104, z: -46 },
  { id: 'nova', name: '별빛 탐사자', x: 0, z: -175 },
];
export const VEHICLES = [
  { id: 'scout', name: '스카우트 호버카', cost: 80, speed: 24, color: '#76e2dd' },
  { id: 'nova', name: '노바 GT', cost: 160, speed: 32, color: '#e7b66f' },
];
const REWARD = 40;
const empty = () => ({ captured: [], owned: [], selected: 'scout' });
export const credits = (profile) => profile.captured.length * REWARD - profile.owned.reduce((sum, id) => sum + VEHICLES.find(v => v.id === id).cost, 0);

export function readProfile(text) {
  try {
    const raw = JSON.parse(text || '{}');
    if (!raw || typeof raw !== 'object') return empty();
    const profile = empty();
    profile.captured = [...new Set(Array.isArray(raw.captured) ? raw.captured : [])].filter(id => ALIENS.some(a => a.id === id));
    for (const id of Array.isArray(raw.owned) ? raw.owned : []) {
      const vehicle = VEHICLES.find(v => v.id === id);
      if (vehicle && !profile.owned.includes(id) && credits(profile) >= vehicle.cost) profile.owned.push(id);
    }
    if (VEHICLES.some(v => v.id === raw.selected)) profile.selected = raw.selected;
    return profile;
  } catch { return empty(); }
}

function onFoot(context) {
  return context.layer === 'meadow' && context.view === 'walk' && !context.mounted && context.grounded === true;
}
export function capture(profile, id, context) {
  const alien = ALIENS.find(a => a.id === id);
  const pos = context.position;
  if (!alien || profile.captured.includes(id) || !onFoot(context) || !pos || !Number.isFinite(pos.x) || !Number.isFinite(pos.z) || Math.hypot(pos.x - alien.x, pos.z - alien.z) > 7) return false;
  profile.captured.push(id);
  return true;
}
export function purchase(profile, id) {
  const vehicle = VEHICLES.find(v => v.id === id);
  if (!vehicle || profile.owned.includes(id) || credits(profile) < vehicle.cost) return false;
  profile.owned.push(id); profile.selected = id;
  return true;
}
export function canRide(profile, id, context) {
  return profile.owned.includes(id) && onFoot(context);
}

if (typeof document !== 'undefined') {
  // shortcut: this is a local game save; use a server ledger before adding shared rewards.
  const key = 'heobrain.expedition.v1';
  let profile = empty(), mounted = false, active = false, storageAvailable = true, ready = false;
  try { profile = readProfile(localStorage.getItem(key)); } catch { storageAvailable = false; }
  const root = document.createElement('section');
  root.className = 'alien-game'; root.setAttribute('aria-label', '외계 생명체 탐사와 차고');
  root.innerHTML = `<button type="button" class="alien-game-launch">✦ 외계 생명체 탐사 <span class="alien-wallet">0 C</span></button>
    <div class="alien-game-panel" hidden><div class="alien-game-heading"><strong>탐사와 차고</strong><button type="button" class="alien-game-close" aria-label="탐사 패널 닫기">×</button></div>
    <p class="alien-game-note">생명체 두 마리를 안전하게 포획하면 첫 차를 살 수 있어요.</p>
    <p class="alien-game-progress"></p><p class="alien-game-target"></p>
    <button type="button" class="alien-game-start">지상에서 탐사 시작</button>
    <div class="alien-game-actions"><button type="button" class="alien-game-catch" disabled>포획 · F</button><button type="button" class="alien-game-ride" disabled>탑승 · V</button></div>
    <div class="alien-game-garage"></div><p class="alien-game-status" role="status"></p>
    <p class="alien-game-note">WASD 이동 · 드래그 시선 · F 포획 · V 탑승/하차<br>게임 크레딧은 이 브라우저에 저장됩니다. 실제 결제·업무 승인과 별도입니다.</p></div>`;
  document.body.append(root);
  const panel = root.querySelector('.alien-game-panel');
  const launch = root.querySelector('.alien-game-launch');
  const status = root.querySelector('.alien-game-status');
  const start = root.querySelector('.alien-game-start');
  const catchButton = root.querySelector('.alien-game-catch');
  const rideButton = root.querySelector('.alien-game-ride');
  const pad = document.createElement('div'); pad.className = 'alien-game-pad'; pad.setAttribute('aria-label', '터치 이동');
  pad.innerHTML = '<button type="button" data-key="w" aria-label="앞으로 이동">↑</button><button type="button" data-key="a" aria-label="왼쪽 이동">←</button><button type="button" data-key="s" aria-label="뒤로 이동">↓</button><button type="button" data-key="d" aria-label="오른쪽 이동">→</button>';
  document.body.append(pad);
  const mobileActions = document.createElement('div'); mobileActions.className = 'alien-game-mobile-actions';
  mobileActions.innerHTML = '<span></span><button type="button" class="mobile-catch" disabled>포획</button><button type="button" class="mobile-ride" disabled>탑승</button>';
  document.body.append(mobileActions);
  const office = () => window.__officeWorld;
  const context = () => {
    const o = office(), p = o?.controls.player;
    return { layer: o?.space.layer, view: o?.space.view, position: p?.pos, grounded: p?.grounded, mounted };
  };
  function save() {
    try { localStorage.setItem(key, JSON.stringify(profile)); }
    catch { storageAvailable = false; }
  }
  function say(text) { status.textContent = text + (storageAvailable ? '' : ' 저장 공간을 사용할 수 없어 이번 방문 동안만 유지됩니다.'); }
  function nearest() {
    const p = context().position;
    if (!p) return null;
    return ALIENS.filter(a => !profile.captured.includes(a.id)).map(a => ({ ...a, distance: Math.hypot(a.x - p.x, a.z - p.z) })).sort((a, b) => a.distance - b.distance)[0];
  }
  function render() {
    root.querySelector('.alien-wallet').textContent = `${credits(profile)} C`;
    root.querySelector('.alien-game-progress').textContent = `포획 도감 ${profile.captured.length}/8 · 보유 차량 ${profile.owned.length}/2`;
    root.querySelector('.alien-game-garage').replaceChildren(...VEHICLES.map(vehicle => {
      const item = document.createElement('div'); item.className = 'alien-game-vehicle';
      const owned = profile.owned.includes(vehicle.id);
      const label = document.createElement('span'); label.textContent = `${vehicle.name} · ${Math.round(vehicle.speed * 3.6)}km/h`;
      const button = document.createElement('button'); button.type = 'button';
      button.textContent = owned ? (profile.selected === vehicle.id ? '선택됨' : '선택') : `${vehicle.cost} C 구매`;
      button.disabled = mounted || (owned ? profile.selected === vehicle.id : credits(profile) < vehicle.cost);
      button.onclick = () => {
        if (owned) { profile.selected = vehicle.id; save(); say(`${vehicle.name} 선택. 지상에서 V로 탑승하세요.`); }
        else if (purchase(profile, vehicle.id)) { save(); say(`${vehicle.name} 구매 완료. V 또는 탑승 버튼으로 운전하세요.`); }
        render();
      };
      item.append(label, button); return item;
    }));
  }
  const setPanel = (open) => { panel.hidden = !open; launch.setAttribute('aria-expanded', String(open)); };
  launch.onclick = () => setPanel(panel.hidden);
  root.querySelector('.alien-game-close').onclick = () => setPanel(false);
  start.disabled = true;
  start.onclick = () => {
    const o = office(); if (!ready) return;
    active = true; o.controls.enableTouchWalk(true); o.controls.setLayer('meadow', true);
    if (matchMedia('(max-width:700px)').matches) setPanel(false);
    say('앞쪽 빛 고리의 생명체로 다가가세요. 7m 안에서 F로 포획합니다.'); start.blur();
  };
  function catchNearest() {
    const target = nearest();
    if (target && capture(profile, target.id, context())) {
      save(); say(`${target.name} 포획! +40 C${credits(profile) >= 80 && !profile.owned.length ? ' · 이제 첫 차를 구매할 수 있습니다.' : ''}`); render();
    }
  }
  catchButton.onclick = catchNearest;
  mobileActions.querySelector('.mobile-catch').onclick = catchNearest;
  function toggleRide() {
    const o = office(); if (!o) return;
    if (mounted) { o.controls.setVehicleSpeed(0); mounted = false; say('하차했습니다. 가까운 생명체를 포획할 수 있습니다.'); }
    else if (canRide(profile, profile.selected, context())) {
      const vehicle = VEHICLES.find(v => v.id === profile.selected);
      mounted = o.controls.setVehicleSpeed(vehicle.speed);
      if (mounted) say(`${vehicle.name} 운전 중. WASD로 이동하고 V로 하차하세요.`);
    }
    render();
  }
  rideButton.onclick = toggleRide;
  mobileActions.querySelector('.mobile-ride').onclick = toggleRide;
  window.addEventListener('keydown', event => {
    if (event.repeat || event.ctrlKey || event.metaKey || event.altKey || event.target.closest?.('input,textarea,select,[contenteditable="true"]')) return;
    if (!active || office()?.space.view !== 'walk') return;
    if (event.key.toLowerCase() === 'f') { event.preventDefault(); catchNearest(); }
    if (event.key.toLowerCase() === 'v') { event.preventDefault(); toggleRide(); }
  });
  const clearTouch = () => { for (const button of pad.querySelectorAll('button')) { office()?.controls.keys.delete(button.dataset.key); button.classList.remove('pressed'); } };
  pad.querySelectorAll('button').forEach(button => {
    button.onpointerdown = event => { if (!active) return; event.preventDefault(); button.setPointerCapture(event.pointerId); office()?.controls.keys.add(button.dataset.key); button.classList.add('pressed'); };
    button.onpointerup = button.onpointercancel = () => { office()?.controls.keys.delete(button.dataset.key); button.classList.remove('pressed'); };
  });
  window.addEventListener('blur', clearTouch); window.addEventListener('pagehide', clearTouch);
  document.addEventListener('visibilitychange', () => { if (document.hidden) clearTouch(); });
  const timer = setInterval(() => {
    const o = office(); if (!o?.space.data || !o.controls.player || !o.world.scene) return;
    if (!ready) { ready = true; start.disabled = false; buildScene(o); }
    if (mounted && (o.space.layer !== 'meadow' || o.space.view !== 'walk' || o.controls.vehicleSpeed === 0)) {
      o.controls.setVehicleSpeed(0); mounted = false; render();
    }
    const walking = active && o.space.layer === 'meadow' && o.space.view === 'walk';
    document.body.classList.toggle('alien-game-active', walking);
    const target = nearest();
    const targetText = profile.captured.length === 8 ? '모든 생명체를 발견했습니다. 두 차량으로 도시를 탐험하세요.' : walking && target ? `${target.name}까지 ${Math.round(target.distance)}m · ${mounted ? '하차 후 포획' : '7m 안에서 포획'}` : '지상 탐사를 시작하면 가까운 목표를 안내합니다.';
    root.querySelector('.alien-game-target').textContent = targetText;
    catchButton.disabled = !walking || mounted || !target || target.distance > 7 || !o.controls.player.grounded;
    rideButton.disabled = !mounted && !canRide(profile, profile.selected, context());
    rideButton.textContent = mounted ? '하차 · V' : '탑승 · V';
    mobileActions.querySelector('span').textContent = target ? `${target.name} ${Math.round(target.distance)}m` : '도감 완성!';
    mobileActions.querySelector('.mobile-catch').disabled = catchButton.disabled;
    mobileActions.querySelector('.mobile-ride').disabled = rideButton.disabled;
    mobileActions.querySelector('.mobile-ride').textContent = mounted ? '하차' : '탑승';
  }, 200);
  window.addEventListener('pagehide', event => {
    if (!event.persisted) clearInterval(timer);
    office()?.controls.setVehicleSpeed(0); mounted = false; render();
  });
  render(); say('포획 보상 40 C · 첫 차량 80 C');

  function buildScene(o) {
    const B = window.BABYLON, scene = o.world.scene;
    const material = (name, hex, glow = false) => {
      const m = new B.StandardMaterial(name, scene); m.diffuseColor = B.Color3.FromHexString(hex);
      if (glow) { m.emissiveColor = m.diffuseColor.scale(.45); m.disableLighting = true; } return m;
    };
    const colors = ['#71e6b9','#b8a1ff','#f3c473','#81c9ff','#d3f5ed','#f5a395','#b9d978','#a8bfff'];
    const dark = material('alien-game-eyes', '#132536'), glow = material('alien-game-signal', '#97eedc', true);
    const box = (name, size, pos, mat, parent) => {
      const mesh = B.MeshBuilder.CreateBox(name, { width: size[0], height: size[1], depth: size[2] }, scene);
      mesh.position.set(...pos); mesh.material = mat; mesh.parent = parent; mesh.isPickable = false; return mesh;
    };
    const aliens = ALIENS.map((a, i) => {
      const node = new B.TransformNode(`alien-game-${a.id}`, scene), skin = material(`alien-game-skin-${i}`, colors[i]);
      const ground = Math.max(o.world.meadowHeight(a.x, a.z), o.world.groundRoadHeight(a.x, a.z) ?? -Infinity);
      node.position.set(a.x, ground, a.z);
      box('alien-body', [1.6, 1.6, 1], [0, 1.5, 0], skin, node);
      box('alien-head', [2, 1.3, 1.3], [0, 2.7, 0], skin, node);
      for (const side of [-1, 1]) { box('alien-eye', [.38, .45, .12], [side*.48, 2.8, -.71], dark, node); box('alien-boot', [.5, .65, .6], [side*.46, .5, 0], dark, node); }
      box('alien-antenna', [.14,.7,.14], [0,3.6,0], glow, node);
      const ring = B.MeshBuilder.CreateTorus('alien-waypoint', { diameter: 5, thickness: .12, tessellation: 24 }, scene);
      ring.parent = node; ring.position.y = .28; ring.material = glow; ring.isPickable = false;
      return { node, ring, id: a.id };
    });
    const car = new B.TransformNode('owned-hovercar', scene);
    const paint = material('owned-hovercar-paint', '#76e2dd'), trim = material('owned-hovercar-trim', '#243c54'), light = material('owned-hovercar-light', '#b8f4ff', true);
    paint.specularColor = new B.Color3(.7,.8,.8); paint.specularPower = 90;
    box('hovercar-lower-hull', [2.6,.5,3.4], [0,.48,0], trim, car);
    box('hovercar-coachwork', [2.4,.5,3.1], [0,.88,0], paint, car);
    box('hovercar-seat', [.85,.2,.8], [0,1.05,0], trim, car);
    box('hovercar-seat-back', [.85,.65,.2], [0,1.3,-.45], trim, car);
    for (const side of [-1,1]) {
      box('hovercar-side-rail', [.18,.35,2.8], [side*1.08,1.2,0], trim, car);
      box('hovercar-headlight', [.55,.15,.1], [side*.75,.96,1.57], light, car);
      box('hovercar-thruster', [.5,.2,.8], [side*.9,.2,-.9], glow, car);
    }
    car.setEnabled(false);
    let lastColor = '';
    scene.onBeforeRenderObservable.add(() => {
      for (const alien of aliens) {
        alien.node.setEnabled(o.space.layer === 'meadow' && !profile.captured.includes(alien.id));
        alien.ring.setEnabled(active);
      }
      car.setEnabled(mounted && o.space.layer === 'meadow' && o.space.view === 'walk');
      if (mounted) {
        car.position.copyFrom(o.controls.player.pos); car.rotation.y = o.controls.player.av.root.rotation.y;
        const hex = VEHICLES.find(v => v.id === profile.selected).color;
        if (lastColor !== hex) { paint.diffuseColor = B.Color3.FromHexString(hex); lastColor = hex; }
      }
    });
  }
}
