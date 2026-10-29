import { readFile } from 'node:fs/promises';
import assert from 'node:assert/strict';
import { test } from 'node:test';
const source=await readFile(new URL('../app.js',import.meta.url),'utf8');
const start=source.indexOf('  const results = {'),end=source.indexOf('\n  };',start);
assert(start>=0 && end>start,'results implementation must exist');
const literal=source.slice(source.indexOf('{',start),end+4);
const escLine=source.split('\n').find(line=>line.startsWith('  const esc = ')).trim();
const esc=Function('return ('+escLine.slice('const esc = '.length,-1)+')')();
const H='a'.repeat(64),OTHER='b'.repeat(64),PRIVATE='PRIVATE_SENTINEL_DO_NOT_EXPOSE';
const job=(id='job_1',extra={})=>({id,title:'작업 '+id,state:'complete',source_hash:H,manifest:{hash:OTHER,source_hash:H,files:[]},...extra});
const response=(body,status=200,type='application/json')=>new Response(JSON.stringify(body),{status,headers:{'Content-Type':type}});
function fixture(options={}){
  const elements=new Map(),classes=new Set(),requests=[];
  const $=id=>{if(!elements.has(id))elements.set(id,{textContent:'',innerHTML:'',hidden:false,attributes:{},setAttribute(k,v){this.attributes[k]=v;},querySelectorAll(){return [];},focus(){}});return elements.get(id);};
  const data={apiUrl:Object.hasOwn(options,'apiUrl')?options.apiUrl:'/api/space'},location=new URL('https://office.test/world/index.html?api=/api/space');
  const controls={keys:new Set(['w']),dragging:true,setVehicleSpeed(){},setView(){}},world={syncs:0,syncRendering(){this.syncs++;}},space={};
  const document={body:{classList:{add:c=>classes.add(c),remove:c=>classes.delete(c)}},addEventListener(){}};
  const fetch=(url,init)=>{requests.push({url,init});return options.fetch?options.fetch(url,init):Promise.resolve(response({jobs:[]}));};
  const results=Function('data','location','fetch','AbortController','setTimeout','clearTimeout','$','esc','controls','world','space','document','workshop','workbench','hud','return ('+literal+')')
    (data,location,fetch,AbortController,setTimeout,clearTimeout,$,esc,controls,world,space,document,{opened:false},{setRoster(){}},{closePanel(){}});
  const actualRender=results.render;let renders=0;results.render=()=>{renders++;};results.opened=true;
  return {results,data,location,requests,elements,$,controls,world,space,classes,actualRender,get renders(){return renders;}};
}
function deferredFixture(){
  const pending=[];
  const f=fixture({fetch:(url,init)=>new Promise((resolve,reject)=>pending.push({url,init,resolve,reject,settled:false}))});
  const reply=(i,body,status=200,type='application/json')=>{pending[i].settled=true;pending[i].resolve(response(body,status,type));};
  return {...f,pending,reply,drain(){for(const p of pending)if(!p.settled){p.settled=true;p.resolve(response({jobs:[]}));}}};
}
function deepKeys(value){return value&&typeof value==='object'?Object.keys(value).flatMap(k=>[k,...deepKeys(value[k])]):[];}

test('result endpoints require the exact same-origin space API and never enable artifact routes',()=>{
  const f=fixture(),r=f.results;
  assert.equal(r.endpoint('list'),'https://office.test/api/dashboard');
  assert.equal(r.endpoint('job','j_1-2'),'https://office.test/api/jobs/j_1-2');
  assert.equal(r.endpoint('deliveries','j'),'https://office.test/api/jobs/j/deliveries');
  assert.equal(r.endpoint('draft','j','d_1'),'https://office.test/api/jobs/j/drafts/d_1/preview');
  for(const kind of ['artifact','delete','approve','publish','zip','__proto__'])assert.equal(r.endpoint(kind,'j','d'),null);
  for(const value of [null,'https://evil.test/api/space','https://office.test.evil.test/api/space','https://u:p@office.test/api/space','http://office.test/api/space','/api/space/','/api/%73pace','/data/space.json','javascript:alert(1)','data:application/json,{}','file:///api/space','blob:https://office.test/id']){
    f.data.apiUrl=value;assert.equal(r.endpoint('list'),null,String(value));
  }
  f.data.apiUrl='https://office.test/api/space?ignored=https://evil.test#ignored';assert.equal(r.endpoint('list'),'https://office.test/api/dashboard');
});

