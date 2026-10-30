import { readFile } from 'node:fs/promises';
import assert from 'node:assert/strict';
import { test } from 'node:test';

const source = await readFile(new URL('../app.js', import.meta.url), 'utf8');
function objectLiteral(name) {
  const start = source.indexOf('  const ' + name + ' = {');
  const end = source.indexOf('\n  };', start);
  assert(start >= 0 && end > start, name + ' must exist');
  return source.slice(source.indexOf('{', start), end + 4);
}
function method(object, name, globals = {}) {
  const start = source.indexOf('    ' + name + '(', source.indexOf('  const ' + object + ' = {'));
  const end = source.indexOf('\n    },', start);
  assert(start >= 0 && end > start, object + '.' + name + ' must exist');
  return Function(...Object.keys(globals), 'return ({' + source.slice(start, end + 6) + '}).' + name)(...Object.values(globals));
}
const projection = stamp => ({ generatedAt: stamp, stages: [{ id: 'scripts', name: stamp, items: [] }], agents: [] });
async function until(predicate) {
  for (let i = 0; i < 30 && !predicate(); i++) await Promise.resolve();
  assert(predicate(), 'expected asynchronous state transition');
}
function fixture({ ignoreAbort = false } = {}) {
  const pending = [], timeouts = new Map(), intervals = new Map(), events = new Map(), elements = new Map();
  let next = 0;
  const $ = id => {
    if (!elements.has(id)) elements.set(id, { hidden: true });
    return elements.get(id);
  };
  const document = { hidden: false, addEventListener(name, listener) {
    if (!events.has(name)) events.set(name, []);
    events.get(name).push(listener);
  } };
  const fetch = (url, init) => new Promise((resolve, reject) => {
    pending.push({ url, init, resolve, reject });
    if (!ignoreAbort) init.signal.addEventListener('abort', () => reject(new Error('aborted')), { once: true });
  });
  const setTimeout = (fn, delay) => { const id = ++next; timeouts.set(id, { fn, delay }); return id; };
  const clearTimeout = id => timeouts.delete(id);
  const setInterval = (fn, delay) => { const id = ++next; intervals.set(id, { fn, delay }); return id; };
  const clearInterval = id => intervals.delete(id);
  const notice = (title, text) => { Object.assign($('notice'), { hidden: false, title, text }); };
  const data = Function('fetch', 'AbortController', 'setTimeout', 'clearTimeout', 'setInterval', 'document', '$', 'notice', 'PALETTE', 'return (' + objectLiteral('data') + ')')
    (fetch, AbortController, setTimeout, clearTimeout, setInterval, document, $, notice, ['#123456']);
  data.apiUrl = '/api/space';
  const observations = [];
  data.onChange(value => observations.push(value));
  const reply = (index, body) => pending[index].resolve({ ok: true, json: async () => body });
  const fail = (index, message = 'HTTP 503') => pending[index].reject(new Error(message));
  return { data, pending, timeouts, intervals, events, document, $, observations, reply, fail, notice, setTimeout, setInterval, clearInterval,
    expire() { const [id, timer] = [...timeouts].find(([, timer]) => timer.delay === 12000); timeouts.delete(id); timer.fn(); },
    poll() { for (const timer of intervals.values()) timer.fn(); },
    resume() { document.hidden = false; for (const listener of events.get('visibilitychange') || []) listener(); },
  };
}

