import { test } from 'node:test';
import assert from 'node:assert/strict';
import { readFile } from 'node:fs/promises';

const source = await readFile(new URL('../app.js', import.meta.url), 'utf8');
const escape = value => String(value).replace(/[&<>"']/g, c => ({ '&': '&amp;', '<': '&lt;', '>': '&gt;', '"': '&quot;', "'": '&#39;' }[c]));
const reference = { request_id: 'aa3a151d-72e8-4abf-b09d-10d416279c41', task_id: 't_final123', run_id: 3, event_id: 9 };
const observation = (patch = {}) => ({ request_id: reference.request_id, board: 'heobrain-office', status: 'completed', native_status: 'done', assignee: 'lumi', native_task_id: 't_root123',
  events: [{ id: 9, kind: 'completed', assignee: 'lumi', task_id: reference.task_id, run_id: 3 }],
  report: { summary: '<img src=x onerror=alert(1)>\n실제 결과입니다.', verified: true, task_id: reference.task_id, run_id: 3, event_id: 9 }, ...patch });
function fixture({ phone = false } = {}) {
  const vector = (x = 0, y = 0, z = 0) => ({ x, y, z, clone() { return vector(this.x, this.y, this.z); }, copyFrom(v) { this.x = v.x; this.y = v.y; this.z = v.z; } });
  const elements = new Map(), $ = id => { if (!elements.has(id)) elements.set(id, { hidden: true, textContent: '', innerHTML: '', dataset: {}, setAttribute() {}, addEventListener() {} }); return elements.get(id); };
  const space = { layer: 'office', view: 'walk', stages: [{ id: 'inbox', name: '생활 비서 팀', pos: vector(23), bridge: { start: vector(10), end: vector(15) } }], agents: [] };
  const data = { source: 'live', error: null }, messages = [], moves = [], embed = { enabled: true, post: m => messages.push(m) };
  const world = { buildAvatar() { return { root: { position: vector(), rotation: {}, setEnabled() {} }, marker: {}, body: {} }; }, local: (_s, x, y, z) => vector(x, y, z), setPose() {}, mat: () => ({}), animateWalk() {} };
  const controls = { player: { pos: vector() }, keys: new Set(['w', ' ']), dragging: true, vy: 4, vehicleSpeed: 12, touchWalkEnabled: false,
    setVehicleSpeed(value) { this.vehicleSpeed = value; }, enableTouchWalk(value) { this.touchWalkEnabled = value; },
    enterStage(stage) { moves.push(stage.id); this.player.pos.copyFrom(vector(23, 0, 7)); } };
  const closes = [], classes = new Set(), document = { hidden: false, body: { classList: { add: name => classes.add(name), remove: name => classes.delete(name) } },
    querySelector: selector => selector === '#play-hub .play-hub-close' ? { click() { closes.push('play'); space.playHubOpen=false; } } : null };
  const results = { opened:false, close() { closes.push('results'); this.opened=false; space.resultsOpen=false; } };
  const workshop = { opened:false, setOpen(value) { closes.push('workshop'); this.opened=value; space.buildingOpen=value; } };
  const hud = { cards: new Map() }, workbench = { setRoster(value) { closes.push('roster'); space.rosterOpen=value; } };
  const closeStart=source.indexOf('    closePanel('),closeEnd=source.indexOf('\n    },',closeStart);
  hud.closePanel=Function('space','results','$','document','return ({'+source.slice(closeStart,closeEnd+6)+'}).closePanel')(space,results,$,document);
  const start = source.indexOf('  const assistantNative = {'), end = source.indexOf('\n  };', start);
  const globals = { space, data, embed, world, controls, hud, workbench, workshop, results, $,
    B: { Vector3: function (x, y, z) { return vector(x, y, z); } }, REDUCED: false, document, esc: escape, isPhone: () => phone };
  const adapter = Function(...Object.keys(globals), 'return (' + source.slice(start + '  const assistantNative = '.length, end + 4) + ')')(...Object.values(globals));
  return { adapter, space, data, embed, world, controls, hud, workbench, workshop, results, $, messages, moves, vector, closes, classes };
}
const action = (patch = {}) => ({ source: 'content-office', type: 'assistant-report-action', action: 'result', ...reference, ...patch });

test('live native roster exists before a task without manufacturing work or changing content actors', () => {
  const f = fixture(); f.adapter.ensureProfiles(); f.adapter.ensureProfiles();
  assert.equal(f.adapter.actors.size, 9); assert.equal(f.space.agents.length, 0);
  for (const [profile, actor] of f.adapter.actors) { assert.equal(actor.profile, profile); assert.equal(actor.phase, 'unknown'); assert.equal(actor.taskId, null); }
  for (const source of ['sample', 'sample-fallback', 'none']) { const off = fixture(); off.data.source = source; off.adapter.ensureProfiles(); assert.equal(off.adapter.actors.size, 0); }
});

test('result opens only the full escaped report of the exact verified native task', () => {
  const f = fixture(); f.adapter.sync(observation());
  assert.equal(f.adapter.reportAction(action()), true);
  assert.equal(f.$('panel').hidden, false); assert.match(f.$('panel-title').textContent, /완료 보고/);
  const body = f.$('panel-body').innerHTML;
  for (const value of Object.values(reference)) assert.ok(body.includes(String(value)));
  assert.ok(body.includes('&lt;img')); assert.ok(!body.includes('<img')); assert.ok(body.includes('실제 결과입니다.'));
  assert.equal(f.moves.length, 0);
  assert.deepEqual(f.messages.at(-1), { type: 'assistant-report-result', action: 'result', ...reference, ok: true, message: '이 업무의 검증된 완료 보고를 열었습니다.' });
});

test('forged, stale and unverified report actions never move the player or open a result', () => {
  for (const patch of [{ request_id: 'bb3a151d-72e8-4abf-b09d-10d416279c41' }, { task_id: 't_other' }, { run_id: 4 }, { event_id: 10 }, { action: 'approve' }, { request_id: '../private' }, { run_id: '3' }]) {
    const f = fixture(); f.adapter.sync(observation()); assert.equal(f.adapter.reportAction(action(patch)), false); assert.equal(f.moves.length, 0); assert.equal(f.$('panel').hidden, true);
  }
  for (const patch of [{ report: { ...observation().report, verified: false } }, { status: 'running' }, { native_status: 'running' }, { events: [] }]) {
    const f = fixture(); f.adapter.sync(observation(patch)); assert.equal(f.adapter.reportAction(action()), false); assert.equal(f.$('panel').hidden, true);
  }
});

test('latest request observation invalidates old report actions and stores an independent report snapshot', () => {
  const f = fixture(), request = observation(); f.adapter.sync(request); request.report.summary = '변조된 원문';
  assert.equal(f.adapter.reportAction(action()), true); assert.ok(!f.$('panel-body').innerHTML.includes('변조된 원문'));
  f.hud.closePanel(); f.adapter.sync(observation({ status: 'running', report: null }));
  assert.equal(f.adapter.reportAction(action()), false); assert.equal(f.$('panel').hidden, true);
});

test('visit enters the actual inbox workstation on mobile, clears motion and opens that task report', () => {
  const f = fixture({ phone: true }); f.adapter.sync(observation());
  assert.equal(f.adapter.reportAction(action({ action: 'visit' })), true); assert.deepEqual(f.moves, ['inbox']);
  assert.equal(f.controls.keys.size, 0); assert.equal(f.controls.vy, 0); assert.equal(f.controls.dragging, false); assert.equal(f.controls.vehicleSpeed, 0); assert.equal(f.controls.touchWalkEnabled, true);
  assert.match(f.$('panel-sub').textContent, /생활 비서 팀.*Hermes 업무실/); assert.ok(f.$('panel-body').innerHTML.includes(reference.task_id));
});

test('offline, stale data and missing actual workstation fail closed without a content-job fallback', () => {
  for (const change of [f => { f.data.source = 'sample'; }, f => { f.data.error = 'stale'; }, f => { f.embed.enabled = false; }, f => { f.space.stages = []; }, f => { f.controls.player = null; }]) {
    const f = fixture(); f.adapter.sync(observation()); change(f); assert.equal(f.adapter.reportAction(action({ action: 'visit' })), false); assert.equal(f.moves.length, 0); assert.equal(f.$('panel').hidden, true);
  }
});

test('nearby native talk is explicit, profile-bound, available on mobile and never submits a task', () => {
  const f = fixture({ phone: true }); f.adapter.ensureProfiles();
  const actor = f.adapter.actors.get('ada'); f.controls.player.pos.copyFrom(actor.pos);
  assert.equal(f.adapter.nearby().profile, 'ada'); assert.equal(f.adapter.talk('ada'), true);
  assert.deepEqual(f.messages, [{ type: 'assistant-open', assistant: 'ada' }]); assert.equal(f.controls.keys.size, 0);
  assert.equal(f.adapter.talk('director'), false); assert.equal(f.messages.length, 1);
  f.adapter.updateTalk(); assert.equal(f.$('native-talk').hidden, false); assert.match(f.$('native-talk').textContent, /에이다.*말걸기/); assert.match(f.$('native-talk').textContent, /응답 상태 미확인/);
});

test('native proximity obeys range, current layer/view and stale state without stealing focus', () => {
  const f = fixture(); f.adapter.ensureProfiles();
  f.controls.player.pos.copyFrom(f.vector(40, 0, 40)); assert.equal(f.adapter.nearby(), null); f.adapter.updateTalk(); assert.equal(f.$('native-talk').hidden, true);
  for (const patch of [{ layer: 'meadow' }, { view: 'overview' }, { rosterOpen: true }, { buildingOpen: true }, { resultsOpen: true }, { playHubOpen: true }]) {
    Object.assign(f.space, { layer: 'office', view: 'walk', rosterOpen: false, buildingOpen: false, resultsOpen: false, playHubOpen: false }, patch); f.controls.player.pos.copyFrom(f.adapter.actors.get('lumi').pos); assert.equal(f.adapter.nearby(), null);
  }
  Object.assign(f.space, { layer: 'office', view: 'walk', playHubOpen: false }); f.data.error = 'stale'; assert.equal(f.adapter.nearby(), null); assert.equal(f.adapter.talk('lumi'), false);
});

test('existing E interaction prefers a nearby Hermes profile and preserves content-role stage inspection', () => {
  const start = source.indexOf('    toggleNearestAgent('), end = source.indexOf('\n    },', start);
  const calls = [], player = { pos: { x: 0, y: 0, z: 0 } }, native = { nearby: () => ({ profile: 'ada' }), talk: profile => { calls.push(profile); return true; } };
  const space = { agents: [{ stageId: 'scripts', pos: { x: 1, y: 0, z: 0 } }] }, world = { assistantNative: native }, controls = { player };
  const toggle = Function('space', 'world', 'controls', 'B', 'return ({' + source.slice(start, end + 6) + '}).toggleNearestAgent')(space, world, controls, { Vector3: { Distance: (a,b) => Math.hypot(a.x-b.x,a.y-b.y,a.z-b.z) } });
  const hud = { openStage: stage => calls.push(stage) }; toggle.call(hud); assert.deepEqual(calls, ['ada']);
  native.nearby = () => null; toggle.call(hud); assert.deepEqual(calls, ['ada', 'scripts']);
});

test('both report actions close every competing mode before showing the report and close restores input', () => {
  for (const selectedAction of ['result','visit']) {
    const f=fixture(); f.adapter.sync(observation());
    Object.assign(f.space,{rosterOpen:true,buildingOpen:true,resultsOpen:true,playHubOpen:true,selectedStage:'scripts'}); f.workshop.opened=true; f.results.opened=true;
    assert.equal(f.adapter.reportAction(action({action:selectedAction})),true);
    for(const key of ['rosterOpen','buildingOpen','resultsOpen','playHubOpen'])assert.equal(f.space[key],false,key);
    assert.deepEqual(new Set(f.closes),new Set(['roster','workshop','results','play']));
    assert.equal(f.space.nativeReportOpen,true); assert.equal(f.space.selectedStage,null); assert.equal(f.$('panel').hidden,false);
    assert.equal(f.controls.vehicleSpeed,0); assert.equal(f.controls.vy,0); assert.ok(f.classes.has('native-report-view'));
    f.hud.closePanel(); assert.equal(f.space.nativeReportOpen,false); assert.ok(!f.classes.has('native-report-view'));
  }
});

test('result from the ground keeps position and layer while invalid actions preserve all existing modes', () => {
  const f=fixture({phone:true}); f.adapter.sync(observation()); f.space.layer='meadow'; const before={...f.controls.player.pos};
  assert.equal(f.adapter.reportAction(action()),true); assert.equal(f.space.layer,'meadow'); assert.equal(f.moves.length,0); assert.equal(f.controls.player.pos.x,before.x); assert.equal(f.controls.player.pos.z,before.z); assert.equal(f.space.nativeReportOpen,true);
  const rejected=fixture(); rejected.adapter.sync(observation()); Object.assign(rejected.space,{rosterOpen:true,buildingOpen:true,resultsOpen:true,playHubOpen:true});
  assert.equal(rejected.adapter.reportAction(action({task_id:'t_forged'})),false); assert.deepEqual(rejected.closes,[]);
  for(const key of ['rosterOpen','buildingOpen','resultsOpen','playHubOpen'])assert.equal(rejected.space[key],true,key);
  assert.equal(rejected.controls.vehicleSpeed,12); assert.equal(rejected.controls.vy,4);
});

test('a native report pauses physical movement and E but Escape closes only the report', () => {
  const start=source.indexOf('    onKey('),end=source.indexOf('\n    },',start),space={nativeReportOpen:true,view:'walk'};
  let closed=0;const hud={closePanel(){closed++;space.nativeReportOpen=false;}}, controls={keys:new Set()};
  const onKey=Function('space','hud','return ({'+source.slice(start,end+6)+'}).onKey')(space,hud);
  const event=(key,code)=>({key,code,target:{closest:()=>false},preventDefault(){}});
  onKey.call(controls,event('w','KeyW'),true);assert.equal(controls.keys.size,0);
  onKey.call(controls,event('e','KeyE'),true);assert.equal(closed,0);
  onKey.call(controls,event('Escape','Escape'),true);assert.equal(closed,1);assert.equal(space.nativeReportOpen,false);
  const tickStart=source.indexOf('    tick(dt)',source.indexOf('  const controls = {')),tickEnd=source.indexOf('\n    },',tickStart);
  const tick=Function('space','return ({'+source.slice(tickStart,tickEnd+6)+'}).tick')({nativeReportOpen:true,view:'walk'});
  assert.doesNotThrow(()=>tick.call({},1),'paused report must not access or advance physics or camera state');
});
