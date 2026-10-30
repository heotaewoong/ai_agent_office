import type { Metadata } from "next";
import { leadSourceFromQuery, magnetKeyFromQuery } from "../../lib/public-lead";
import { LeadSignup } from "./lead-signup";

// 독자가 직접 여는 공개 신청 페이지. 운영자 화면(셸)과 운영 데이터는 불러오지 않습니다.
export const metadata: Metadata = {
  title: "무료 자료 신청 · HeoBrain",
  description: "HeoBrain 무료 학습 자료 신청",
  robots: { index: false, follow: false },
  // 기본 /favicon.ico 요청을 만들지 않아 공개 예외 경로를 늘리지 않습니다.
  icons: { icon: "data:," },
};

export default async function LeadPage({ searchParams }: { searchParams: Promise<Record<string, string | string[] | undefined>> }) {
  const params = await searchParams;
  return <LeadSignup magnetKey={magnetKeyFromQuery(params.m)} source={leadSourceFromQuery(params.src)} />;
}
