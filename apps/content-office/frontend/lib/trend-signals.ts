// 트렌드 신호(0원): 서버 office/trend_signals.py가 모은 자동완성과 위키백과 조회수를 보여 주는 형태.
export type TrendSource = "google" | "youtube" | "naver" | "wikipedia";
export type TrendRow = {
  seed: string; source: TrendSource; label: string; checked_at: string;
  status: "ok" | "empty" | "blocked" | "missing" | "error";
  items: { text: string; new?: boolean }[];
  views?: { title: string; last7: number; prev7: number; change_pct: number | null };
  url?: string; note?: string;
};
export type TrendSettings = { enabled: boolean; seeds: string[]; sources: TrendSource[] };
export type TrendStatus = {
  settings: TrendSettings;
  report: { checked_at: string; rows: TrendRow[]; counts: Record<string, number>; paid_calls: number; method: string } | null;
  labels: Record<TrendSource, string>;
  limits: { max_seeds: number; pause_seconds: number; min_views: number };
  not_connected: string[];
};

const STATUS_LABEL: Record<TrendRow["status"], string> = { ok: "", empty: "비었어요", blocked: "막혔어요", missing: "자료 없음", error: "읽지 못했어요" };

/** 한 칸에 보여 줄 한 줄. 숫자가 받쳐 주지 않는 말은 만들지 않는다. */
export function trendLine(row: TrendRow): string {
  if (row.status !== "ok") return [STATUS_LABEL[row.status], row.note].filter(Boolean).join(". ");
  if (row.views) {
    const { last7, prev7, change_pct } = row.views;
    const rate = change_pct === null ? "" : `, ${change_pct > 0 ? "+" : ""}${change_pct}%`;
    return `최근 7일 ${last7.toLocaleString("ko-KR")}회, 그 전 7일 ${prev7.toLocaleString("ko-KR")}회${rate}`;
  }
  return row.items.map(item => item.text + (item.new ? " (새로)" : "")).join(", ");
}

/** 씨앗 단어 입력(한 줄에 하나)을 서버 규칙에 맞게 정리한다. */
export function parseSeeds(text: string, max = 8): string[] {
  return [...new Set(text.split("\n").map(line => line.trim()).filter(Boolean))].slice(0, max);
}
