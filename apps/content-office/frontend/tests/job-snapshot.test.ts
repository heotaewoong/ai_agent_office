import test from "node:test";
import assert from "node:assert/strict";
import { reuseUnchangedJob } from "../lib/job-snapshot.ts";
import type { Job } from "../lib/types.ts";

const initial = { id: "job-a", state: "source_review", source_hash: "same-source", title: "원고", tasks: [{ id: "task-a", state: "queued" }], source_packet: { body: "사용자 원고", quality: { status: "passed" } }, manifest: { hash: "same-manifest", files: [] } } as unknown as Job;

test("동일 조회는 기존 참조를 유지하고 첫 조회와 다른 작업은 새 내용을 사용한다", () => {
  const fresh = JSON.parse(JSON.stringify(initial)) as Job;
  assert.equal(reuseUnchangedJob(initial, fresh), initial);
  assert.equal(reuseUnchangedJob(null, fresh), fresh);
  const other = { ...fresh, id: "job-b" };
  assert.equal(reuseUnchangedJob(initial, other), other);
});

test("원고 해시가 같아도 작업 진행·검수·제작 파일 변경은 모두 갱신한다", () => {
  for (const change of [
    { tasks: [{ id: "task-a", state: "failed", error: "합성 실패" }] },
    { source_packet: { ...initial.source_packet, quality: { status: "failed", critical: true } } },
    { manifest: { ...initial.manifest, files: [{ id: "asset-a", name: "short.mp4" }] } },
    { state: "release_review" },
    { selections: { blog: true, video: false, cards: false, pdf: false } },
  ]) {
    const next = { ...initial, ...change } as unknown as Job;
    assert.equal(reuseUnchangedJob(initial, next), next);
  }
});

test("비교는 서버 응답이나 보존한 원고·제작 파일을 수정하지 않는다", () => {
  const next = JSON.parse(JSON.stringify(initial)) as Job;
  const before = JSON.stringify(initial);
  reuseUnchangedJob(initial, next);
  assert.equal(JSON.stringify(initial), before);
  assert.equal(JSON.stringify(next), before);
});
