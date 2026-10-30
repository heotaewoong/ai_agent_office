import { readFile } from 'node:fs/promises';
import { createRequire } from 'node:module';
import assert from 'node:assert/strict';
import { test } from 'node:test';
const B=createRequire(import.meta.url)('../vendor/babylon.min.js');
const source=await readFile(new URL('../app.js',import.meta.url),'utf8');
function method(name,globals={}){
  const start=source.indexOf('    '+name+'(',source.indexOf('  const world = {'));
  const end=source.indexOf('\n    },',start);
  assert(start>=0&&end>start,'world.'+name+' exists');
  return Function(...Object.keys(globals),'return ({'+source.slice(start,end+6)+'}).'+name)(...Object.values(globals));
}
function fixture(quality='high'){
  const engine=new B.NullEngine({renderWidth:64,renderHeight:64,textureSize:64}),scene=new B.Scene(engine);
  const light=new B.DirectionalLight('test-sun',new B.Vector3(0,-1,1),scene),shadows=new B.ShadowGenerator(128,light);
  const world={scene,matCache:new Map(),mat:method('mat',{B}),pbr:method('pbr',{B,QUALITY:quality}),box:method('box',{B}),
    buildAvatar:method('buildAvatar',{B,QUALITY:quality}),setPose:method('setPose'),animateWalk:method('animateWalk'),
    castShadow:mesh=>shadows.addShadowCaster(mesh,false),receiveShadow:mesh=>{mesh.receiveShadows=true;}};
  return {world,scene,shadows,create:()=>world.buildAvatar('pilot','#f5d6b8','#4f8df7','#7fe3ff'),dispose:()=>{scene.dispose();engine.dispose();}};
}
const detail=(pivot,suffix)=>pivot.getChildMeshes().find(mesh=>mesh.name.endsWith(suffix+'-detail'));
const near=(actual,expected)=>assert(Math.abs(actual-expected)<1e-5,actual+' ~= '+expected);

for(const quality of ['low','high'])test('avatar '+quality+' keeps the rig and material contract with a bounded detail budget',()=>{
  const f=fixture(quality);try{
    const av=f.create();
    assert.deepEqual(Object.keys(av).sort(),['root','legL','legR','armL','armR','head','body','marker','hipY','phase'].sort());
    assert.equal(av.hipY,.78);assert(av.phase>=0&&av.phase<6);
    assert(av.body.material instanceof B.StandardMaterial);assert(av.head.material instanceof B.StandardMaterial);
    assert(av.marker.material instanceof B.StandardMaterial);assert.equal(av.marker.material.disableLighting,true);
    for(const key of ['legL','legR','armL','armR'])assert.equal(av[key].parent,av.root);
    const meshes=av.root.getChildMeshes();assert(meshes.every(mesh=>!mesh.isPickable));
    assert(meshes.length<=(quality==='high'?21:19));
    assert.equal(f.scene.meshes.length,meshes.length+f.world.avatarDetailTemplates.size,'only bounded hidden templates remain beside avatar instances');
    for(const template of f.world.avatarDetailTemplates.values()){
      assert.equal(template.parent,null);assert.equal(template.isVisible,false);
      assert.equal(template.isPickable,false);
    }
    const casters=f.shadows.getShadowMap().renderList;
    assert(!casters.includes(av.marker));assert(!casters.some(mesh=>mesh.material.disableLighting));
    av.body.material.emissiveColor=new B.Color3(.1,.2,.3);
    assert(av.body.material.emissiveColor.equals(new B.Color3(.1,.2,.3)));
    assert.notEqual(av.body.material,av.marker.material,'status changes remain separate from clothing');
    assert(detail(av.root,'hair-cap'));assert(detail(av.root,quality==='high'?'eye-white':'eye'));
    av.root.computeWorldMatrix(true);
    const headFace=av.head.position.z+.58/2;
    const face=detail(av.root,quality==='high'?'eye-white':'eye');face.computeWorldMatrix(true);
    const eyeVertices=face.getVerticesData(B.VertexBuffer.PositionKind),eyeDepths=[];
    for(let i=0;i<eyeVertices.length;i+=3)if(eyeVertices[i+1]>1.84&&eyeVertices[i+1]<1.96&&eyeVertices[i+2]>0)eyeDepths.push(eyeVertices[i+2]);
    assert(eyeDepths.length>=16);assert(Math.min(...eyeDepths)>headFace,'eye surface is separated from the head face');
  }finally{f.dispose();}
});

