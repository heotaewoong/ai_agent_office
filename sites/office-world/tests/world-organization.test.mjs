import { readFile } from 'node:fs/promises';
import assert from 'node:assert/strict';
import { test } from 'node:test';

const source = await readFile(new URL('../app.js', import.meta.url), 'utf8');
function method(object, name, globals = {}) {
  const start = source.indexOf('    ' + name + '(', source.indexOf('  const ' + object + ' = {'));
  const end = source.indexOf('\n    },', start);
  assert(start >= 0 && end > start, `${object}.${name} exists`);
  return Function(...Object.keys(globals), 'return ({' + source.slice(start, end + 6) + '}).' + name)(...Object.values(globals));
}

const physicalIds = ['inbox', 'scripts', 'creative', 'outbox', 'ops'];
const teamIds = ['life', 'content', 'dev', 'wiki', 'stocks'];

test('visible department shortcuts show every team name and open its existing physical zone after refresh', () => {
  const data=method('organization','project')(fixture());
  const nodes=new Map();
  const node=()=>({children:[],style:{setProperty(){}},events:{},querySelectorAll:()=>[],appendChild(el){this.children.push(el);},replaceChildren(){this.children=[];},setAttribute(){},addEventListener(type,fn){this.events[type]=fn;},dataset:{}});
  const $=id=>{if(!nodes.has(id))nodes.set(id,node());return nodes.get(id);};
  const hud={cards:new Map(),refresh(){},openStage(id){this.opened=id;}};
  const rebuild=method('hud','rebuild',{$,space:{stages:data.stages},explorationNames:new Map(),exploration(){},document:{createElement:node}});
  rebuild.call(hud,data);
  assert.deepEqual($('department-nav').children.map(el=>el.textContent),['1 · 생활 비서 팀','2 · 콘텐츠 자동화 팀','3 · 개발 팀','4 · 옵시디언 팀','5 · 주식 팀']);
  $('department-nav').children.forEach((el,i)=>{el.events.click();assert.equal(hud.opened,physicalIds[i]);});
  rebuild.call(hud,data);
  assert.equal($('department-nav').children.length,5,'polling must not duplicate shortcuts');
});
function fixture() {
  const views = ['news', 'studio', 'delivery', 'delivery', 'activity'];
  const rooms = { research: 'inbox', editor: 'scripts', critique: 'scripts', eval: 'scripts', video: 'creative', qa: 'creative', release: 'outbox', marketing: 'outbox', director: 'ops' };
  return {
    version: 1, generatedAt: '2026-10-30T12:00:00+09:00',
    office: { name: '기존 콘텐츠 오피스', url: '/content' },
    brain: { notes: 7, sources: 3, label: '기존 콘텐츠 근거' },
    stages: physicalIds.map((id, i) => ({
      id, name: ['오늘의 뉴스', '원고 작업실', '제작 스튜디오', '제작·출고함', '운영 기록'][i],
      color: '#123456', approval: ['⓪ 기획 선택', '① 원고 승인', '영상 검토', '② 출고 승인 · ③ 회차', '교훈 승인'][i],
      view: views[i], url: '/content', items: [{
        id: `original-${id}`, title: `원래 ${id} 업무`, state: i === 2 ? 'source_approved' : 'source_review',
        stateLabel: '원래 상태 문구', needsHuman: i !== 2, agentId: Object.keys(rooms).find(key => rooms[key] === id),
        view: views[i], actions: i === 2 ? [{ id: 'produce', label: '제작 시작' }] : [],
      }],
    })),
    agents: Object.entries(rooms).map(([id, stageId]) => ({ id, name: id, stageId, status: id === 'critique' ? 'unknown' : 'waiting', engine: '원래 엔진', model: '', task: '원래 관측 업무' })),
    events: physicalIds.map(stageId => ({ stageId, time: '12:00', text: `기존 ${stageId} 기록` })),
    flows: [{ from: 'inbox', to: 'scripts', itemId: 'original-scripts' }, { from: 'creative', to: 'outbox', itemId: 'original-outbox' }],
  };
}

test('organization projection preserves physical zones and the complete original workflow without mutating input', () => {
  const project = method('organization', 'project'), input = fixture(), before = structuredClone(input);
  const result = project(input), content = result.stages.find(stage => stage.teamId === 'content');
  assert.deepEqual(input, before);
  assert.equal(result.organizationVersion, 1);
  assert.deepEqual(result.stages.map(stage => stage.id), physicalIds);
  assert.deepEqual(result.stages.map(stage => stage.teamId), teamIds);
  assert.equal(content.id, 'scripts');
  assert.deepEqual(content.workflowStages, before.stages);
  assert.deepEqual(content.workflowFlows, before.flows);
  assert.deepEqual(result.flows, []);
  assert.equal(result.brain.notes, before.brain.notes);
  assert.equal(result.brain.sources, before.brain.sources);
  assert.equal(result.generatedAt, before.generatedAt);
});

test('content items retain original identifiers, review state and exact existing action routes', () => {
  const input = fixture(), result = method('organization', 'project')(input);
  const content = result.stages.find(stage => stage.teamId === 'content');
  assert.equal(content.items.length, input.stages.reduce((count, stage) => count + stage.items.length, 0));
  for (const stage of input.stages) {
    for (const item of stage.items) {
      const projected = content.items.find(candidate => candidate.id === item.id);
      assert(projected, item.id);
      for (const key of Object.keys(item)) assert.deepEqual(projected[key], item[key], `${item.id}.${key}`);
      assert.equal(projected.workflowStageId, stage.id);
      assert.equal(projected.workflowStageName, stage.name);
    }
  }
});

