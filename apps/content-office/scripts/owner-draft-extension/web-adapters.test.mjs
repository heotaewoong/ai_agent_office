import test from 'node:test';
import assert from 'node:assert/strict';
import vm from 'node:vm';
import {readFileSync} from 'node:fs';

async function verifyBlog(body = 'approved body') {
 let listener;
 const title={value:'approved title'};
 const content={innerText:body};
 const location=new URL('https://onethingflow.tistory.com/manage/newpost/?draftId=12345');
 const document={querySelector(selector){
  if(selector==='#post-title-inp')return title;
  if(selector==='#editor-tistory_ifr')return {contentDocument:{body:content}};
  return null;
 }};
 const context={location,document,chrome:{runtime:{id:'fixture',onMessage:{addListener(fn){listener=fn;}}}}};
 vm.runInNewContext(readFileSync(new URL('./web-adapters.js',import.meta.url),'utf8'),context);
 const item={id:'od_'+'a'.repeat(24),channel_key:'tistory_main',visibility:'draft',
  authorized_end:'2099-01-01T00:00:00Z',title:'approved title',text:'approved body'};
 return new Promise(resolve=>listener({kind:'verify-nonpublic',item},{id:'fixture'},resolve));
}

test('재열기 증거는 사무실 ID로 만든 주소 대신 실제 확인한 플랫폼 주소다',async()=>{
 const answer=await verifyBlog();
 assert.equal(answer.verified,true);
 assert.equal(answer.external_id,'https://onethingflow.tistory.com/manage/newpost/?draftId=12345');
 assert.equal(answer.external_id.includes('/draft/od_'),false);
});

test('재열기 본문이 바뀌면 실제 주소가 있어도 저장 완료로 보내지 않는다',async()=>{
 const answer=await verifyBlog('different body');
 assert.equal(answer.verified,false);
 assert.equal(answer.state,'blocked');
});
