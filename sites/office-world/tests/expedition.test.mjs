import { readFile } from 'node:fs/promises';
import assert from 'node:assert/strict';
import { test } from 'node:test';

const source = await readFile(new URL('../expedition.js', import.meta.url), 'utf8');
const { ALIENS, VEHICLES, credits, readProfile, capture, purchase, canRide, selectVehicle, startTestDrive } =
  await import('data:text/javascript;base64,' + Buffer.from(source).toString('base64'));
const profile = () => readProfile(null);
const context = (alien = ALIENS[0], overrides = {}) => ({
  layer: 'meadow', view: 'walk', grounded: true, mounted: false,
  position: { x: alien.x, z: alien.z }, ...overrides,
});

test('damaged storage and forged balance do not grant currency or ownership', () => {
  for (const text of ['{broken', 'null', 'false', '7', '[]', '{}']) {
    const p = readProfile(text);
    assert.equal(credits(p), 0);
    assert.deepEqual(p.owned, []);
  }
  const p = readProfile(JSON.stringify({ credits: 999999, captured: ['unknown'], owned: ['nova'], selected: 'unknown' }));
  assert.equal(credits(p), 0);
  assert.deepEqual(p.owned, []);
  assert.equal(p.selected, VEHICLES[0].id);
});

test('restoration deduplicates known captures and only funds known vehicles once', () => {
  const p = readProfile(JSON.stringify({
    captured: [...ALIENS.map(a => a.id), ALIENS[0].id, null, {}, 'unknown'],
    owned: ['scout', 'scout', 'unknown', 'nova', 'nova'], selected: 'nova',
  }));
  assert.equal(p.captured.length, ALIENS.length);
  assert.deepEqual(p.owned, ['scout', 'nova']);
  assert.equal(credits(p), ALIENS.length * 40 - VEHICLES.reduce((sum, v) => sum + v.cost, 0));
  assert.equal(p.selected, 'nova');
});

test('a capture pays once and the seventh metre is an inclusive boundary', () => {
  const p = profile(), alien = ALIENS[0];
  assert.equal(capture(p, alien.id, context(alien, { position: { x: alien.x + 7, z: alien.z } })), true);
  assert.equal(credits(p), 40);
  const before = JSON.stringify(p);
  assert.equal(capture(p, alien.id, context(alien)), false);
  assert.equal(JSON.stringify(p), before);
});

test('capture requires walking on the ground in the matching world layer', () => {
  for (const override of [
    { layer: 'office' }, { view: 'overview' }, { mounted: true }, { grounded: false },
    { grounded: undefined }, { position: null }, { position: { x: NaN, z: 0 } },
    { position: { x: Infinity, z: 0 } }, { position: { x: ALIENS[0].x + 7.001, z: ALIENS[0].z } },
  ]) {
    const p = profile();
    assert.equal(capture(p, ALIENS[0].id, context(ALIENS[0], override)), false);
    assert.deepEqual(p.captured, []);
    assert.equal(credits(p), 0);
  }
  assert.equal(capture(profile(), 'unknown', context()), false);
});

test('insufficient funds and repeat purchases preserve the ledger', () => {
  const p = profile(), scout = VEHICLES.find(v => v.id === 'scout');
  capture(p, ALIENS[0].id, context(ALIENS[0]));
  const before = JSON.stringify(p);
  assert.equal(purchase(p, scout.id), false);
  assert.equal(purchase(p, 'unknown'), false);
  assert.equal(JSON.stringify(p), before);
  capture(p, ALIENS[1].id, context(ALIENS[1]));
  assert.equal(credits(p), scout.cost);
  assert.equal(purchase(p, scout.id), true);
  assert.equal(credits(p), 0);
  assert.equal(p.selected, scout.id);
  const purchased = JSON.stringify(p);
  assert.equal(purchase(p, scout.id), false);
  assert.equal(JSON.stringify(p), purchased);
});

test('both known vehicles are free to drive without changing capture or purchase progress', () => {
  const p = profile();
  for (const vehicle of VEHICLES) {
    assert.equal(selectVehicle(p, vehicle.id), true);
    assert.equal(canRide(p, vehicle.id, context()), true);
    const space = { layer: 'office', view: 'overview' };
    const actions = [];
    const controls = {
      player: { grounded: false }, vehicleSpeed: 0,
      enableTouchWalk(enabled) { actions.push(['touch', enabled]); },
      setLayer(layer, walk) {
        actions.push(['layer', layer, walk]);
        space.layer = layer; space.view = walk ? 'walk' : 'overview'; this.player.grounded = true;
      },
      setVehicleSpeed(speed) { this.vehicleSpeed = speed; return true; },
    };
    assert.equal(startTestDrive(p, { space, controls }), true);
    assert.equal(controls.vehicleSpeed, vehicle.speed);
    assert.deepEqual(actions, [['touch', true], ['layer', 'meadow', true]]);
    assert.deepEqual(p.owned, []);
    assert.deepEqual(p.captured, []);
    assert.equal(credits(p), 0);
    assert.deepEqual(readProfile(JSON.stringify(p)), p);
  }
});