test('route identifiers reject schemes, traversal, encoding, HTML and oversized or non-string input',()=>{
  const r=fixture().results;
  for(const id of ['',null,1,{},'a'.repeat(129),'../x','x/y','x\\y','x%2fy','javascript:alert(1)','<img>','x y','x?y','x#y','한글','\nx']){
    assert.equal(r.endpoint('job',id),null,String(id));assert.equal(r.endpoint('draft','good',id),null,String(id));
  }
  assert(r.endpoint('job','A'.repeat(128)));assert(r.endpoint('job','__proto__'));
});

test('summary only retains bounded metadata and strips private bodies, paths, URLs, actors and synthetic run identifiers',()=>{
  const r=fixture().results;
  const raw=job('j',{title:'t'.repeat(250),body:PRIVATE,evidence:PRIVATE,path:PRIVATE,payload:PRIVATE,url:PRIVATE,actor:PRIVATE,run_id:PRIVATE,attempt_id:PRIVATE,
    manifest:{hash:H.toUpperCase(),source_hash:OTHER,body:PRIVATE,files:[{id:'f_1',kind:'video',sha256:H,outputs:['youtube',{},PRIVATE.slice(0,0)],path:PRIVATE,url:PRIVATE,body:PRIVATE,payload:PRIVATE}]},
    source_approval:{id:'approval_1',version:H,decision:'approved',created_at:'2026-10-30T00:00:00Z',actor:PRIVATE,evidence:PRIVATE},
    release_approval:{id:'not-exposed',version:OTHER,decision:'rejected',created_at:'2026-10-30T00:01:00Z',outputs:['youtube',{}],actor:PRIVATE}});
  const s=r.summary(raw);
  assert.deepEqual(Object.keys(s).sort(),['id','title','state','sourceHash','manifestHash','manifestSourceHash','sourceApproval','releaseApproval','files'].sort());
  assert.equal(s.title.length,200);assert.equal(s.manifestHash,H);assert.equal(s.releaseApproval.id,null);assert.deepEqual(s.releaseApproval.outputs,['youtube']);
  assert.deepEqual(Object.keys(s.files[0]).sort(),['id','kind','sha256','outputs'].sort());
  for(const key of ['body','evidence','path','payload','url','actor','run_id','attempt_id'])assert(!deepKeys(s).includes(key));
  assert(!JSON.stringify(s).includes(PRIVATE));assert.equal(r.summary({id:'../invalid'}),null);assert.equal(r.summary(null),null);
});

test('malformed metadata is bounded without inventing approvals, hashes, run IDs or a publication result',()=>{
  const r=fixture().results;
  const raw=job('j',{title:{html:'x'},source_hash:'not-a-sha',source_approval:null,release_approval:null,manifest:{hash:12,source_hash:H+'x',files:Array.from({length:100},()=>({id:'../bad',kind:{},sha256:'x',outputs:Array(25).fill('z'.repeat(90))}))}});
  const s=r.summary(raw);assert.equal(s.title,'j');assert.equal(s.sourceHash,null);assert.equal(s.manifestHash,null);assert.equal(s.manifestSourceHash,null);
  assert.equal(s.sourceApproval,null);assert.equal(s.releaseApproval,null);assert.equal(s.files.length,80);assert.equal(s.files[0].id,null);
  assert.equal(s.files[0].outputs.length,20);assert(s.files[0].outputs.every(v=>v.length===60));assert.equal(r.match(null,null),'버전 미제공');
  const d=r.detail({...raw,tasks:[{id:'task',kind:'video',state:'complete',run_id:PRIVATE,attempt_id:PRIVATE,body:PRIVATE},{id:'../bad'}],drafts:[{id:'draft',title:'text',version:'1',created_at:'time',body:PRIVATE},{id:'../bad'}]},null);
  assert.deepEqual(Object.keys(d).sort(),['job','tasks','drafts','deliveries','deliveryError'].sort());
  assert.equal(d.tasks.length,1);assert.deepEqual(Object.keys(d.tasks[0]).sort(),['id','kind','state','createdAt','updatedAt'].sort());
  assert.equal(d.drafts.length,1);assert.equal(d.drafts[0].version,null);assert.deepEqual(d.deliveries,[]);assert.equal(d.deliveryError,true);
  assert(!JSON.stringify(d).includes(PRIVATE));assert.throws(()=>r.detail({id:'../invalid'},{}));
});

