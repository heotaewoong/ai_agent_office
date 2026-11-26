/** 승인⓪, 승인① 화면에서 근거와 원고를 사람이 빨리 보게 돕는 표시(2026-11-26). 막지 않고 보여 주기만 한다. */

export type RejectReason = "fact" | "explanation" | "style" | "design" | "rights" | "format";

/** 서버 improvements.REASONS와 같은 순서와 키. */
export const REJECT_REASONS: { key: RejectReason; label: string }[] = [
  { key: "fact", label: "사실, 숫자, 출처가 틀림" },
  { key: "explanation", label: "설명이 부족하거나 주제를 벗어남" },
  { key: "style", label: "문체, 말투" },
  { key: "design", label: "디자인, 화면" },
  { key: "rights", label: "권리, 저작권" },
  { key: "format", label: "형식, 분량" },
];

const DAY = 86_400_000;

/** 발행일 표시. 1년(365일)이 넘으면 stale. 날짜가 없거나 이상하면 null. */
export function freshness(published: string | undefined, today: Date = new Date()): { label: string; stale: boolean } | null {
  if (!published || !/^\d{4}-\d{2}-\d{2}$/.test(published)) return null;
  const time = Date.parse(`${published}T00:00:00Z`);
  if (!Number.isFinite(time)) return null;
  const days = Math.floor((today.getTime() - time) / DAY);
  const stale = days > 365;
  return { label: stale ? `발행 ${published} · 1년 넘음` : `발행 ${published}`, stale };
}

/** 인용 문단을 핵심 문장 앞, 핵심 문장, 뒤로 나눈다. 핵심 문장이 문단에 없으면 통째로 돌려준다. */
export function highlightParts(quote: string, highlight?: string): { text: string; mark: boolean }[] {
  const at = highlight ? quote.indexOf(highlight) : -1;
  if (!highlight || at < 0) return [{ text: quote, mark: false }];
  return [
    { text: quote.slice(0, at), mark: false },
    { text: highlight, mark: true },
    { text: quote.slice(at + highlight.length), mark: false },
  ].filter((part) => part.text.length > 0);
}