test('free selection and driving retain invalid-input, airborne and mounted guards', () => {
  const p = profile(), before = JSON.stringify(p);
  assert.equal(selectVehicle(p, 'unknown'), false);
  assert.equal(selectVehicle(p, 'nova', true), false);
  assert.equal(JSON.stringify(p), before);
  assert.equal(canRide(p, 'unknown', context()), false);
  for (const override of [{ layer: 'office' }, { view: 'overview' }, { mounted: true }, { grounded: false }, { grounded: undefined }])
    assert.equal(canRide(p, 'scout', context(ALIENS[0], override)), false);
  assert.equal(startTestDrive(p, null), false);
  const space = { layer: 'meadow', view: 'walk' };
  let drives = 0;
  const controls = {
    player: { grounded: false }, vehicleSpeed: 0,
    enableTouchWalk() {}, setVehicleSpeed() { drives++; return true; },
    setLayer() { assert.fail('Do not teleport a grounded-mode player just to bypass airborne checks'); },
  };
  assert.equal(startTestDrive(p, { space, controls }), false);
  controls.player.grounded = true; controls.vehicleSpeed = 24;
  assert.equal(startTestDrive(p, { space, controls }), false);
  assert.equal(drives, 0);
  assert.equal(JSON.stringify(p), before);
});

test('a full collection can buy both vehicles and survives a normal save round trip', () => {
  const p = profile();
  for (const alien of ALIENS) assert.equal(capture(p, alien.id, context(alien)), true);
  for (const vehicle of VEHICLES) assert.equal(purchase(p, vehicle.id), true);
  assert.equal(credits(p), 80);
  const restored = readProfile(JSON.stringify(p));
  assert.deepEqual(restored, p);
  assert.equal(credits(restored), credits(p));
});

function drivePanelSync(mounted, drive, summary, state, classes) {
  const start = source.indexOf('  function syncDrivePanel() {');
  const end = source.indexOf('\n  }', start);
  assert(start >= 0 && end > start, 'the native disclosure must synchronize driving visibility');
  return Function('mounted', 'drive', 'driveSummary', 'driveState', 'document',
    'tourPanel', 'return ' + source.slice(start, end + 4))(mounted, drive, summary, state, { body: { classList: classes } }, { open: true });
}

test('optional driving stays folded until opened and preserves controls when reopened', () => {
  const controls = { selected: 'nova', tour: { next: 2 } }, classes = new Map();
  const drive = { open: false, controls, set innerHTML(_) { assert.fail('folding must not replace vehicle or tour controls'); } };
  const summary = { setAttribute(key, value) { this[key] = value; } }, state = {};
  const sync = drivePanelSync(false, drive, summary, state, { toggle: (key, value) => classes.set(key, value) });
  sync();
  assert.equal(drive.open, false);
  assert.equal(classes.get('free-drive-open'), false);
  assert.equal(classes.get('tour-panel-open'), false);
  for (const open of [true, false, true]) {
    drive.open = open; sync();
    assert.equal(classes.get('free-drive-open'), open);
    assert.equal(classes.get('tour-panel-open'), open);
    assert.equal(drive.controls, controls);
    assert.equal(drive.controls.selected, 'nova');
    assert.equal(drive.controls.tour.next, 2);
  }
  assert.equal(summary['aria-disabled'], 'false');
});

test('driving keeps the disclosure open so dismount controls remain available', () => {
  const drive = { open: false }, summary = { setAttribute(key, value) { this[key] = value; } }, state = {};
  const flags = new Map(), classes = { toggle: (key, value) => flags.set(key, value) };
  const sync = drivePanelSync(true, drive, summary, state, classes);
  sync();
  assert.equal(drive.open, true);
  assert.equal(flags.get('free-drive-open'), true);
  assert.equal(summary['aria-disabled'], 'true');
  drive.open = false; sync();
  assert.equal(drive.open, true, 'programmatic folding cannot hide an active driver\'s dismount button');
  drivePanelSync(false, drive, summary, state, classes)();
  assert.equal(summary['aria-disabled'], 'false');
  drive.open = false; drivePanelSync(false, drive, summary, state, classes)();
  assert.equal(flags.get('free-drive-open'), false);
});
