import assert from 'node:assert/strict';
import {test} from 'node:test';
import {summarizeTimings, assertComparableRuns, measureCameraScenario} from './camera-performance-probe.mjs';

test('timing summaries preserve samples and missing GPU data stays unknown',()=>{
  const samples=[4,1,3,2];
  assert.deepEqual(summarizeTimings(samples),{n:4,p50:3,p95:4,mean:2.5});
  assert.deepEqual(samples,[4,1,3,2]);
  assert.deepEqual(summarizeTimings([]),{n:0,p50:null,p95:null,mean:null});
  assert.throws(()=>summarizeTimings([1,NaN]),/finite/);
});

const run=()=>({layer:'office',quality:'high',qualityFeatures:{shadows:true,postProcesses:true,ssaoSamples:16},css:[1280,720],canvas:[1280,720],dpr:1,
  renderer:'same GPU',meshes:885,vertices:680000,
  cameraPath:{alpha:-Math.PI/2,beta:1.15,radius:210,target:[0,-18,0],amplitude:.32,period:45},
  warmupFrames:100,sampleFrames:180});

test('different render resolution, quality, geometry or camera paths cannot be called a fair A/B',()=>{
  assert.equal(assertComparableRuns(run(),run()),true);
  for(const changed of [{canvas:[1920,1080]},{quality:'low'},{meshes:100},{cameraPath:{radius:430}},{sampleFrames:60}]) {
    assert.throws(()=>assertComparableRuns(run(),{...run(),...changed}),/conditions differ/);
  }
});

test('unchanged high labels cannot hide disabled effects or fewer AO samples',()=>{
  for(const changed of [{shadows:false,postProcesses:true,ssaoSamples:16},
    {shadows:true,postProcesses:false,ssaoSamples:16},{shadows:true,postProcesses:true,ssaoSamples:8}]) {
    assert.throws(()=>assertComparableRuns(run(),{...run(),qualityFeatures:changed}),/conditions differ/);
  }
});

test('camera probes preserve the existing render pixel density by default',async()=>{
  let scale=.5,clock=0;
  const engine={getHardwareScalingLevel:()=>scale,setHardwareScalingLevel:v=>{scale=v;},resize(){},
    getRenderWidth:()=>800/scale,getRenderHeight:()=>600/scale,getGlInfo:()=>({renderer:'test'})};
  class Instrumentation {
    frameTimeCounter={current:1};renderTimeCounter={current:1};
    activeMeshesEvaluationTimeCounter={current:1};gpuFrameTimeCounter={current:0};dispose(){}
  }
  const env={document:{hidden:false},innerWidth:800,innerHeight:600,devicePixelRatio:2,
    performance:{now:()=>clock},setTimeout,clearTimeout,cancelAnimationFrame(){},
    requestAnimationFrame(fn){queueMicrotask(()=>fn(clock+=16));return 1;},
    BABYLON:{SceneInstrumentation:Instrumentation,EngineInstrumentation:Instrumentation,Vector3:{FromArray:a=>a}}};
  const camera={setTarget(){}};
  const office={quality:'high',space:{view:'overview'},controls:{setLayer(){},overview:camera},
    world:{engine,scene:{meshes:[{name:'fixed',getTotalVertices:()=>24}]}}};
  const measured=await measureCameraScenario(office,{warmupFrames:1,sampleFrames:2},env);
  assert.deepEqual(measured.canvas,[1600,1200],'measurement must not silently lower native rendering quality');
  assert.equal(scale,.5,'original render density must remain after measurement');
});