function startup(f) {
  const start = source.indexOf('  function start() {');
  const end = source.indexOf('\n  }', start);
  const calls = { posts: [], flows: [], trips: 0 };
  const space = { data: null, stages: [], agents: [], rosterOpen: false };
  const world = { init() {}, buildStages(stages) { space.stages = stages; },
    buildAgents(agents) { space.agents = agents.map(agent => ({ ...agent, mode: 'seated' })); },
    updateAgentStatuses() {}, spawnFlow(flow) { calls.flows.push(flow); }, memoryTrip() { calls.trips++; } };
  const globals = { world, organization: Function('return (' + objectLiteral('organization') + ')')(), hud: { init() {}, rebuild() {}, refresh() {} }, controls: { init() {}, setLayer() {}, animateCamera() {}, setView() {} },
    data: f.data, embed: { init() {}, post(message) { calls.posts.push(message); } },
    workbench: { init() {} }, workshop: { init() {} }, results: { init() {} },
    space, REDUCED: false, QUALITY: 'low', document: f.document, $: f.$, setTimeout: f.setTimeout, setInterval: f.setInterval, clearInterval: f.clearInterval,
    location: { search: '' }, localStorage: { getItem() { return null; } }, isPhone: () => false, notice: f.notice,
    B: { Vector3: class { constructor(x, y, z) { Object.assign(this, { x, y, z }); } } }, OVERVIEW_HOME: {} };
  f.data.init = () => {};
  Function(...Object.keys(globals), source.slice(start, end + 4) + '\nstart();')(...Object.values(globals));
  return { calls, space };
}

test('a hanging live read times out, keeps the last source, and releases the polling lock', async () => {
  const f = fixture();
  f.data.source = 'live';
  const request = f.data.load(false);
  assert.equal(f.pending.length, 1);
  assert.equal([...f.timeouts.values()][0].delay, 12000);
  f.expire();
  assert.equal(await request, false);
  assert.match(f.data.error, /시간이 초과/);
  assert.equal(f.data.source, 'live');
  assert.deepEqual(f.observations, [null]);
  assert.equal(f.data.loading, false);
  assert.equal(f.data.controller, null);
  assert.equal(f.timeouts.size, 0);
});

for (const part of ['fetch', 'json']) test('the deadline bounds an uncooperative ' + part + ' and clears the request timer', async () => {
  const f = fixture({ ignoreAbort: true });
  const request = f.data.load(false);
  let completeJson;
  if (part === 'json') {
    f.pending[0].resolve({ ok: true, json: () => new Promise(resolve => { completeJson = resolve; }) });
    await until(() => Boolean(completeJson));
  }
  f.expire();
  assert.equal(await request, false);
  assert.equal(f.data.loading, false);
  assert.equal(f.data.controller, null);
  assert.equal(f.timeouts.size, 0);
  const retry = f.data.load(false);
  f.reply(1, projection('recovered'));
  assert.equal(await retry, true);
  if (part === 'json') completeJson(projection('too-late'));
  else f.reply(0, projection('too-late'));
  await Promise.resolve();
  assert.equal(f.data.error, null);
  assert.deepEqual(f.observations.filter(Boolean).map(value => value.generatedAt), ['recovered']);
});

test('slow polling coalesces instead of accumulating concurrent live reads', async () => {
  const f = fixture();
  const request = f.data.load(false);
  for (let i = 0; i < 5; i++) assert.equal(await f.data.load(false), false);
  assert.equal(f.pending.length, 1);
  f.reply(0, projection('current'));
  assert.equal(await request, true);
  assert.equal(f.observations.length, 1);
  assert.equal(f.observations[0].generatedAt, 'current');
});

test('a superseded response cannot replace a newer projection even when transport ignores abort', async () => {
  const f = fixture({ ignoreAbort: true });
  const old = f.data.load(false);
  const current = f.data.load(false, true);
  assert.equal(f.pending[0].init.signal.aborted, true);
  assert.equal(await old, false);
  assert.equal(f.data.loading, true);
  assert.equal(f.timeouts.size, 1);
  f.reply(1, projection('new'));
  assert.equal(await current, true);
  f.reply(0, projection('old'));
  assert.equal(await old, false);
  assert.deepEqual(f.observations.map(x => x.generatedAt), ['new']);
  assert.equal(f.data.error, null);
  assert.equal(f.data.loading, false);
});

