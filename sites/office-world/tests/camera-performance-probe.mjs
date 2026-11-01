// Local browser diagnostic; not imported by the production world.
export function summarizeTimings(samples) {
  if(samples.some(n=>!Number.isFinite(n)||n<0))throw Error('Timings must be finite and nonnegative');
  const sorted=[...samples].sort((a,b)=>a-b),n=sorted.length;
  return {n,p50:n?sorted[Math.floor(n*.5)]:null,p95:n?sorted[Math.floor(n*.95)]:null,
    mean:n?sorted.reduce((sum,v)=>sum+v,0)/n:null};
}

export function assertComparableRuns(a,b) {
  for(const key of ['layer','quality','css','canvas','dpr','renderer','meshes','vertices','cameraPath','warmupFrames','sampleFrames']) {
    if(a[key]===undefined||b[key]===undefined||JSON.stringify(a[key])!==JSON.stringify(b[key])) {
      throw Error(`A/B conditions differ: ${key}`);
    }
  }
  return true;
}

export async function measureCameraScenario(office,{layer='office',warmupFrames=100,sampleFrames=180}={},env=window) {
  if(!['office','meadow'].includes(layer)||!Number.isInteger(warmupFrames)||warmupFrames<1||
    !Number.isInteger(sampleFrames)||sampleFrames<2||sampleFrames>600)throw Error('Invalid camera scenario');
  if(env.document.hidden)throw Error('The measurement tab must be visible');
  const {world,controls,space}=office,B=env.BABYLON,scene=world.scene;
  if(space.view!=='overview')throw Error('Return to overview before running a camera probe');
  const deadline=env.performance.now()+45000;
  const nextFrame=()=>new Promise((resolve,reject)=>{
    let timer;
    const id=env.requestAnimationFrame(t=>{env.clearTimeout(timer);resolve(t);});
    timer=env.setTimeout(()=>{env.cancelAnimationFrame(id);reject(Error('Frame probe timed out'));},
      Math.max(1,Math.min(2000,deadline-env.performance.now())));
  });
  // Quality remains unchanged; both variants use one render pixel per CSS pixel.
  const previousScale=world.engine.getHardwareScalingLevel();
  world.engine.setHardwareScalingLevel(1);world.engine.resize();
  controls.setLayer(layer);
  let si,ei,camera,alpha;
  try {
    for(let i=0;i<warmupFrames;i++)await nextFrame();
    controls.cameraTween=null;camera=controls.overview;
    const cameraPath={alpha:-Math.PI/2,beta:1.15,radius:layer==='office'?210:430,
      target:[0,-18,0],amplitude:.32,period:45};
    alpha=cameraPath.alpha;camera.alpha=alpha;camera.beta=cameraPath.beta;camera.radius=cameraPath.radius;
    camera.setTarget(B.Vector3.FromArray(cameraPath.target));
    camera.inertialAlphaOffset=camera.inertialBetaOffset=camera.inertialRadiusOffset=0;
    si=new B.SceneInstrumentation(scene);ei=new B.EngineInstrumentation(world.engine);
    si.captureFrameTime=si.captureRenderTime=si.captureActiveMeshesEvaluationTime=true;
    ei.captureGPUFrameTime=true;
    const frame=[],cpu=[],render=[],activeEval=[],gpu=[];
    let last;
    for(let i=0;i<sampleFrames;i++) {
      camera.alpha=alpha+Math.sin(i/cameraPath.period)*cameraPath.amplitude;
      const t=await nextFrame();
      if(last!==undefined)frame.push(t-last);last=t;
      cpu.push(si.frameTimeCounter.current);render.push(si.renderTimeCounter.current);
      activeEval.push(si.activeMeshesEvaluationTimeCounter.current);
      const gpuNs=ei.gpuFrameTimeCounter.current;
      if(Number.isFinite(gpuNs)&&gpuNs>0)gpu.push(gpuNs/1e6);
    }
    // Transient work-flow dots are counted separately from the unchanged world geometry.
    const structural=scene.meshes.filter(m=>m.name!=='flow');
    return {at:new Date().toISOString(),layer,quality:office.quality,
      css:[env.innerWidth,env.innerHeight],canvas:[world.engine.getRenderWidth(),world.engine.getRenderHeight()],
      dpr:env.devicePixelRatio,renderer:world.engine.getGlInfo().renderer,
      meshes:structural.length,vertices:structural.reduce((n,m)=>n+m.getTotalVertices(),0),
      transientFlows:scene.meshes.length-structural.length,cameraPath,warmupFrames,sampleFrames,
      frame:summarizeTimings(frame),cpu:summarizeTimings(cpu),render:summarizeTimings(render),
      activeEval:summarizeTimings(activeEval),gpu:summarizeTimings(gpu),
      heap:env.performance.memory?.usedJSHeapSize??null};
  } finally {
    si?.dispose();ei?.dispose();
    if(camera)camera.alpha=alpha;
    world.engine.setHardwareScalingLevel(previousScale);world.engine.resize();
  }
}
