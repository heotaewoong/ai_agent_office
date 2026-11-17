import test from "node:test";
import assert from "node:assert/strict";
import {readFileSync} from "node:fs";
import {createRequire} from "node:module";
import {renderToStaticMarkup} from "react-dom/server";
import {createElement} from "react";
import ts from "typescript";

const require=createRequire(import.meta.url);
test("파이프라인 초기 화면은 조회 전 상태를 꾸미지 않고 인증 준비 전에 지도를 노출하지 않는다",()=>{
 const source=readFileSync(new URL("../app/pipeline-studio.tsx",import.meta.url),"utf8");
 const compiled=ts.transpileModule(source,{compilerOptions:{module:ts.ModuleKind.CommonJS,jsx:ts.JsxEmit.ReactJSX,target:ts.ScriptTarget.ES2022}}).outputText;
 const calls:string[]=[];
 const module={exports:{} as {PipelineStudio?:()=>ReturnType<typeof createElement>}};
 const localRequire=(id:string)=>{
  if(id==="../lib/api")return {api:{architecture(){calls.push("architecture");throw Error("SSR must not fetch");}}};
  if(id==="./architecture-view")return {ArchitectureView:()=>createElement("div",null,"legacy")};
  if(id==="../lib/workflow")return {formatDate:()=>"date"};
  if(id.endsWith(".css"))return {};
  return require(id);
 };
 Function("require","module","exports",compiled)(localRequire,module,module.exports);
 const html=renderToStaticMarkup(createElement(module.exports.PipelineStudio!));
 assert.match(html,/콘텐츠 파이프라인/);
 assert.match(html,/기획·구현 지도/);assert.match(html,/운영 상세/);
 assert.match(html,/확인 전/);assert.doesNotMatch(html,/0원|<iframe/);
 assert.match(html,/pipeline-map-new-tab/);assert.match(html,/role="tablist"/);
 assert.deepEqual(calls,[]);
});
