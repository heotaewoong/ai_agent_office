import { readFile } from 'node:fs/promises';
import assert from 'node:assert/strict';
import { test } from 'node:test';
const source = await readFile(new URL('../app.js', import.meta.url), 'utf8');
test('overview return releases movement and closes obstructing work panels', () => {
 const start=source.indexOf('    exitSpace() {'), end=source.indexOf('\n    },',start);
 const calls=[];
 const exit=Function('hud','workshop','workbench','world','return ({'+source.slice(start,end+6)+'}).exitSpace')(
 {closePanel:()=>calls.push('panel')},{opened:true,setOpen:v=>calls.push(['build',v])},
 {setRoster:v=>calls.push(['roster',v])},{syncRendering:()=>calls.push('render')});
 const controls={keys:new Set(['w']),dragging:true,focused:'team',setVehicleSpeed:v=>calls.push(['speed',v]),setView:v=>calls.push(['view',v]),resetOverview:()=>calls.push('reset')};
 exit.call(controls);
 assert.equal(controls.keys.size,0); assert.equal(controls.dragging,false); assert.equal(controls.focused,null);
 assert.ok(calls.some(c=>Array.isArray(c)&&c[0]==='speed'&&c[1]===0));
 assert.ok(calls.some(c=>Array.isArray(c)&&c[0]==='roster'&&c[1]===false));
 assert.equal(calls.at(-1),'render');
});
