import test from 'node:test';
import assert from 'node:assert/strict';
import {readFileSync} from 'node:fs';
import {createRequire} from 'node:module';
import ts from 'typescript';

const require = createRequire(import.meta.url);
const compiled = ts.transpileModule(readFileSync(new URL('../app/owner-draft-options.tsx', import.meta.url), 'utf8'), {
  compilerOptions: {module: ts.ModuleKind.CommonJS, jsx: ts.JsxEmit.ReactJSX},
}).outputText;

test('Instagram 대기는 승인 이동만 안내하고 이미 저장된 채널의 재전송·승인·예약 버튼을 만들지 않는다', () => {
  const items = [
    {id:'ig', channel_key:'instagram_main', state:'office_held', reason:'현재 글·미디어의 출고 승인②가 필요합니다'},
    {id:'yt', channel_key:'youtube_main_ko', state:'platform_private'},
    {id:'li', channel_key:'linkedin_personal', state:'platform_draft'},
    {id:'th', channel_key:'threads_main', state:'platform_draft'},
    {id:'ti', channel_key:'tistory_main', state:'platform_draft'},
    {id:'nv', channel_key:'naver_blog_main', state:'platform_draft'},
  ];
  let cursor = 0;
  const modules: Record<string, unknown> = {
    react: {useState: () => [cursor++ === 0 ? {items} : '', () => {}], useEffect: () => {}},
    '../lib/api': {api: new Proxy({}, {get: () => {throw new Error('렌더에서 API 작업 금지');}})},
    '../lib/delivery-console': {hostStatusLine: () => 'PC 실행기 연결됨'},
  };
  const module = {exports: {} as {OwnerDraftStatus: (props: any) => any}};
  Function('require', 'module', 'exports', compiled)((name: string) => modules[name] ?? require(name), module, module.exports);
  const tree = module.exports.OwnerDraftStatus({jobId:'job-review'});
  const nodes: any[] = [];
  const text = (value: any): string => {
    if (Array.isArray(value)) return value.map(text).join('');
    if (value?.props) {nodes.push(value); return text(value.props.children);}
    return typeof value === 'string' ? value : '';
  };
  const content = text(tree);
  assert.match(content, /오피스 게시 대기 · 최종 승인② 전 전달 안 함/);
  assert.match(content, /이미 저장된 채널은 다시 보내지 않습니다/);
  assert.match(content, /플랫폼 비공개 확인/);
  assert.equal(nodes.filter(n => n.type === 'button').length, 1);
  assert.equal(nodes.find(n => n.type === 'a').props.href, '/publish?job=job-review#delivery-release-job-review');
  assert.equal(nodes.filter(n => n.type === 'li').length, 6);
});
