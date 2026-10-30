export type NewsSegment = "all" | "exam" | "ai";
export const newsSegments = [{ id: "all", label: "전체" }, { id: "exam", label: "자격증·수험생" }, { id: "ai", label: "AI·자동화" }] as const;
export function newsSegment(value: string | null): NewsSegment { return value === "exam" || value === "ai" ? value : "all"; }
export function filterNews<T extends { segment?: string }>(articles: T[], segment: NewsSegment) { return segment === "all" ? articles : articles.filter(article => article.segment === segment); }
export function newsEmptyState(segment: NewsSegment, total: number, sources: number, checked: boolean, failed: boolean) {
  if (segment !== "all" && !sources) return { kind: "sources", title: "이 분류에 등록된 뉴스 소스가 없어요", text: "공식 출처 연결이 필요해요. 기획 화면에서는 독자 질문이나 출처가 있는 직접 기획으로 시작할 수 있어요." };
  if (!checked) return { kind: "first", title: "아직 뉴스 수집 기록이 없어요", text: "작업 시간을 연 뒤 RSS 새로 수집을 요청하거나, 기획 화면에서 직접 시작하세요." };
  if (failed) return { kind: "failure", title: "수집 실패로 후보를 확인할 수 없어요", text: "운영 기록에서 실패한 출처를 확인하세요. 수집 실패를 뉴스가 없는 것으로 표시하지 않아요." };
  return total ? { kind: "filtered", title: "선택한 분류에 해당하는 기사가 없어요", text: "전체 분류에서 다른 후보를 확인하거나 출처가 있는 기획을 직접 등록하세요." } : { kind: "empty", title: "최근 7일에 선정 가능한 기사가 없어요", text: "수집은 확인됐지만 날짜·중복 조건을 통과한 후보가 없어요. 운영 기록에서 수집 결과를 확인하세요." };
}
