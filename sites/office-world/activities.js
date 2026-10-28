// City exploration records visits only; they never award work completion or approvals.
export const CITY_PLACES = [
  { id: 'transfer', title: '지상 환승 광장', layer: 'meadow', x: 0, z: -46, radius: 12, hint: '포털 가까이에서 승강장을 찾아보세요.' },
  { id: 'memory-plaza', title: '공중 공유 기억 광장', layer: 'office', x: 0, z: 0, radius: 8, hint: '공중 오피스 중앙의 기억 코어까지 걸어가세요.' },
  { id: 'sky-view', title: '공중 도시 전망대', layer: 'office', x: 42, z: 0, radius: 10, hint: '공중 플랫폼 동쪽 가장자리에서 도시를 내려다보세요.' },
];

export function nearbyPlaceIds(layer, position) {
  if (!position || !Number.isFinite(position.x) || !Number.isFinite(position.z)) return [];
  return CITY_PLACES.filter((q) => q.layer === layer && Math.hypot(position.x - q.x, position.z - q.z) <= q.radius).map((q) => q.id);
}

export function readVisits(text) {
  try {
    const value = JSON.parse(text || '[]');
    return new Set(Array.isArray(value) ? value.filter((id) => CITY_PLACES.some((q) => q.id === id)) : []);
  } catch { return new Set(); }
}

if (typeof document !== 'undefined') {
  const key = 'heobrain.city-visits.v1';
  let visits = new Set();
  try { visits = readVisits(localStorage.getItem(key)); } catch { /* browsing without storage still works */ }
  let selected = CITY_PLACES.find((q) => !visits.has(q.id)) || CITY_PLACES[0];
  let marker = null;
  let markerMaterial = null;
  let lastDistance = '';
  const root = document.createElement('details');
  root.className = 'city-activities';
  root.innerHTML = '<summary><span>도시 탐험</span><strong aria-live="polite"></strong></summary><div class="city-activities-body"><p class="city-activities-note">직접 걸어서 세 장소를 발견하세요. 이 브라우저의 탐험 기록입니다.</p><ol></ol><p class="city-activities-distance"></p><p class="city-activities-hint"></p><button type="button">선택 장소 안내</button><p class="city-activities-note">업무 완료·승인·실제 AI 성과와 별도입니다.</p></div>';
  document.body.append(root);
  const list = root.querySelector('ol');
  const guideButton = root.querySelector('.city-activities-body > button');
  guideButton.disabled = true;
  guideButton.textContent = '공간을 읽는 중';
  function render() {
    root.querySelector('strong').textContent = `${visits.size}/3`;
    list.replaceChildren(...CITY_PLACES.map((q) => {
      const item = document.createElement('li');
      const button = document.createElement('button');
      button.type = 'button';
      button.textContent = `${visits.has(q.id) ? '✓' : '○'} ${q.title}`;
      button.setAttribute('aria-pressed', String(selected.id === q.id));
      button.addEventListener('click', () => { selected = q; lastDistance = ''; render(); });
      item.append(button); return item;
    }));
    root.querySelector('.city-activities-hint').textContent = selected.hint;
  }
  guideButton.addEventListener('click', (event) => {
    const office = window.__officeWorld;
    if (!office?.space?.data) return;
    if (office.space.layer !== selected.layer) office.controls.setLayer(selected.layer);
    // Camera guidance moves no player to the destination and grants no visit.
    office.controls.setView('overview');
    office.controls.animateCamera({
      target: new window.BABYLON.Vector3(selected.x, office.world.heightAt(selected.x, selected.z), selected.z),
      radius: selected.layer === 'meadow' ? 64 : 42,
      beta: 1.08,
    }, 800);
    root.querySelector('.city-activities-distance').textContent = '빛 고리가 목적지입니다. 컴퓨터에서 걷기 모드로 직접 이동하세요.';
    event.currentTarget.blur();
  });
  render();
  const timer = setInterval(() => {
    if (document.hidden) return;
    const office = window.__officeWorld;
    if (!office?.space?.data || !office.controls?.player) return;
    guideButton.disabled = false;
    guideButton.textContent = '선택 장소 안내';
    const { space, world } = office;
    const player = office.controls.player;
    if (space.view === 'walk') {
      let changed = false;
      nearbyPlaceIds(space.layer, player.pos).forEach((id) => { if (!visits.has(id)) { visits.add(id); changed = true; } });
      if (changed) {
        try { localStorage.setItem(key, JSON.stringify([...visits])); } catch { /* session progress is retained */ }
        render();
      }
    }
    if (space.layer === selected.layer) {
      const distance = Math.round(Math.hypot(player.pos.x - selected.x, player.pos.z - selected.z));
      const status = space.view === 'walk' ? `선택 장소까지 ${distance}m` : '관제에서는 장소를 둘러보고, 컴퓨터 걷기 모드에서 방문을 기록합니다.';
      if (status !== lastDistance) { root.querySelector('.city-activities-distance').textContent = status; lastDistance = status; }
      if (!marker) {
        const B = window.BABYLON;
        marker = B.MeshBuilder.CreateTorus('city-quest-marker', { diameter: 6, thickness: 0.16, tessellation: 32 }, world.scene);
        markerMaterial = new B.StandardMaterial('city-quest-marker-material', world.scene);
        markerMaterial.diffuseColor = B.Color3.FromHexString('#ffcf78');
        markerMaterial.emissiveColor = B.Color3.FromHexString('#aa7d30');
        markerMaterial.disableLighting = true;
        marker.material = markerMaterial; marker.isPickable = false;
      }
      marker.position.set(selected.x, world.heightAt(selected.x, selected.z) + 0.3, selected.z);
      marker.setEnabled(root.open);
    } else if (marker) marker.setEnabled(false);
  }, 600);
  window.addEventListener('pagehide', (event) => {
    if (event.persisted) return;
    clearInterval(timer); marker?.dispose(); markerMaterial?.dispose();
  });
}
