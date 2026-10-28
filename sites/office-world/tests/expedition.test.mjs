import { readFile } from 'node:fs/promises';
import assert from 'node:assert/strict';
import { test } from 'node:test';

const source = await readFile(new URL('../expedition.js', import.meta.url), 'utf8');
const { ALIENS, VEHICLES, credits, readProfile, capture, purchase, canRide } =
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

test('only a vehicle owned by an on-foot grounded player can be mounted', () => {
  const p = profile();
  assert.equal(canRide(p, 'scout', context()), false);
  capture(p, ALIENS[0].id, context(ALIENS[0]));
  capture(p, ALIENS[1].id, context(ALIENS[1]));
  purchase(p, 'scout');
  assert.equal(canRide(p, 'scout', context()), true);
  assert.equal(canRide(p, 'nova', context()), false);
  assert.equal(canRide(p, 'unknown', context()), false);
  for (const override of [{ layer: 'office' }, { view: 'overview' }, { mounted: true }, { grounded: false }])
    assert.equal(canRide(p, 'scout', context(ALIENS[0], override)), false);
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