test('startup reaches polling and ready after both uncooperative source deadlines', async () => {
  const f = fixture({ ignoreAbort: true });
  const boot = startup(f);
  f.expire();
  await until(() => f.pending.length === 2);
  f.expire();
  await until(() => boot.calls.posts.some(message => message.type === 'ready'));
  assert.equal(f.data.loading, false);
  assert.equal(f.timeouts.size, 0);
  assert.equal(f.intervals.size, 1);
  assert.equal(f.$('notice').hidden, false);
  f.poll();
  assert.equal(f.pending.length, 3);
  f.reply(2, projection('reconnected'));
  await until(() => !f.data.loading);
  assert.equal(f.data.source, 'live');
  assert.equal(f.$('notice').hidden, true);
});

test('startup still sends ready and starts polling if projection initialization rejects', async () => {
  const f = fixture();
  f.data.load = async () => { throw new Error('unexpected projection failure'); };
  const boot = startup(f);
  await until(() => boot.calls.posts.some(message => message.type === 'ready'));
  assert.equal(f.intervals.size, 1);
  assert.match(f.data.error, /투영 초기화 실패/);
  assert.equal(f.$('notice').hidden, false);
});

test('live recovery stops sample trips, sample intervals, and delayed sample flows', async () => {
  const f = fixture();
  const boot = startup(f);
  f.fail(0);
  await until(() => f.pending.length === 2);
  f.reply(1, { ...projection('sample'), agents: [{ id: 'sample-agent', stageId: 'scripts', status: 'idle' }], flows: [{ from: 'scripts', to: 'memory', itemId: 'sample-only' }] });
  await until(() => boot.calls.posts.some(message => message.type === 'ready'));
  const [simulationId, simulation] = [...f.intervals].find(([, timer]) => timer.delay === 11000);
  const delayedFlow = [...f.timeouts.values()].find(timer => timer.delay === 600);
  assert.equal(f.data.source, 'sample-fallback');
  simulation.fn();
  assert.equal(boot.calls.trips, 1);
  assert.equal(boot.calls.flows.length, 1);
  const retry = f.data.load(false);
  f.reply(2, projection('live'));
  assert.equal(await retry, true);
  assert.equal(f.data.source, 'live');
  assert.equal(f.intervals.has(simulationId), false);
  simulation.fn();
  delayedFlow.fn();
  assert.equal(boot.calls.trips, 1);
  assert.equal(boot.calls.flows.length, 1);
});

test('an old failure does not erase a newer successful connection', async () => {
  const f = fixture({ ignoreAbort: true });
  const old = f.data.load(false);
  const current = f.data.load(false, true);
  f.reply(1, projection('new'));
  await current;
  f.fail(0);
  assert.equal(await old, false);
  assert.equal(f.data.source, 'live');
  assert.equal(f.data.error, null);
  assert.equal(f.observations.length, 1);
});

test('initial live timeout can show an explicit sample and then recover to live data', async () => {
  const f = fixture();
  const initial = f.data.load(true);
  f.expire();
  await until(() => f.pending.length === 2);
  assert.equal(f.pending[1].url, 'data/space.json');
  f.reply(1, projection('sample'));
  assert.equal(await initial, true);
  assert.equal(f.data.source, 'sample-fallback');
  assert.match(f.data.error, /실시간 읽기 실패/);
  const retry = f.data.load(false);
  f.reply(2, projection('live'));
  assert.equal(await retry, true);
  assert.equal(f.data.source, 'live');
  assert.equal(f.data.error, null);
  assert.equal(f.$('notice').hidden, true);
});

test('failure of both initial sources still permits polling recovery and clears its notice', async () => {
  const f = fixture();
  const initial = f.data.load(true);
  f.fail(0);
  await until(() => f.pending.length === 2);
  f.fail(1, 'sample unavailable');
  assert.equal(await initial, false);
  assert.equal(f.$('notice').hidden, false);
  f.data.startPolling();
  f.poll();
  assert.equal(f.pending.length, 3);
  f.reply(2, projection('recovered'));
  await until(() => !f.data.loading);
  assert.equal(f.data.source, 'live');
  assert.equal(f.data.error, null);
  assert.equal(f.$('notice').hidden, true);
});

