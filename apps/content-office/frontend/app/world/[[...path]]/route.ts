import { readFile } from "node:fs/promises";
import { resolveWorldFile, WORLD_ROOT } from "../../../lib/world-files";

export const dynamic = "force-dynamic";

export async function GET(
  _req: Request,
  { params }: { params: Promise<{ path?: string[] }> },
) {
  const segs = (await params).path;
  if (!segs || segs.length === 0)
    return new Response(null, { status: 302, headers: { Location: "/world/index.html" } });
  const file = resolveWorldFile(WORLD_ROOT, segs);
  if (!file) return new Response("Not found", { status: 404 });
  try {
    return new Response(await readFile(file.path), {
      headers: { "Content-Type": file.type, "Cache-Control": "no-store", "X-Content-Type-Options": "nosniff" },
    });
  } catch {
    return new Response("Not found", { status: 404 });
  }
}
