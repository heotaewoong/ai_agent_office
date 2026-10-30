import {test} from 'node:test';
import assert from 'node:assert/strict';
import {readFile} from 'node:fs/promises';
import {createRequire} from 'node:module';
import {createAtriumDetail} from '../atrium-detail.js';
const B=createRequire(import.meta.url)('../vendor/babylon.min.js');
const text=await readFile(new URL('../assets/atrium-detail-v3.json',import.meta.url),'utf8');
const native=JSON.parse(text);
const load=scene=>B.SceneLoader.LoadAssetContainerAsync('','data:'+text,scene,null,'.babylon').catch(error=>{throw error.innerError||error;});
const flush=async()=>{for(let i=0;i<20;i++)await Promise.resolve();};
function fixture(quality='high'){
  const engine=new B.NullEngine(),scene=new B.Scene(engine),casts=[];
  const makeStage=()=>{
    const node=new B.TransformNode('stage',scene),base=B.MeshBuilder.CreateBox('base',{},scene);
    node.position.set(25,0,-12);node.rotation.y=.6;base.parent=node;
    return {node,atriumArchitecture:{meshes:[base]}};
  };
  const stage=makeStage(),space={layer:'office',stages:[stage]},pending=[];
  scene.activeCamera=new B.FreeCamera('test',new B.Vector3(25,4,-12),scene);
  scene.activeCamera.getViewMatrix(true);
  const world={scene,castShadow:mesh=>casts.push(mesh),receiveShadow:mesh=>{mesh.receiveShadows=true;}};
  const controller=createAtriumDetail({world,space,quality,loadAsset:()=>new Promise(resolve=>pending.push(resolve))});
  return {engine,scene,stage,space,world,pending,casts,controller,makeStage,
    async finish(index=0){const c=await load(scene);pending[index](c);await flush();return c;},
    dispose(){controller.dispose();scene.dispose();engine.dispose();}};
}

test('Blender atrium has verified provenance, bounded geometry and no external texture/light/camera',async()=>{
  assert.equal(native.metadata.sourceSha256,'8c095d52e92064dc6eb48b8e6fc87a5f4665b9fb9bcecaeb12d298442e0be5dd');
  const f=fixture();try{
    const c=await load(f.scene),meshes=c.meshes.filter(m=>m.getTotalVertices());
    assert.equal(meshes.length,4);assert.equal(c.materials.length,4);
    assert.equal(c.textures.length+c.cameras.length+c.lights.length,0);
    assert.equal(meshes.reduce((n,m)=>n+m.getTotalIndices()/3,0),6204);
    assert.equal(native.metadata.triangles,6204);assert(Buffer.byteLength(text)<900000);c.dispose();
  }finally{f.dispose();}
});
test('low mode never requests atrium geometry or registers a render observer',async()=>{
  const f=fixture('low');try{f.controller.sync();await flush();assert.equal(f.pending.length,0);assert.equal(f.controller.status().phase,'disabled');assert(f.stage.atriumArchitecture.meshes[0].isEnabled());}finally{f.dispose();}
});
test('near load preserves the base until ready, attaches once to the rotated stage and reuses the asset',async()=>{
  const f=fixture();try{
    f.controller.sync();f.controller.sync();await flush();assert.equal(f.pending.length,1);
    assert(f.stage.atriumArchitecture.meshes[0].isEnabled());
    const c=await f.finish();assert.equal(f.controller.status().phase,'ready');assert.equal(f.controller.status().active,true);
    assert(!f.stage.atriumArchitecture.meshes[0].isEnabled());assert.equal(f.casts.length,4);
    for(const root of c.meshes.filter(m=>m.name==='__root__'))assert.equal(root.parent,f.stage.node);
    assert(c.meshes.every(m=>!m.isPickable&&!m.checkCollisions));
    f.space.layer='meadow';f.controller.sync();assert.equal(f.controller.status().active,false);assert(f.stage.atriumArchitecture.meshes[0].isEnabled());
    f.space.layer='office';f.controller.sync();assert.equal(f.pending.length,1);assert.equal(f.controller.status().active,true);
    f.controller.dispose();assert(f.stage.atriumArchitecture.meshes[0].isEnabled());assert(c.meshes.every(m=>m.isDisposed()));
  }finally{f.dispose();}
});
test('a stage rebuilt while loading cannot attach its late asset to the replacement stage',async()=>{
  const f=fixture();try{
    f.controller.sync();await flush();const old=f.stage;
    f.space.stages=[f.makeStage()];old.node.dispose();f.controller.sync();await flush();
    assert.equal(f.pending.length,2);const late=await f.finish(0);assert(late.meshes.every(m=>m.isDisposed()));
    const current=await f.finish(1);assert.equal(f.controller.status().active,true);
    assert.equal(current.meshes.find(m=>m.name==='__root__').parent,f.space.stages[0].node);
  }finally{f.dispose();}
});
test('invalid geometry fails closed and retains the existing building',async()=>{
  const f=fixture();try{
    f.controller.sync();await flush();const c=await load(f.scene);c.meshes.find(m=>m.getTotalVertices()).dispose();
    f.pending[0](c);await flush();assert.equal(f.controller.status().phase,'failed');assert(f.stage.atriumArchitecture.meshes[0].isEnabled());assert(c.meshes.every(m=>m.isDisposed()));
  }finally{f.dispose();}
});
