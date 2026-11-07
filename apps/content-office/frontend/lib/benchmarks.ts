import type { Idea } from './types';

export type BenchmarkSource = { id: string; creator_id: string; name: string; platform: string; url: string; fields: string[]; channel_id?: string };
export type BenchmarkMetric = { value: number | null; availability: 'observed' | 'not_visible' | 'unknown'; raw_text: string; precision: 'exact' | 'approximate' | 'unknown' };
export type BenchmarkMetricName = 'views' | 'likes' | 'comments' | 'reposts';
export type BenchmarkItem = { id: string; title: string; url: string; source_id: string; creator_id: string; source_name: string; platform: string; fields: string[]; published_at: string | null; checked_at: string; summary: string; verification_state: string; idea_angle: string;
  metrics?: Partial<Record<BenchmarkMetricName, BenchmarkMetric>>;
  provenance?: { method: 'youtube_rss' | 'browser_public_observation' | 'discovery_public'; source_url: string; observed_at: string; capture_sha256: string | null; source_hash?: string; scope: string };
  freshness?: 'recent' | 'historical' | 'unknown'; source_kind?: string; signals?: Record<string, number | string | null>;
};
export type BenchmarkSourceStatus = { source_id: string; state: string; method: string; checked_at: string | null; count: number | null; error: string | null; note: string };
export type BenchmarkIdea = Idea & { platform?: string; fields?: string[]; target_platforms?: string[]; angle?: string; source_id?: string; creator_id?: string; origin?: string; created_at?: string };
export type BenchmarkOverview = {
  registry: { sources: BenchmarkSource[] }; registry_hash: string; fields: string[]; platforms: Record<string, string>;
  items: BenchmarkItem[]; sources_status: BenchmarkSourceStatus[]; activity: { state: string; updated_at?: string; error?: string | null } | null;
  window_open: boolean; ideas: BenchmarkIdea[]; snapshot_hash?: string; trend_refs?: BenchmarkItem[];
  coverage?: { available_items: number; returned_items: number; limit: number; official_limit: number };
};
export type BenchmarkRegistryInput = { sources: BenchmarkSource[]; expected_hash: string };
export type BenchmarkIdeaInput = { title: string; source_url: string; source_id: string; fields: string[]; target_platforms: string[]; angle: string; expected_hash: string; item_id?: string; snapshot_hash?: string };
export type BenchmarkResearchInput = { source_ids: string[]; fields: string[]; platforms: string[]; expected_hash: string; item_ids?: string[]; snapshot_hash?: string };
export type BenchmarkResearchPacket = { text: string; registry_hash: string; snapshot_hash?: string };
export type BenchmarkRefreshResult = { task: { id?: string; state?: string } | null; window_open: boolean };
export type BenchmarkFilters = { field: string; platform: string; query: string };

export function benchmarkMetricText(metric?: BenchmarkMetric): string {
  if (metric?.availability === 'not_visible') return '비표시';
  if (!metric || metric.availability !== 'observed' || metric.value === null || !Number.isFinite(metric.value) || metric.value < 0) return '미확인';
  const value = metric.value.toLocaleString('ko-KR');
  return metric.precision === 'approximate' ? `${metric.raw_text || value} (근사)` : value;
}
export function benchmarkCollectionText(item: BenchmarkItem): string {
  return ({ youtube_rss: 'YouTube 공개 RSS', browser_public_observation: '연결 브라우저 관측', discovery_public: '공개 트렌드 자료' } as Record<string, string>)[item.provenance?.method ?? ''] ?? '수집 방식 미확인';
}
export function benchmarkFreshnessText(item: BenchmarkItem, now: number): string {
  const date = item.published_at ? Date.parse(item.published_at) : NaN;
  if (!Number.isFinite(date) || date > now) return '발행일 확인 필요';
  return now - date > 7 * 86400000 ? '과거 게시물 · 7일 초과' : '최근 7일 게시물';
}
export function sortBenchmarkReactions(items: BenchmarkItem[], platform: string, metric: BenchmarkMetricName): BenchmarkItem[] {
  if (platform === 'all' || items.some(item => item.platform !== platform)) return items;
  const value = (item: BenchmarkItem) => {
    const observation = item.metrics?.[metric];
    return observation?.availability === 'observed' && observation.value !== null && Number.isFinite(observation.value) && observation.value >= 0 ? observation.value : -1;
  };
  return [...items].sort((a, b) => value(b) - value(a));
}

