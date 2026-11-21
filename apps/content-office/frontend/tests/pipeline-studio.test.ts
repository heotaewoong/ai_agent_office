import test from "node:test";
import assert from "node:assert/strict";
import {readFileSync} from "node:fs";
import {createRequire} from "node:module";
import {renderToStaticMarkup} from "react-dom/server";
import {createElement} from "react";
import ts from "typescript";

const require=createRequire(import.meta.url);
function renderStudio(snapshot?:Record<string,unknown>) {
 const source=readFileSync(new URL("../app/pipeline-studio.tsx",import.meta.url),"utf8").replace(/\r\n/g,"\n");
 const compiled=ts.transpileModule(source,{compilerOptions:{module:ts.ModuleKind.CommonJS,jsx:ts.JsxEmit.ReactJSX,target:ts.ScriptTarget.ES2022}}).outputText;
 const calls:string[]=[];
 const module={exports:{} as {PipelineStudio?:()=>ReturnType<typeof createElement>}};
 const localRequire=(id:string)=>{
  if(id==="react" && snapshot) {const react=require(id);return {...react,useState:(initial:unknown)=>react.useState(initial===null?snapshot:initial)};}
  if(id==="../lib/api")return {api:{architecture(){calls.push("architecture");throw Error("SSR must not fetch");}}};
  if(id==="./architecture-view")return {ArchitectureView:()=>createElement("div",null,"legacy")};
  if(id==="../lib/workflow")return {formatDate:()=>"date"};
  if(id.endsWith(".css"))return {};
  return require(id);
 };
 Function("require","module","exports",compiled)(localRequire,module,module.exports);
 const html=renderToStaticMarkup(createElement(module.exports.PipelineStudio!));
 return {html,calls};
}

test("파이프라인 초기 화면은 조회 전 상태를 꾸미지 않고 인증 준비 전에 지도를 노출하지 않는다",()=>{
 const {html,calls}=renderStudio();
 assert.match(html,/콘텐츠 파이프라인/);
 assert.match(html,/기획·구현 지도/);assert.match(html,/운영 상세/);
 assert.match(html,/확인 전/);assert.doesNotMatch(html,/0원|<iframe/);
 assert.match(html,/pipeline-map-new-tab/);assert.match(html,/role="tablist"/);
 assert.deepEqual(calls,[]);
});

const snapshot=(worker:Record<string,unknown>)=>({window:{status:"closed"},worker,budget:{remaining_krw:-17194.4,cap_krw:0},git:{commit:"20bbd8e"}});

test("음수 장부 잔액은 보존하고 사용 가능 예산은 0원으로 표시한다",()=>{
 const data=snapshot({state:"stopped"});const before=JSON.stringify(data);
 const {html}=renderStudio(data);
 assert.match(html,/<dt>사용 가능 예산<\/dt><dd>0원<\/dd>/);
 assert.match(html,/한도 0원 · 장부 잔액 -17,194원/);
 assert.equal(JSON.stringify(data),before);
});

for(const [name,heartbeat] of [["오래된 기록",new Date(Date.now()-180000).toISOString()],["잘못된 시각","not-a-date"],["미래 시각",new Date(Date.now()+60000).toISOString()]] as const) {
 test(`${name}의 online 상태는 최근 상태 미확인으로 표시한다`,()=>{
  const {html}=renderStudio(snapshot({state:"online",heartbeat}));
  assert.match(html,/<dd>최근 상태 미확인<\/dd>/);
  assert.match(html,/마지막 기록: 온라인 · /);
 });
}

test("최근의 정상 heartbeat가 있는 online 기록만 온라인 기록으로 표시한다",()=>{
 const {html}=renderStudio(snapshot({state:"online",heartbeat:new Date(Date.now()-10000).toISOString()}));
 assert.match(html,/<dd>온라인 기록<\/dd>/);
 assert.match(html,/마지막 기록: 온라인 · /);
});

