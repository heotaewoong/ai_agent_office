import test from 'node:test';
import assert from 'node:assert/strict';
import {cardVersionChoices,comparedCardNumbers} from '../lib/card-comparison.ts';
import type {ContentHistory} from '../lib/version-history.ts';
const history={job_id:'job-a',sources:[],productions:[{created_at:'2026-10-30T00:00:00Z',current:true,approved_before:true,manifest:{hash:'manifest-a',source_hash:'source-a',files:[{id:'asset-a',name:'card-01.png',kind:'image',url:'/api/artifacts/asset_a',sha256:'hash-a'},{id:'asset-b',name:'card-03.png',kind:'image',url:'/api/artifacts/asset_b'}]}}],drafts:[{id:'draft-a',job_id:'job-a',title:'검토',body:'본문',status:'draft',source_hash_snapshot:'source-old',assets:[{name:'card-01.png',media_type:'image/png',sha256:'hash-d',size:10},{name:'card-02.png',media_type:'image/png',sha256:'hash-e',size:20}]}]} as ContentHistory;
test('제작물과 검토본은 실제 파일·독립 원고 해시·승인 기록을 유지하고 장 번호 합집합으로 비교한다',()=>{
  const before=JSON.stringify(history),[a,b]=cardVersionChoices(history);
  assert.equal(a.sourceHash,'source-a');assert.match(a.approval,/과거 출고 승인/);
  assert.equal(b.sourceHash,'source-old');assert.match(b.approval,/검토본/);
  assert.equal(b.cards[0].url,'/api/jobs/job-a/drafts/draft-a/files/card-01.png');
  assert.deepEqual(comparedCardNumbers(a,b),[1,2,3]);
  assert.equal(a.cards.find(c=>c.number===2),undefined);
  assert.equal(JSON.stringify(history),before);
});
test('다른 파일·외부 URL·중복 장 번호를 임의로 이미지로 채택하지 않는다',()=>{
  const fixture=JSON.parse(JSON.stringify(history)) as ContentHistory;
  fixture.productions[0].manifest.files.push({id:'remote',name:'card-04.png',kind:'image',url:'https://external.example/tracker.png'},{id:'duplicate',name:'card-01.png',kind:'image',url:'/api/artifacts/duplicate'},{id:'thumb',name:'thumbnail.png',kind:'image',url:'/api/artifacts/thumb'});
  const [a]=cardVersionChoices(fixture);
  assert.deepEqual(a.ambiguous,[1]);assert.deepEqual(a.cards.map(c=>c.number),[3]);
});
test('보관 카드가 없는 이력에 과거 판본을 만들어 넣지 않는다',()=>{
  assert.deepEqual(cardVersionChoices({job_id:'empty',sources:[],productions:[],drafts:[]}),[]);
  assert.deepEqual(comparedCardNumbers(),[]);
});

