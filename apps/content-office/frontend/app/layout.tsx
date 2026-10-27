import type { Metadata } from "next";
import "./globals.css";

export const metadata: Metadata = {
  title: "HeoBrain — 콘텐츠 오피스",
  description:
    "공식 RSS에서 검증된 한국어 원고와 블로그·영상 제작까지, 나의 AI 콘텐츠 편집실.",
  robots: { index: false, follow: false },
};

export default function RootLayout({
  children,
}: Readonly<{ children: React.ReactNode }>) {
  return (
    <html lang="ko">
      <body>{children}</body>
    </html>
  );
}
