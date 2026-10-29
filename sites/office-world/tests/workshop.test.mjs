import { readFile } from 'node:fs/promises';
import { createRequire } from 'node:module';
import assert from 'node:assert/strict';
import { test } from 'node:test';
const B = createRequire(import.meta.url)('../vendor/babylon.min.js');
const source = await readFile(new URL('../app.js', import.meta.url), 'utf8');
function method(object, name, globals = {}) {
  const start = source.indexOf('    ' + name + '(', source.indexOf('  const ' + object + ' = {'));
  const end = source.indexOf('\n    },', start);
  assert(start >= 0 && end > start, object + '.' + name + ' must exist');
  return Function(...Object.keys(globals), 'return ({' + source.slice(start, end + 6) + '}).' + name)(...Object.values(globals));
}
function fixture(raw = null, geometry = false) {
  const entries = new Map([['heobrain.expedition.v1', '{"credits":240,"selectedVehicle":"nova"}'], ['heobrain.city-visits.v1', '["arrival"]']]);
  if (raw !== null) entries.set('heobrain.buildings.v1', raw);
  const storage = { failWrite:false, failRead:false, writes:[], getItem(key) { if(this.failRead) throw Error('blocked'); return entries.get(key) ?? null; }, setItem(key, value) { if(this.failWrite) throw Error('quota'); this.writes.push(key); entries.set(key, value); } };
  const space = { stages:[], layer:'office' }, controls = { player:{ pos:new B.Vector3(0, 0, -52) } };
  const world = { officeObstacles:[] };
  let engine, scene, shadows;
  if(geometry) {
    engine = new B.NullEngine({renderWidth:64,renderHeight:64,textureSize:64}); scene = new B.Scene(engine);
    shadows = new B.ShadowGenerator(128,new B.DirectionalLight('sun',new B.Vector3(0,-1,1),scene));
    Object.assign(world, {scene,shadows,matCache:new Map(), architecturePlan:method('world','architecturePlan',{QUALITY:'high'}),
      mat:method('world','mat',{B}),pbr:method('world','pbr',{B,QUALITY:'high'}),buildArchitecture:method('world','buildArchitecture',{B}),
      castShadow:m=>shadows.addShadowCaster(m,false),receiveShadow:m=>{m.receiveShadows=true;} });
  }
  const start=source.indexOf('  const workshop = {'), end=source.indexOf('\n  };',start);
  assert(start>=0 && end>start);
  const workshop=Function('B','world','space','controls','localStorage','return ('+source.slice(source.indexOf('{',start),end+4)+')')(B,world,space,controls,storage);
  workshop.sync=()=>{};
  if(!geometry) workshop.rebuild=()=>{};
  workshop.restore();
  return {workshop,world,space,controls,storage,entries,scene,shadows,dispose(){scene?.dispose();engine?.dispose();}};
}
const building = (id='b1',kind='tower',col=0,row=0,turn=0) => ({id,kind,col,row,turn});
const snapshot = w => JSON.stringify({items:w.items,history:w.history,storedRaw:w.storedRaw,selectedId:w.selectedId});

test('layout validation rejects damaged fields, prototype catalog keys and duplicate identifiers', () => {
  const {workshop:w}=fixture();
  assert.equal(w.validateLayout([building()]),'');
  for(const bad of [null,{},'bad',[null],[{...building(),id:1}],[{...building(),id:'b0'}],[{...building(),id:'b1000000'}],
    [{...building(),kind:'missing'}],[{...building(),kind:'constructor'}],[{...building(),kind:'__proto__'}],
    [{...building(),col:NaN}],[{...building(),col:Infinity}],[{...building(),col:'1'}],[{...building(),row:1.5}],
    [{...building(),turn:-1}],[{...building(),turn:4}],[{...building(),turn:1.5}],[building(),building()]]) {
    assert.notEqual(w.validateLayout(bad),'',JSON.stringify(bad));
  }
});

