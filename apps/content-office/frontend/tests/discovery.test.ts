import test from 'node:test';
import assert from 'node:assert/strict';
import { signalLabels, researchSourceLabels } from '../lib/discovery.ts';

test('source counters keep distinct units and never label missing values as zero or growth', () => {
  assert.deepEqual(signalLabels({youtube_views:123,hn_points:4,hn_comments:null,unknown:'secret'}),['누적 조회 123','HN 점수 4']);
  assert.deepEqual(signalLabels({search_volume_label:'10K+'}),['근사 검색량 10K+']);
  assert.equal(researchSourceLabels.community,'HN 커뮤니티 반응');
});
