import type { Idea } from "./types";

export type IdeaFilter = "all" | "ready" | "blocked" | "selected";
export type IdeaStatus = { key: Exclude<IdeaFilter, "all">; label: string; tone: "blue" | "red" | "green" };

/** 목록과 상세에서 같은 말로 보여 줄 기획 상태. */
export function ideaStatus(idea: Pick<Idea, "state" | "blocked">): IdeaStatus {
  if (idea.state === "selected") return { key: "selected", label: "작업 만듦", tone: "green" };
  if (idea.blocked.length > 0) return { key: "blocked", label: `막힘 ${idea.blocked.length}`, tone: "red" };
  return { key: "ready", label: "작업 가능", tone: "blue" };
}

/** 조회수 대비 반응 구간을 사람이 읽는 말로 바꾼다. 측정값이 없으면 아무것도 표시하지 않는다. */
export function outlierLabel(band: string | null | undefined): string {
  switch (band) {
    case "10x+": return "평소의 10배 넘는 반응";
    case "5-10x": return "평소의 5~10배 반응";
    case "2-5x": return "평소의 2~5배 반응";
    case "under-2x": return "평소 수준 반응";
    default: return "";
  }
}

export const ideaFilters: { id: IdeaFilter; label: string }[] = [
  { id: "all", label: "전체" },
  { id: "ready", label: "작업 가능" },
  { id: "blocked", label: "막힘" },
  { id: "selected", label: "작업 만듦" },
];

export function countIdeas(ideas: Pick<Idea, "state" | "blocked">[]): Record<IdeaFilter, number> {
  const counts: Record<IdeaFilter, number> = { all: ideas.length, ready: 0, blocked: 0, selected: 0 };
  for (const idea of ideas) counts[ideaStatus(idea).key] += 1;
  return counts;
}

export function filterIdeas<T extends Pick<Idea, "state" | "blocked" | "title">>(ideas: T[], filter: IdeaFilter, query: string): T[] {
  const words = query.trim().toLowerCase().split(/\s+/).filter(Boolean);
  return ideas.filter((idea) =>
    (filter === "all" || ideaStatus(idea).key === filter) &&
    words.every((word) => idea.title.toLowerCase().includes(word)),
  );
}
