import type { Metadata } from "next";
import "./fonts.css";
import "./globals.css";
import "./theme.css";

export const metadata: Metadata = {
  title: "HeoBrain 콘텐츠 오피스",
  description:
    "공식 RSS에서 검증된 한국어 원고와 블로그·영상 제작까지, 나의 AI 콘텐츠 편집실.",
  robots: { index: false, follow: false },
};

/** Applies the saved light/dark choice before the first paint so the page never flashes. */
const themeBootstrap = `try{var t=localStorage.getItem("office-theme");if(t==="light"||t==="dark")document.documentElement.dataset.theme=t}catch(e){}`;

export default function RootLayout({
  children,
}: Readonly<{ children: React.ReactNode }>) {
  return (
    <html lang="ko" suppressHydrationWarning>
      <head>
        <script dangerouslySetInnerHTML={{ __html: themeBootstrap }} />
      </head>
      <body>{children}</body>
    </html>
  );
}
