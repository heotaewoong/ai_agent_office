export type ResearchConfig = { platforms: string[]; topic: string; region: string; youtube_channels: string[] };
export type ResearchCandidate = { id: string; title: string; url: string; feed_name: string; kind: string; signals: Record<string, string | number | null>; published_at: string; observed_at: string; date_note?: string | null; signal_note?: string | null; reason: string };
export type DiscoveryStatus = {
  config: ResearchConfig; config_hash: string; platforms: Record<string, string>; plan: Record<string, string[]>;
  window_open: boolean; stale: boolean; unconnected: string[];
  activity?: { state: string; updated_at: string; error?: string } | null;
  task?: { state: string };
  snapshot: null | { config_hash: string; checked_at: string; method: string; paid_calls: number;
    sources: { id: string; name: string; state: string; count: number | null; raw_items?: number; error?: string }[];
    recommendations: Record<string, ResearchCandidate[]> };
};
export const researchSourceLabels: Record<string, string> = { youtube: 'YouTube 공개 채널', community: 'HN 커뮤니티 반응', search_trend: 'Google 급상승 검색', news_aggregator: 'Google 뉴스', official: '공식 발표·연구' };
export function signalLabels(signals: ResearchCandidate['signals']): string[] {
  const labels: Record<string, string> = { youtube_views: '누적 조회', hn_points: 'HN 점수', hn_comments: 'HN 댓글', search_volume_label: '근사 검색량' };
  return Object.entries(signals).filter(([key, value]) => key in labels && value !== null).map(([key, value]) => `${labels[key]} ${value}`);
}