const searchable = (value: string) => value.normalize('NFKC').toLocaleLowerCase('ko-KR');
function matches(fields: string[], platform: string, text: string, filters: BenchmarkFilters): boolean {
  return (filters.field === 'all' || fields.includes(filters.field))
    && (filters.platform === 'all' || platform === filters.platform)
    && searchable(text).includes(searchable(filters.query.trim()));
}
export function filterBenchmarkItems(items: BenchmarkItem[], filters: BenchmarkFilters): BenchmarkItem[] {
  return items.filter(item => matches(item.fields, item.platform, [item.title, item.summary, item.source_name, item.idea_angle].join(' '), filters));
}
export function filterBenchmarkSources(sources: BenchmarkSource[], filters: BenchmarkFilters): BenchmarkSource[] {
  return sources.filter(source => matches(source.fields, source.platform, `${source.name} ${source.url}`, filters));
}
function benchmarkUrlKey(value: string): string | null {
  try {
    const url = new URL(value);
    url.hostname = url.hostname.toLowerCase().replace(/^www\./, '');
    if (['youtube.com', 'm.youtube.com', 'youtu.be'].includes(url.hostname)) {
      const video = url.hostname === 'youtu.be' ? url.pathname.split('/')[1]
        : url.pathname === '/watch' ? url.searchParams.get('v')
        : /^\/(?:shorts|embed)\//.test(url.pathname) ? url.pathname.split('/')[2] : null;
      if (video) return `https://youtube.com/watch?v=${encodeURIComponent(video)}`;
    }
    for (const key of [...url.searchParams.keys()]) {
      if (/^utm_/i.test(key) || /^(?:fbclid|gclid|igsh|igshid)$/i.test(key)) url.searchParams.delete(key);
    }
    url.searchParams.sort();
    return url.origin + url.pathname.replace(/\/+$/, '') + (url.searchParams.size ? `?${url.searchParams}` : '');
  } catch { return null; }
}
export function registeredBenchmarkItems(items: BenchmarkItem[], officialUrls: string[] = []): BenchmarkItem[] {
  const seen = new Set(officialUrls.map(benchmarkUrlKey).filter((url): url is string => url !== null));
  return items.filter(item => {
    if (!item.source_id) return false;
    const url = benchmarkUrlKey(item.url);
    if (!url || seen.has(url)) return false;
    seen.add(url);
    return true;
  });
}
export function filterBenchmarkIdeas(ideas: BenchmarkIdea[], sources: BenchmarkSource[], filters: BenchmarkFilters): BenchmarkIdea[] {
  return ideas.filter(idea => {
    const source = sources.find(row => row.id === idea.source_id);
    return matches(idea.fields ?? source?.fields ?? [], idea.platform ?? source?.platform ?? 'website', [idea.title, idea.angle ?? '', source?.name ?? ''].join(' '), filters);
  });
}
export function groupBenchmarkSources(sources: BenchmarkSource[]): { id: string; name: string; sources: BenchmarkSource[] }[] {
  const groups = new Map<string, { id: string; name: string; sources: BenchmarkSource[] }>();
  for (const source of sources) {
    const group = groups.get(source.creator_id) ?? { id: source.creator_id, name: source.name, sources: [] };
    group.sources.push(source);
    groups.set(source.creator_id, group);
  }
  return [...groups.values()];
}
export function splitBenchmarkDates(items: BenchmarkItem[], now: number) {
  const dated: BenchmarkItem[] = [], undated: BenchmarkItem[] = [];
  for (const item of items) {
    const published = item.published_at ? Date.parse(item.published_at) : NaN;
    (Number.isFinite(published) && published <= now ? dated : undated).push(item);
  }
  dated.sort((left, right) => Date.parse(right.published_at!) - Date.parse(left.published_at!));
  return { dated, undated };
}
export function parseBenchmarkFields(value: string): string[] {
  const fields = [...new Set(value.split(/[,\n]/).map(field => field.trim()).filter(Boolean))];
  if (!fields.length) throw new Error('분야를 하나 이상 입력하세요.');
  if (fields.length > 6) throw new Error('분야는 최대 6개까지 등록할 수 있습니다.');
  if (fields.some(field => [...field].length > 30)) throw new Error('각 분야는 30자 이내로 입력하세요.');
  return fields;
}
export function benchmarkPublicUrl(value: string): string | null {
  try {
    const url = new URL(value), host = url.hostname.toLowerCase().replace(/\.$/, '');
    if (url.protocol !== 'https:' || url.username || url.password || url.port || !host.includes('.')
      || host === 'localhost' || /\.(?:local|localhost|internal|test|invalid)$/.test(host)
      || /^\d+\.\d+\.\d+\.\d+$/.test(host) || host.includes(':')) return null;
    return url.href;
  } catch { return null; }
}
