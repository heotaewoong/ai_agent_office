import { readFile } from 'node:fs/promises';
import assert from 'node:assert/strict';
import { test } from 'node:test';

const source = await readFile(new URL('../app.js', import.meta.url), 'utf8');
function literal(name) {
  const start = source.indexOf('  const ' + name + ' = {'), end = source.indexOf('\n  };', start);
  assert(start >= 0 && end > start, name + ' must exist');
  return source.slice(source.indexOf('{', start), end + 4);
}
const unescape = text => text.replace(/&quot;/g, '"').replace(/&#39;/g, "'").replace(/&lt;/g, '<').replace(/&gt;/g, '>').replace(/&amp;/g, '&');
const esc = value => String(value).replace(/[&<>"']/g, c => ({ '&': '&amp;', '<': '&lt;', '>': '&gt;', '"': '&quot;', "'": '&#39;' }[c]));

function fixture() {
  const document = { activeElement: null, body: null };
  class Element {
    constructor(tag = 'div') {
      this.tagName = tag.toUpperCase(); this.dataset = {}; this.children = []; this.parentNode = null;
      this.disabled = false; this.hidden = false; this.textContent = ''; this.scrollTop = 0;
      this.htmlWrites = 0; this.nodeWrites = 0; this.focusCalls = 0;
      this.style = { setProperty() {} }; this.classList = { toggle() {} };
    }
    contains(node) { for (; node; node = node.parentNode) if (node === this) return true; return false; }
    detachChildren() {
      if (document.activeElement !== this && this.contains(document.activeElement)) document.activeElement = document.body;
      this.children.forEach(child => { child.parentNode = null; }); this.children = []; this.scrollTop = 0;
    }
    set innerHTML(html) {
      this.detachChildren(); this.htmlWrites++;
      this.markup = html.replace(/ disabled(?=>)/g, ' disabled=""');
      for (const match of html.matchAll(/<(button|a|input|select|video)\b([^>]*)>/g)) {
        const child = new Element(match[1]);
        for (const attr of match[2].matchAll(/([\w-]+)(?:="([^"]*)")?/g)) {
          const value = unescape(attr[2] || '');
          if (attr[1].startsWith('data-')) child.dataset[attr[1].slice(5).replace(/-([a-z])/g, (_, c) => c.toUpperCase())] = value;
          if (attr[1] === 'disabled') child.disabled = true;
        }
        this.append(child);
      }
    }
    get innerHTML() { return this.markup ?? this.children.map(child => child.tagName + child.textContent + child.innerHTML).join('|'); }
    append(...children) { for (const child of children) { child.parentNode = this; this.children.push(child); } }
    replaceChildren(...children) { this.detachChildren(); this.nodeWrites++; this.markup = undefined; this.append(...children); }
    querySelectorAll(selector) {
      const all = this.children.flatMap(child => [child, ...child.querySelectorAll(selector)]);
      return selector === '[data-focus-key]' ? all.filter(child => child.dataset.focusKey !== undefined) : all;
    }
    focus(options) { if (!this.disabled && !this.hidden) { document.activeElement = this; this.focusCalls++; this.focusOptions = options; } }
    setAttribute(name, value) { this[name] = value; }
  }
  document.body = new Element('body'); document.activeElement = document.body;
  document.createElement = tag => new Element(tag);
  const elements = new Map(), $ = id => { if (!elements.has(id)) elements.set(id, new Element()); return elements.get(id); };
  $('roster-search').value = ''; $('roster-attention').checked = false;
  const item = { id: 'job_1', title: '원고', state: 'research_ready', stateLabel: '근거 준비', view: 'studio', actions: [{ id: 'draft', label: '원고 생성' }] };
  const stage = { id: 'scripts', name: '원고 작업실', color: '#123456', approval: '① 원고', items: [item] };
  const agent = { id: 'editor', name: '편집', status: 'idle', stageId: 'scripts', engine: '앱 작업자', model: '', task: '대기' };
  const snapshot = { generatedAt: '2026-10-30T05:00:00+09:00', stages: [stage], agents: [agent], brain: { name: '근거', notes: 1, sources: 1, label: '과거 자료' }, events: [] };
  const space = { stages: snapshot.stages, agents: snapshot.agents, data: snapshot, layer: 'office', pendingActions: new Set(), selectedStage: null };
  const data = { source: 'live', error: null }, results = { opened: false }, hud = {}, workbench = {};
  const globals = { $, document, space, data, results, hud, workbench, esc, fmt: String, fmtTime: String, faceColor: () => '#123456', statusLabel: s => s,
    exploration() {}, embed: { enabled: true }, controls: { focusStage() {}, focusHub() {} } };
  const make = name => Function(...Object.keys(globals), 'return (' + literal(name) + ')')(...Object.values(globals));
  Object.assign(hud, make('hud')); Object.assign(workbench, make('workbench'));
  hud.brainCard = new Element('button'); hud.pushEvents = () => {};
  return { $, document, Element, hud, workbench, space, data, results, snapshot, stage, agent };
}

test('unchanged stage polls preserve the same button, focus and scroll position', () => {
  const f = fixture(), body = f.$('panel-body');
  f.hud.openStage('scripts');
  const button = body.children.find(node => node.dataset.open === 'studio');
  button.focus(); body.scrollTop = 75;
  const writes = body.htmlWrites;
  f.snapshot.generatedAt = '2026-10-30T05:00:10+09:00';
  f.hud.refresh(f.snapshot);
  assert.equal(body.htmlWrites, writes);
  assert.equal(f.document.activeElement, button);
  assert.equal(body.children.includes(button), true);
  assert.equal(body.scrollTop, 75);
});

test('changed stage state is rendered while the same safe action retains keyboard focus', () => {
  const f = fixture(), body = f.$('panel-body');
  f.hud.openStage('scripts');
  const old = body.children.find(node => node.dataset.open === 'studio'); old.focus();
  f.stage.items[0].stateLabel = '새 검수 결과';
  f.hud.refresh(f.snapshot);
  const current = body.children.find(node => node.dataset.open === 'studio');
  assert.notEqual(current, old);
  assert.match(body.innerHTML, /새 검수 결과/);
  assert.equal(f.document.activeElement, current);
  assert.equal(current.focusOptions.preventScroll, true);
});

test('refresh never steals focus outside the changed panel and does not focus a removed or disabled action', () => {
  const f = fixture(), body = f.$('panel-body');
  f.hud.openStage('scripts');
  const search = f.$('roster-search'); search.focus();
  f.stage.items[0].title = '새 제목'; f.hud.refresh(f.snapshot);
  assert.equal(f.document.activeElement, search);
  body.children.find(node => node.dataset.action === 'draft').focus();
  f.data.error = '연결 지연'; f.hud.refresh(f.snapshot);
  assert.equal(f.document.activeElement, f.document.body);
  assert.equal(body.children.find(node => node.dataset.action === 'draft').disabled, true);
  body.children.find(node => node.dataset.open === 'studio').focus();
  f.stage.items = []; f.hud.refresh(f.snapshot);
  assert.equal(f.document.activeElement, f.document.body);
});

test('roster timestamp polls retain DOM identity and focus; real status changes update and preserve the matching agent', () => {
  const f = fixture(), list = f.$('roster-list'), panel = f.$('roster-panel');
  const replace = list.replaceChildren.bind(list);
  list.replaceChildren = (...nodes) => { panel.scrollTop = 0; replace(...nodes); };
  f.workbench.refresh(f.snapshot);
  const old = list.children[0].children.at(-1); old.focus(); panel.scrollTop = 120;
  const writes = list.nodeWrites;
  f.snapshot.generatedAt = '2026-10-30T05:00:10+09:00';
  f.workbench.refresh(f.snapshot);
  assert.equal(list.nodeWrites, writes);
  assert.equal(f.document.activeElement, old);
  f.agent.status = 'waiting'; f.agent.task = '원고 검토 필요';
  f.workbench.refresh(f.snapshot);
  const current = list.children[0].children.at(-1);
  assert.notEqual(current, old);
  assert.equal(f.document.activeElement, current);
  assert.equal(list.children[0].children[1].textContent, 'waiting');
  assert.equal(list.children[0].children[3].textContent, '원고 검토 필요');
  assert.equal(panel.scrollTop, 120);
});

test('roster filters preserve search input and outside focus while removed agents do not regain focus', () => {
  const f = fixture(), list = f.$('roster-list'), search = f.$('roster-search');
  f.workbench.refresh(f.snapshot);
  search.focus(); search.value = '일치하지 않는 검색어';
  f.workbench.refresh(f.snapshot);
  assert.equal(search.value, '일치하지 않는 검색어');
  assert.equal(f.document.activeElement, search);
  assert.equal(list.children[0].textContent, '조건에 맞는 동료가 없습니다.');
  search.value = ''; f.workbench.refresh(f.snapshot);
  list.children[0].children.at(-1).focus();
  f.snapshot.agents = []; f.workbench.refresh(f.snapshot);
  assert.equal(f.document.activeElement, f.document.body);
});

test('results view keeps its selected job and media nodes through unrelated projection polling', () => {
  const f = fixture(), body = f.$('panel-body');
  f.hud.openStage('scripts');
  f.results.opened = true;
  body.innerHTML = '<select id="result-job"></select><video></video>';
  const [select, video] = body.children;
  select.value = 'job_2'; video.currentTime = 17; video.paused = false; select.focus();
  const writes = body.htmlWrites;
  f.hud.refresh(f.snapshot);
  assert.equal(body.htmlWrites, writes);
  assert.equal(select.value, 'job_2'); assert.equal(video.currentTime, 17); assert.equal(video.paused, false);
  assert.equal(f.document.activeElement, select);
  f.results.opened = false;
  f.hud.openStage('scripts');
  assert.match(body.innerHTML, /원고/);
  assert.equal(body.children.includes(video), false);
});

test('footer feedback updates retain its own focus without recreating the content body', () => {
  const f = fixture(), body = f.$('panel-body'), foot = f.$('panel-foot');
  f.hud.openStage('scripts');
  const old = foot.children[0]; old.focus();
  const bodyWrites = body.htmlWrites;
  f.space.embedResult = { ok: false, message: '요청 상태를 확인하세요' };
  f.hud.refresh(f.snapshot);
  assert.equal(body.htmlWrites, bodyWrites);
  assert.match(foot.innerHTML, /요청 상태를 확인하세요/);
  assert.notEqual(foot.children[0], old);
  assert.equal(f.document.activeElement, foot.children[0]);
});

test('focus keys handle quoted identifiers but never choose ambiguous or different jobs', () => {
  const quoted = fixture(), body = quoted.$('panel-body');
  quoted.stage.items[0].id = 'job_"quoted]';
  quoted.hud.openStage('scripts');
  body.children.find(node => node.dataset.open === 'studio').focus();
  quoted.stage.items[0].title = '수정된 제목'; quoted.hud.refresh(quoted.snapshot);
  assert.equal(quoted.document.activeElement, body.children.find(node => node.dataset.open === 'studio'));

  const duplicate = fixture(), duplicateBody = duplicate.$('panel-body');
  duplicate.stage.items.push({ ...duplicate.stage.items[0] }); duplicate.hud.openStage('scripts');
  duplicateBody.children.find(node => node.dataset.open === 'studio').focus();
  duplicate.stage.items[0].title = '수정'; duplicate.hud.refresh(duplicate.snapshot);
  assert.equal(duplicate.document.activeElement, duplicate.document.body);

  const changed = fixture(), changedBody = changed.$('panel-body');
  changed.hud.openStage('scripts'); changedBody.children.find(node => node.dataset.open === 'studio').focus();
  changed.stage.items[0].id = 'another_job'; changed.hud.refresh(changed.snapshot);
  assert.equal(changed.document.activeElement, changed.document.body);
});
