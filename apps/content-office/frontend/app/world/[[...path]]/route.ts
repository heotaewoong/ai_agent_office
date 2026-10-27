import { readFile } from "node:fs/promises";
import { resolveWorldFile, WORLD_ROOT } from "../../../lib/world-files";

export const dynamic = "force-dynamic";

export async function GET(
  _req: Request,
  { params }: { params: Promise<{ path?: string[] }> },
) {
  const file = resolveWorldFile(WORLD_ROOT, (await params).path);
  if (!file) return new Response("Not found", { status: 404 });
  try {
    return new Response(await readFile(file.path), {
      headers: { "Content-Type": file.type, "Cache-Control": "no-store" },
    });
  } catch {
    return new Response("Not found", { status: 404 });
  }
}
