import test from 'node:test';
import assert from 'node:assert/strict';
import {readFileSync} from 'node:fs';
import {runInNewContext} from 'node:vm';
import ts from 'typescript';
import {includeOpenedJobs} from '../lib/job-filters.ts';
import {officeHref} from '../lib/navigation.ts';

const source = ts.createSourceFile('office-shell.tsx', readFileSync(new URL('../app/office-shell.tsx', import.meta.url), 'utf8'), ts.ScriptTarget.Latest, true, ts.ScriptKind.TSX);
function findCode(predicate: (node: ts.Node) => boolean) {
  let found: ts.Node | undefined;
  function visit(node: ts.Node) { if (predicate(node)) found = node; ts.forEachChild(node, visit); }
  visit(source);
  assert.ok(found);
  const expression = ts.isJsxAttribute(found) && found.initializer && ts.isJsxExpression(found.initializer) ? found.initializer.expression! : found;
  return ts.transpileModule(`(${expression.getText(source)})`, {compilerOptions: {target: ts.ScriptTarget.ES2022}}).outputText;
}

for (const label of ['원고 승인', '이 원고 승인·자동 제작']) test(`${label}: 검수 통과 원고도 작업 시간이 닫히면 자동 제작 승인을 요청할 수 없다`, () => {
  let disabled: ts.Expression | undefined;
  function visit(node: ts.Node) {
    if (ts.isJsxElement(node) && node.children.some(child => ts.isJsxText(child) && child.text.trim() === label)) {
      const attr = node.openingElement.attributes.properties.find(attr => ts.isJsxAttribute(attr) && attr.name.getText(source) === 'disabled');
      if (attr && ts.isJsxAttribute(attr) && attr.initializer && ts.isJsxExpression(attr.initializer)) disabled = attr.initializer.expression;
    }
    ts.forEachChild(node, visit);
  }
  visit(source);
  assert.ok(disabled);
  const code = ts.transpileModule(`(${disabled.getText(source)})`, {}).outputText;
  const context = {locked:false, passed:true, selectionCount:2, approvalIsCurrent:()=>true, approvalVersion:'v1', job:{source_hash:'v1'}, requestBlockedReason:'작업 시간이 종료됐습니다.'};
  assert.equal(runInNewContext(code, context), true);
  assert.equal(runInNewContext(code, {...context, requestBlockedReason:undefined}), false);
});

for (const attribute of ['onCreated', 'onSelected']) test(`${attribute}: 새 작업을 열면 이전 검색 조건을 지우고 응답을 즉시 목록에 보존한다`, () => {
  const state = {jobs: [{id:'old', title:'기존', state:'failed'}], query:'없는 제목', status:'failed', output:'pdf', active:'old', href:''};
  const context = {
    includeOpenedJobs, officeHref,
    setDashboard(update: (current: {jobs: unknown[]}) => {jobs: typeof state.jobs}) {state.jobs = update({jobs:state.jobs}).jobs;},
    clearJobFilters() {state.query='';state.status='all';state.output='all';},
    selectJob(id: string) {state.active=id;},
    router: {push(href: string) {state.href=href;}},
    setView() {}, loadDashboard: async () => {},
  };
  let helper = () => {};
  try {helper = runInNewContext(findCode(node => ts.isFunctionDeclaration(node) && node.name?.text === 'openCreatedJobs'), context);} catch { /* The old handlers have no helper. */ }
  const handler = runInNewContext(findCode(node => ts.isJsxAttribute(node) && node.name.getText(source) === attribute && !!node.initializer && ts.isJsxExpression(node.initializer) && !!node.initializer.expression), {...context, openCreatedJobs: helper});
  handler({id:'new', title:'새 글', state:'research_ready', selections:{blog:true}});
  assert.equal(state.query, '');
  assert.equal(state.status, 'all');
  assert.equal(state.output, 'all');
  assert.deepEqual(state.jobs.map(job => job.id), ['new','old']);
  assert.equal(state.active, 'new');
  assert.equal(state.href, '/scripts/new');
});

test('복수 뉴스 응답의 모든 작업을 보존하고 첫 작업을 열며 기존 작업을 중복 표시하지 않는다', () => {
  let jobs: any[] = [{id:'old', title:'기존 뉴스', state:'research_ready'}, {id:'keep', title:'다른 작업', state:'failed'}];
  let active = '', href = '', cleared = false;
  const open = runInNewContext(findCode(node => ts.isFunctionDeclaration(node) && node.name?.text === 'openCreatedJobs'), {
    includeOpenedJobs, officeHref,
    setDashboard(update: (current: {jobs:any[]}) => {jobs:any[]}) {jobs=update({jobs}).jobs;},
    clearJobFilters() {cleared=true;}, selectJob(id:string) {active=id;}, router:{push(value:string) {href=value;}},
  });
  open([{id:'new', title:'첫 뉴스', state:'research_ready'}, {id:'old', title:'다시 연 뉴스', state:'source_review'}]);
  assert.deepEqual(jobs.map(job=>job.id), ['new','old','keep']);
  assert.equal(jobs[1].title, '다시 연 뉴스');
  assert.equal(active, 'new');
  assert.equal(href, '/scripts/new');
  assert.equal(cleared, true);
});
