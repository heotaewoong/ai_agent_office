import test from 'node:test';
import assert from 'node:assert/strict';
import { readFileSync } from 'node:fs';
import { createRequire } from 'node:module';
import { createElement } from 'react';
import { renderToStaticMarkup } from 'react-dom/server';
import ts from 'typescript';
import { api } from '../lib/api.ts';
import * as bridge from '../lib/world-bridge.ts';

function compile(relative: string, replacements: Record<string, unknown> = {}) {
  const url = new URL(relative, import.meta.url);
  const normalRequire = createRequire(url);
  const code = ts.transpileModule(readFileSync(url, 'utf8'), { compilerOptions: {
    module: ts.ModuleKind.CommonJS, jsx: ts.JsxEmit.ReactJSX, target: ts.ScriptTarget.ES2022,
  } }).outputText;
  const result: any = {};
  new Function('require', 'exports', code)((name: string) => replacements[name] ?? normalRequire(name), result);
  return result;
}

test('world embeds the real collapsed report panel using the existing GET adapter without executing actions', () => {
  const realPanel = compile('../app/assistant-reports.tsx').AssistantReports;
  const passed: Array<{ connected: boolean; loadReports: unknown }> = [];
  const world = compile('../app/world-view.tsx', {
    '../lib/api': { api }, '../lib/world-bridge': bridge,
    './assistant-reports': { AssistantReports: (props: { connected: boolean; loadReports: () => Promise<unknown> }) => {
      passed.push(props); return createElement(realPanel, props);
    } },
  }).WorldView;
  let actions = 0;
  for (const connected of [false, true]) {
    const html = renderToStaticMarkup(createElement(world, { connected, activeId: '', busy: false,
      onOpen: () => { actions++; }, onAction: async () => { actions++; },
    }));
    assert.match(html, /비서 협업 보고/);
    assert.match(html, /aria-expanded="false"/);
    assert.match(html, /title="오피스 월드"/);
    assert.match(html, /\/world\/index.html\?api=\/api\/space/);
    assert.equal(passed.at(-1)?.connected, connected);
    assert.equal(passed.at(-1)?.loadReports, api.assistantReports);
  }
  assert.equal(actions, 0);
});
