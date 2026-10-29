import { readFile } from 'node:fs/promises';
import assert from 'node:assert/strict';
import { test } from 'node:test';

const source = await readFile(new URL('../expedition.js', import.meta.url), 'utf8');
const { TOUR_STOPS, createTour, advanceTour, readProfile, credits } =
  await import('data:text/javascript;base64,' + Buffer.from(source).toString('base64'));
const context = (z, overrides = {}) => ({
  layer: 'meadow', view: 'walk', grounded: true, mounted: true,
  vehicleId: 'scout', position: { x: 0, y: 0, z }, groundY: 0, paused: false,
  ...overrides,
});

test('a real continuous drive records the four stops in order and completion is bounded', () => {
  const tour = createTour(), milestones = [];
  let now = 0;
  assert.equal(advanceTour(tour, context(-64), now), false);
  for (let z = -60; z <= 200; z += 4) {
    now += 200;
    const before = tour.next;
    if (advanceTour(tour, context(z), now)) milestones.push(tour.next);
    assert.ok(tour.next - before <= 1);
  }
  assert.deepEqual(milestones, [1, 2, 3, 4]);
  assert.equal(tour.next, TOUR_STOPS.length);
  assert.equal(tour.previous, null);
  for (let i = 1; i <= 5; i++) assert.equal(advanceTour(tour, context(189 + i), now + i * 200), false);
  assert.equal(tour.next, 4);
});

test('the start sample, standing still and tiny movement never collect a stop', () => {
  const tour = createTour();
  assert.equal(advanceTour(tour, context(-15), 0), false);
  assert.equal(advanceTour(tour, context(-15), 200), false);
  assert.equal(advanceTour(tour, context(-14.999), 400), false);
  assert.equal(tour.next, 0);
  assert.equal(advanceTour(tour, context(-14), 600), true);
});

test('later stops and distant parallel travel do not skip the next required stop', () => {
  const tour = createTour();
  advanceTour(tour, context(118), 0);
  assert.equal(advanceTour(tour, context(122), 200), false);
  assert.equal(advanceTour(tour, context(126), 400), false);
  assert.equal(tour.next, 0);
  const away = createTour();
  advanceTour(away, context(-20, { position: { x: 9, y: 0, z: -20 } }), 0);
  assert.equal(advanceTour(away, context(-10, { position: { x: 9, y: 0, z: -10 } }), 1000), false);
  assert.equal(away.next, 0);
});

test('dismounting, layers, overview, pauses and invalid grounding discard the movement bridge', () => {
  const invalid = [
    { mounted: false }, { mounted: undefined }, { layer: 'office' }, { view: 'overview' },
    { paused: true }, { paused: undefined }, { grounded: false }, { vehicleId: 'unknown' },
    { position: { x: 0, y: 1.51, z: -15 } }, { groundY: null },
    { position: { x: NaN, y: 0, z: -15 } }, { position: { x: 0, y: Infinity, z: -15 } },
    { position: { x: 0, y: 0, z: NaN } }, { position: null },
  ];
  for (const overrides of invalid) {
    const tour = createTour();
    advanceTour(tour, context(-25), 0);
    assert.equal(advanceTour(tour, context(-15, overrides), 200), false);
    assert.equal(tour.previous, null);
    assert.equal(tour.next, 0);
    assert.equal(advanceTour(tour, context(-14), 400), false);
    assert.equal(advanceTour(tour, context(-13), 600), true);
  }
});

test('a long gap, reversed clock or implausible jump re-baselines without collecting', () => {
  for (const [from, at] of [[-25, 1501], [-25, 0], [-25, -1], [-100, 200]]) {
    const tour = createTour();
    advanceTour(tour, context(from), 0);
    assert.equal(advanceTour(tour, context(-15), at), false);
    assert.equal(tour.next, 0);
  }
  for (const invalidTime of [NaN, Infinity, '200']) {
    const tour = createTour();
    advanceTour(tour, context(-25), 0);
    assert.equal(advanceTour(tour, context(-15), invalidTime), false);
    assert.equal(tour.previous, null);
  }
});

test('a low-frame-rate segment can cross a stop even when both sampled endpoints are outside', () => {
  const tour = createTour();
  advanceTour(tour, context(-27), 0);
  assert.equal(advanceTour(tour, context(-3), 1000), true);
  assert.equal(tour.next, 1);
});

test('changing vehicles resets the prior movement sample before it can collect', () => {
  const tour = createTour();
  advanceTour(tour, context(-25), 0);
  assert.equal(advanceTour(tour, context(-20, { vehicleId: 'nova' }), 200), false);
  assert.equal(tour.next, 0);
  assert.equal(advanceTour(tour, context(-19, { vehicleId: 'nova' }), 400), true);
});