test('rotating a non-square building swaps its footprint and enforces the whole protected plot', () => {
  const {workshop:w}=fixture(), lab=building('b1','lab',5,3);
  assert.equal(w.validateLayout([lab]),'');
  assert.deepEqual([w.bounds(lab).w,w.bounds(lab).d],[6,4]);
  assert.deepEqual([w.bounds({...lab,turn:1}).w,w.bounds({...lab,turn:1}).d],[4,6]);
  assert.notEqual(w.validateLayout([{...lab,turn:1}]),'');
  for(const item of [{...lab,col:-1},{...lab,row:-1},{...lab,col:8},{...lab,row:5}]) assert.notEqual(w.validateLayout([item]),'');
});

test('overlap is rejected, adjacent footprints fit, and the eight-building limit is enforced', () => {
  const {workshop:w}=fixture();
  assert.notEqual(w.validateLayout([building(),building('b2','tower',1,0)]),'');
  assert.equal(w.validateLayout([building(),building('b2','tower',2,0)]),'');
  const eight=[];for(const row of [0,2]) for(const col of [0,2,4,6]) eight.push(building('b'+(eight.length+1),'tower',col,row));
  assert.equal(w.validateLayout(eight),'');
  assert.notEqual(w.validateLayout([...eight,building('b9','tower',0,4)]),'');
});

test('placement persists a clean versioned layout and preserves existing game and vehicle storage', () => {
  const {workshop:w,storage,entries}=fixture(), untouched=new Map(entries);
  assert.equal(w.applyDraft(),true); assert.equal(w.items.length,1); assert.equal(w.selectedId,'b1');
  const raw=entries.get(w.key),saved=JSON.parse(raw);
  assert.equal(saved.version,1);assert.deepEqual(saved.items,w.items);assert.deepEqual(storage.writes,[w.key]);
  for(const [key,value]of untouched) assert.equal(entries.get(key),value);
  const restored=fixture(raw).workshop;
  assert.deepEqual(restored.items,w.items);assert.equal(restored.storageBlocked,false);assert.deepEqual(restored.history,[]);
  const next=[{...w.items[0],extra:'discard'}];assert.equal(w.persist(next,'b1'),true);next[0].col=7;
  assert.equal(w.items[0].col,1);assert.equal('extra' in w.items[0],false);
});

test('storage failure leaves saved content, layout, selection and undo history unchanged', () => {
  const {workshop:w,storage,entries}=fixture();assert.equal(w.applyDraft(),true);
  const before=snapshot(w),raw=entries.get(w.key);storage.failWrite=true;w.draft.turn=1;
  assert.equal(w.applyDraft(),false);assert.equal(snapshot(w),before);assert.equal(entries.get(w.key),raw);
  storage.failWrite=false;assert.equal(w.applyDraft(),true);assert.equal(w.items[0].turn,1);
});

test('another tab cannot be silently overwritten and reopening restore loads its newer layout', () => {
  const {workshop:w,entries}=fixture();assert.equal(w.applyDraft(),true);const before=snapshot(w);
  const external=JSON.stringify({version:1,items:[building('b7','lab',0,0,1)]});entries.set(w.key,external);
  assert.equal(w.persist([building('b1')]),false);assert.equal(snapshot(w),before);assert.equal(entries.get(w.key),external);
  w.restore();assert.deepEqual(w.items,[building('b7','lab',0,0,1)]);assert.deepEqual(w.history,[]);assert.equal(w.storedRaw,external);
});

test('invalid or future storage remains untouched and blocks destructive replacement', () => {
  const bads=['{','null','[]','x'.repeat(32769),JSON.stringify({version:2,items:[]}),JSON.stringify({version:1,items:[building('b1','constructor')]}),JSON.stringify({version:1,items:[building(),building()]})];
  for(const raw of bads){const {workshop:w,entries}=fixture(raw);assert.deepEqual(w.items,[]);assert.equal(w.storageBlocked,true);
    assert.equal(w.persist([building()]),false);assert.equal(entries.get(w.key),raw);assert.equal(w.history.length,0);}
  const {workshop:w,storage}=fixture();storage.failRead=true;w.restore();assert.equal(w.storageBlocked,true);assert.equal(w.persist([]),false);
});