test('delivery records remain separate from completed tasks and missing or failed ledger data is explicit',()=>{
  const r=fixture().results,raw=job('j',{tasks:[{id:'t',state:'complete'}]});
  const empty=r.detail(raw,{deliveries:[]});assert.equal(empty.deliveryError,false);assert.deepEqual(empty.deliveries,[]);
  assert.equal(empty.job.sourceApproval,null);assert.equal(empty.job.releaseApproval,null);
  const d=r.detail(raw,{deliveries:[{state:'uploaded',visibility:'unlisted',privacy_status:'private',updated_at:'time',url:PRIVATE,body:PRIVATE,actor:PRIVATE}]});
  assert.deepEqual(d.deliveries,[{state:'uploaded',visibility:'unlisted',privacyStatus:'private',updatedAt:'time'}]);
  assert(!JSON.stringify(d).includes(PRIVATE));assert.equal(r.detail(raw,{}).deliveryError,true);
});

test('rendering escapes hostile text and exposes only a safe draft preview and review app link',()=>{
  const f=fixture(),r=f.results,attack='<img src=x onerror="alert(1)"><script>alert(2)</script>';
  const raw=job('job_ok',{title:attack,state:attack,manifest:{hash:H,source_hash:H,files:[{id:'html_file',kind:attack,sha256:OTHER,outputs:[attack],url:'javascript:alert(9)',path:PRIVATE}]},drafts:[{id:'draft_ok',title:attack,version:2}],tasks:[{id:'task_ok',kind:attack,state:attack}]});
  r.jobs=[r.summary(raw)];r.current=r.detail(raw,{deliveries:[{state:attack,privacy_status:attack}]});r.selectedId='job_ok';r.listAt=new Date().toISOString();r.detailAt=r.listAt;
  f.actualRender.call(r);
  const html=f.$('panel-body').innerHTML+f.$('panel-foot').innerHTML;
  assert(!/<(?:script|img|iframe)\b/i.test(html));assert(html.includes('&lt;img'));assert(!html.includes(PRIVATE));assert(!html.includes('/artifacts/'));
  const hrefs=[...html.matchAll(/href="([^"]+)"/g)].map(m=>m[1]);
  assert.deepEqual(hrefs,['https://office.test/api/jobs/job_ok/drafts/draft_ok/preview','https://office.test/']);
  assert.equal(f.requests.length,0);assert(html.includes('별도 run/attempt ID는 미제공'));assert(html.includes('선택값·출력별 승인 유효성'));
});

test('sample mode and unsupported load kinds never fetch or fabricate a successful result',async()=>{
  const f=fixture({apiUrl:null}),r=f.results;assert.equal(await r.load(),false);assert.equal(f.requests.length,0);assert.deepEqual(r.jobs,[]);assert.equal(r.current,null);assert.equal(r.listAt,null);assert(r.error);
  f.data.apiUrl='/api/space';for(const kind of ['artifact','deliveries','draft','approve','publish'])assert.equal(await r.load(kind,'job'),false);
  assert.equal(f.requests.length,0);assert.deepEqual(r.jobs,[]);
});

test('every data request is a non-cached same-origin GET and HTTP 401 or unexpected content cannot become empty success',async()=>{
  for(const [status,type,body]of [[401,'application/json',{jobs:[]}],[503,'application/json',{jobs:[]}],[200,'text/html',{jobs:[]}],[200,'application/json',{}],[200,'application/json',null]]){
    const f=fixture({fetch:async()=>response(body,status,type)}),r=f.results;assert.equal(await r.load(),false);assert(r.error);assert.equal(r.listAt,null);assert.deepEqual(r.jobs,[]);
    assert.equal(f.requests.length,1);const init=f.requests[0].init;assert.equal(init.method,'GET');assert.equal(init.credentials,'same-origin');assert.equal(init.cache,'no-store');assert.equal(init.redirect,'error');assert(init.signal instanceof AbortSignal);
  }
});

test('a successful list deduplicates validated jobs and a later failure retains a clearly stale prior observation',async()=>{
  let fail=false;const f=fixture({fetch:async()=>fail?response({},401):response({jobs:[job('good'),job('good',{title:'duplicate'}),{id:'../invalid'},job('second')]})}),r=f.results;
  assert.equal(await r.load(),true);assert.deepEqual(r.jobs.map(j=>j.id),['good','second']);assert(r.listAt);const stamp=r.listAt;
  fail=true;assert.equal(await r.load(),false);assert.equal(r.listAt,stamp);assert.deepEqual(r.jobs.map(j=>j.id),['good','second']);
  f.actualRender.call(r);assert(f.$('panel-body').innerHTML.includes('목록은 마지막 조회 기록입니다.'));
});

