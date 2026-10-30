import test from "node:test";
import assert from "node:assert/strict";
import { productionNext } from "../lib/production-next.ts";
import type { Job } from "../lib/types.ts";

test("empty outbox points to the exact unapproved source, not a false delivery", () => {
  const job = { id: "job_one", state: "source_review", source_hash: "new", source_approval: { version: "old", decision: "approved" }, selections: {} } as Job;
  assert.equal(productionNext(job)?.href, "/scripts/job_one");
  assert.match(productionNext(job)!.title, /승인①/);
});
test("a queued job does not ask for duplicate production", () => {
  assert.equal(productionNext({ state: "production_queued" } as Job)?.href, null);
  assert.equal(productionNext({ manifest: { files: [{ name: "article.md" }] } } as Job), null);
});
