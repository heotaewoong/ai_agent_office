export const platformNewsLabels: Record<string, string> = {
  youtube: 'YouTube', instagram: 'Instagram', naver_blog: '네이버 블로그', tistory: '티스토리',
  threads: 'Threads', tiktok: 'TikTok', x: 'X', linkedin: 'LinkedIn',
  newsletter: '뉴스레터', website: '웹사이트', other: '기타',
};

type Metric = 'views' | 'likes' | 'reactions' | 'comments' | 'reposts';

export type PlatformNews = {
  checked_at: string | null;
  snapshot_hash?: string | null;
  topic: string;
  region: string;
  platforms: {
    id: string;
    label: string;
    source_status: 'available' | 'observed' | 'waiting' | 'stale' | 'error';
    method: string;
    ranking_basis: string;
    message?: string;
    checked_at: string | null;
    criteria?: {
      kind: 'popularity' | 'latest';
      metric: 'views' | 'likes' | 'reactions' | null;
      published_days: number;
      observation_days: number;
      reference_days: number;
      source: 'youtube_api' | 'public_rss' | 'browser_observation';
      scope: string;
    };
    items: PlatformNewsItem[];
    reference_items?: PlatformNewsItem[];
  }[];
};

export type PlatformNewsItem = {
  id: string;
  title: string;
  url: string;
  source: string;
  published_at: string | null;
  summary: string;
  metrics: Partial<Record<Metric, number>>;
  metric_precision?: Partial<Record<Metric, 'exact' | 'approximate'>>;
  observed_at: string | null;
  reference_reason?: string;
};
