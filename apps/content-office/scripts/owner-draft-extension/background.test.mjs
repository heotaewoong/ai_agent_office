import test from 'node:test';
import assert from 'node:assert/strict';

async function run(items, channel) {
 let listener;
 const calls=[];
 const state={enabled:true,connectionCheckedAt:Date.now()};
 globalThis.chrome={
  runtime:{id:'test',getManifest:()=>({version:'0.1.0'}),onInstalled:{addListener(){}},onStartup:{addListener(){}},onMessage:{addListener(fn){listener=fn;}},async sendNativeMessage(host,msg){calls.push(msg.command);if(msg.command==='poll')return {ok:true,items};throw Error('unexpected mutation');}},
  storage:{local:{async get(){return state;},async set(patch){Object.assign(state,patch);}}},
  alarms:{create(){},onAlarm:{addListener(){}}},
 };
 await import(`./background.mjs?case=${Math.random()}`);
 await new Promise(resolve=>listener(channel?{command:'verify-channel',channel}:{command:'run'},{id:'test'},resolve));
 return {state,calls};
}
test('대기 초안이 없으면 검증 완료 대신 승인·채널 선택 대기를 표시',async()=>{
 const {state,calls}=await run([],'linkedin_personal');
 assert.equal(state.results[0]?.state,'no_approved_pending_draft');
 assert.deepEqual(calls,['poll']);
});
test('미구현 Instagram은 초안을 점유하지 않고 지원 확인 대기 표시',async()=>{
 const item={id:'od_'+'a'.repeat(24),content_hash:'b'.repeat(64),channel_key:'instagram_main',account_id:'titan.bears',text:'synthetic approved text',visibility:'draft',authorized_end:'2099-01-01T00:00:00Z'};
 const {state,calls}=await run([item],'instagram_main');
 assert.equal(state.results[0]?.state,'adapter_not_implemented');
 assert.deepEqual(calls,['poll']);
});
