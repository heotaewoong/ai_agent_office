export type View = "home" | "news" | "plans" | "studio" | "delivery" | "world" | "settings" | "activity" | "architecture";
const paths: Record<View, string> = { home: "/", news: "/news", plans: "/plans", studio: "/scripts", delivery: "/publish", world: "/office3d", settings: "/settings", activity: "/runs", architecture: "/pipeline" };
export function officeHref(view: View, jobId = "") {
  return paths[view] + (view === "studio" && jobId ? "/" + encodeURIComponent(jobId) : view === "delivery" && jobId ? "?job=" + encodeURIComponent(jobId) : "");
}
export function officeRoute(path: string): { view: View; jobId?: string } {
  const pathname = path.split("?")[0].replace(/\/$/, "") || "/";
  if (pathname.startsWith("/scripts/")) {
    try { return { view: "studio", jobId: decodeURIComponent(pathname.slice(9)) }; } catch { return { view: "studio" }; }
  }
  return { view: (Object.entries(paths).find(([, value]) => value === pathname)?.[0] ?? "home") as View };
}
