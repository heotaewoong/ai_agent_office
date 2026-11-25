import type { IdeaBookEvidence, IdeaPublicEvidence } from "./types";

/** 인쇄 쪽이 있으면 그 쪽, 없으면 PDF 파일 기준 쪽. 서버(private_books.page_label)와 같은 규칙이다. */
export function bookPage(item: Pick<IdeaBookEvidence, "printed_page" | "file_page">): string {
  if (item.printed_page) return `${item.printed_page}쪽`;
  if (item.file_page) return `PDF ${item.file_page}쪽(파일 기준)`;
  return "";
}

/** 공개 글에 적힐 출처 한 줄. 책은 『제목』, 저자, 쪽. 강의 자료는 「자료명」. */
export function bookCitation(item: Pick<IdeaBookEvidence, "kind" | "title" | "author" | "printed_page" | "file_page">): string {
  if (item.kind === "course") return `강의 자료 「${item.title}」`;
  return [`『${item.title}』`, item.author ?? "", bookPage(item)].filter(Boolean).join(", ");
}

export function bookPolicy(item: Pick<IdeaBookEvidence, "kind" | "author" | "quote_policy">): string {
  const rule = item.quote_policy === "paraphrase_only" ? "풀어 쓰기만 가능" : "짧은 인용 가능(두 문장까지)";
  return item.kind === "book" && !item.author ? `${rule}, 저자 미기록` : rule;
}

export function bookDiscoveryLine(discovery: { status: string; mode: string }): string {
  const found = discovery.status === "ready" ? "개인 DB에서 후보를 찾았어요. 고른 문단만 원고 근거가 돼요." : "개인 DB에서 맞는 문단을 찾지 못했어요.";
  return discovery.mode === "text" ? `${found} 임베딩 서버를 켜지 못해 키워드로만 찾았어요.` : found;
}

/** 공개 근거 문단의 위치. 자료 창고 PDF 쪽과 소제목 경로가 있을 때만 붙는다. */
export function evidencePlace(item: Pick<IdeaPublicEvidence, "locator" | "heading">): string {
  const page = item.locator && /^p\.\d+$/.test(item.locator) ? `PDF ${item.locator.slice(2)}쪽` : "";
  return [page, item.heading ?? ""].filter(Boolean).join(" · ");
}
