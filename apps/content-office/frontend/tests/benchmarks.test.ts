import test from 'node:test';
import assert from 'node:assert/strict';
import { filterBenchmarkItems, filterBenchmarkSources, filterBenchmarkIdeas, groupBenchmarkSources, splitBenchmarkDates, parseBenchmarkFields, benchmarkPublicUrl, registeredBenchmarkItems, type BenchmarkItem, type BenchmarkSource } from '../lib/benchmarks.ts';

const sources: BenchmarkSource[] = [
  { id: 'ig-one', creator_id: 'one', name: '한 크리에이터', platform: 'instagram', url: 'https://www.instagram.com/one/', fields: ['AI 활용'] },
  { id: 'yt-one', creator_id: 'one', name: '한 크리에이터 유튜브', platform: 'youtube', url: 'https://www.youtube.com/@one', fields: ['공부법'] },
  { id: 'web-two', creator_id: 'two', name: '두 번째', platform: 'website', url: 'https://example.org/', fields: ['AI 활용'] },
];
const row = (id: string, platform: string, fields: string[], published_at: string | null): BenchmarkItem => ({ id, title: `${id} 회의록 활용`, url: `https://example.org/${id}`, source_id: id, creator_id: id, source_name: id, platform, fields, published_at, checked_at: '2026-11-06T01:00:00Z', summary: '공개 설명', verification_state: 'unverified', idea_angle: '기획 제안' });

test('분야·출처 플랫폼·검색을 함께 적용하고 입력 목록을 바꾸지 않는다', () => {
  const rows = [row('a', 'instagram', ['AI 활용'], null), row('b', 'youtube', ['AI 활용'], null), row('c', 'instagram', ['공부법'], null)];
  assert.deepEqual(filterBenchmarkItems(rows, { field: 'AI 활용', platform: 'instagram', query: '회의록' }).map(item => item.id), ['a']);
  assert.deepEqual(filterBenchmarkItems(rows, { field: 'all', platform: 'all', query: '없는 검색' }), []);
  assert.deepEqual(rows.map(item => item.id), ['a', 'b', 'c']);
});

test('경쟁사 소식은 등록 출처만 남기고 공식 뉴스의 동일 원문을 정규화해 제외한다', () => {
  const rows = [
    { ...row('fallback', 'website', [], null), source_id: '', url: 'https://example.org/official' },
    { ...row('duplicate', 'website', [], null), url: 'https://www.example.org/post/?utm_source=mail#summary' },
    { ...row('youtube-copy', 'youtube', [], null), url: 'https://youtu.be/video-one?si=share' },
    { ...row('different', 'website', [], null), url: 'https://example.org/post?id=2' },
    { ...row('same-post', 'website', [], null), url: 'https://example.org/post?id=2#other' },
  ];
  const result = registeredBenchmarkItems(rows, ['https://example.org/post', 'https://www.youtube.com/watch?v=video-one&feature=share', 'https://example.org/post?id=1']);
  assert.deepEqual(result.map(item => item.id), ['different']);
  assert.equal(rows.length, 5);
});

test('같은 크리에이터의 여러 플랫폼을 하나로 묶고 원래 source를 보존한다', () => {
  const groups = groupBenchmarkSources(sources);
  assert.equal(groups.length, 2);
  assert.deepEqual(groups[0].sources.map(source => source.id), ['ig-one', 'yt-one']);
  assert.equal(sources.length, 3);
});

test('기획 조사 조건은 출처의 분야·플랫폼·이름으로 좁히고 등록 원본을 보존한다', () => {
  assert.deepEqual(filterBenchmarkSources(sources, { field: 'AI 활용', platform: 'instagram', query: '한 크리에이터' }).map(source => source.id), ['ig-one']);
  assert.deepEqual(filterBenchmarkSources(sources, { field: 'all', platform: 'youtube', query: '두 번째' }), []);
  assert.equal(sources.length, 3);
});

test('미래·미상·잘못된 발행일은 최신 소식과 분리하고 확인일로 순서를 꾸미지 않는다', () => {
  const rows = [row('old', 'youtube', [], '2026-11-01T00:00:00Z'), row('missing', 'youtube', [], null), row('future', 'youtube', [], '2026-11-07T00:00:00Z'), row('new', 'youtube', [], '2026-11-05T00:00:00Z'), row('invalid', 'youtube', [], 'not-a-date')];
  const result = splitBenchmarkDates(rows, Date.parse('2026-11-06T01:00:00Z'));
  assert.deepEqual(result.dated.map(item => item.id), ['new', 'old']);
  assert.deepEqual(result.undated.map(item => item.id), ['missing', 'future', 'invalid']);
});

test('아이디어의 출처 플랫폼 필터는 게시 대상 플랫폼과 혼동하지 않는다', () => {
  const ideas = [{ id: 'idea-a', title: '첫 소재', state: 'candidate' as const, source_url: sources[0].url, source_id: 'ig-one', fields: ['AI 활용'], target_platforms: ['youtube'], angle: '', score: 0, outlier_band: 'unknown', reasons: [], blocked: [] }];
  assert.equal(filterBenchmarkIdeas(ideas, sources, { field: 'AI 활용', platform: 'instagram', query: '' }).length, 1);
  assert.equal(filterBenchmarkIdeas(ideas, sources, { field: 'all', platform: 'youtube', query: '' }).length, 0);
});

test('출처를 바꾸거나 삭제해도 저장 시점의 아이디어 플랫폼을 보존한다', () => {
  const ideas = [{ id: 'saved', title: '저장한 소재', state: 'candidate' as const, source_url: sources[0].url, source_id: 'ig-one', platform: 'instagram', fields: ['AI 활용'], target_platforms: ['youtube'], score: 0, outlier_band: 'unknown', reasons: [], blocked: [] }];
  const changed = sources.map(source => ({ ...source, platform: 'youtube' }));
  for (const registry of [changed, []]) {
    assert.equal(filterBenchmarkIdeas(ideas, registry, { field: 'all', platform: 'instagram', query: '' }).length, 1);
    assert.equal(filterBenchmarkIdeas(ideas, registry, { field: 'all', platform: 'youtube', query: '' }).length, 0);
  }
});

test('분야 입력은 중복을 제거하되 빈 값·개수·길이 상한을 지킨다', () => {
  assert.deepEqual(parseBenchmarkFields(' AI 활용,공부법\nAI 활용 '), ['AI 활용', '공부법']);
  assert.throws(() => parseBenchmarkFields(' , '), /분야/);
  assert.throws(() => parseBenchmarkFields('a,b,c,d,e,f,g'), /6/);
  assert.throws(() => parseBenchmarkFields('가'.repeat(31)), /30/);
});

test('원문 링크에 HTTPS 공개 주소만 허용한다', () => {
  assert.equal(benchmarkPublicUrl('https://www.instagram.com/one/'), 'https://www.instagram.com/one/');
  for (const url of ['javascript:alert(1)', 'http://example.org/', 'https://user:pass@example.org/', 'https://localhost/', 'https://127.0.0.1/', 'https://[::1]/', 'https://10.1.2.3/', 'https://example.local/']) assert.equal(benchmarkPublicUrl(url), null);
});
