import type { NextExam } from "./types";

/** 화면 링크는 인증정보·로컬 주소가 없는 공개 HTTPS 도메인만 허용한다. DNS 조회는 하지 않는다. */
export function calendarSourceUrl(nextExam: NextExam | null | undefined): string | null {
  const value = nextExam?.source_url;
  if (typeof value !== "string" || !value || /\s/.test(value)) return null;
  try {
    const url = new URL(value);
    const host = url.hostname.toLowerCase().replace(/\.$/, "");
    if (url.protocol !== "https:" || !host.includes(".") || url.username || url.password || (url.port && url.port !== "443")) return null;
    if (host === "localhost" || /\.(?:local|localhost|internal)$/.test(host) || /^(?:\d+\.){3}\d+$/.test(host) || host.includes(":")) return null;
    return url.href;
  } catch {
    return null;
  }
}

export function isVerifiedExam(nextExam: NextExam | null | undefined): boolean {
  return Boolean(nextExam?.verified === true && Number.isFinite(nextExam.days_left) && calendarSourceUrl(nextExam));
}

/** 확인 기록과 출처가 없는 날짜는 확정 D-day로 승격하지 않는다. */
export function dDayLabel(nextExam: NextExam | null | undefined): string {
  if (!nextExam) return "";
  if (!isVerifiedExam(nextExam)) return `${nextExam.name ? nextExam.name + " · " : ""}미확인 추정 시기 · 공식 공고·모집요강 확인`;
  const days = Math.trunc(nextExam.days_left);
  const d = days === 0 ? "D-Day" : days > 0 ? `D-${days}` : `D+${Math.abs(days)}`;
  return nextExam.name ? `${nextExam.name} ${d}` : d;
}

export function calendarTimeliness(nextExam: NextExam | null | undefined, value: number | null | undefined): number | null {
  return isVerifiedExam(nextExam) && typeof value === "number" && Number.isFinite(value) ? timelinessPercent(value) : null;
}

/** 서버의 시의성 0..1을 막대 폭(0~100 정수)으로. */
export function timelinessPercent(value: number | null | undefined): number {
  if (typeof value !== "number" || !Number.isFinite(value)) return 0;
  return Math.round(Math.min(1, Math.max(0, value)) * 100);
}
