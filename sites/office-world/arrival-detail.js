// Blender-authored geometry uses the native Babylon format already in our engine.
export function createArrivalDetail({ world, space, quality, loadAsset }) {
  let phase = quality === 'high' ? 'idle' : 'disabled', container = null, active = false, disposed = false, last = -Infinity;
  const base = () => (world.arrivalArchitecture?.meshes || []).filter(m => !m.isDisposed());
  const show = value => {
    active = value;
    for (const mesh of base()) mesh.setEnabled(!value);
    for (const mesh of container?.meshes || []) mesh.setEnabled(value);
  };
  const sync = () => {
    if (disposed || phase === 'disabled') return;
    const position = world.scene.activeCamera?.globalPosition;
    const distance = position ? Math.hypot(position.x, position.y - 3.5, position.z + 53) : Infinity;
    const near = space.layer === 'office' && distance <= (active ? 52 : 38);
    if (phase === 'ready') { show(near); return; }
    if (!near || phase !== 'idle') return;
    phase = 'loading';
    Promise.resolve().then(loadAsset).then(value => {
      if (disposed) { value.dispose(); return; }
      container = value;
      const visible = value.meshes.filter(m => m.getTotalVertices() > 0);
      if (visible.length !== 4 || visible.reduce((n, m) => n + m.getTotalIndices() / 3, 0) !== 5076) throw Error('Unexpected arrival geometry');
      for (const mesh of value.meshes) {
        mesh.setEnabled(false); mesh.isPickable = false; mesh.checkCollisions = false;
        if (!mesh.parent) mesh.position.z -= 53;
      }
      value.addAllToScene();
      for (const mesh of value.meshes) {
        mesh.computeWorldMatrix(true); mesh.freezeWorldMatrix();
        if (mesh.getTotalVertices()) { world.castShadow(mesh); world.receiveShadow(mesh); }
      }
      phase = 'ready'; sync();
    }).catch(() => { if (!disposed) { phase = 'failed'; container?.dispose(); container = null; show(false); } });
  };
  const observer = phase === 'disabled' ? null : world.scene.onBeforeRenderObservable.add(() => {
    const now = performance.now();
    if (now - last >= 250) { last = now; sync(); }
  });
  const dispose = () => {
    if (disposed) return;
    show(false); disposed = true;
    if (observer) world.scene.onBeforeRenderObservable.remove(observer);
    container?.dispose(); container = null;
  };
  world.scene.onDisposeObservable.addOnce(dispose);
  return { sync, dispose, status: () => ({ phase, active, disposed }) };
}

export function installArrivalDetail(office, B, fetchAsset = fetch) {
  if (!office?.world?.scene) return null;
  const { world, space, quality } = office;
  return createArrivalDetail({ world, space, quality, loadAsset: async () => {
    const response = await fetchAsset(new URL('assets/arrival-detail-v2.json', import.meta.url), { signal: AbortSignal.timeout(8000) });
    if (!response.ok) throw Error('Arrival asset unavailable');
    const text = await response.text();
    if (text.length > 900000) throw Error('Arrival asset too large');
    return B.SceneLoader.LoadAssetContainerAsync('', 'data:' + text, world.scene, undefined, '.babylon');
  } });
}
if (typeof document !== 'undefined') {
  const start = () => {
    const office = window.__officeWorld;
    if (office?.world?.scene && !office.world.arrivalDetail) office.world.arrivalDetail = installArrivalDetail(office, window.BABYLON);
  };
  if (document.readyState !== 'complete') document.addEventListener('DOMContentLoaded', start, { once: true });
  start();
}
