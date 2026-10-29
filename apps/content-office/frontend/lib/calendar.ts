import type { NextExam } from "./types";

/** 기획 카드에 붙는 D-day 배지 문구. 다음 시험이 없으면 빈 문자열. */
export function dDayLabel(nextExam: NextExam | null | undefined): string {
  if (!nextExam) return "";
  const days = Math.trunc(nextExam.days_left);
  const d = days === 0 ? "D-Day" : days > 0 ? `D-${days}` : `D+${Math.abs(days)}`;
  return nextExam.name ? `${nextExam.name} ${d}` : d;
}

/** 서버의 시의성 0..1을 막대 폭(0~100 정수)으로. */
export function timelinessPercent(value: number | null | undefined): number {
  if (typeof value !== "number" || !Number.isFinite(value)) return 0;
  return Math.round(Math.min(1, Math.max(0, value)) * 100);
}
