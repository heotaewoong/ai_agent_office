import { test } from 'node:test';
import assert from 'node:assert/strict';
import { fitPanelSize } from '../panel-resize.js';

test('oversized panels stay inside the available viewer', () => {
  assert.deepEqual(fitPanelSize(1000, 900, 358, 640, 240), { width: 358, height: 640 });
});

test('shrinking retains readable width and space for the header, footer and content', () => {
  assert.deepEqual(fitPanelSize(120, 100, 1248, 560, 330), { width: 320, height: 330 });
});

test('a small viewer takes precedence over the normal minimum size', () => {
  assert.deepEqual(fitPanelSize(320, 260, 248, 136, 240), { width: 248, height: 136 });
});
