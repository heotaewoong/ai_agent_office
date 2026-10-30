import {readFile} from 'node:fs/promises';
import assert from 'node:assert/strict';
import {test} from 'node:test';
import {installPlayHub} from '../play-hub.js';
const source=await readFile(new URL('../app.js',import.meta.url),'utf8');

test('an incomplete game UI stays untouched rather than hiding existing controls',()=>{
  assert.equal(installPlayHub({querySelector:()=>null},()=>undefined),null);
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
