import { readFile } from 'node:fs/promises';
import assert from 'node:assert/strict';
import { test } from 'node:test';

const source = await readFile(new URL('../app.js', import.meta.url), 'utf8');
const start = source.indexOf('    onKey('), end = source.indexOf('\n    },', start);
const handler = (space, world = {}, hud = {}) => Function('space', 'world', 'hud', 'return ({' + source.slice(start, end + 6) + '}).onKey')(space, world, hud);
const event = (key, code, editing = false) => ({ key, code, target: { closest: selector => editing && selector.includes('input') }, preventDefault() {} });

test('physical WASD moves with a Korean layout and releases even after the layout changes', () => {
  const onKey = handler({ view: 'walk' });
  for (const [key, code, move] of [['ㅈ','KeyW','w'], ['ㅁ','KeyA','a'], ['ㄴ','KeyS','s'], ['ㅇ','KeyD','d']]) {
    const controls = { keys: new Set() };
    onKey.call(controls, event(key, code), true);
    assert.deepEqual([...controls.keys], [move]);
    onKey.call(controls, event(move.toUpperCase(), code), false);
    assert.equal(controls.keys.size, 0);
  }
});

test('modal and editing guards still block physical movement while keyup releases held keys', () => {
  for (const flag of ['rosterOpen','buildingOpen','resultsOpen','playHubOpen']) {
    const controls = { keys: new Set(['w']) }, onKey = handler({ view: 'walk', [flag]: true });
    onKey.call(controls, event('ㅈ','KeyW'), false);
    assert.equal(controls.keys.size, 0);
    onKey.call(controls, event('ㅈ','KeyW'), true);
    assert.equal(controls.keys.size, 0);
  }
  const controls = { keys: new Set() }, onKey = handler({ view: 'walk' });
  onKey.call(controls, event('ㅈ','KeyW',true), true);
  assert.equal(controls.keys.size, 0);
});

test('legacy character movement and arrow keys retain their existing behavior', () => {
  const controls = { keys: new Set() }, onKey = handler({ view: 'walk' });
  for (const [key, code, expected] of [['w',undefined,'w'],['ArrowUp','ArrowUp','arrowup']]) {
    onKey.call(controls, event(key,code), true); assert.ok(controls.keys.has(expected));
    onKey.call(controls, event(key,code), false); assert.equal(controls.keys.size, 0);
  }
});

test('physical mode, camera reset and interaction keys work with Korean character values', () => {
  let view = null, layer = null;
  const controls = { keys: new Set(), player: { av: { root: { rotation: { y: 1 } } }, pos: { x: 0, z: 0 } },
    setView: value => { view = value; }, setLayer: value => { layer = value; }, yaw: 0, pitch: 0 };
  const onKey = handler({ view: 'walk', layer: 'meadow' }, { portals: { meadow: { x: 0, z: 0 } } });
  onKey.call(controls, event('ㅡ','KeyM'), true); assert.equal(view, 'overview');
  onKey.call(controls, event('ㄱ','KeyR'), true); assert.equal(controls.yaw, 1 + Math.PI); assert.equal(controls.pitch, .18);
  onKey.call(controls, event('ㄷ','KeyE'), true); assert.equal(layer, 'office');
  view = null; onKey.call(controls, event('ㅡ','KeyM',true), true); assert.equal(view, null);
});