test('gloves and boots follow animated pivots and retain forward toes and a ground-level sole',()=>{
  const f=fixture();try{
    const av=f.create();
    for(const leg of [av.legL,av.legR]){
      const boot=detail(leg,'boot');assert(boot);assert.equal(boot.parent,leg);
      boot.computeWorldMatrix(true);const box=boot.getBoundingInfo().boundingBox;
      near(box.minimumWorld.y,0);assert(box.maximumWorld.z>.23,'boot toe extends forward along +Z');
    }
    const glove=detail(av.armL,'glove');assert(glove);glove.computeWorldMatrix(true);
    const original=glove.getBoundingInfo().boundingBox.centerWorld.clone();
    av.phase=0;f.world.animateWalk(av,Math.PI/18,2);glove.computeWorldMatrix(true);
    assert(B.Vector3.Distance(original,glove.getBoundingInfo().boundingBox.centerWorld)>.05);
    f.world.setPose(av,'sit');assert.equal(av.legL.rotation.x,-Math.PI/2);assert.equal(av.armL.rotation.x,-.9);
    f.world.setPose(av,'stand');for(const key of ['armL','armR','legL','legR'])assert.equal(av[key].rotation.x,0);
  }finally{f.dispose();}
});

test('merged face and equipment inherit root rotation and translation exactly once',()=>{
  const f=fixture();try{
    const av=f.create(),hair=detail(av.root,'hair-cap');hair.computeWorldMatrix(true);
    const local=B.Vector3.FromArray(hair.getVerticesData(B.VertexBuffer.PositionKind),0);
    av.root.position.set(24,3,-17);av.root.rotation.y=.73;av.root.computeWorldMatrix(true);hair.computeWorldMatrix(true);
    const actual=B.Vector3.TransformCoordinates(local,hair.getWorldMatrix());
    const expected=B.Vector3.TransformCoordinates(local,av.root.getWorldMatrix());
    assert(B.Vector3.Distance(actual,expected)<1e-5);
    av.root.position.x+=7;av.root.computeWorldMatrix(true);hair.computeWorldMatrix(true);
    const moved=B.Vector3.TransformCoordinates(local,hair.getWorldMatrix());near(moved.x-actual.x,7);near(moved.y,actual.y);near(moved.z,actual.z);
  }finally{f.dispose();}
});

test('rebuilding avatars releases merged geometry and reuses cached materials and surface textures',()=>{
  const f=fixture();try{
    let counts;
    for(let i=0;i<4;i++){
      const av=f.create(),current={materials:f.scene.materials.length,textures:f.scene.textures.length};
      if(counts)assert.deepEqual(current,counts);else counts=current;
      assert.equal(f.world.surfaceTextures.size,1,'one shared metal texture');
      av.root.dispose();assert.equal(f.scene.meshes.length,f.world.avatarDetailTemplates.size);assert.equal(f.scene.transformNodes.length,0);
      assert([...f.world.avatarDetailTemplates.values()].every(mesh=>mesh.instances.length===0));
      assert.equal(f.shadows.getShadowMap().renderList.length,0,'no disposed avatar remains a caster');
    }
  }finally{f.dispose();}
});

test('shared detail instances survive disposal of another avatar and keep independent poses',()=>{
  const f=fixture();try{
    const first=f.create(),second=f.create(),left=detail(first.armL,'glove'),other=detail(second.armL,'glove');
    assert(left instanceof B.InstancedMesh);assert.equal(left.sourceMesh,other.sourceMesh);
    assert.equal(left.sourceMesh.receiveShadows,true);
    first.armL.rotation.x=.8;second.armL.rotation.x=-.3;
    assert.notDeepEqual(left.computeWorldMatrix(true).asArray(),other.computeWorldMatrix(true).asArray());
    const template=other.sourceMesh,count=f.world.avatarDetailTemplates.size;
    first.root.dispose();assert.equal(other.isDisposed(),false);assert.equal(template.isDisposed(),false);
    second.root.dispose();assert.equal(f.world.avatarDetailTemplates.size,count);
    assert.equal(template.instances.length,0);
  }finally{f.dispose();}
});
