import {readFile} from 'node:fs/promises';
import assert from 'node:assert/strict';
import {test} from 'node:test';

const source=await readFile(new URL('../app.js',import.meta.url),'utf8');
const start=source.indexOf('    tick() {',source.indexOf('    hideAgentCard()'));
const end=source.indexOf('\n    drawMinimap()',start);

function fixture({focused=null,walk=false}={}) {
  const events=[];
  const card=id=>({hidden:false,
    get offsetWidth(){events.push(`read:${id}`);return 100;},
    get offsetHeight(){events.push(`read:${id}`);return 30;},
    style:new Proxy({}, {set(target,key,value){events.push(`write:${id}`);target[key]=value;return true;}})});
  const pos=(x,y,z)=>({x,y,z,add(v){return pos(x+v.x,y+v.y,z+v.z);}});
  const stages=[{id:'a',pos:pos(10,0,0)},{id:'b',pos:pos(200,0,0)}];
  const space={stages,agents:[],layer:'office',view:walk?'walk':'overview'};
  const B={Vector3:class{constructor(x,y,z){Object.assign(this,{x,y,z});}static Distance(a,b){return Math.hypot(a.x-b.x,a.y-b.y,a.z-b.z);}}};
  const controls={focused,player:{pos:pos(0,0,0)}};
  const world={canvas:{clientWidth:400,clientHeight:300},toLocal:()=>({x:100,z:100})};
  const tick=Function('space','controls','world','B','isPhone','$','performance',`return ({${source.slice(start,end)}}).tick`)(space,controls,world,B,()=>false,()=>({getBoundingClientRect:()=>({bottom:20})}),{now:()=>0});
  const hud={miniT:0,cards:new Map(stages.map(s=>[s.id,card(s.id)])),brainCard:{style:{}},agentCard:{hidden:false},project:p=>({x:p.x,y:40,visible:true}),drawMinimap(){throw Error('not due');}};
  return {events,hud,run:()=>tick.call(hud)};
}

test('all visible stage-card dimensions are read before writing any card position',()=>{
  const f=fixture();f.run();
  const firstWrite=f.events.findIndex(e=>e.startsWith('write:'));
  const lastRead=f.events.findLastIndex(e=>e.startsWith('read:'));
  assert(firstWrite>lastRead,'interleaving dimensions and positions can force a layout for each card');
  assert.equal(f.hud.cards.get('a').style.left,'58px');
  assert.equal(f.hud.cards.get('a').style.top,'62px');
  assert.equal(f.hud.cards.get('b').style.left,'200px');
});

test('focused-out cards stay hidden and are not measured',()=>{
  const f=fixture({focused:'b'});f.run();
  assert.equal(f.hud.cards.get('a').hidden,true);
  assert.equal(f.hud.cards.get('b').hidden,false);
  assert(!f.events.includes('read:a'));
});
