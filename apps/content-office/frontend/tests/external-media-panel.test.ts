import test from "node:test";
import assert from "node:assert/strict";
import {readFileSync} from "node:fs";
import {createRequire} from "node:module";
import ts from "typescript";
const nativeRequire=createRequire(import.meta.url);
const source=readFileSync(new URL("../app/external-media-panel.tsx",import.meta.url),"utf8");
const compiled=ts.transpileModule(source,{compilerOptions:{module:ts.ModuleKind.CommonJS,jsx:ts.JsxEmit.ReactJSX}}).outputText;
function nodes(tree:any):any[]{return Array.isArray(tree)?tree.flatMap(nodes):tree?.props?[tree,...nodes(tree.props.children)]:[];}
const job={id:"job_fixture",source_hash:"current",source_packet:{body:"원문",external_media:{version:"external-media-v1",draft_id:"draft_fixture"}},drafts:[]};
function harness(apiOverrides:Record<string,unknown>={}) {
 const values:any[]=[];let index=0;
 const calls:any[]=[];const navigations:string[]=[];
 const api={prepareExternalMedia:async(...args:any[])=>{calls.push(["prepare",...args]);return{};},adoptExternalMedia:async(...args:any[])=>{calls.push(["adopt",...args]);return{};},...apiOverrides};
 const module={exports:{}as any};
 Function("require","exports",compiled)((name:string)=>name==="react"?{useId:()=>"review",useState:(initial:any)=>{const i=index++;if(!(i in values))values[i]=initial;return[values[i],(v:any)=>values[i]=v];}}:name==="../lib/api"?{api}:nativeRequire(name),module.exports);
 const oldWindow=(globalThis as any).window;
 (globalThis as any).window={location:{assign:(url:string)=>navigations.push(url)}};
 return{calls,navigations,render:(props:any={job})=>{index=0;return nodes(module.exports.ExternalMediaPanel(props));},cleanup:()=>{(globalThis as any).window=oldWindow;}};
}
test("초기 렌더는 승인·파일 가져오기 요청을 보내지 않고 체크 전 승인 버튼을 막는다",()=>{
 const h=harness();try{const list=h.render();assert.equal(h.calls.length,0);assert.equal(list.find(n=>n.type==="button").props.disabled,true);assert.equal(list.find(n=>n.type==="input").props.checked,false);assert.ok(list.find(n=>n.type==="video").props.src.endsWith("/drafts/draft_fixture/files/short.mp4"));}finally{h.cleanup();}
});
test("사람 체크 후 클릭한 현재 원고 판본만 승인·연결 요청에 보낸다",async()=>{
 const h=harness();try{h.render().find(n=>n.type==="input").props.onChange({target:{checked:true}});const button=h.render().find(n=>n.type==="button");assert.equal(button.props.disabled,false);button.props.onClick();await new Promise(resolve=>setImmediate(resolve));assert.deepEqual(h.calls,[["adopt","job_fixture",{version:"current",reviewed:true}]]);assert.deepEqual(h.navigations,["/publish?job=job_fixture"]);}finally{h.cleanup();}
});
test("미저장 편집 잠금이면 체크·버튼과 직접 클릭 요청 모두 차단한다",async()=>{
 const h=harness();try{const list=h.render({job,editLocked:true});assert.equal(list.find(n=>n.type==="input").props.disabled,true);const button=list.find(n=>n.type==="button");assert.equal(button.props.disabled,true);button.props.onClick();await new Promise(resolve=>setImmediate(resolve));assert.equal(h.calls.length,0);}finally{h.cleanup();}
});
test("연결 실패는 오류를 남기고 자동 재시도·페이지 이동하지 않는다",async()=>{
 const h=harness({adoptExternalMedia:async()=>{throw new Error("판본 충돌");}});try{h.render().find(n=>n.type==="input").props.onChange({target:{checked:true}});h.render().find(n=>n.type==="button").props.onClick();await new Promise(resolve=>setImmediate(resolve));assert.equal(h.navigations.length,0);assert.equal(h.render().find(n=>n.props.role==="alert").props.children,"판본 충돌");}finally{h.cleanup();}
});
test("이미 연결된 현재 판본은 다시 승인하는 대신 출고② 안내만 보인다",()=>{
 const h=harness();try{const list=h.render({job:{...job,source_approval:{version:"current",decision:"approved"},manifest:{source_hash:"current",hash:"manifest"}}});assert.equal(list.filter(n=>n.type==="button").length,0);assert.ok(list.find(n=>n.props.role==="status"));assert.equal(h.calls.length,0);}finally{h.cleanup();}
});
test("필수 다섯 파일이 없는 일반 편집 초안에는 가져오기 승인을 노출하지 않는다",()=>{
 const h=harness();try{assert.deepEqual(h.render({job:{id:"job_fixture",source_hash:"current",drafts:[{id:"draft_other",assets:[{name:"note.md"}]}]}}),[]);}finally{h.cleanup();}
});
