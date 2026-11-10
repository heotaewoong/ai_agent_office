import { readFileSync } from 'node:fs';
import assert from 'node:assert/strict';
import { test } from 'node:test';
const source = readFileSync(new URL('../app.js', import.meta.url), 'utf8');
function renderMethod(clock) {
  const start = source.indexOf('    renderNextFrame(');
  const end = source.indexOf('\n    },', start);
  assert(start >= 0 && end > start, 'world must bound unfinished GPU frames');
  return Function('performance', 'return ({' + source.slice(start, end + 6) + '}).renderNextFrame')({ now: () => clock.value });
}
function fixture() {
  const clock = { value: 100 }, calls = [];
  const gl = { TIMEOUT_EXPIRED: 1, SYNC_GPU_COMMANDS_COMPLETE: 2, status: 0, lost: false,
    isContextLost() { return this.lost; },
    clientWaitSync(sync, flags, timeout) { assert.equal(flags, 0); assert.equal(timeout, 0); calls.push('poll'); return this.status; },
    deleteSync() { calls.push('delete'); }, fenceSync() { calls.push('fence'); return {}; }, flush() { calls.push('flush'); } };
  const world = { renderContext: gl, scene: { render() { calls.push('render'); } }, engine: { getDeltaTime: () => 16 } };
  return { clock, calls, gl, world, frame: renderMethod(clock) };
}
test('unfinished GPU work yields without submitting a second frame or blocking', () => {
  const f = fixture(); f.frame.call(f.world); f.gl.status = f.gl.TIMEOUT_EXPIRED;
  for (let i = 0; i < 20; i++) f.frame.call(f.world);
  assert.equal(f.calls.filter(x => x === 'render').length, 1);
  assert.equal(f.calls.filter(x => x === 'fence').length, 1);
  assert.equal(f.calls.filter(x => x === 'poll').length, 20);
});
test('GPU completion releases the fence and preserves elapsed animation time', () => {
  const f = fixture(); f.frame.call(f.world); f.clock.value = 350; f.frame.call(f.world);
  assert.deepEqual(f.calls, ['render', 'fence', 'flush', 'poll', 'delete', 'render', 'fence', 'flush']);
  assert.equal(f.world.renderDeltaMs, 250);
});
test('context loss drops stale work; restored context can render again', () => {
  const f = fixture(); f.frame.call(f.world); f.gl.lost = true; f.frame.call(f.world);
  assert.equal(f.world.pendingFrame, null); f.gl.lost = false; f.frame.call(f.world);
  assert.equal(f.calls.filter(x => x === 'render').length, 2);
});
test('WebGL1 fallback continues rendering without sync extensions', () => {
  const f = fixture(); f.world.renderContext = null; f.frame.call(f.world); f.frame.call(f.world);
  assert.deepEqual(f.calls, ['render', 'render']);
});
test('failed or unavailable fences cannot permanently stall the scene', () => {
  const f = fixture(); f.frame.call(f.world); f.gl.status = -1; f.gl.fenceSync = () => null;
  f.frame.call(f.world); f.frame.call(f.world);
  assert.equal(f.calls.filter(x => x === 'render').length, 3);
});
