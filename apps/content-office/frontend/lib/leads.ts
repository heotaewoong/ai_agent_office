/** 화면용 이메일 형식 검사. 마스킹·저장은 서버가 합니다. */
export function validEmail(value: string): boolean {
  const v = value.trim();
  if (!v || v.length > 254) return false;
  return /^[^\s@]+@[^\s@]+\.[^\s@]+$/.test(v);
}

const SOURCE_LABELS: Record<string, string> = {
  homepage: "홈페이지",
  youtube: "YouTube",
  blog: "블로그",
  newsletter: "뉴스레터",
  manual: "수동 등록",
  other: "기타",
};

export function leadSourceLabel(source: string): string {
  return SOURCE_LABELS[source] ?? source;
}
