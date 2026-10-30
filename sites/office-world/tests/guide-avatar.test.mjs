import {test} from 'node:test';
import assert from 'node:assert/strict';
import {readFile} from 'node:fs/promises';
import {createRequire} from 'node:module';
import {createGuideAvatar} from '../guide-avatar.js';
const B=createRequire(import.meta.url)('../vendor/babylon.min.js');
const source=await readFile(new URL('../app.js',import.meta.url),'utf8');
const text=await readFile(new URL('../assets/guide-avatar-v1.json',import.meta.url),'utf8');
const flush=async()=>{for(let i=0;i<20;i++)await Promise.resolve();};
function method(name){
  const start=source.indexOf('    '+name+'(',source.indexOf('  const world = {')),end=source.indexOf('\n    },',start);
  return Function('B','QUALITY','return ({'+source.slice(start,end+6)+'}).'+name)(B,'high');
}
function fixture(quality='high'){
  const engine=new B.NullEngine(),scene=new B.Scene(engine),sun=new B.DirectionalLight('sun',new B.Vector3(0,-1,1),scene),shadows=new B.ShadowGenerator(128,sun);
  const world={scene,matCache:new Map(),castShadow:mesh=>shadows.addShadowCaster(mesh,false),receiveShadow:mesh=>{mesh.receiveShadows=true;}};
  for(const name of ['mat','pbr','box','buildAvatar','setPose','animateWalk'])world[name]=method(name);
  const avatar=world.buildAvatar('player','#f5d6b8','#f4f1ea','#7fe3ff'),controls={player:{av:avatar}},space={view:'overview'},pending=[];
  const controller=createGuideAvatar({world,controls,space,quality,loadAsset:()=>new Promise((resolve,reject)=>pending.push({resolve,reject}))});
  return{engine,scene,world,avatar,controls,space,pending,controller,shadows,
    async finish(){const c=await B.SceneLoader.LoadAssetContainerAsync('','data:'+text,scene,null,'.babylon');pending[0].resolve(c);await flush();return c;},
    dispose(){controller.dispose();scene.dispose();engine.dispose();}};
}
test('native guide geometry fits the existing rig, uses four original materials and has outward normals',async()=>{
  const model=JSON.parse(text);assert.equal(model.metadata.triangles,3672);assert.equal(model.materials.length,4);
  assert(Buffer.byteLength(text)<1500000);assert(!model.textures&&!model.cameras&&!model.lights);
  let triangles=0;
  for(const geo of model.geometries.vertexData){
    triangles+=geo.indices.length/3;
    for(let i=0;i<geo.indices.length;i+=3){
      const a=B.Vector3.FromArray(geo.positions,geo.indices[i]*3),b=B.Vector3.FromArray(geo.positions,geo.indices[i+1]*3),c=B.Vector3.FromArray(geo.positions,geo.indices[i+2]*3);
      const n=B.Vector3.FromArray(geo.normals,geo.indices[i]*3);
      assert(B.Vector3.Dot(B.Vector3.Cross(b.subtract(a),c.subtract(a)),n)<=1e-7,'Babylon clockwise face normal');
    }
  }
  assert.equal(triangles,3672);
});
test('low quality and overview make no guide asset request',async()=>{
  for(const quality of ['low','high']){
    const f=fixture(quality);try{f.controller.sync();await flush();assert.equal(f.pending.length,0);if(quality==='low'){f.space.view='walk';f.controller.sync();await flush();assert.equal(f.pending.length,0);}}finally{f.dispose();}
  }
});
test('walking appearance retains the movement rig, independent limbs, root visibility and original fallback',async()=>{
  const f=fixture();try{
    const originals=f.avatar.root.getChildMeshes().filter(m=>m!==f.avatar.marker),hidden=originals[0];hidden.isVisible=false;
    f.space.view='walk';f.controller.sync();f.controller.sync();await flush();assert.equal(f.pending.length,1);
    assert(originals.slice(1).every(m=>m.isVisible));const c=await f.finish();assert.equal(f.controller.status().phase,'ready');
    assert(originals.every(m=>!m.isVisible));assert.equal(c.meshes.length,14);
    for(const mesh of c.meshes){assert.equal(mesh.parent,f.avatar[mesh.metadata.rigPart]);assert.equal(mesh.isEnabled(),true);assert.equal(mesh.isPickable,false);assert.equal(mesh.checkCollisions,false);}
    const boot=c.meshes.find(m=>m.metadata.rigPart==='legL'),initial=boot.computeWorldMatrix(true).clone();
    f.avatar.root.position.set(31,2,-17);f.avatar.root.computeWorldMatrix(true);boot.computeWorldMatrix(true);
    assert.notDeepEqual(initial.asArray(),boot.getWorldMatrix().asArray());
    const walking=boot.getWorldMatrix().clone();f.world.animateWalk(f.avatar,.5,3);f.avatar.legL.computeWorldMatrix(true);boot.computeWorldMatrix(true);
    assert.notDeepEqual(walking.asArray(),boot.getWorldMatrix().asArray());
    f.avatar.root.setEnabled(false);assert(c.meshes.every(m=>!m.isEnabled()));f.avatar.root.setEnabled(true);
    f.controller.dispose();assert(originals.slice(1).every(m=>m.isVisible));assert.equal(hidden.isVisible,false);
    assert(c.meshes.every(m=>m.isDisposed()));
  }finally{f.dispose();}
});
test('a failed request preserves the default player instead of retrying forever',async()=>{
  const f=fixture();try{f.space.view='walk';f.controller.sync();await flush();f.pending[0].reject(Error('offline'));await flush();assert.equal(f.controller.status().phase,'failed');f.controller.sync();await flush();assert.equal(f.pending.length,1);assert(f.avatar.body.isVisible);}finally{f.dispose();}
});
test('late loading after player disposal releases all imported meshes',async()=>{
  const f=fixture();try{f.space.view='walk';f.controller.sync();await flush();f.avatar.root.dispose();const c=await f.finish();assert(c.meshes.every(m=>m.isDisposed()));}finally{f.dispose();}
});
