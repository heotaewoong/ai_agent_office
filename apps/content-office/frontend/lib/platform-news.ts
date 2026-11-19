export const platformNewsLabels: Record<string, string> = {
  youtube: 'YouTube', instagram: 'Instagram', naver_blog: '네이버 블로그', tistory: '티스토리',
  threads: 'Threads', tiktok: 'TikTok', x: 'X', linkedin: 'LinkedIn',
  newsletter: '뉴스레터', website: '웹사이트', other: '기타',
};

type Metric = 'views' | 'likes' | 'reactions' | 'comments' | 'reposts';

export type PlatformNews = {
  checked_at: string | null;
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
    items: {
      id: string;
      title: string;
      url: string;
      source: string;
      published_at: string | null;
      summary: string;
      metrics: Partial<Record<Metric, number>>;
      metric_precision?: Partial<Record<Metric, 'exact' | 'approximate'>>;
      observed_at: string | null;
    }[];
  }[];
};
