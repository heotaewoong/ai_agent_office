import test from 'node:test';
import assert from 'node:assert/strict';
import {readFileSync} from 'node:fs';
import {createRequire} from 'node:module';
import ts from 'typescript';
const nativeRequire=createRequire(import.meta.url);
const compiled=ts.transpileModule(readFileSync(new URL('../app/youtube-panel.tsx',import.meta.url),'utf8'),{compilerOptions:{module:ts.ModuleKind.CommonJS,jsx:ts.JsxEmit.ReactJSX}}).outputText;
function nodes(tree:any):any[]{return Array.isArray(tree)?tree.flatMap(nodes):tree?.props?[tree,...nodes(tree.props.children)]:[];}
function render(records:any[],key:string){let index=0;const channels=[{key:'youtube_main_ko',label:'한국어',locale:'ko'},{key:'youtube_english',label:'영어',locale:'en'}];const state=[records,'',channels,key];const mod={exports:{} as any};
 Function('require','exports',compiled)((name:string)=>name==='react'?{useState:()=>[state[index++],()=>{}],useCallback:(f:any)=>f,useEffect:()=>{}}:name==='../lib/api'?{api:{}}:name==='../lib/settings'?{canReconcile:()=>true,studioUrl:()=>null}:name==='../lib/channels'?{localeLabel:(v:any)=>v}:name==='../lib/delivery-readiness'?{youtubePreflight:()=>({ok:true,reason:'ready'}),packetLanguage:()=>null,sourceChannelMismatch:()=>null,deliveryRecordLabel:(r:any)=>r.state}:name==='../lib/workflow'?{formatDate:()=>''}:name==='./icons'?{Icon:()=>null}:nativeRequire(name),mod.exports);
 return nodes(mod.exports.YoutubePanel({job:{id:'job',tasks:[]},busy:false,youtubeConfigured:true,preferredChannelKey:key,action:async()=>true}));
}

test('another YouTube account pending record does not block or appear under the selected account',()=>{
 const n=render([{id:'one',channel_key:'youtube_main_ko',state:'pending_owner',title:'다른 계정 대기'}],'youtube_english');
 assert.equal(n.find(x=>x.type==='button'&&x.props.children==='비공개로 올리기').props.disabled,false);
 assert.equal(n.some(x=>x.type==='span'&&x.props.children==='다른 계정 대기'),false);
});
test('the selected account pending record blocks duplicate upload and remains visible',()=>{
 const n=render([{id:'one',channel_key:'youtube_main_ko',state:'pending_owner',title:'현재 계정 대기'}],'youtube_main_ko');
 assert.equal(n.find(x=>x.type==='button'&&x.props.children==='비공개로 올리기').props.disabled,true);
 assert.equal(n.some(x=>x.type==='span'&&x.props.children==='현재 계정 대기'),true);
});
test('legacy unknown account records still block until reconciled rather than guessing the target',()=>{
 const n=render([{id:'legacy',state:'unknown',title:'계정 미확인'}],'youtube_english');
 assert.equal(n.find(x=>x.type==='button'&&x.props.children==='비공개로 올리기').props.disabled,true);
});