function callbackFromSource(start:string,end:string) {
 const source=readFileSync(new URL("../app/pipeline-studio.tsx",import.meta.url),"utf8").replace(/\r\n/g,"\n");
 const from=source.indexOf(start);assert.ok(from>=0);const to=source.indexOf(end,from);assert.ok(to>from);
 return source.slice(from+start.length,to);
}

test("브라우저 전체화면 거부는 같은 지도 확대보기로 전환하고 닫기는 API 재호출 없이 복귀한다",async()=>{
 const body=callbackFromSource("  const toggleFullscreen=async()=>{","  const windowStatus=").replace(/};\s*$/,"}");
 const factory=Function("document","canvas","expanded","setFullscreenError","setExpanded","return async()=>{"+body);
 const states:boolean[]=[],messages:string[]=[];let calls=0;
 const target={requestFullscreen:async()=>{calls++;throw Error("denied");}};
 await factory({fullscreenElement:null},{current:target},false,(message:string)=>messages.push(message),(value:boolean)=>states.push(value))();
 assert.deepEqual(states,[true]);assert.match(messages.at(-1)!,/확대보기로 전환/);assert.equal(calls,1);
 states.length=0;
 await factory({fullscreenElement:null},{current:target},true,()=>{},(value:boolean)=>states.push(value))();
 assert.deepEqual(states,[false]);assert.equal(calls,1);
});

test("확대보기 Escape와 정리는 iframe 이벤트·배경 inert·스크롤·초점을 복구한다",()=>{
 const body=callbackFromSource("  useEffect(()=>{\n    if(!expanded || !canvas.current)return;","  },[expanded,mapLoaded]);");
 const code=ts.transpileModule("module.exports=()=>{if(!expanded || !canvas.current)return;"+body+"};",{compilerOptions:{target:ts.ScriptTarget.ES2022,module:ts.ModuleKind.CommonJS}}).outputText;
 class Element {parentElement:Element|null=null;children:Element[]=[];inert=false;style={overflow:"auto"};}
 const bodyEl=new Element(),container=new Element(),target=new Element(),outside=new Element(),previouslyInert=new Element();
 container.parentElement=bodyEl;target.parentElement=container;container.children=[target,previouslyInert];previouslyInert.inert=true;bodyEl.children=[container,outside];
 const documentHandlers=new Map<string,(event:unknown)=>void>(),frameHandlers=new Map<string,(event:unknown)=>void>();
 const events=(handlers:Map<string,(event:unknown)=>void>)=>({addEventListener:(type:string,handler:(event:unknown)=>void)=>handlers.set(type,handler),removeEventListener:(type:string)=>handlers.delete(type)});
 const doc={body:bodyEl,...events(documentHandlers)},inside=events(frameHandlers),states:boolean[]=[];let focus=0,prevented=0,stopped=0;
 const module={exports:null as null|(()=>()=>void)};
 Function("module","expanded","canvas","document","HTMLElement","frame","fullscreenButton","requestAnimationFrame","cancelAnimationFrame","setExpanded","setFullscreenError",code)(module,true,{current:target},doc,Element,{current:{contentDocument:inside}},{current:{isConnected:true,focus(){focus++;}}},()=>1,()=>{},(state:boolean)=>states.push(state),()=>{});
 const cleanup=module.exports!();
 assert.equal(outside.inert,true);assert.equal(bodyEl.style.overflow,"hidden");assert.ok(frameHandlers.has("keydown"));
 frameHandlers.get("keydown")!({key:"Escape",preventDefault(){prevented++;},stopImmediatePropagation(){stopped++;}});
 assert.deepEqual(states,[false]);assert.equal(prevented,1);assert.equal(stopped,1);
 cleanup();assert.equal(outside.inert,false);assert.equal(previouslyInert.inert,true);assert.equal(bodyEl.style.overflow,"auto");assert.equal(focus,1);assert.equal(documentHandlers.size,0);assert.equal(frameHandlers.size,0);
});
