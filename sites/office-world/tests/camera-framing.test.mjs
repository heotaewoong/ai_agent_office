import { readFile } from 'node:fs/promises';
import { createRequire } from 'node:module';
import { test } from 'node:test';
import assert from 'node:assert/strict';
const B = createRequire(import.meta.url)('../vendor/babylon.min.js');
const source = await readFile(new URL('../app.js', import.meta.url), 'utf8');
const start = source.indexOf('    syncCameraFraming(', source.indexOf('  const controls = {'));
const end = source.indexOf('\n    },', start);
const method = world => Function('world','B',`return ({${source.slice(start,end+6)}}).syncCameraFraming`)(world,B);

test('portrait driving preserves horizontal space for the vehicle and landscape keeps the original FOV mode', () => {
  for (const [width,height] of [[320,900],[390,844],[768,900],[1280,720]]) {
    const engine=new B.NullEngine({renderWidth:width,renderHeight:height}),scene=new B.Scene(engine);
    try {
      const camera=new B.UniversalCamera('walk',new B.Vector3(0,4.8,-10),scene);
      camera.setTarget(new B.Vector3(0,1.5,0));scene.activeCamera=camera;
      method({engine}).call({walk:camera});
      assert.equal(camera.fovMode,width<height?B.Camera.FOVMODE_HORIZONTAL_FIXED:B.Camera.FOVMODE_VERTICAL_FIXED);
      const matrix=camera.getViewMatrix(true).multiply(camera.getProjectionMatrix(true)),viewport=camera.viewport.toGlobal(width,height);
      const left=B.Vector3.Project(new B.Vector3(-1.3,.88,0),B.Matrix.Identity(),matrix,viewport);
      const right=B.Vector3.Project(new B.Vector3(1.3,.88,0),B.Matrix.Identity(),matrix,viewport);
      assert((right.x-left.x)/width<.5,'a 2.6m vehicle must leave visible road on both sides');
    } finally {scene.dispose();engine.dispose();}
  }
});

test('resizing back to landscape restores the original framing and pre-init resize is safe', () => {
  let ratio=.4;const world={engine:{getAspectRatio:()=>ratio}},controls={walk:{}};
  const sync=method(world);sync.call(controls);assert.equal(controls.walk.fovMode,B.Camera.FOVMODE_HORIZONTAL_FIXED);
  ratio=2;sync.call(controls);assert.equal(controls.walk.fovMode,B.Camera.FOVMODE_VERTICAL_FIXED);
  assert.doesNotThrow(()=>sync.call({}));
});
