import { readFile } from 'node:fs/promises';
import assert from 'node:assert/strict';
import { test } from 'node:test';

const source = await readFile(new URL('../activities.js', import.meta.url), 'utf8');
const { nearbyPlaceIds, readVisits } = await import('data:text/javascript;base64,' + Buffer.from(source).toString('base64'));

test('a visit requires the matching layer and an actual nearby position', () => {
  assert.deepEqual(nearbyPlaceIds('meadow', { x: 0, z: -46 }), ['transfer']);
  assert.deepEqual(nearbyPlaceIds('office', { x: 0, z: -46 }), []);
  assert.deepEqual(nearbyPlaceIds('office', { x: 0, z: 0 }), ['memory-plaza']);
  assert.deepEqual(nearbyPlaceIds('office', { x: 42, z: 0 }), ['sky-view']);
  assert.deepEqual(nearbyPlaceIds('meadow', { x: 20, z: -46 }), []);
});

test('invalid positions and damaged storage cannot grant exploration progress', () => {
  assert.deepEqual(nearbyPlaceIds('office', { x: NaN, z: 0 }), []);
  assert.deepEqual(nearbyPlaceIds('office', null), []);
  assert.equal(readVisits('{broken').size, 0);
  assert.equal(readVisits(JSON.stringify(['transfer', 'transfer', 'unknown'])).size, 1);
});
