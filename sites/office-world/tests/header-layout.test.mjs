import { readFile } from 'node:fs/promises';
import { test } from 'node:test';
import assert from 'node:assert/strict';

const source = await readFile(new URL('../app.js', import.meta.url), 'utf8');
const start = source.indexOf('    watchHeader(', source.indexOf('  const hud = {'));
const end = source.indexOf('\n    },', start);
function fixture(hasObserver = true) {
  const styles = new Map(), listeners = new Map(), header = { bottom: 131.57, getBoundingClientRect() { return { bottom: this.bottom }; } };
  let notify, watched, disconnected = false, dispose;
  const document = { querySelector: () => header, documentElement: { style: { setProperty: (key, value) => styles.set(key, value) } } };
  const window = { addEventListener: (key, value) => listeners.set(key, value), removeEventListener: key => listeners.delete(key) };
  const ResizeObserver = hasObserver ? class { constructor(callback) { notify = callback; } observe(value) { watched = value; } disconnect() { disconnected = true; } } : undefined;
  const world = { scene: { onDisposeObservable: { addOnce: callback => { dispose = callback; } } } };
  const watch = Function('document', 'window', 'ResizeObserver', 'world', `return ({${source.slice(start, end + 6)}}).watchHeader`)(document, window, ResizeObserver, world);
  return { watch, header, styles, listeners, resize() { (notify ?? listeners.get('resize'))(); }, dispose() { dispose(); }, get watched() { return watched; }, get disconnected() { return disconnected; } };
}

test('HUD follows the actual header after department names or toolbar rows change and releases its observer', () => {
  const f = fixture(); f.watch();
  assert.equal(f.watched, f.header);
  assert.equal(f.styles.get('--world-header-bottom'), '132px');
  f.header.bottom = 187.2; f.resize();
  assert.equal(f.styles.get('--world-header-bottom'), '188px');
  f.dispose(); assert(f.disconnected); assert.equal(f.listeners.size, 0);
});

test('without ResizeObserver the world still starts and follows viewport resize', () => {
  const f = fixture(false); f.watch();
  assert.equal(f.styles.get('--world-header-bottom'), '132px');
  f.header.bottom = 141.7; f.resize();
  assert.equal(f.styles.get('--world-header-bottom'), '142px');
  f.dispose(); assert.equal(f.listeners.size, 0);
});
