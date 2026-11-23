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
  pasted: boolean;
  origin: SourceOrigin;
  origin_ref: string | null;
  file_name: string | null;
  created_at: string;
  updated_at: string;
};
export type SourceItemDetail = SourceItem & { passage_texts: string[] };
/** 근거로 켠 링크 자료 가운데 기획 근거 검색에 들어갈 준비(벡터 계산)가 끝난 문단 수. */
export type SourceVectors = { passages: number; ready: number; pending: number; available: boolean };
export type SourceLibrary = {
  areas: SourceArea[];
  items: SourceItem[];
  stats: { items: number; ready: number; passages: number; evidence: number; needs_check: number };
  vectors: SourceVectors;
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

/** 근거로 켠 링크가 기획 근거 검색에 얼마나 연결됐는지 한 줄로 알려 준다. 켠 링크가 없으면 빈 문자열. */
export function vectorSummary(vectors: SourceVectors): string {
  if (!vectors.passages) return "";
  const ready = vectors.ready.toLocaleString("ko-KR");
  const total = vectors.passages.toLocaleString("ko-KR");
  if (!vectors.available) return `근거로 켠 링크 문단 ${total}개가 있지만, 이 서버에서 근거 검색 준비 도구를 찾지 못해 기획 근거 찾기에는 아직 나오지 않아요.`;
  return vectors.pending ? `근거로 켠 링크를 기획 근거 찾기에 연결하는 중이에요. 문단 ${ready}/${total}개 준비됨` : `근거로 켠 링크 문단 ${total}개가 기획 근거 찾기에 연결돼 있어요.`;
}

/** 근거로 켰을 때 그 자료가 어디에 쓰이는지. 링크는 출처가 있어 공개 근거 후보가 되고, 메모와 파일은 내 글의 재료가 된다. */
export function evidenceHint(item: Pick<SourceItem, "kind">): string {
  return item.kind === "link" ? "기획의 근거 찾기에 후보로 나와요" : "‘내 글로 만들기’에서 불러올 수 있어요";
}

/** 읽지 못한 링크와 파일만 본문을 직접 붙여 넣을 수 있다. */
export function canPaste(item: Pick<SourceItem, "kind" | "status">): boolean {
  return item.status === "needs_check" && item.kind !== "memo";
}

/** '내 글로 만들기'에 불러올 수 있는 자료: 근거로 켠 메모·파일과 내 링크. */
export function importableSources(items: SourceItem[]): SourceItem[] {
  return items.filter((item) => item.status === "done" && item.use_as_evidence && (item.kind !== "link" || item.mine));
}

/** 쓰던 본문 뒤에 불러온 글을 붙인다. 본문 한도를 넘으면 잘라 내고 알려 준다. */
export function appendBody(current: string, addition: string, limit = 50_000): { body: string; cut: boolean } {
  const joined = current.trim() ? `${current.trimEnd()}\n\n${addition}` : addition;
  return { body: joined.slice(0, limit), cut: joined.length > limit };
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