test('malformed projection is not a live success and does not prevent a later retry', async () => {
  const f = fixture();
  const initial = f.data.load(true);
  f.reply(0, { stages: 'invalid' });
  assert.equal(await initial, false);
  assert.equal(f.data.source, 'sample');
  assert.equal(f.$('notice').hidden, false);
  assert.match(f.data.error, /데이터 형식/);
  assert.deepEqual(f.observations, [null]);
  const retry = f.data.load(false);
  f.reply(1, projection('valid'));
  assert.equal(await retry, true);
  assert.equal(f.data.source, 'live');
  assert.equal(f.data.error, null);
  assert.equal(f.$('notice').hidden, true);
});

test('hidden tabs stop polling and visible return makes exactly one fresh read', async () => {
  const f = fixture();
  f.data.startPolling();
  f.data.startPolling();
  assert.equal(f.intervals.size, 1);
  assert.equal(f.events.get('visibilitychange').length, 1);
  f.document.hidden = true;
  f.poll();
  assert.equal(f.pending.length, 0);
  f.resume();
  f.poll();
  assert.equal(f.pending.length, 1);
  f.reply(0, projection('visible'));
  await until(() => !f.data.loading);
  assert.equal(f.data.source, 'live');
});

test('stale live HUD names the last record and disables server actions until recovery', () => {
  const elements = new Map();
  const $ = id => {
    if (!elements.has(id)) elements.set(id, { hidden: true, innerHTML: '', textContent: '', contains() { return false; }, style: { setProperty() {} }, setAttribute(name, value) { this[name] = value; } });
    return elements.get(id);
  };
  const item = { id: 'job_1', title: '검토할 원고', state: 'research_ready', stateLabel: '근거 준비', view: 'studio', actions: [{ id: 'draft', label: '원고 생성' }] };
  const stage = { id: 'scripts', name: '원고', color: '#123456', items: [item] };
  const space = { stages: [stage], agents: [], layer: 'office', pendingActions: new Set() };
  const data = { source: 'live', error: '실시간 읽기 실패: HTTP 503' };
  const results = { opened: false };
  const workbench = { sourceLabel: method('workbench', 'sourceLabel') };
  const globals = { $, document: { activeElement: null }, space, data, results, workbench, esc: String, fmt: String, fmtTime: String, faceColor() {}, exploration() {}, embed: { enabled: true }, controls: { focusStage() {} } };
  const hud = { cards: new Map(), renderedContent: new WeakMap(), replaceContent: method('hud', 'replaceContent', globals), brainCard: { innerHTML: '' }, pushEvents() {}, openStage: method('hud', 'openStage', globals) };
  const refresh = method('hud', 'refresh', globals);
  const snapshot = { brain: { name: '근거', notes: 1, sources: 1, label: '과거 자료' }, generatedAt: 'last-success', events: [] };
  refresh.call(hud, snapshot);
  assert.equal($('source-pill').textContent, '연결 지연 · 마지막 API 데이터');
  assert.equal($('source-pill').role, 'status');
  hud.openStage('scripts');
  assert.match($('panel-body').innerHTML, /data-action="draft"[^>]* disabled/);
  assert.match($('panel-body').innerHTML, /오피스에서 열기/);
  data.error = null;
  refresh.call(hud, snapshot);
  assert.equal($('source-pill').textContent, '실시간 API');
  assert.doesNotMatch($('panel-body').innerHTML, /data-action="draft"[^>]* disabled/);
  data.source = 'sample-fallback';
  data.error = 'offline';
  hud.openStage('scripts');
  assert.doesNotMatch($('panel-body').innerHTML, /data-action="draft"/);
});
