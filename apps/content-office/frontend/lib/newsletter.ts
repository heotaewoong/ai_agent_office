/** 회차 키 기본값 'YYYY-MM-wN'. 서울 날짜 기준으로 1~7일 w1, 8~14일 w2, 15~21일 w3, 22~28일 w4, 29~31일 w5. */
export function defaultIssueKey(date: Date): string {
  const parts = new Intl.DateTimeFormat("en-CA", {
    timeZone: "Asia/Seoul",
    year: "numeric",
    month: "2-digit",
    day: "2-digit",
  }).formatToParts(date);
  const get = (type: string) => parts.find((p) => p.type === type)?.value ?? "";
  const day = Number(get("day"));
  const week = Math.floor((day - 1) / 7) + 1;
  return `${get("year")}-${get("month")}-w${week}`;
}

export function validIssueKey(value: string): boolean {
  return /^\d{4}-\d{2}-w[1-5]$/.test(value.trim());
}

const STATE_LABELS: Record<string, string> = {
  draft: "초안",
  approved: "③ 회차 승인",
  rejected: "반려",
  sent_manual: "수동 발송 완료",
};

export function newsletterStateLabel(state: string): string {
  return STATE_LABELS[state] ?? state;
}
