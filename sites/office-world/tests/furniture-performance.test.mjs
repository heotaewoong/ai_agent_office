import {readFile} from 'node:fs/promises';
import {createRequire} from 'node:module';
import assert from 'node:assert/strict';
import {test} from 'node:test';
const B=createRequire(import.meta.url)('../vendor/babylon.min.js');
const source=await readFile(new URL('../app.js',import.meta.url),'utf8');
const start=source.indexOf('    buildDesk('),end=source.indexOf('\n    },',start);

test('furniture batches preserve translated and rotated geometry, picking and mutable screens',()=>{
  const engine=new B.NullEngine(),scene=new B.Scene(engine),materials=new Map(),expected=[];
  let desk,originalVertices=0;
  const scopedB={...B,Mesh:{MergeMeshes(parts,...args){
    const parent=scene.getTransformNodeByName('desk-test-0').computeWorldMatrix(true);
    for(const part of parts){
      const points=part.getVerticesData(B.VertexBuffer.PositionKind),matrix=part.computeWorldMatrix(true).multiply(parent);
      for(let i=0;i<points.length;i+=3)expected.push(B.Vector3.TransformCoordinates(B.Vector3.FromArray(points,i),matrix));
    }
    return B.Mesh.MergeMeshes(parts,...args);
  }}};
  const build=Function('B','return ({'+source.slice(start,end+6)+'}).buildDesk')(scopedB);
  const stage={id:'test',color:'#abcdef',node:new B.TransformNode('stage',scene),desks:[],rotY:.6};
  stage.node.position.set(31,4,-17);stage.node.rotation.y=.6;
  const world={scene,local:(_st,x,y,z)=>B.Vector3.TransformCoordinates(new B.Vector3(x,y,z),stage.node.computeWorldMatrix(true)),
    box(name,w,h,d,hex,opts={}){
      const key=hex+JSON.stringify(opts);
      if(!materials.has(key))materials.set(key,new B.StandardMaterial(key,scene));
      const mesh=B.MeshBuilder.CreateBox(name,{width:w,height:h,depth:d},scene);originalVertices+=mesh.getTotalVertices();mesh.material=materials.get(key);return mesh;
    }};
  try{
    build.call(world,stage,2,-3,.9,0);desk=scene.getTransformNodeByName('desk-test-0');
    assert.equal(desk.getChildMeshes().length,8,'14 original furniture pieces become eight meshes');
    assert.equal(desk.getChildMeshes().reduce((n,m)=>n+m.getTotalVertices(),0),originalVertices,'all box geometry is retained once per desk');
    const screen=stage.desks[0].screen;
    assert.equal(screen.isDisposed(),false);assert.equal(screen.isPickable,false);assert.equal(screen.parent,desk);
    const otherMaterials=desk.getChildMeshes().filter(m=>m!==screen).map(m=>m.material);
    screen.material=new B.StandardMaterial('changed-task-screen',scene);
    assert.deepEqual(desk.getChildMeshes().filter(m=>m!==screen).map(m=>m.material),otherMaterials);
    const actual=[];
    for(const mesh of desk.getChildMeshes().filter(m=>m.name.startsWith('desk-static-'))){
      assert.equal(mesh.metadata.stageId,'test');
      assert.equal(mesh.isPickable,!mesh.name.endsWith('mug'));
      const points=mesh.getVerticesData(B.VertexBuffer.PositionKind),matrix=mesh.computeWorldMatrix(true);
      for(let i=0;i<points.length;i+=3)actual.push(B.Vector3.TransformCoordinates(B.Vector3.FromArray(points,i),matrix));
    }
    assert.equal(actual.length,expected.length);
    for(const p of expected)assert(actual.some(q=>B.Vector3.Distance(p,q)<1e-4),'parent transform must apply exactly once');
    stage.node.dispose();assert.equal(scene.meshes.length,world.deskDetailTemplates.size,'only shared templates survive a room rebuild');
    assert([...world.deskDetailTemplates.values()].every(mesh=>mesh.instances.length===0));
  }finally{scene.dispose();engine.dispose();}
});

test('desks share immutable geometry while room picking, screen state and disposal remain independent',()=>{
  const engine=new B.NullEngine(),scene=new B.Scene(engine),materials=new Map();
  const build=Function('B','return ({'+source.slice(start,end+6)+'}).buildDesk')(B);
  const world={scene,local:(st,x,y,z)=>B.Vector3.TransformCoordinates(new B.Vector3(x,y,z),st.node.computeWorldMatrix(true)),
    box(name,w,h,d,hex,opts={}){
      const key=hex+JSON.stringify(opts);if(!materials.has(key))materials.set(key,new B.StandardMaterial(key,scene));
      const mesh=B.MeshBuilder.CreateBox(name,{width:w,height:h,depth:d},scene);mesh.material=materials.get(key);return mesh;
    }};
  const a={id:'first',color:'#abcdef',node:new B.TransformNode('first',scene),desks:[],rotY:.4},b={id:'second',color:'#fedcba',node:new B.TransformNode('second',scene),desks:[],rotY:-.7};
  a.node.position.set(-12,0,4);a.node.rotation.y=a.rotY;b.node.position.set(25,0,-8);b.node.rotation.y=b.rotY;
  try{
    build.call(world,a,1,0,.6,0);build.call(world,b,-2,1,-.5,0);
    const rootA=scene.getTransformNodeByName('desk-first-0'),rootB=scene.getTransformNodeByName('desk-second-0');
    const rigidA=rootA.getChildMeshes().find(m=>m.name==='desk-static-leg-0'),rigidB=rootB.getChildMeshes().find(m=>m.name==='desk-static-leg-0');
    assert(rigidA instanceof B.InstancedMesh);assert.equal(rigidA.sourceMesh,rigidB.sourceMesh);
    const screenB=b.desks[0].screen,materialB=screenB.material;a.desks[0].screen.material=new B.StandardMaterial('only-first-screen',scene);assert.equal(screenB.material,materialB);
    const top=rootB.getChildMeshes().find(m=>m.name==='desk-top');assert(top instanceof B.Mesh);assert(!(top instanceof B.InstancedMesh));
    top.material=new B.StandardMaterial('room-trim',scene);assert.notEqual(top.material,rootA.getChildMeshes().find(m=>m.name==='desk-top').material);
    const p=world.local(b,-2,3,1),hit=scene.pickWithRay(new B.Ray(p,new B.Vector3(0,-1,0)),m=>m.isPickable&&m.metadata?.stageId==='second');
    assert(hit.hit);assert.equal(hit.pickedMesh.metadata.stageId,'second');
    a.node.dispose();assert.equal(rigidB.isDisposed(),false);assert.equal(rigidB.sourceMesh.isDisposed(),false);
    b.node.dispose();assert([...world.deskDetailTemplates.values()].every(m=>m.instances.length===0));
  }finally{scene.dispose();engine.dispose();}
});