test('an older list response cannot overwrite a newer response even if the fetch ignores abortion',async()=>{
  const f=deferredFixture(),r=f.results,first=r.load(),second=r.load();
  try{assert.equal(f.pending.length,2);assert.equal(f.pending[0].init.signal.aborted,true);
    f.reply(1,{jobs:[job('new')]});assert.equal(await second,true);f.reply(0,{jobs:[job('old')]});assert.equal(await first,false);
    assert.deepEqual(r.jobs.map(j=>j.id),['new']);assert.equal(r.loading,false);assert.equal(r.controller,null);
  }finally{f.drain();await Promise.allSettled([first,second]);}
});

test('an older job and ledger pair cannot replace a newer selection and each task retains its original ID',async()=>{
  const f=deferredFixture(),r=f.results,first=r.load('job','old'),second=r.load('job','new');
  try{assert.equal(f.pending.length,4);assert(f.pending[0].init.signal.aborted);assert(f.pending[1].init.signal.aborted);
    f.reply(2,job('new',{tasks:[{id:'original_task',kind:'video',state:'running'}]}));f.reply(3,{deliveries:[]});assert.equal(await second,true);
    f.reply(0,job('old'));f.reply(1,{deliveries:[{state:'uploaded'}]});assert.equal(await first,false);
    assert.equal(r.selectedId,'new');assert.equal(r.current.job.id,'new');assert.equal(r.current.tasks[0].id,'original_task');assert.deepEqual(r.current.deliveries,[]);
  }finally{f.drain();await Promise.allSettled([first,second]);}
});

test('closing aborts the active request, resumes the world, and ignores late responses',async()=>{
  const f=deferredFixture(),r=f.results,pending=r.load('job','j');
  try{r.close();assert.equal(r.opened,false);assert.equal(r.loading,false);assert.equal(r.controller,null);assert.equal(f.space.resultsOpen,false);assert.equal(f.world.syncs,1);assert.equal(f.controls.keys.size,0);assert.equal(f.controls.dragging,false);assert(f.pending.every(v=>v.init.signal.aborted));
    f.reply(0,job('j'));f.reply(1,{deliveries:[]});assert.equal(await pending,false);assert.equal(r.current,null);assert.equal(r.detailAt,null);assert.equal(f.$('panel').hidden,true);
  }finally{f.drain();await Promise.allSettled([pending]);}
});

test('a failed ledger is explicit while a wrong job identity or failed job never becomes a valid detail',async()=>{
  for(const mode of ['ledger-failed','job-failed','wrong-job']){
    const f=fixture({fetch:async url=>url.endsWith('/deliveries')?(mode==='ledger-failed'?response({},401):response({deliveries:[]})):(mode==='job-failed'?response({},401):response(job(mode==='wrong-job'?'other':'wanted')))}),r=f.results;
    const ok=await r.load('job','wanted');
    if(mode==='ledger-failed'){assert.equal(ok,true);assert.equal(r.current.job.id,'wanted');assert.equal(r.current.deliveryError,true);assert.deepEqual(r.current.deliveries,[]);}
    else{assert.equal(ok,false);assert.equal(r.current,null);assert.equal(r.detailAt,null);assert(r.error);}
    assert(f.requests.every(v=>v.init.method==='GET'));
  }
});


test('JSON parsing failures expose a generic error without leaking parser message or response body',async()=>{
  const secret='SECRET_BODY_SENTINEL';
  const f=fixture({fetch:async()=>({ok:true,status:200,headers:new Headers({'content-type':'application/json'}),json:async()=>{throw new Error(secret);}})}),r=f.results;
  assert.equal(await r.load(),false);assert.match(r.error,/조회 데이터 형식/);assert(!r.error.includes(secret));
  assert.deepEqual(r.jobs,[]);assert.equal(r.current,null);assert.equal(r.listAt,null);assert.equal(r.loading,false);
  f.actualRender.call(r);const html=f.$('panel-body').innerHTML+f.$('panel-foot').innerHTML;
  assert(!html.includes(secret));assert(html.includes('조회 데이터 형식'));assert.equal(f.requests.length,1);
});
