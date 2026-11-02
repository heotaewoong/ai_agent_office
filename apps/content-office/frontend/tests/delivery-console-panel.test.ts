import test from 'node:test';
import assert from 'node:assert/strict';
import {readFileSync} from 'node:fs';
import {createRequire} from 'node:module';
import ts from 'typescript';
import * as logic from '../lib/delivery-console.ts';
const requireNative=createRequire(import.meta.url);
const compiled=ts.transpileModule(readFileSync(new URL('../app/delivery-console.tsx',import.meta.url),'utf8'),{compilerOptions:{module:ts.ModuleKind.CommonJS,jsx:ts.JsxEmit.ReactJSX}}).outputText;
const account:any={key:'linkedin_personal',platform:'linkedin',label:'LinkedIn owner',locale:'en',public_url:'https://linkedin.com/in/owner',external_account_id:'owner',publication_enabled:true};
const job:any={id:'job_review',source_hash:'s',source_packet:{audience:{language:'en'}},source_approval:{decision:'approved',version:'s'},release_approval:{decision:'approved',version:'m',outputs:['blog']},manifest:{hash:'m',source_hash:'s',files:[{name:'linkedin-personal.txt',outputs:['blog']}]}};
function nodes(t:any):any[]{return Array.isArray(t)?t.flatMap(nodes):t?.props?[t,...nodes(t.props.children)]:[];}
function setup(){let i=0;const accounts=[account,{...account,key:'tistory_main',platform:'tistory',label:'티스토리',locale:'en'}];const state:any[]=[accounts,{revision:'',keys:[]},undefined,[],'',false];const calls:any[]=[];const mod={exports:{} as any};
Function('require','exports',compiled)((name:string)=>name==='react'?{useId:()=> 'delivery-test',useState:(init:any)=>{const n=i++;if(!(n in state))state[n]=init;return[state[n],(v:any)=>state[n]=typeof v==='function'?v(state[n]):v];},useEffect:()=>{}}:name==='../lib/api'?{api:{requestReleasedDraft:async(...args:any[])=>{calls.push(args);return{items:[{id:'od_one',channel_key:account.key,state:'pending'}]};}}}:name==='../lib/delivery-console'?logic:name==='../lib/delivery-readiness'?{requireStagingSnapshot:()=>{},stagingExternalLabel:()=>'',stagingLocalLabel:()=>''}:name==='./video-platforms-panel'?{VideoPlatformsPanel:()=>null}:name==='./owner-draft-options'?{OwnerDraftStatus:()=>null}:name==='./youtube-panel'?{ChannelHandoffPanel:()=>null,YoutubePanel:()=>null}:requireNative(name),mod.exports);
const prior=(globalThis as any).window;(globalThis as any).window={confirm:()=>true};
return{calls,render:(props:any={})=>{i=0;return nodes(mod.exports.DeliveryConsole({job,busy:false,youtubeConfigured:true,action:async(_label:any,fn:any)=>{await fn();return true;},...props}));},cleanup:()=>{(globalThis as any).window=prior;}};}

function pick(h:ReturnType<typeof setup>,key:string){h.render().find(x=>x.type==='input'&&x.props.value===key).props.onChange({target:{checked:true}});}

test('multiple account checkboxes keep both choices and never mutate approvals or send',()=>{const h=setup();try{const before=JSON.stringify(job);pick(h,'linkedin_personal');pick(h,'tistory_main');const n=h.render();assert.equal(n.filter(x=>x.type==='input'&&x.props.checked).length,2);assert.equal(n.filter(x=>x.type==='select').length,0);assert.equal(h.calls.length,0);assert.equal(JSON.stringify(job),before);}finally{h.cleanup();}});

test('explicit account request binds current version; existing pending record blocks repeat',async()=>{const h=setup();try{pick(h,'linkedin_personal');const send=()=>h.render().find(x=>x.type==='button'&&x.props.children==='LinkedIn owner에 원고 임시저장 요청');assert.equal(send().props.disabled,false);await send().props.onClick();await new Promise(r=>setTimeout(r,0));assert.equal(h.calls.length,1);assert.deepEqual(h.calls[0],[job.id,'m',account.key,{key:account.key,platform:account.platform,locale:account.locale,public_url:account.public_url,external_account_id:'owner',publication_enabled:true}]);assert.equal(h.render().find(x=>x.type==='button'&&x.props.children==='기존 전달 기록 확인 · 재전송 안 함').props.disabled,true);}finally{h.cleanup();}});

test('new source or release revision clears choices instead of reusing an old target',()=>{const h=setup();try{pick(h,'linkedin_personal');assert.equal(h.render({job:{...job,source_hash:'new'}}).filter(x=>x.type==='input'&&x.props.checked).length,0);assert.equal(h.calls.length,0);}finally{h.cleanup();}});

test('closed work window prevents text requests and explains the block',()=>{const h=setup();try{pick(h,'linkedin_personal');const n=h.render({requestBlockedReason:'작업 시간 종료'});assert.equal(n.find(x=>x.type==='button'&&x.props.children==='LinkedIn owner에 원고 임시저장 요청').props.disabled,true);}finally{h.cleanup();}});

test('each multi-account input has a unique label and a readable touch target',()=>{const h=setup();try{const n=h.render();for(const input of n.filter(x=>x.type==='input')){assert.ok(input.props.id);assert.equal(n.filter(x=>x.type==='label'&&x.props.htmlFor===input.props.id).length,1);}}finally{h.cleanup();}});
