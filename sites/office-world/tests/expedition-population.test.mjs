import { readFile } from 'node:fs/promises';
import assert from 'node:assert/strict';
import { test } from 'node:test';

const source = await readFile(new URL('../expedition.js', import.meta.url), 'utf8');
const game = await import('data:text/javascript;base64,' + Buffer.from(source).toString('base64'));
const legacyIds = ['mint', 'violet', 'amber', 'azure', 'pearl', 'coral', 'lime', 'nova'];

test('more creatures are spread along the arrival plaza and nearby roads without replacing the original collection', () => {
  assert.equal(game.ALIENS.length, 16);
  assert.deepEqual(game.ALIENS.slice(0, 8).map(a => a.id), legacyIds);
  assert.equal(new Set(game.ALIENS.map(a => a.id)).size, 16);
  assert.ok(game.ALIENS.filter(a => Math.hypot(a.x, a.z + 64) <= 45).length >= 6);
  for (const a of game.ALIENS) {
    assert.ok(Number.isFinite(a.x) && Number.isFinite(a.z));
    for (const b of game.ALIENS) if (a !== b) assert.ok(Math.hypot(a.x - b.x, a.z - b.z) > 14);
  }
});

test('a captured creature becomes visible after ten seconds, and stays hidden in the air layer', () => {
  assert.equal(typeof game.alienVisible, 'function');
  assert.equal(game.alienVisible('meadow', undefined, 0), true);
  assert.equal(game.alienVisible('meadow', 0, 9999), false);
  assert.equal(game.alienVisible('meadow', 0, 10000), true);
  assert.equal(game.alienVisible('office', undefined, 10000), false);
  assert.equal(game.alienVisible('office', 0, 20000), false);
});

test('an old complete collection keeps its vehicles and balance; reappearing creatures never pay twice', () => {
  const saved = { captured: legacyIds, owned: ['scout', 'nova'], selected: 'nova' };
  const p = game.readProfile(JSON.stringify(saved));
  assert.deepEqual(p, saved);
  assert.equal(game.credits(p), 80);
  const before = JSON.stringify(p), a = game.ALIENS[0];
  assert.equal(game.capture(p, a.id, { layer: 'meadow', view: 'walk', grounded: true, mounted: false, position: a }), false);
  assert.equal(JSON.stringify(p), before);
});
