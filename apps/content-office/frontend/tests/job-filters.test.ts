import test from 'node:test';
import assert from 'node:assert/strict';
import {filterJobs,jobFilterStates} from '../lib/job-filters.ts';
const jobs = [{id:'one',title:'ＡＩ 카드뉴스',state:'source_review',output_kinds:['cards','blog']},{id:'two',title:'영상 기획',state:'failed',output_kinds:['video']},{id:'old',title:'이전 작업',state:'custom'}];
test('검색은 전각·대소문자를 정규화하고 상태·제작 종류를 함께 적용한다', () => {
  assert.deepEqual(filterJobs(jobs,' ai ','source_review','cards').map(j=>j.id),['one']);
  assert.deepEqual(filterJobs(jobs,'','failed','video').map(j=>j.id),['two']);
  assert.equal(filterJobs(jobs,'영상','all','cards').length,0);
});
test('미지정·미확인 상태도 찾고 원본과 순서를 보존한다', () => {
  const before=JSON.stringify(jobs);
  assert.deepEqual(filterJobs(jobs,'','all','unspecified').map(j=>j.id),['old']);
  assert.deepEqual(filterJobs(jobs,'','all','all'),jobs);
  assert.equal(JSON.stringify(jobs),before);
});
test('실시간 갱신으로 마지막 해당 작업의 상태가 바뀌어도 선택한 상태 옵션은 유지한다',()=>{
  assert.deepEqual(jobFilterStates([{id:'a',title:'작업',state:'source_review'}],'failed'),['failed','source_review']);
  assert.deepEqual(jobFilterStates([], 'failed'),['failed']);
});

import { includeOpenedJobs, prioritizeActiveJob } from '../lib/job-filters.ts';
test('뉴스에서 다시 연 오래된 작업은 현재 작업으로 맨 위에 표시하고 원본 목록을 보존한다',()=>{
 const rows=[...jobs],pinned=prioritizeActiveJob(rows,'old');
 assert.deepEqual(pinned.map(x=>x.id),['old','one','two']);assert.deepEqual(rows,jobs);
});
test('생성 응답의 작업은 즉시 목록에 반영하고 같은 ID를 중복 표시하지 않는다',()=>{
 const opened:any={id:'old',title:'같은 뉴스의 기존 작업',state:'research_ready',selections:{blog:true,video:true,cards:false},source_packet:null};
 const merged=includeOpenedJobs(jobs,[opened]);assert.deepEqual(merged.map(x=>x.id),['old','one','two']);assert.deepEqual(merged[0].output_kinds,['blog','video']);
 assert(!('source_packet' in merged[0]));assert.equal(jobs[2].title,'이전 작업');
});
