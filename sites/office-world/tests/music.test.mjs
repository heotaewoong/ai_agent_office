import { test } from 'node:test';
import assert from 'node:assert/strict';
import { mountMusic } from '../music-controls.js';

function fixture(available = true) {
  const nodes = {};
  for (const id of ['world-music', 'world-music-toggle', 'world-music-volume', 'world-music-status']) {
    nodes[id] = { handlers: {}, attrs: {}, disabled: true, value: '0.25',
      addEventListener(name, fn) { this.handlers[name] = fn; },
      getAttribute(name) { return this.attrs[name]; },
      setAttribute(name, value) { this.attrs[name] = value; } };
  }
  const audio = nodes['world-music'];
  audio.plays = 0;
  audio.play = () => { audio.plays++; return Promise.resolve(); };
  audio.pause = () => { audio.handlers.pause?.(); };
  const events = {};
  const doc = { hidden: false, getElementById: id => nodes[id],
    addEventListener: (name, fn) => events[name] = fn,
    defaultView: { addEventListener: (name, fn) => events[name] = fn } };
  mountMusic(doc, async () => ({ ok: true, json: async () => ({ available }) }));
  return { nodes, audio, doc, events, button: nodes['world-music-toggle'] };
}
const settled = () => new Promise(resolve => setImmediate(resolve));
test('off by default; explicit click starts; hidden page stops without resuming', async () => {
  const f = fixture(); await settled();
  assert.equal(f.audio.plays, 0);
  assert.equal(f.audio.src, undefined);
  assert.equal(f.button.disabled, false);
  f.button.handlers.click(); await settled();
  assert.equal(f.audio.plays, 1);
  assert.equal(f.audio.src, '/api/world/music/audio');
  assert.equal(f.button.attrs['aria-pressed'], 'true');
  f.doc.hidden = true; f.events.visibilitychange();
  assert.equal(f.button.attrs['aria-pressed'], 'false');
  f.doc.hidden = false; f.events.visibilitychange();
  assert.equal(f.audio.plays, 1);
});
test('unavailable stays disabled and playback rejection resets button', async () => {
  const unavailable = fixture(false); await settled();
  assert.equal(unavailable.button.disabled, true);
  const f = fixture(); await settled();
  f.audio.play = () => Promise.reject(new Error('blocked'));
  f.button.handlers.click(); await settled();
  assert.equal(f.button.attrs['aria-pressed'], 'false');
  assert.match(f.nodes['world-music-status'].textContent, /재생을 시작하지/);
});
test('volume is clamped and pending playback cannot revive stopped status', async () => {
  const f = fixture(); await settled();
  f.nodes['world-music-volume'].value = '5';
  f.nodes['world-music-volume'].handlers.input();
  assert.equal(f.audio.volume, 1);
  f.audio.play = () => new Promise(resolve => f.resolve = resolve);
  f.button.handlers.click(); f.button.handlers.click(); f.resolve(); await settled();
  assert.equal(f.button.attrs['aria-pressed'], 'false');
});