test('undo restores add, rotation and removal in reverse order without creating more history', () => {
  const {workshop:w,entries}=fixture();const vehicle=entries.get('heobrain.expedition.v1');
  assert.equal(w.applyDraft(),true);const original=w.items.map(i=>({...i}));w.draft.turn=1;assert.equal(w.applyDraft(),true);
  assert.equal(w.remove(),true);assert.deepEqual(w.items,[]);assert.equal(w.history.length,3);
  assert.equal(w.undo(),true);assert.equal(w.items[0].turn,1);assert.equal(w.history.length,2);
  assert.equal(w.undo(),true);assert.deepEqual(w.items,original);assert.equal(w.history.length,1);
  assert.equal(w.undo(),true);assert.deepEqual(w.items,[]);assert.equal(w.history.length,0);assert.equal(w.undo(),false);
  assert.equal(entries.get('heobrain.expedition.v1'),vehicle);assert.deepEqual(JSON.parse(entries.get(w.key)).items,[]);
});

test('a failed undo retains its history and bounded history keeps only twenty changes', () => {
  const {workshop:w,storage}=fixture();assert.equal(w.applyDraft(),true);w.draft.turn=1;assert.equal(w.applyDraft(),true);
  const before=snapshot(w);storage.failWrite=true;assert.equal(w.undo(),false);assert.equal(snapshot(w),before);
  storage.failWrite=false;assert.equal(w.undo(),true);assert.equal(w.items[0].turn,0);
  for(let i=0;i<25;i++)assert.equal(w.persist([building('b1','tower',0,0,i%4)]),true);
  assert.equal(w.history.length,20);for(let i=0;i<20;i++)assert.equal(w.undo(),true);assert.equal(w.undo(),false);
});

test('existing circular facilities, radial roads and the office player are protected from placement', () => {
  const {workshop:w,world,controls,space}=fixture(), item=building('b1','tower',1,1),b=w.bounds(item),x=(b.minX+b.maxX)/2,z=(b.minZ+b.maxZ)/2;
  assert.equal(w.obstruction(item),'');world.officeObstacles=[{x,z,r:1}];assert.notEqual(w.obstruction(item),'');
  world.officeObstacles=[];controls.player.pos.set(x,0,z);assert.notEqual(w.obstruction(item),'');space.layer='meadow';assert.equal(w.obstruction(item),'');
  controls.player.pos.set(0,0,-52);space.layer='office';space.stages=[{angle:Math.atan2(z,x)}];assert.notEqual(w.obstruction(item),'');
});

test('walking collision uses only displayed buildings with explicit player clearance', () => {
  const {workshop:w}=fixture(),item=building(),b=w.bounds(item);w.items=[item];w.visibleItems=[];
  assert.equal(w.collides({x:b.minX+1,z:b.minZ+1}),false);w.visibleItems=[item];
  assert.equal(w.collides({x:b.minX+1,z:b.minZ+1}),true);assert.equal(w.collides({x:b.minX-.39,z:b.minZ+1}),true);
  assert.equal(w.collides({x:b.minX-.41,z:b.minZ+1}),false);assert.equal(w.collides({x:b.minX-.1,z:b.minZ+1},0),false);
});

