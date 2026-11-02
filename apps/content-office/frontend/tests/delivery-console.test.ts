import {test} from 'node:test';
import assert from 'node:assert/strict';
import {choiceReadiness, platformChoices} from '../lib/delivery-console.ts';
const job:any={source_hash:'s',source_packet:{audience:{language:'en'}},source_approval:{decision:'approved',version:'s'},manifest:{hash:'m',source_hash:'s',files:[{name:'short.mp4',outputs:['video']},{name:'linkedin-personal.txt',outputs:['blog']}]},release_approval:{decision:'approved',version:'m',outputs:['video','blog']}};
const account:any={key:'linkedin_personal',platform:'linkedin',label:'LinkedIn',locale:'en',public_url:'https://linkedin.com/in/example',publication_enabled:true};
test('current released text can be explicitly requested without changing approvals',()=>{const before=JSON.stringify(job);assert.equal(choiceReadiness(job,account,'draft').ok,true);assert.equal(JSON.stringify(job),before);});
test('missing release, wrong language and stale manifest are blocked',()=>{assert.equal(choiceReadiness({...job,release_approval:null},account,'draft').ok,false);assert.equal(choiceReadiness(job,{...account,locale:'ko'},'draft').ok,false);assert.equal(choiceReadiness({...job,manifest:{...job.manifest,source_hash:'old'}},account,'draft').ok,false);});
test('unregistered TikTok and unsupported Instagram draft never look ready',()=>{assert.ok(platformChoices.includes('tiktok'));assert.equal(choiceReadiness(job,undefined,'draft').ok,false);assert.equal(choiceReadiness(job,{...account,platform:'instagram'},'draft').ok,false);assert.equal(choiceReadiness(job,{...account,platform:'tiktok'},'draft').ok,false);});
test('wrong output and missing current file cannot be requested',()=>{assert.equal(choiceReadiness({...job,release_approval:{...job.release_approval,outputs:['video']}},account,'draft').ok,false);assert.equal(choiceReadiness({...job,manifest:{...job.manifest,files:[]}},account,'draft').ok,false);});
test('office mode is explicitly local and requires no remote action',()=>{assert.equal(choiceReadiness(job,undefined,'office').ok,true);assert.match(choiceReadiness(job,undefined,'office').reason,/EC2/);});

test('Naver uses the real registry platform id and approved text file',()=>{assert.ok((platformChoices as readonly string[]).includes('naver_blog'));const n={...account,key:'naver_blog_main',platform:'naver_blog'};const j={...job,manifest:{...job.manifest,files:[{name:'naver.txt',outputs:['blog']}]}};assert.equal(choiceReadiness(j,n,'draft').ok,true);});

test('host status line says plainly when the owner PC runner is off, so a pending delivery is not mistaken for progress',async()=>{
 const {hostStatusLine}=await import('../lib/delivery-console.ts');
 const now=Date.parse('2026-11-02T13:00:00Z');
 assert.match(hostStatusLine({online:false,last_seen:null},now),/한 번도 접속하지 않았/);
 assert.match(hostStatusLine({online:false,last_seen:'2026-11-01T10:41:02Z'},now),/꺼져 있/);
 assert.match(hostStatusLine({online:false,last_seen:'2026-11-01T10:41:02Z'},now),/26시간 전/);
 assert.match(hostStatusLine({online:true,last_seen:'2026-11-02T12:59:30Z'},now),/연결됨/);
 assert.equal(hostStatusLine(undefined,now),'');
});
