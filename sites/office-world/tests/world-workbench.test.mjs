import { readFile } from 'node:fs/promises';
import assert from 'node:assert/strict';
import { test } from 'node:test';
const source = await readFile(new URL('../app.js', import.meta.url), 'utf8');
function method(object, name, globals = {}) {
  const start = source.indexOf('    ' + name + '(', source.indexOf('  const ' + object + ' = {'));
  const end = source.indexOf('\n    },', start);
  assert(start >= 0 && end > start);
  return Function(...Object.keys(globals), 'return ({' + source.slice(start, end + 6) + '}).' + name)(...Object.values(globals));
}

test('low quality bounds render density while high quality retains a two-pixel cap', () => {
  const low = method('world', 'renderScale', { QUALITY: 'low' });
  const high = method('world', 'renderScale', { QUALITY: 'high' });
  for (const dpr of [1, 2, 3, NaN, Infinity, -1, undefined]) assert.equal(low(dpr), 1);
  assert.equal(high(1.5), 1 / 1.5); assert.equal(high(3), .5); assert.equal(high(NaN), 1);
});

test('render suspension handles list view, result gallery and hidden tabs without duplicate loops', () => {
  const document = { hidden: false }, space = { rosterOpen: false, resultsOpen: false }, calls = [];
  const sync = method('world', 'syncRendering', { document, space });
  const frame = () => {};
  const world = { renderFrame: frame, renderPaused: true, engine: {
    resize: () => calls.push('resize'), runRenderLoop: fn => { assert.equal(fn, frame); calls.push('run'); },
    stopRenderLoop: fn => { assert.equal(fn, frame); calls.push('stop'); },
  } };
  sync.call(world); sync.call(world);
  space.rosterOpen = true; sync.call(world);
  document.hidden = true; sync.call(world); space.rosterOpen = false; sync.call(world);
  assert.deepEqual(calls, ['resize', 'run', 'stop']);
  document.hidden = false; sync.call(world); sync.call(world);
  assert.deepEqual(calls, ['resize', 'run', 'stop', 'resize', 'run']);
  space.resultsOpen = true; sync.call(world); sync.call(world);
  assert.deepEqual(calls, ['resize', 'run', 'stop', 'resize', 'run', 'stop']);
  space.rosterOpen = true; space.resultsOpen = false; sync.call(world);
  assert.deepEqual(calls, ['resize', 'run', 'stop', 'resize', 'run', 'stop']);
  space.rosterOpen = false; sync.call(world); sync.call(world);
  assert.deepEqual(calls, ['resize', 'run', 'stop', 'resize', 'run', 'stop', 'resize', 'run']);
});

test('attention filtering is explicit and sorting does not mutate source observations', () => {
  const filter = method('workbench', 'filteredAgents');
  const agents = [ { id:'a',name:'작가',status:'idle',task:'원고' }, { id:'b',name:'검수',status:'waiting',task:'원고 검토' }, { id:'c',name:'도구',status:'error',task:'연결 실패' }, { id:'d',name:'미확인',status:'unknown',task:'원고' } ];
  assert.deepEqual(filter(agents, '', true).map(a => a.id), ['c','d','b']);
  assert.deepEqual(filter(agents, ' 원고 ', false).map(a => a.id), ['d','b','a']);
  assert.deepEqual(agents.map(a => a.id), ['a','b','c','d']);
  const next = method('workbench', 'nextAttentionId');
  const ctx = { filteredAgents: filter };
  assert.equal(next.call(ctx, agents, null), 'c'); assert.equal(next.call(ctx, agents, 'c'), 'd');
  assert.equal(next.call(ctx, agents, 'd'), 'b'); assert.equal(next.call(ctx, agents, 'b'), 'c');
  assert.equal(next.call(ctx, [agents[3]], null), 'd');
});

test('unknown provider status is never silently normalized to idle', () => {
  const normalize = method('data', 'normalize', { PALETTE: ['#123456'] });
  const d = normalize({ stages:[{id:'s'}], agents:[{id:'a',stageId:'s',status:'unexpected'}, {id:'b',stageId:'s',status:'waiting'}] });
  assert.equal(d.agents[0].status, 'unknown'); assert.equal(d.agents[1].status, 'waiting');
});

test('physics stays per-frame while HUD updates are bounded and running markers stay visible', () => {
  let physics = 0, hudUpdates = 0;
  const space = { view:'overview', agents:[{status:'running',av:{marker:{isVisible:false}}}] };
  const tick = method('world', 'tick', { space, REDUCED:true, controls:{tick(){physics++},overview:{radius:100}}, hud:{tick(){hudUpdates++}}, document:{body:{classList:{toggle(){}}}} });
  const world = { engine:{getDeltaTime:()=>1000/60},time:0,stepTraffic(){} };
  for(let i=0;i<60;i++) { tick.call(world); assert.equal(space.agents[0].av.marker.isVisible,true); }
  assert.equal(physics,60); assert(hudUpdates>=12 && hudUpdates<=15);
});


test('sample fallback and stale real observations keep different source labels', () => {
  const label = method('workbench','sourceLabel');
  assert.equal(label('sample-fallback',true),'실시간 연결 실패 · 예시 데이터');
  assert.equal(label('live',true),'연결 지연 · 마지막 API 데이터');
  assert.equal(label('live',false),'실시간 API');
  assert.equal(label('sample',false),'예시 데이터 · 실행 연결 전');
});

test('paused or reduced scenes do not accumulate delayed flows or cosmetic trips', () => {
  for(const mode of ['reduced','hidden','roster']){
    const globals={REDUCED:mode==='reduced',document:{hidden:mode==='hidden'},space:{rosterOpen:mode==='roster'}};
    const flow=method('world','spawnFlow',globals),trip=method('world','memoryTrip',globals);
    for(let i=0;i<100;i++){assert.equal(flow({}),undefined);assert.equal(trip({}),undefined);}
  }
});

test('motion policy restores controls without losing a manual traffic pause', () => {
  const button={setAttribute(k,v){this[k]=v}}, get=()=>button;
  const reduced=method('world','syncMotionUI',{$:get,REDUCED:true});
  const normal=method('world','syncMotionUI',{$:get,REDUCED:false});
  const world={trafficPaused:true};
  reduced.call(world);assert.equal(button.disabled,true);assert.equal(button['aria-pressed'],'true');
  normal.call(world);assert.equal(button.disabled,false);assert.equal(button.textContent,'교통 연출 재생');
  world.trafficPaused=false;normal.call(world);assert.equal(button['aria-pressed'],'false');
});
