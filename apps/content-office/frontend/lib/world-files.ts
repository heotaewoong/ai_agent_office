import { posix, resolve } from "node:path";
import { readFile } from "node:fs/promises";
import { gzip } from "node:zlib";
import { promisify } from "node:util";
const gzipAsync = promisify(gzip);

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
  const type = path === posix.join(base, "vendor", "LICENSE-babylon.txt")
    ? "text/plain; charset=utf-8"
    : TYPES[posix.extname(path).toLowerCase()];
  return type ? { path, type } : null;
}

export function acceptsWorldGzip(header: string | null): boolean {
  const choices = new Map<string, number>();
  for (const entry of (header ?? "").split(",")) {
    const match = entry.trim().match(/^(gzip|\*)(?:\s*;\s*q\s*=\s*(0(?:\.\d{0,3})?|1(?:\.0{0,3})?))?$/i);
    if (match) choices.set(match[1].toLowerCase(), Number(match[2] ?? 1));
  }
  return (choices.get("gzip") ?? choices.get("*") ?? 0) > 0;
}

/** Keep existing sidecars; compress changing JS/CSS asynchronously without a stale cache. */
export async function readWorldFile(file: { path: string; type: string }, encoding: string | null) {
  if ((file.path.endsWith(".json") || file.path.endsWith("/vendor/babylon.min.js")) && acceptsWorldGzip(encoding)) {
    try {
      return { body: await readFile(file.path + ".gz"), encoding: "gzip" };
    } catch (cause) {
      if ((cause as NodeJS.ErrnoException).code !== "ENOENT") throw cause;
    }
  }
  const body = await readFile(file.path);
  if (/\.(js|css)$/.test(file.path) && body.length > 1024 && acceptsWorldGzip(encoding)) {
    const compressed = await gzipAsync(body, { level: 6 });
    if (compressed.length < body.length) return { body: compressed, encoding: "gzip" };
  }
  return { body, encoding: null };
}
