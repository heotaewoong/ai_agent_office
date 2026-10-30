import { Suspense } from "react";
import Office from "../office-shell";
export default function OfficeLayout({ children }: { children: React.ReactNode }) {
  return <Suspense fallback={<p role="status">오피스를 불러오는 중입니다.</p>}><Office>{children}</Office></Suspense>;
}
