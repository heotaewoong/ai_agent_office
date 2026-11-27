export type View = "home" | "news" | "sources" | "plans" | "studio" | "delivery" | "world" | "settings" | "activity" | "architecture" | "create";
const paths: Record<View, string> = { home: "/", news: "/news", sources: "/sources", plans: "/plans", studio: "/scripts", delivery: "/publish", world: "/office3d", settings: "/settings", activity: "/runs", architecture: "/pipeline", create: "/create" };
export function officeHref(view: View, jobId = "") {
  return paths[view] + (view === "studio" && jobId ? "/" + encodeURIComponent(jobId) : view === "delivery" && jobId ? "?job=" + encodeURIComponent(jobId) : "");
}
export function officeRoute(path: string): { view: View; jobId?: string } {
  const pathname = path.split("?")[0].replace(/\/$/, "") || "/";
  if (pathname === "/benchmarks") return { view: "news" };
  if (pathname.startsWith("/scripts/")) {
    try { return { view: "studio", jobId: decodeURIComponent(pathname.slice(9)) }; } catch { return { view: "studio" }; }
  }
  return { view: (Object.entries(paths).find(([, value]) => value === pathname)?.[0] ?? "home") as View };
}