test('all nine observed actors and events move explicitly to content without inventing a runtime status', () => {
  const input = fixture(), result = method('organization', 'project')(input);
  assert.equal(result.agents.length, 9);
  for (const actor of input.agents) {
    const projected = result.agents.find(candidate => candidate.id === actor.id);
    assert.equal(projected.stageId, 'scripts');
    assert.equal(projected.workflowStageId, actor.stageId);
    assert.equal(projected.teamId, 'content');
    for (const key of ['id', 'name', 'status', 'engine', 'model', 'task']) assert.equal(projected[key], actor[key]);
  }
  assert.equal(result.agents.find(actor => actor.id === 'critique').status, 'unknown');
  assert.equal(result.events.length, input.events.length);
  result.events.forEach((event, index) => {
    assert.equal(event.stageId, 'scripts');
    assert.equal(event.workflowStageId, input.events[index].stageId);
    assert.equal(event.text, input.events[index].text);
    assert.equal(event.time, input.events[index].time);
  });
});

test('planned teams show goals separately and have no fabricated jobs, actors or execution actions', () => {
  const result = method('organization', 'project')(fixture());
  for (const stage of result.stages.filter(candidate => candidate.teamId !== 'content')) {
    assert.deepEqual(stage.items, []);
    assert.equal(result.agents.filter(actor => actor.stageId === stage.id).length, 0);
    assert.equal(typeof stage.description, 'string');
    assert(stage.description.trim());
    assert(Array.isArray(stage.goals));
    assert.equal(stage.connection, stage.teamId === 'stocks' ? 'undecided' : 'planned');
  }
});

test('projection is idempotent and fresh polls replace observations rather than accumulate or cache them', () => {
  const project = method('organization', 'project'), firstInput = fixture(), first = project(firstInput);
  assert.deepEqual(project(first), first);
  assert.deepEqual(project(firstInput), first);
  const nextInput = fixture();
  nextInput.stages[1].items[0].state = 'release_review';
  nextInput.stages[1].items[0].stateLabel = '새 관측 상태';
  nextInput.agents[1].status = 'running';
  const next = project(nextInput), content = next.stages.find(stage => stage.teamId === 'content');
  assert.equal(content.items.find(item => item.id === 'original-scripts').state, 'release_review');
  assert.equal(content.workflowStages[1].items[0].stateLabel, '새 관측 상태');
  assert.equal(next.agents[1].status, 'running');
  assert.equal(first.agents[1].status, 'waiting');
  assert.equal(content.items.length, 5);
  assert.equal(next.agents.length, 9);
});

test('unrelated, missing and duplicate stage sets pass through unchanged instead of being relabeled', () => {
  const project = method('organization', 'project');
  for (const ids of [[], ['other'], physicalIds.slice(0, 4), [...physicalIds, 'other'], ['inbox', 'scripts', 'creative', 'outbox', 'inbox'], teamIds]) {
    const input = { stages: ids.map(id => ({ id, items: [] })), agents: [], events: [], flows: [] };
    assert.equal(project(input), input);
  }
});

test('overflow standing positions give five content actors distinct spots with clearance', () => {
  const spot = method('world', 'standingSpot'), positions = Array.from({ length: 5 }, (_, i) => spot(i));
  assert.equal(new Set(positions.map(point => `${point.x}:${point.z}`)).size, 5);
  for (const point of positions) assert(Number.isFinite(point.x) && Number.isFinite(point.z));
  for (let i = 0; i < positions.length; i++) for (let j = i + 1; j < positions.length; j++) {
    assert(Math.hypot(positions[i].x - positions[j].x, positions[i].z - positions[j].z) >= 1.49);
  }
});

test('actual actor placement resets the overflow index per physical room', () => {
  const vector = (x, y, z) => ({ x, y, z, clone() { return vector(this.x, this.y, this.z); } });
  const stage = (id, deskCount) => ({ id, rotY: 0, desks: Array.from({ length: deskCount }, (_, i) => ({ taken: null, faceY: 0, sitPos: vector(i * 1.8, 0, -3.6) })) });
  const space = { stages: [stage('scripts', 4), stage('other', 1)], agents: [] }, calls = [];
  const standingSpot = method('world', 'standingSpot');
  const build = method('world', 'buildAgents', { space });
  build.call({
    clearAgents() { space.agents = []; space.stages.forEach(room => room.desks.forEach(desk => { desk.taken = null; })); },
    buildAvatar() { return { root: { position: { copyFrom() {} }, rotation: {} } }; },
    standingSpot(index) { calls.push(index); return standingSpot(index); },
    local(room, x, y, z) { return vector(x + (room.id === 'other' ? 100 : 0), y, z); },
    setPose() {}, applyStatus() {},
  }, [...Array.from({ length: 9 }, (_, i) => ({ id: `content-${i}`, stageId: 'scripts' })), ...Array.from({ length: 3 }, (_, i) => ({ id: `other-${i}`, stageId: 'other' }))]);
  assert.deepEqual(calls, [0, 1, 2, 3, 4, 0, 1]);
  const overflow = space.agents.filter(actor => actor.stageId === 'scripts' && actor.mode === 'standing');
  assert.equal(overflow.length, 5);
  assert.equal(new Set(overflow.map(actor => `${actor.pos.x}:${actor.pos.z}`)).size, 5);
});

test("central control is safe before the first projection arrives", () => {
  const open = method("hud", "openBrain", {space:{data:null}});
  assert.doesNotThrow(() => open());
});
