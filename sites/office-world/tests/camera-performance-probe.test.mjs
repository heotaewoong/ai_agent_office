import assert from 'node:assert/strict';
import {test} from 'node:test';
import {summarizeTimings, assertComparableRuns} from './camera-performance-probe.mjs';

test('timing summaries preserve samples and missing GPU data stays unknown',()=>{
  const samples=[4,1,3,2];
  assert.deepEqual(summarizeTimings(samples),{n:4,p50:3,p95:4,mean:2.5});
  assert.deepEqual(samples,[4,1,3,2]);
  assert.deepEqual(summarizeTimings([]),{n:0,p50:null,p95:null,mean:null});
  assert.throws(()=>summarizeTimings([1,NaN]),/finite/);
});

const run=()=>({layer:'office',quality:'high',css:[1280,720],canvas:[1280,720],dpr:1,
  renderer:'same GPU',meshes:885,vertices:680000,
  cameraPath:{alpha:-Math.PI/2,beta:1.15,radius:210,target:[0,-18,0],amplitude:.32,period:45},
  warmupFrames:100,sampleFrames:180});

test('different render resolution, quality, geometry or camera paths cannot be called a fair A/B',()=>{
  assert.equal(assertComparableRuns(run(),run()),true);
  for(const changed of [{canvas:[1920,1080]},{quality:'low'},{meshes:100},{cameraPath:{radius:430}},{sampleFrames:60}]) {
    assert.throws(()=>assertComparableRuns(run(),{...run(),...changed}),/conditions differ/);
  }
});
