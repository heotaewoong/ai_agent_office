import { test } from 'node:test';
import assert from 'node:assert/strict';
import { readFile } from 'node:fs/promises';
const source = await readFile(new URL('../app.js', import.meta.url), 'utf8');
function fixture() {
  const start = source.indexOf('  const assistantNative = {'), end = source.indexOf('\n  };', start);
  assert(start >= 0 && end > start, 'native-only actor adapter must exist');
  const vector = (x = 0, y = 0, z = 0) => ({ x, y, z, clone() { return vector(this.x, this.y, this.z); }, copyFrom(v) { Object.assign(this, { x: v.x, y: v.y, z: v.z }); } });
  const space = { layer: 'office', stages: [{ id: 'inbox', pos: vector(23, 0, 0), bridge: { start: vector(10), end: vector(15) } }], agents: [] };
  const data = { source: 'live', error: null }, embed = { enabled: true };
  const world = { buildAvatar() { return { root: { position: vector(), rotation: { y: 0 }, getChildMeshes: () => [], dispose() {} }, marker: {}, body: {} }; }, local: (_stage,x,y,z) => vector(x,y,z), setPose() {}, mat: () => ({}), markerColor: () => '#ffffff', animateWalk() {} };
  const controls = { player: { pos: vector(1, 0, 1) } };
  const adapter = Function('space', 'data', 'embed', 'world', 'controls', 'B', 'REDUCED', 'document', 'return (' + source.slice(start + '  const assistantNative = '.length, end + 4) + ')')(space, data, embed, world, controls, { Vector3: function (x, y, z) { return vector(x, y, z); } }, false, { hidden: false });
  return { adapter, space, data, embed };
}
const request = (patch = {}) => ({ request_id: 'aa3a151d-72e8-4abf-b09d-10d416279c41', board: 'heobrain-office', status: 'running', native_status: 'running', assignee: 'lumi', native_task_id: 't_1234abcd', events: [{ id: 1, kind: 'spawned', assignee: 'lumi', task_id: 't_1234abcd', run_id: 2 }], report: null, ...patch });
test('only real assignee events create a separate native actor and duplicate polls do not restart movement', () => {
  const f = fixture(); f.adapter.sync(request());
  assert.equal(f.adapter.actors.size, 1); assert.equal(f.space.agents.length, 0, 'nine content actors are untouched');
  const actor = f.adapter.actors.get('lumi'), path = actor.path;
  assert.equal(actor.taskId, 't_1234abcd'); assert.equal(actor.phase, 'working');
  f.adapter.sync(request()); assert.equal(actor.path, path);
  f.adapter.sync(request({ events: [{ ...request().events[0], assignee: 'director', id: 2 }] }));
  assert.equal(f.adapter.actors.size, 1, 'content role is not a native profile');
});
test('unverified completion never returns a worker; verified matching completion returns only the actual coordinator', () => {
  const f = fixture(); f.adapter.sync(request()); const actor = f.adapter.actors.get('lumi');
  const complete = request({ status: 'completed', native_status: 'done', events: [{ ...request().events[0], id: 2, kind: 'completed' }] });
  f.adapter.sync(complete); assert.notEqual(actor.phase, 'returning');
  f.adapter.sync({ ...complete, report: { verified: true, task_id: 't_1234abcd', run_id: 2, event_id: 2 } });
  assert.equal(actor.phase, 'returning');
  const path = actor.path; f.adapter.sync({ ...complete, report: { verified: true, task_id: 't_1234abcd', run_id: 2, event_id: 2 } }); assert.equal(actor.path, path);
});
test('offline and stale world observations never manufacture native workers', () => {
  for (const source of ['sample', 'none']) { const f = fixture(); f.data.source = source; f.adapter.sync(request()); assert.equal(f.adapter.actors.size, 0); }
  const f = fixture(); f.data.error = 'unavailable'; f.adapter.sync(request()); assert.equal(f.adapter.actors.size, 0);
});

test('a verified final Lumi descendant returns without replacing the stable root task ID', () => {
  const f = fixture();
  const final = request({ status: 'completed', native_status: 'done', events: [{ id: 3, kind: 'completed', assignee: 'lumi', task_id: 't_final123', run_id: 3 }], report: { verified: true, task_id: 't_final123', run_id: 3, event_id: 3 } });
  f.adapter.sync(final);
  assert.equal(f.adapter.actors.get('lumi').phase, 'returning');
  assert.equal(final.native_task_id, 't_1234abcd');
});
