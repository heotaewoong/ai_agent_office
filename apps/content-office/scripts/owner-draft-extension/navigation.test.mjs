import test from 'node:test';
import assert from 'node:assert/strict';
import {readyPage} from './navigation.mjs';

test('이미 로딩된 탭도 준비 완료로 처리하고 리스너 제거',async()=>{
 const listeners=new Set();
 globalThis.chrome={tabs:{onUpdated:{addListener:f=>listeners.add(f),removeListener:f=>listeners.delete(f)},get:async()=>({status:'complete'})}};
 await readyPage(1);
 assert.equal(listeners.size,0);
});
test('새로고침 완료가 즉시 와도 감지하며 다른 탭 완료는 무시',async()=>{
 const listeners=new Set();let finished=false;
 globalThis.chrome={tabs:{onUpdated:{addListener:f=>listeners.add(f),removeListener:f=>listeners.delete(f)},get:async()=>({status:'loading'})}};
 const p=readyPage(1,async()=>{for(const f of listeners)f(2,{status:'complete'});await Promise.resolve();assert.equal(finished,false);for(const f of listeners)f(1,{status:'complete'});});
 await p.then(()=>{finished=true;});assert.equal(listeners.size,0);
});
test('탭 접근 실패 때 대기하지 않고 정리 후 실패',async()=>{
 const listeners=new Set();
 globalThis.chrome={tabs:{onUpdated:{addListener:f=>listeners.add(f),removeListener:f=>listeners.delete(f)},get:async()=>{throw Error('tab closed');}}};
 await assert.rejects(readyPage(1),/tab closed/);assert.equal(listeners.size,0);
});
