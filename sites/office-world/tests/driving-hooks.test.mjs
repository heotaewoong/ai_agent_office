import { readFile } from 'node:fs/promises';
import assert from 'node:assert/strict';
import { test } from 'node:test';

const source = await readFile(new URL('../app.js', import.meta.url), 'utf8');
function method(name, globals = {}) {
  const start = source.indexOf(`    ${name}(`, source.indexOf('  const controls = {'));
  const end = source.indexOf('\n    },', start);
  assert(start >= 0 && end > start, `${name} must remain available to the game module`);
  return Function(...Object.keys(globals), `return ({${source.slice(start, end + 6)}}).${name}`)(...Object.values(globals));
}

class Vector {
  constructor(x = 0, y = 0, z = 0) { Object.assign(this, { x, y, z }); }
  static Zero() { return new Vector(); }
  static Lerp(a, b, t) { return a.scale(1 - t).add(b.scale(t)); }
  add(v) { return new Vector(this.x + v.x, this.y + v.y, this.z + v.z); }
  addInPlace(v) { return this.copyFrom(this.add(v)); }
  subtractInPlace(v) { return this.addInPlace(v.scale(-1)); }
  scale(n) { return new Vector(this.x * n, this.y * n, this.z * n); }
  scaleInPlace(n) { return this.copyFrom(this.scale(n)); }
  copyFrom(v) { Object.assign(this, { x: v.x, y: v.y, z: v.z }); return this; }
  lengthSquared() { return this.x ** 2 + this.y ** 2 + this.z ** 2; }
  length() { return Math.sqrt(this.lengthSquared()); }
  normalize() { const n = this.length(); return n ? this.scaleInPlace(1 / n) : this; }
}

function movementFixture(speed, pressed = []) {
  const pos = new Vector(), checks = [], poses = [];
  const player = { pos, grounded: true, walkT: 0, av: { root: { position: new Vector(), rotation: {} } } };
  const controls = {
    player, keys: new Set(pressed), vehicleSpeed: speed, vy: 0, yaw: 0, pitch: .18,
    cameraTween: null, walk: { position: new Vector(), setTarget() {} },
  };
  const space = { layer: 'meadow', view: 'walk' };
  const world = {
    heightAt: () => 0,
    walkable(candidate, fromY, clearance) {
      checks.push({ distance: Math.hypot(candidate.x - pos.x, candidate.z - pos.z), clearance });
      return !world.wall || candidate.z < 1 || candidate.z > 1.4;
    },
    setPose: (_, pose) => poses.push(pose), animateWalk() {},
  };
  return { controls, world, space, checks, poses, tick: method('tick', { space, world, B: { Vector3: Vector } }) };
}

test('the vehicle hook rejects invalid speed and riding on the office layer', () => {
  const space = { layer: 'meadow' }, world = { heightAt: () => 2 };
  const setSpeed = method('setVehicleSpeed', { space, world });
  const controls = { vehicleSpeed: 0, vy: 5, keys: new Set([' ']), player: { pos: new Vector(), grounded: false } };
  for (const speed of [NaN, Infinity, -1, 36.01, '24', null]) assert.equal(setSpeed.call(controls, speed), false);
  assert.equal(setSpeed.call(controls, 24), true);
  assert.equal(controls.vehicleSpeed, 24);
  assert.equal(controls.player.grounded, true);
  assert.equal(controls.vy, 0);
  assert.equal(controls.player.pos.y, 2);
  assert.equal(controls.keys.has(' '), false);
  space.layer = 'office';
  assert.equal(setSpeed.call(controls, 32), false);
  assert.equal(setSpeed.call(controls, 0), true);
  assert.equal(controls.vehicleSpeed, 0);
});

test('high-speed movement reuses collision checks without jumping a thin wall', () => {
  const f = movementFixture(36, ['w']); f.world.wall = true;
  f.tick.call(f.controls, .1);
  assert(f.controls.player.pos.z > 0 && f.controls.player.pos.z < 1);
  assert(f.checks.length > 1);
  assert(f.checks.every(c => c.distance <= .350000001));
  assert(f.checks.every(c => c.clearance >= Math.hypot(2.6 / 2, 3.4 / 2)));
});

test('driving suppresses jump while normal walking keeps the existing jump', () => {
  const driving = movementFixture(24, [' ']);
  driving.tick.call(driving.controls, .1);
  assert.equal(driving.controls.player.grounded, true);
  assert.equal(driving.controls.player.pos.y, 0);
  assert(driving.poses.includes('sit'));
  const walking = movementFixture(0, [' ']);
  walking.tick.call(walking.controls, .1);
  assert.equal(walking.controls.player.grounded, false);
  assert(walking.controls.player.pos.y > 0);
});

test('mobile movement is explicitly enabled and clearing it releases held controls', () => {
  const space = { view: 'walk' }, views = [];
  const enable = method('enableTouchWalk', { space, isPhone: () => true });
  const controls = { keys: new Set(['w']), setView: view => views.push(view) };
  assert.equal(enable.call(controls, true), true);
  assert.equal(controls.keys.size, 0);
  controls.keys.add('s');
  assert.equal(enable.call(controls, false), false);
  assert.equal(controls.keys.size, 0);
  assert.deepEqual(views, ['overview']);
});


test('vehicle form controls keep keyboard navigation and keyup always releases movement', () => {
  const space = { layer: 'meadow', view: 'walk' };
  const views = [];
  const controls = { keys: new Set(['w']), setView: view => views.push(view) };
  const onKey = method('onKey', { space, world: {}, hud: {} });
  let prevented = 0;
  const element = tag => ({
    closest(selector) {
      return selector.split(',').some(part => {
        const match = /^([a-z]+)(?:\[[^\]]+\])?$/.exec(part.trim());
        return !!match && match[1] === tag;
      }) ? this : null;
    },
  });
  const event = (key, editing) => ({
    key, target: element(editing ? 'select' : 'canvas'),
    preventDefault() { prevented++; },
  });
  onKey.call(controls, event('w', true), false);
  assert.equal(controls.keys.size, 0);
  for (const key of ['ArrowDown', ' ', 'm', 'w']) onKey.call(controls, event(key, true), true);
  assert.equal(controls.keys.size, 0);
  assert.deepEqual(views, []);
  assert.equal(prevented, 0);
  const buttonEvent = key => ({
    key, target: element('button'),
    preventDefault() { prevented++; },
  });
  onKey.call(controls, buttonEvent(' '), true);
  assert.equal(controls.keys.size, 0);
  onKey.call(controls, buttonEvent('w'), true);
  assert.equal(controls.keys.size, 0, 'a focused button retains its key events instead of driving the world');
  assert.equal(prevented, 0);
  onKey.call(controls, buttonEvent('w'), false);
  assert.equal(controls.keys.size, 0);
  onKey.call(controls, event('w', false), true);
  assert(controls.keys.has('w'));
  onKey.call(controls, event('w', false), false);
  assert.equal(controls.keys.size, 0);
});
