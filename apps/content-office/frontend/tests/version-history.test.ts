import test from 'node:test';
import assert from 'node:assert/strict';
import {changedLineCounts,comparisonChoices,type ContentHistory} from '../lib/version-history.ts';

test('comparison handles repeated lines and CRLF without inventing deletions',()=>{
  assert.deepEqual(changedLineCounts('a\r\na\r\nb','a\nb\nc'),{added:1,removed:1});
  assert.deepEqual(changedLineCounts('a\nb','b\na'),{added:0,removed:0});
});
test('current source and improved draft remain separate comparison targets',()=>{
  const choices=comparisonChoices({sources:[{id:'s',current:true,packet:{title:'현재',body:'old'}}],drafts:[{id:'d',title:'개선',body:'new'}]} as ContentHistory);
  assert.equal(choices.length,2);
  assert.match(choices[0].label,/현재 원고/);
  assert.equal(choices[1].body,'new');
  assert.notEqual(choices[0].id,choices[1].id);
});
