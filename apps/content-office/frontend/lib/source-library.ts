/** 자료 창고: 운영자가 넣은 링크·메모·파일과, 초안 근거로 쓸지에 대한 표시. */
export type SourceOrigin = "manual" | "idea" | "news" | "artifact" | "import";
export type SourceStatus = "pending" | "working" | "done" | "needs_check" | "duplicate";
export type SourceArea = { id: string; label: string; items: number };
export type SourceItem = {
  id: string;
  kind: "link" | "memo" | "file";
  area: string;
  area_label: string;
  mine: boolean;
  title: string;
  url: string | null;
  status: SourceStatus;
  note: string;
  passages: number;
  use_as_evidence: boolean;
  origin: SourceOrigin;
  origin_ref: string | null;
  file_name: string | null;
  created_at: string;
  updated_at: string;
};
export type SourceItemDetail = SourceItem & { passage_texts: string[] };
export type SourceLibrary = {
  areas: SourceArea[];
  items: SourceItem[];
  stats: { items: number; ready: number; passages: number; evidence: number; needs_check: number };
  limits: { links: number; file_mb: number; memo_chars: number };
};
export type SourceLinkResult = { url: string; result: "added" | "exists" | "rejected"; reason?: string; item?: SourceItem };
export type SourceHit = {
  item_id: string;
  paragraph: number;
  title: string;
  url: string | null;
  area: string;
  area_label: string;
  mine: boolean;
  kind: SourceItem["kind"];
  use_as_evidence: boolean;
  text: string;
  score: number;
  matched: string[];
};
export type SourceEntry = { area: string; mine?: boolean; origin?: SourceOrigin; origin_ref?: string };
export type SourcePatch = { use_as_evidence?: boolean; area?: string; mine?: boolean; title?: string };
export type SourceFilter = "all" | "evidence" | "mine" | "check";

export const sourceStatus: Record<SourceStatus, { label: string; tone: "green" | "orange" | "red" | "neutral" }> = {
  done: { label: "저장됨", tone: "green" },
  pending: { label: "읽는 중", tone: "neutral" },
  working: { label: "읽는 중", tone: "neutral" },
  needs_check: { label: "확인 필요", tone: "red" },
  duplicate: { label: "중복", tone: "orange" },
};
export const sourceOrigins: Record<SourceOrigin, string> = {
  manual: "직접 넣음",
  idea: "기획에서",
  news: "뉴스에서",
  artifact: "내 제작물",
  import: "이전 자료함",
};
export const sourceKinds: Record<SourceItem["kind"], string> = { link: "링크", memo: "메모", file: "파일" };
export const sourceFilters: { id: SourceFilter; label: string }[] = [
  { id: "all", label: "전체" },
  { id: "evidence", label: "근거로 사용" },
  { id: "mine", label: "내 경험·내 글" },
  { id: "check", label: "확인 필요" },
];

/** 붙여 넣은 글에서 주소만 순서대로 고른다. 같은 주소는 한 번만 남긴다. */
export function splitLinks(text: string): string[] {
  return [...new Set(text.split(/[\s,]+/).map((value) => value.trim()).filter((value) => /^https?:\/\//i.test(value)))];
}

export function filterSources(items: SourceItem[], area: string, filter: SourceFilter, query = ""): SourceItem[] {
  const words = query.trim().toLowerCase().split(/\s+/).filter(Boolean);
  return items.filter((item) => {
    if (area && item.area !== area) return false;
    if (filter === "evidence" && !item.use_as_evidence) return false;
    if (filter === "mine" && !item.mine) return false;
    if (filter === "check" && item.status !== "needs_check" && item.status !== "duplicate") return false;
    const haystack = `${item.title} ${item.url ?? ""} ${item.file_name ?? ""}`.toLowerCase();
    return words.every((word) => haystack.includes(word));
  });
}

/** 서버가 받는 형식의 연결 항목 ID만 넘긴다. 형식이 다르면 연결 없이 저장한다. */
export function safeOriginRef(value: unknown): string | undefined {
  return typeof value === "string" && /^[A-Za-z0-9_.:-]{1,160}$/.test(value) ? value : undefined;
}

/** 뉴스 분류를 창고 분야의 기본값으로 바꾼다. 운영자가 넣기 전에 바꿀 수 있다. */
export function areaForSegment(segment?: string): string {
  return segment === "exam" ? "A" : "B";
}

export function sourceSummary(stats: SourceLibrary["stats"]): string {
  return `자료 ${stats.items}건 · 문단 ${stats.passages.toLocaleString("ko-KR")}개 · 근거로 사용 ${stats.evidence}건` + (stats.needs_check ? ` · 확인 필요 ${stats.needs_check}건` : "");
}

export function displayDay(value: string): string {
  const time = Date.parse(value);
  return Number.isFinite(time) ? new Intl.DateTimeFormat("ko-KR", { timeZone: "Asia/Seoul", month: "long", day: "numeric" }).format(new Date(time)) : "";
}

export async function fileToBase64(file: Blob): Promise<string> {
  const bytes = new Uint8Array(await file.arrayBuffer());
  let binary = "";
  for (let offset = 0; offset < bytes.length; offset += 0x8000) binary += String.fromCharCode(...bytes.subarray(offset, offset + 0x8000));
  return btoa(binary);
}