test('damaged tour indices and previous samples cannot grant progress or throw', () => {
  for (const next of [-1, 1.5, NaN, Infinity, '0', 5, undefined]) {
    const tour = { next, previous: { x: 0, z: -25, at: 0, vehicleId: 'scout' } };
    assert.equal(advanceTour(tour, context(-20), 200), false);
    assert.equal(tour.next, next);
    assert.equal(tour.previous, null);
  }
  for (const value of [null, undefined, 3, 'tour']) assert.equal(advanceTour(value, context(-15), 200), false);
  const tour = { next: 0, previous: { x: NaN, z: -25, at: 0, vehicleId: 'scout' } };
  assert.equal(advanceTour(tour, context(-20), 200), false);
  assert.equal(advanceTour(tour, context(-19), 400), true);
});

test('tour state is independent and does not change capture, vehicle ownership, currency or saves', () => {
  const profile = readProfile('{"captured":["mint","violet"],"owned":["scout"],"selected":"nova"}');
  const before = JSON.stringify(profile), balance = credits(profile), tour = createTour();
  advanceTour(tour, context(-25, { vehicleId: profile.selected }), 0);
  assert.equal(advanceTour(tour, context(-20, { vehicleId: profile.selected }), 200), true);
  assert.equal(JSON.stringify(profile), before);
  assert.equal(credits(profile), balance);
  assert.deepEqual(createTour(), { next: 0, previous: null });
});

const appSource = await readFile(new URL('../app.js', import.meta.url), 'utf8');
function keyboardFixture() {
  const start = appSource.indexOf('    onKey(', appSource.indexOf('  const controls = {'));
  const end = appSource.indexOf('\n    },', start);
  assert.ok(start >= 0 && end > start);
  const calls = [], space = { view: 'walk', layer: 'meadow' };
  const world = { portals: { meadow: { x: 0, z: 0 } } };
  const hud = { closePanel: () => calls.push('close'), toggleNearestAgent: () => calls.push('agent') };
  const onKey = Function('space', 'world', 'hud', 'return ({' + appSource.slice(start, end + 6) + '}).onKey')(space, world, hud);
  const controls = { keys: new Set(), yaw: 3, pitch: 2, player: { pos: { x: 0, z: 0 }, av: { root: { rotation: { y: 0 } } } },
    setView: () => calls.push('view'), setLayer: () => calls.push('layer'), exitSpace: () => calls.push('exit'), resetOverview: () => calls.push('reset') };
  return { onKey, controls, calls, space };
}
function element(tag, attrs = {}, parent = null) {
  return { tag, attrs, parent,
    matches(selector) {
      if (selector === '[contenteditable]:not([contenteditable="false"])') return Object.hasOwn(this.attrs, 'contenteditable') && this.attrs.contenteditable !== 'false';
      const match = /^([a-z]+)(?:\[([a-z]+)\])?$/.exec(selector);
      return !!match && this.tag === match[1] && (!match[2] || Object.hasOwn(this.attrs, match[2]));
    },
    closest(selector) {
      for (let node = this; node; node = node.parent) if (selector.split(',').some(part => node.matches(part.trim()))) return node;
      return null;
    },
  };
}
function keyEvent(key, target) {
  return { key, target, prevented: false, preventDefault() { this.prevented = true; } };
}

test('focused summary, buttons, links and editable inputs retain keyboard defaults and suppress world shortcuts', () => {
  const ui = [element('span', {}, element('summary')), element('button'), element('span', {}, element('a', { href: '/help' }))];
  const forms = [element('input'), element('textarea'), element('select'), element('div', { contenteditable: 'true' })];
  for (const target of [...ui, ...forms]) for (const key of [' ', 'ArrowUp', 'w', 'm', 'e', 'r']) {
    const { onKey, controls, calls } = keyboardFixture(), event = keyEvent(key, target);
    onKey.call(controls, event, true);
    assert.equal(event.prevented, false, `${target.tag} must keep the ${key} default`);
    assert.deepEqual([...controls.keys], []);
    assert.deepEqual(calls, []);
    assert.equal(controls.yaw, 3);
    assert.equal(controls.pitch, 2);
  }
  for (const target of [...ui, ...forms]) for (const view of ['walk', 'overview']) {
    const { onKey, controls, calls, space } = keyboardFixture(), event = keyEvent('Escape', target);
    space.view = view;
    onKey.call(controls, event, true);
    assert.equal(event.prevented, false);
    assert.deepEqual(calls, forms.includes(target) ? [] : view === 'walk' ? ['exit'] : ['close', 'reset']);
    assert.deepEqual([...controls.keys], []);
  }
});

test('keyup clears movement even over UI or paused panels while canvas movement still works', () => {
  const { onKey, controls, calls, space } = keyboardFixture(), canvas = element('canvas');
  const down = keyEvent('W', canvas);
  onKey.call(controls, down, true);
  assert.equal(down.prevented, true);
  assert.equal(controls.keys.has('w'), true);
  controls.keys.add('arrowup'); space.resultsOpen = true;
  const up = keyEvent('W', element('summary'));
  onKey.call(controls, up, false);
  assert.equal(controls.keys.has('w'), false);
  assert.equal(controls.keys.has('arrowup'), true);
  assert.equal(up.prevented, false);
  space.resultsOpen = false;
  onKey.call(controls, keyEvent('ArrowUp', element('button')), false);
  assert.deepEqual([...controls.keys], []);
  assert.deepEqual(calls, []);
});
