import { test } from 'node:test';
import assert from 'node:assert/strict';
import { readFile } from 'node:fs/promises';
import { createRequire } from 'node:module';
import { createArrivalDetail } from '../arrival-detail.js';
function fixture(quality='high') {
 const mesh=()=>({enabled:true,setEnabled(v){this.enabled=v},isDisposed:()=>false,getTotalVertices:()=>3,getTotalIndices:()=>3807,position:{z:0},computeWorldMatrix(){},freezeWorldMatrix(){}});
 const base=[mesh(),mesh(),mesh(),mesh()],details=[mesh(),mesh(),mesh(),mesh()];
 const observers=new Set();let resolve,reject,loads=0,disposed=0;
 const asset={meshes:details,addAllToScene(){},dispose(){disposed++}};
 const scene={activeCamera:{globalPosition:{x:0,y:3.5,z:-53}},onBeforeRenderObservable:{add:f=>(observers.add(f),f),remove:f=>observers.delete(f)},onDisposeObservable:{addOnce(){}}};
 const world={scene,arrivalArchitecture:{meshes:base},castShadow(){},receiveShadow(){}};
 const space={layer:'office'};
 const controller=createArrivalDetail({world,space,quality,loadAsset:()=>{loads++;return new Promise((a,b)=>{resolve=a;reject=b})}});
 return {controller,world,space,base,details,asset,observers,get loads(){return loads},get disposed(){return disposed},resolve:()=>resolve(asset),reject:()=>reject(Error('offline'))};
}
const flush=async()=>{for(let i=0;i<5;i++)await Promise.resolve()};
test('low quality has no asset request or render observer',async()=>{const f=fixture('low');f.controller.sync();await flush();assert.equal(f.loads,0);assert.equal(f.observers.size,0);assert(f.base.every(m=>m.enabled))});
test('base stays visible while loading; one asset request despite repeated proximity',async()=>{const f=fixture();f.controller.sync();f.controller.sync();await flush();assert.equal(f.loads,1);assert(f.base.every(m=>m.enabled));f.resolve();await flush();assert(f.details.every(m=>m.enabled));assert(f.base.every(m=>!m.enabled));f.controller.dispose()});
test('distance hysteresis and leaving office restore base; returning reuses asset',async()=>{const f=fixture();f.controller.sync();await flush();f.resolve();await flush();f.world.scene.activeCamera.globalPosition.x=45;f.controller.sync();assert(f.controller.status().active);f.world.scene.activeCamera.globalPosition.x=53;f.controller.sync();assert(!f.controller.status().active);f.world.scene.activeCamera.globalPosition.x=40;f.controller.sync();assert(!f.controller.status().active);f.world.scene.activeCamera.globalPosition.x=0;f.controller.sync();assert(f.controller.status().active);f.space.layer='meadow';f.controller.sync();assert(f.base.every(m=>m.enabled));assert.equal(f.loads,1);f.controller.dispose()});
test('moving away before download completes never hides the original',async()=>{const f=fixture();f.controller.sync();await flush();f.space.layer='meadow';f.resolve();await flush();assert(!f.controller.status().active);assert(f.base.every(m=>m.enabled));f.controller.dispose()});
test('failed download keeps original and does not retry every frame',async()=>{const f=fixture();f.controller.sync();await flush();f.reject();await flush();f.controller.sync();await flush();assert.equal(f.loads,1);assert.equal(f.controller.status().phase,'failed');assert(f.base.every(m=>m.enabled));f.controller.dispose()});
test('late completion after disposal releases assets without showing detail',async()=>{const f=fixture();f.controller.sync();await flush();f.controller.dispose();f.resolve();await flush();assert.equal(f.disposed,1);assert.equal(f.observers.size,0);assert(f.base.every(m=>m.enabled))});
test('new base created by world rebuild follows active detail',async()=>{const f=fixture();f.controller.sync();await flush();f.resolve();await flush();f.world.arrivalArchitecture={meshes:[{enabled:true,isDisposed:()=>false,setEnabled(v){this.enabled=v}}]};f.controller.sync();assert(!f.world.arrivalArchitecture.meshes[0].enabled);f.controller.dispose()});
test('native Blender derivative uses existing plugin, four materials and exact origin',async()=>{
 const B=createRequire(import.meta.url)('../vendor/babylon.min.js');const engine=new B.NullEngine(),scene=new B.Scene(engine);
 try{const text=await readFile(new URL('../assets/arrival-detail-v2.json',import.meta.url),'utf8');const json=JSON.parse(text);assert.equal(json.metadata.sourceSha256,'4eb3370839e30e33c637f01ef490f4d45136127ff6adff1d45b847fb9212ece6');
 const c=await B.SceneLoader.LoadAssetContainerAsync('','data:'+text,scene,null,'.babylon');const meshes=c.meshes.filter(m=>m.getTotalVertices());assert.equal(meshes.length,4);assert.equal(c.materials.length,4);assert.equal(c.textures.length,0);assert.equal(c.lights.length+c.cameras.length,0);assert.equal(meshes.reduce((n,m)=>n+m.getTotalIndices()/3,0),5076);
 const lo=new B.Vector3(Infinity,Infinity,Infinity),hi=new B.Vector3(-Infinity,-Infinity,-Infinity);for(const m of meshes){m.computeWorldMatrix(true);lo.minimizeInPlace(m.getBoundingInfo().boundingBox.minimumWorld);hi.maximizeInPlace(m.getBoundingInfo().boundingBox.maximumWorld)}assert(B.Vector3.Distance(lo,new B.Vector3(-7.5,0,-3.11))<.0001);assert(B.Vector3.Distance(hi,new B.Vector3(7.5,7.43,3))<.0001);c.dispose();}finally{scene.dispose();engine.dispose()}
});

test('deferred module waits for DOMContentLoaded when scene is not initialized yet',async()=>{
 const {runInNewContext}=await import('node:vm');const code=(await readFile(new URL('../arrival-detail.js',import.meta.url),'utf8')).replaceAll('export function','function').replace('import.meta.url',"'http://localhost/arrival-detail.js'");
 const callbacks=new Map(),doc={readyState:'interactive',addEventListener:(event,callback)=>callbacks.set(event,callback)},win={__officeWorld:{world:{},quality:'high'}};
 runInNewContext(code,{document:doc,window:win,fetch(){},performance:{now:()=>0},AbortSignal,URL});assert(callbacks.has('DOMContentLoaded'));assert(!win.__officeWorld.world.arrivalDetail);
 const f=fixture();win.__officeWorld={world:f.world,space:f.space,quality:'high'};callbacks.get('DOMContentLoaded')();assert(win.__officeWorld.world.arrivalDetail);win.__officeWorld.world.arrivalDetail.dispose();f.controller.dispose();
});
