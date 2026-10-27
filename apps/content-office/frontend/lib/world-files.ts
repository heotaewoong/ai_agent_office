import { posix, resolve } from "node:path";

export const WORLD_ROOT = resolve(process.cwd(), "..", "..", "..", "sites", "office-world");

const TYPES: Record<string, string> = {
  ".html": "text/html; charset=utf-8",
  ".css": "text/css; charset=utf-8",
  ".js": "text/javascript; charset=utf-8",
  ".json": "application/json; charset=utf-8",
  ".png": "image/png",
  ".svg": "image/svg+xml",
  ".ico": "image/x-icon",
};

export function resolveWorldFile(
  root: string,
  segments: string[] | undefined,
): { path: string; type: string } | null {
  const parts = segments && segments.length ? segments : ["index.html"];
  if (parts.some((p) => p === ".." || p.includes("\\") || p.includes("\0"))) return null;
  const base = posix.normalize(root.replace(/\\/g, "/"));
  const path = posix.normalize(posix.join(base, ...parts));
  if (!path.startsWith(base.endsWith("/") ? base : base + "/")) return null;
  const type = TYPES[posix.extname(path).toLowerCase()];
  return type ? { path, type } : null;
}
