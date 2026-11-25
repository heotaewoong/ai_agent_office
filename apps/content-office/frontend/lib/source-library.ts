/** 자료 창고: 운영자가 넣은 링크·메모·파일과, 초안 근거로 쓸지에 대한 표시. */
export type SourceOrigin = "manual" | "idea" | "news" | "artifact" | "import" | "research";
/** 자료의 쓰임새. fact는 사실 주장을 받치는 근거, example은 출처와 함께 소개만 하는 다른 사람의 방법·사례. */
export type SourceLane = "fact" | "example";
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
  lane: SourceLane;
  lane_label: string;
  file_name: string | null;
  created_at: string;
  updated_at: string;
  /** 원문의 발행일·수정일(YYYY-MM-DD)과 이 자료를 읽은 시각. 예전에 들어온 자료는 비어 있을 수 있다. */
  published_at?: string | null;
  modified_at?: string | null;
  collected_at?: string | null;
  date_source?: string | null;
  extractor?: string | null;
};
/** 문단이 원문 어디에 있었는지. locator는 PDF 쪽("p.3", 파일 기준), heading은 소제목 경로. */
export type SourcePlace = { locator: string | null; heading: string | null };
export type SourceItemDetail = SourceItem & { passage_texts: string[]; passage_places?: SourcePlace[] };
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
export type SourceEntry = { area: string; mine?: boolean; origin?: SourceOrigin; origin_ref?: string; lane?: SourceLane; use_as_evidence?: boolean };
export type SourcePatch = { use_as_evidence?: boolean; area?: string; mine?: boolean; title?: string; lane?: SourceLane };
export type SourceFilter = "all" | "evidence" | "mine" | "example" | "check";

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
  research: "외부 조사에서",
};
export const sourceKinds: Record<SourceItem["kind"], string> = { link: "링크", memo: "메모", file: "파일" };
export const sourceFilters: { id: SourceFilter; label: string }[] = [
  { id: "all", label: "전체" },
  { id: "evidence", label: "근거로 사용" },
  { id: "mine", label: "내 경험·내 글" },
  { id: "example", label: "사례·참고" },
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
    if (filter === "example" && item.lane !== "example") return false;
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
export function evidenceHint(item: Pick<SourceItem, "kind"> & { lane?: SourceLane }): string {
  if (item.kind === "link" && item.lane === "example") return "사례로만 소개돼요. 사실 주장의 근거로는 쓰이지 않아요";
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

const dateSourceTags: Record<string, string> = { htmldate: "추정", "pdf-metadata": "파일 정보", "docx-core": "파일 정보" };

/** 자료의 날짜를 한 줄로 보여 준다. 새 규칙으로 읽었는데 발행일을 못 찾았으면 '발행일 모름'이라고 적는다. */
export function sourceDates(item: Pick<SourceItem, "kind" | "status" | "published_at" | "modified_at" | "collected_at" | "date_source">): string {
  if (item.status !== "done") return "";
  const parts: string[] = [];
  if (item.published_at) {
    const tag = dateSourceTags[item.date_source ?? ""];
    parts.push(`발행 ${item.published_at}${tag ? `(${tag})` : ""}`);
  } else if (item.kind === "link" && item.collected_at) {
    parts.push("발행일 모름");
  }
  if (item.modified_at && item.modified_at !== item.published_at) parts.push(`수정 ${item.modified_at}`);
  if (item.collected_at) parts.push(`읽은 날 ${displayDay(item.collected_at)}`);
  return parts.join(" · ");
}

/** 문단 위치를 한 줄로. PDF는 파일 기준 쪽, 웹은 소제목 경로. 인용할 때 쪽이나 절을 밝히는 데 쓴다. */
export function passagePlace(place?: SourcePlace | null): string {
  if (!place) return "";
  const page = place.locator && /^p\.\d+$/.test(place.locator) ? `PDF ${place.locator.slice(2)}쪽` : place.locator ?? "";
  return [page, place.heading ?? ""].filter(Boolean).join(" · ");
}

export async function fileToBase64(file: Blob): Promise<string> {
  const bytes = new Uint8Array(await file.arrayBuffer());
  let binary = "";
  for (let offset = 0; offset < bytes.length; offset += 0x8000) binary += String.fromCharCode(...bytes.subarray(offset, offset + 0x8000));
  return btoa(binary);
}

export const sourceLanes: Record<SourceLane, string> = { fact: "사실 근거", example: "사례·참고" };
export type ResearchNeed = "required" | "recommended" | "none";
/** 글 유형. 사람이 고르고, 고르기 전에는 서버가 제목으로 추측한 값을 기본값으로만 보여 준다. 라벨은 서버 KINDS와 같다. */
export type ResearchKind = "W1" | "W2" | "W3" | "W4" | "W5";
export const researchKinds: { id: ResearchKind; label: string; help: string }[] = [
  { id: "W1", label: "비교·벤치마킹", help: "여러 도구나 방법을 견줘 보는 글이에요." },
  { id: "W2", label: "공식 발표·공고 해설", help: "발표, 공고, 업데이트 원문을 풀어 주는 글이에요. 원문을 먼저 확인해요." },
  { id: "W3", label: "근거형 설명", help: "연구나 공식 자료로 방법을 설명하는 글이에요." },
  { id: "W4", label: "내 경험 후기", help: "내가 해 본 일을 쓰는 글이에요. 밖에서 찾지 않고 내 원고나 메모로 써요." },
  { id: "W5", label: "범위 밖", help: "다루지 않는 주제예요. 조사하지 않아요." },
];
/** 주제가 어떤 주장을 하는지 보고 서버가 정한 외부 조사 기준. */
export type ResearchPlan = {
  area: string;
  area_label: string;
  area_guessed: boolean;
  experience_first: boolean;
  claims: { id: string; label: string }[];
  warning: string | null;
  fact: { need: ResearchNeed; reason: string; providers: string[] };
  example: { need: ResearchNeed; reason: string };
  need: ResearchNeed;
  summary: string;
  kind: ResearchKind;
  kind_label: string;
  kind_guessed: boolean;
  /** 이 글 유형에서 글을 쓰기 전에 채울 빈칸. */
  blanks: string[];
  /** 범위 밖으로 고른 주제. 그래도 찾아보기를 눌러도 찾지 않는다. */
  blocked: boolean;
  /** 내 경험 후기로 고른 주제. 내 원고나 메모가 있어야 초안을 쓴다. */
  needs_experience_source: boolean;
};
export type ResearchCandidate = {
  key: string;
  lane: SourceLane;
  provider: string;
  provider_label: string;
  title: string;
  url: string;
  snippet: string;
  year: number | null;
  needs_paste: boolean;
  in_library: boolean;
};
export type ResearchResult = {
  plan: ResearchPlan;
  /** translated가 true면 english는 모델이 만든 영어 검색어이고, alternatives는 같이 만든 다른 검색어다. */
  queries: { english: string; names?: string; terms: string[]; custom: boolean; alternatives?: string[]; translated?: boolean };
  library: { fact_sources: number | null; sufficient: boolean };
  candidates: ResearchCandidate[];
  notes: string[];
  searched: boolean;
};
export type ResearchRequest = {
  /** 기획 카드에서 누른 조사면 기획 ID. 추천과 실제로 누른 것을 세는 데만 쓴다. */
  id?: string; title: string; summary?: string; area?: string; kind?: ResearchKind; experience_first?: boolean; query?: string; force?: boolean;
};
export type ResearchTopic = { id?: string; title: string; summary?: string; area?: string; kind?: ResearchKind; experience_first?: boolean };
export type ResearchChoice = { idea_id: string; kind: ResearchKind; kind_label: string; area: string; area_label: string; updated_at: string };
export type TrustedSource = {
  id: string;
  name: string;
  url: string;
  feed_url: string;
  area: string;
  area_label: string;
  lane: SourceLane;
  lane_label: string;
  created_at: string;
  recent?: number;
};

export function researchBadge(need: ResearchNeed): { label: string; tone: "red" | "orange" | "neutral" } {
  if (need === "required") return { label: "외부 조사 필수", tone: "red" };
  return need === "recommended" ? { label: "외부 조사 권장", tone: "orange" } : { label: "외부 조사 안 함", tone: "neutral" };
}

/** 카드에 보여 줄 글 유형과 분야 한 줄. 사람이 아직 고르지 않은 값에는 '추측'을 붙인다. */
export function choiceLine(plan: Pick<ResearchPlan, "kind_label" | "kind_guessed" | "area_label" | "area_guessed">): string {
  const mark = (guessed: boolean) => (guessed ? " (추측)" : "");
  return `글 유형 ${plan.kind_label}${mark(plan.kind_guessed)} · 분야 ${plan.area_label}${mark(plan.area_guessed)}`;
}

/** 고른 유형 때문에 조사 방식이 달라질 때 카드에 알릴 한 줄. 추측한 유형으로는 알리지 않는다. */
export function kindNotice(plan: Pick<ResearchPlan, "blocked" | "needs_experience_source">): string | null {
  if (plan.blocked) return "범위 밖 주제로 골라서 밖으로 찾지 않아요. 이 기획을 넘기거나 글 유형을 바꿔 주세요.";
  if (plan.needs_experience_source) return "내 경험 후기는 내 원고나 메모가 있어야 초안을 써요. 경험 메모를 자료 창고에 넣거나 '내 글로 만들기'에서 시작해 주세요.";
  return null;
}

/** 조사 요청에 실어 보낼 글 유형. 사람이 고른 값만 보내고, 추측한 값은 보내지 않는다. */
export function confirmedKind(plan?: Pick<ResearchPlan, "kind" | "kind_guessed">): ResearchKind | undefined {
  return plan && !plan.kind_guessed ? plan.kind : undefined;
}

export function splitCandidates(candidates: ResearchCandidate[]): Record<SourceLane, ResearchCandidate[]> {
  return { fact: candidates.filter((row) => row.lane !== "example"), example: candidates.filter((row) => row.lane === "example") };
}

export function candidateMeta(candidate: Pick<ResearchCandidate, "provider_label" | "year">): string {
  return candidate.year ? `${candidate.provider_label} · ${candidate.year}년` : candidate.provider_label;
}

/** 검색된 후보 수이며, 확인된 주장 수와 구분한다. */
export function libraryLine(library: ResearchResult["library"]): string {
  if (library.fact_sources === null) return "자료 창고 후보를 지금 조회하지 못했어요.";
  if (library.fact_sources === 0) return "자료 창고에 관련 후보가 아직 없어요.";
  return `자료 창고 후보 ${library.fact_sources}곳 · 원문이 주장을 직접 뒷받침하는지 확인해 주세요.`;
}

/** 후보를 창고에 넣은 결과를 카드에 보여 줄 한 줄로 바꾼다. */
export function savedCandidateNote(row: SourceLinkResult | undefined): { ok: boolean; text: string } {
  const item = row?.item;
  if (!row || row.result === "rejected" || !item) return { ok: false, text: row?.reason || "넣지 못했습니다." };
  if (item.status === "done" && item.use_as_evidence) {
    return { ok: true, text: row.result === "exists" ? "이미 창고에 있던 자료를 근거로 켰어요." : `문단 ${item.passages}개를 넣고 근거로 켰어요.` };
  }
  if (item.status === "duplicate") return { ok: false, text: item.note || "같은 내용이 이미 창고에 있어요." };
  return { ok: false, text: `창고에 '확인 필요'로 남겼어요. ${item.note}`.trim() };
}
