import {test} from 'node:test';
import assert from 'node:assert/strict';
import {readFile} from 'node:fs/promises';
import {createRequire} from 'node:module';
const B=createRequire(import.meta.url)('../vendor/babylon.min.js');
const source=await readFile(new URL('../app.js',import.meta.url),'utf8');
const begin=source.indexOf('    pathDistance('),end=source.indexOf('\n    },',begin);
function method(stages){return Function('B','space','return ({'+source.slice(begin,end+6)+'}).pathDistance')(B,{stages});}
const old=(stages,v)=>{let best=Infinity;for(const st of stages){const b=st.bridge,ab=b.end.subtract(b.start),ap=v.subtract(b.start);const t=Math.max(0,Math.min(1,B.Vector3.Dot(ap,ab)/ab.lengthSquared()));const c=b.start.add(ab.scale(t));best=Math.min(best,Math.hypot(v.x-c.x,v.z-c.z));}return best;};
const stages=[0,1,2,3,4].map(i=>{const a=-Math.PI/2+i*Math.PI*2/5;return {bridge:{start:new B.Vector3(Math.cos(a)*18,0,Math.sin(a)*18),end:new B.Vector3(Math.cos(a)*37,0,Math.sin(a)*37)}};});
test('allocation-free path distance is exact on every deck cell and sloped endpoints',()=>{
 const fn=method(stages);for(let x=-68;x<=68;x++)for(let z=-68;z<=68;z++){const v=new B.Vector3(x+.5,0,z+.5);assert.equal(fn(v),old(stages,v));}
 const slope=[{bridge:{start:new B.Vector3(-3,2,5),end:new B.Vector3(9,-7,11)}}];const f=method(slope);for(let i=0;i<100;i++){const v=new B.Vector3(Math.sin(i)*40,i/7-3,Math.cos(i)*32);assert.equal(f(v),old(slope,v));}
 assert.equal(method([])(new B.Vector3()),Infinity);
});
test('distance query reads coordinates without allocating temporary vectors',()=>{
 const trap=()=>{throw Error('Temporary Vector3 operation');};const point={x:3,y:0,z:4,subtract:trap};const bridge={start:{x:0,y:0,z:0,add:trap},end:{x:10,y:0,z:0,subtract:trap}};
 assert.equal(method([{bridge}])(point),4);
});
