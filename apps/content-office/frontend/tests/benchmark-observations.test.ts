import test from 'node:test';
import assert from 'node:assert/strict';
import { benchmarkMetricText, benchmarkCollectionText, benchmarkFreshnessText, sortBenchmarkReactions, type BenchmarkItem, type BenchmarkMetric } from '../lib/benchmarks.ts';

const metric = (value: number | null, precision: BenchmarkMetric['precision'] = 'exact', raw_text = '', availability: BenchmarkMetric['availability'] = 'observed'): BenchmarkMetric => ({ value, precision, raw_text, availability });
const item = (id: string, platform: string, value: number | null): BenchmarkItem => ({ id, platform, title: id, url: 'https://example.org/' + id, source_id: id, creator_id: id, source_name: id, fields: [], published_at: '2026-11-06T00:00:00Z', checked_at: '2026-11-07T00:00:00Z', summary: '', verification_state: 'metadata_only', idea_angle: '', metrics: { likes: metric(value) } });

test('비표시·미확인 반응을 실제 0과 구분한다', () => {
  assert.equal(benchmarkMetricText(metric(0)), '0');
  assert.equal(benchmarkMetricText(metric(null, 'unknown', '', 'not_visible')), '비표시');
  assert.equal(benchmarkMetricText(metric(null, 'unknown', '', 'unknown')), '미확인');
  assert.equal(benchmarkMetricText(undefined), '미확인');
  assert.equal(benchmarkMetricText(metric(NaN)), '미확인');
});

test('축약 숫자의 원문과 근사 여부를 유지한다', () => {
  assert.equal(benchmarkMetricText(metric(5800, 'approximate', '5.8천')), '5.8천 (근사)');
  assert.equal(benchmarkMetricText(metric(5800, 'approximate')), '5,800 (근사)');
  assert.equal(benchmarkMetricText(metric(761)), '761');
});

test('브라우저 관측을 API·영상 본문 검증 완료로 표시하지 않는다', () => {
  const base = item('a', 'instagram', 1);
  assert.equal(benchmarkCollectionText(base), '수집 방식 미확인');
  assert.equal(benchmarkCollectionText({ ...base, provenance: { method: 'browser_public_observation', source_url: base.url, observed_at: base.checked_at, capture_sha256: 'a'.repeat(64), scope: '프로필 첫 세 게시물' } }), '연결 브라우저 관측');
  assert.equal(benchmarkCollectionText({ ...base, provenance: { method: 'youtube_rss', source_url: base.url, observed_at: base.checked_at, capture_sha256: null, scope: '공개 RSS' } }), 'YouTube 공개 RSS');
});

test('오늘 관측해도 오래된 글은 과거 게시물이고 날짜 미상은 그대로다', () => {
  const now = Date.parse('2026-11-07T00:00:00Z'), base = item('a', 'instagram', 1);
  assert.equal(benchmarkFreshnessText({ ...base, published_at: '2026-10-25T08:01:29Z' }, now), '과거 게시물 · 7일 초과');
  assert.equal(benchmarkFreshnessText({ ...base, published_at: null }, now), '발행일 확인 필요');
  assert.equal(benchmarkFreshnessText({ ...base, published_at: '2026-11-08T00:00:00Z' }, now), '발행일 확인 필요');
  assert.equal(benchmarkFreshnessText(base, now), '최근 7일 게시물');
});

test('같은 플랫폼의 관측 반응만 비교하며 누락값은 뒤로 보낸다', () => {
  const rows = [item('unknown', 'instagram', null), item('zero', 'instagram', 0), item('higher', 'instagram', 761)];
  assert.deepEqual(sortBenchmarkReactions(rows, 'instagram', 'likes').map(r => r.id), ['higher', 'zero', 'unknown']);
  assert.deepEqual(rows.map(r => r.id), ['unknown', 'zero', 'higher']);
});

test('전체 플랫폼 또는 섞인 단위에서는 인기 순위를 만들지 않는다', () => {
  const rows = [item('youtube', 'youtube', 1), item('instagram', 'instagram', 200)];
  assert.deepEqual(sortBenchmarkReactions(rows, 'all', 'likes').map(r => r.id), ['youtube', 'instagram']);
  assert.deepEqual(sortBenchmarkReactions(rows, 'instagram', 'likes').map(r => r.id), ['youtube', 'instagram']);
});
