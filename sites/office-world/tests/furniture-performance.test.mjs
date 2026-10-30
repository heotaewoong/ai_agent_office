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
    assert.equal(scene.meshes.reduce((n,m)=>n+m.getTotalVertices(),0),originalVertices,'all box geometry is retained');
    const screen=stage.desks[0].screen;
    assert.equal(screen.isDisposed(),false);assert.equal(screen.isPickable,false);assert.equal(screen.parent,desk);
    const otherMaterials=desk.getChildMeshes().filter(m=>m!==screen).map(m=>m.material);
    screen.material=new B.StandardMaterial('changed-task-screen',scene);
    assert.deepEqual(desk.getChildMeshes().filter(m=>m!==screen).map(m=>m.material),otherMaterials);
    const actual=[];
    for(const mesh of desk.getChildMeshes().filter(m=>m.name.startsWith('desk-static-'))){
      assert.equal(mesh.metadata.stageId,'test');assert.equal(mesh.isPickable,true);
      const points=mesh.getVerticesData(B.VertexBuffer.PositionKind),matrix=mesh.computeWorldMatrix(true);
      for(let i=0;i<points.length;i+=3)actual.push(B.Vector3.TransformCoordinates(B.Vector3.FromArray(points,i),matrix));
    }
    assert.equal(actual.length,expected.length);
    for(const p of expected)assert(actual.some(q=>B.Vector3.Distance(p,q)<1e-4),'parent transform must apply exactly once');
    stage.node.dispose();assert.equal(scene.meshes.length,0,'rebuild must not leak original furniture');
  }finally{scene.dispose();engine.dispose();}
});
