import test from 'node:test';
import assert from 'node:assert/strict';
import vm from 'node:vm';
import fs from 'node:fs';
const source=fs.readFileSync(new URL('./owner-browseros-adapters.js',import.meta.url),'utf8');
const item={channel_key:'tistory_main',account_id:'onethingflow.tistory.com',title:'New title',text:'New body',visibility:'draft',authorized_end:'2099-01-01T00:00:00Z',target:{public_url:'https://onethingflow.tistory.com'}};
function context(overrides={}){
 const elements={};const document={querySelector:selector=>elements[selector]||null,querySelectorAll:()=>[],body:{innerText:''},...overrides.document};
 return {document,location:{href:'https://onethingflow.tistory.com/manage/newpost/',hostname:'onethingflow.tistory.com',pathname:'/manage/newpost/'},URL,Date,setTimeout,...overrides};
}
const run=(ctx,operation,patch={})=>vm.runInNewContext('('+source+')',ctx)({operation,item:{...item,...patch}});
test('unimplemented Instagram never queries or clicks a page',async()=>{
 const ctx=context({document:{querySelector(){throw Error('must not inspect')}}});
 assert.equal((await run(ctx,'fill',{channel_key:'instagram_main'})).reason,'instagram_held');
});
test('public and expired payloads stop before page interaction',async()=>{
 const ctx=context({document:{querySelector(){throw Error('must not inspect')}}});
 assert.equal((await run(ctx,'fill',{visibility:'public'})).reason,'public_or_expired');
 assert.equal((await run(ctx,'save',{authorized_end:'2000-01-01'})).reason,'public_or_expired');
});
test('cross-account blog host cannot be used',async()=>{
 const ctx=context({location:{href:'https://other.tistory.com/manage/newpost/',hostname:'other.tistory.com',pathname:'/manage/newpost/'}});
 assert.equal((await run(ctx,'inspect')).reason,'account_unverified');
});
test('unknown operation never clicks a control',async()=>{
 const ctx=context();
 assert.equal((await run(ctx,'publish')).ok,false);
});
test('nonempty body prevents even the empty title from being changed',async()=>{
 let writes=0;
 const title={value:'',tagName:'TEXTAREA',focus(){writes++;}};
 const body={innerText:'Existing native draft',focus(){writes++;}};
 const ctx=context({document:{querySelector:s=>s==='#post-title-inp'?title:s==='#editor-tistory_ifr'?{contentDocument:{body}}:null,querySelectorAll:()=>[]}});
 const result=await run(ctx,'fill');
 assert.equal(result.reason,'existing_native_draft');
 assert.equal(writes,0);
 assert.equal(title.value,'');
});
test('Naver account link is checked as a normalized URL including protocol-relative hrefs',async()=>{
 const node=text=>({cloneNode:()=>({textContent:text,querySelectorAll:()=>[]})});
 const title=node('Title'),body=node('Body');
 const link={href:'https://admin.blog.naver.com/oneflowwhy',getClientRects:()=>[{}]};
 const ctx=context({location:{hostname:'blog.naver.com',pathname:'/oneflowwhy/postwrite'},document:{
  querySelector:s=>s==='.se-documentTitle'?{}:s==='.se-documentTitle .se-text-paragraph'?title:null,
  querySelectorAll:s=>s==='a[href]'?[link]:s==='.se-component.se-text .se-text-paragraph'?[body]:[]
 }});
 const result=await run(ctx,'inspect',{channel_key:'naver_blog_main',account_id:'oneflowwhy'});
 assert.equal(result.ok,true);
 assert.equal(result.text,'Body');
});
