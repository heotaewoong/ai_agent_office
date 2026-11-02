import test from 'node:test';
import assert from 'node:assert/strict';
import { readFileSync, existsSync } from 'node:fs';
import { createRequire } from 'node:module';
import { createElement } from 'react';
import { renderToStaticMarkup } from 'react-dom/server';
import ts from 'typescript';

await import('../lib/assistant-requests.ts');
test('central assistant exposes a real bounded input and an explicit native handoff without calling the backend on render', () => {
  const url = new URL('../app/assistant-chat.tsx', import.meta.url);
  assert.ok(existsSync(url), 'actual assistant input must exist');
  const code = ts.transpileModule(readFileSync(url, 'utf8'), { compilerOptions: { module: ts.ModuleKind.CommonJS, jsx: ts.JsxEmit.ReactJSX, target: ts.ScriptTarget.ES2022 } }).outputText;
  const exports: any = {}, require = createRequire(url);
  new Function('require', 'exports', code)(require, exports);
  let calls = 0;
  for (const connected of [true, false]) {
    const html = renderToStaticMarkup(createElement(exports.AssistantChat, { connected, openSignal: 0, createRequest: async () => { calls++; }, loadRequest: async () => { calls++; }, onObservation() {} }));
    assert.match(html, /루미에게 업무 맡기기/);
    assert.match(html, /<dialog/);
    assert.match(html, /<textarea/);
    assert.match(html, /maxLength="4000"/);
    assert.match(html, /원고 승인|사람 승인/);
    assert.doesNotMatch(html, /업무를 완료했습니다/);
  }
  assert.equal(calls, 0);
});