test('real building meshes fit all rotated footprints and rebuilds dispose preview geometry without resource growth', () => {
  const f=fixture(null,true),w=f.workshop;w.ready=true;
  try{
    for(const kind of Object.keys(w.catalog))for(let turn=0;turn<4;turn++){
      const item=building('b1',kind,1,1,turn),node=w.model(item,null),b=w.bounds(item),spec=w.catalog[kind];
      assert.equal(node.getChildMeshes().length,4);node.computeWorldMatrix(true);
      for(const mesh of node.getChildMeshes()){
        mesh.computeWorldMatrix(true);const bounds=mesh.getBoundingInfo().boundingBox;
        for(const v of bounds.vectorsWorld){assert(v.x>=b.minX-1e-5 && v.x<=b.maxX+1e-5);assert(v.z>=b.minZ-1e-5 && v.z<=b.maxZ+1e-5);assert(v.y>=-1e-5 && v.y<=spec.h+1e-5);}
        assert.equal(mesh.isPickable,false);
      }
      node.dispose();
    }
    w.items=[building('b1','tower',0,0),building('b2','lab',2,0),building('b3','port',6,0)];w.opened=true;
    w.rebuild();w.draft={kind:'tower',col:0,row:3,turn:0};w.updatePreview();w.draft.col=7;w.updatePreview();
    const counts=()=>[f.scene.meshes.length,f.scene.transformNodes.length,f.scene.materials.length,f.scene.textures.length,f.shadows.getShadowMap().renderList.length];
    const initial=counts(), saved=JSON.stringify(w.items);assert.equal(w.visibleItems.length,3);assert(w.preview);
    for(let i=0;i<3;i++){w.rebuild();assert.deepEqual(counts(),initial);assert.equal(JSON.stringify(w.items),saved);}
    assert(f.shadows.getShadowMap().renderList.every(mesh=>!mesh.isDisposed()));
    w.clear();assert.equal(f.scene.meshes.length,0);assert.equal(f.scene.transformNodes.length,0);assert.equal(f.shadows.getShadowMap().renderList.length,0);
  }finally{f.dispose();}
});


test('unchanged selection stays solid, a pending rotation shows one ghost, and closing restores the saved model', () => {
  const f=fixture(null,true),w=f.workshop;w.ready=true;w.opened=true;
  try{
    const item=building('b1','lab',1,1);w.items=[item];w.selectedId=item.id;
    w.draft={kind:item.kind,col:item.col,row:item.row,turn:item.turn};w.rebuild();
    const solid=w.models.get(item.id),meshCount=f.scene.meshes.length;
    assert.equal(w.draftMatchesSelection(),true);assert.equal(w.preview,null);assert.equal(solid.isEnabled(),true);
    w.updatePreview();assert.equal(w.preview,null);assert.equal(f.scene.meshes.length,meshCount);
    w.draft.turn=1;w.updatePreview();
    const ghost=w.preview;assert(ghost);assert.equal(w.draftMatchesSelection(),false);assert.equal(solid.isEnabled(),false);
    assert.equal(ghost.getChildMeshes().length,4);assert.equal(f.scene.meshes.length,meshCount+4);
    assert.deepEqual(w.items,[item]);
    const elements={'build-panel':{hidden:false},'btn-build':{pressed:null,setAttribute(k,v){assert.equal(k,'aria-pressed');this.pressed=v;},focus(){this.focused=true;}}};
    const classes=new Set(['building-view']);let attached=0;
    f.world.canvas={};f.controls.keys=new Set(['w']);f.controls.dragging=true;
    f.controls.overview={attachControl(canvas,pointer){assert.equal(canvas,f.world.canvas);assert.equal(pointer,true);attached++;}};
    w.setOpen=method('workshop','setOpen',{B,world:f.world,space:f.space,controls:f.controls,localStorage:f.storage,$:id=>elements[id],document:{body:{classList:{remove:name=>classes.delete(name)}}}});
    w.setOpen(false);
    assert.equal(ghost.isDisposed(),true);assert.equal(w.preview,null);assert.equal(solid.isEnabled(),true);
    assert.equal(f.scene.meshes.length,meshCount);assert.equal(w.opened,false);assert.equal(f.space.buildingOpen,false);
    assert.equal(f.controls.keys.size,0);assert.equal(f.controls.dragging,false);assert.equal(attached,1);assert.equal(classes.has('building-view'),false);
    assert.equal(elements['build-panel'].hidden,true);assert.equal(elements['btn-build'].pressed,'false');assert.equal(elements['btn-build'].focused,true);
    if(w.pickPlane)assert.equal(w.pickPlane.isPickable,false);
    assert.deepEqual(w.items,[item]);
  }finally{f.dispose();}
});
