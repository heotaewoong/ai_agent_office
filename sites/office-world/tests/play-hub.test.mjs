import {readFile} from 'node:fs/promises';
import assert from 'node:assert/strict';
import {test} from 'node:test';
import {installPlayHub} from '../play-hub.js';
const source=await readFile(new URL('../app.js',import.meta.url),'utf8');
const hubSource=await readFile(new URL('../play-hub.js',import.meta.url),'utf8');

test('an incomplete game UI stays untouched rather than hiding existing controls',()=>{
  assert.equal(installPlayHub({querySelector:()=>null},()=>undefined),null);
});

test('failed boarding keeps its message visible; successful boarding focuses the world',()=>{
  const start=hubSource.indexOf("  doc.addEventListener('click', event => {");
  const end=hubSource.indexOf('\n  });',start);
  const body=hubSource.slice(hubSource.indexOf('{',start)+1,end);
  for(const speed of [0,24]){
    const calls=[],canvas={focus:options=>{assert.equal(options.preventScroll,true);calls.push('focus-world');}};
    const onClick=Function('opened','office','setOpen','doc','return event=>{'+body+'}')(true,
      ()=>({space:{view:'walk'},controls:{vehicleSpeed:speed}}),value=>calls.push(value),{getElementById:()=>canvas});
    onClick({target:{closest:()=>({matches:()=>false})}});
    assert.deepEqual(calls,speed?[false,'focus-world']:[]);
    if(speed)assert.equal(canvas.tabIndex,0);
  }
});

test('opening the play drawer blocks movement and still releases previously held keys',()=>{
  const start=source.indexOf('    onKey('),end=source.indexOf('\n    },',start);
  const space={playHubOpen:true,view:'walk'};
  const handler=Function('space','return ({'+source.slice(start,end+6)+'}).onKey')(space);
  const controls={keys:new Set(['w'])};
  handler.call(controls,{key:'w'},false);
  assert.equal(controls.keys.size,0,'keyup must release a key even with the drawer open');
  for(const key of ['w','a','s','d','m','e','r','Escape'])handler.call(controls,{key},true);
  assert.equal(controls.keys.size,0,'no movement or world action is queued behind the drawer');
});
