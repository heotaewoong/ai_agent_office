import test from "node:test";
import assert from "node:assert/strict";
import {
  acceptJobRefresh,
  evidenceInputAllowed,
  retryBlockedReason,
  completedOutputs,
  validReleaseOutputs,
  toggleArticle,
  canApproveSource,
  safeArtifactUrl,
  remainingWindow,
  approvalIsCurrent,
} from "../lib/workflow.ts";

test("근거 입력은 준비·실패 또는 실제 근거가 없는 작업에만 나타난다", () => {
  assert.equal(
    evidenceInputAllowed({
      state: "source_review",
      article: { evidence: [{ id: "e1" }] },
    }),
    false,
  );
  assert.equal(
    evidenceInputAllowed({
      state: "research_ready",
      article: { evidence: [{}] },
    }),
    true,
  );
  assert.equal(
    evidenceInputAllowed({ state: "failed", article: { evidence: [{}] } }),
    true,
  );
  assert.equal(
    evidenceInputAllowed({ state: "source_review", article: { evidence: [] } }),
    true,
  );
});

test("재시도는 현재 판본의 등록된 실패 작업만 허용하고 중복·결과불명을 차단한다", () => {
  const task = {
    id: "task-1",
    kind: "draft",
    state: "failed",
    payload: { job_id: "job-1", source_hash: "v1" },
  };
  const job = { id: "job-1", state: "failed", source_hash: "v1" };
  assert.equal(retryBlockedReason(task, job, [task]), null);
  assert.ok(retryBlockedReason({ ...task, state: "completed" }, job));
  assert.ok(retryBlockedReason(task, { ...job, source_hash: "v2" }));
  assert.ok(
    retryBlockedReason(
      { ...task, state: "unknown" },
      { ...job, state: "needs_reconciliation" },
    ),
  );
  assert.ok(
    retryBlockedReason(task, job, [
      task,
      { ...task, id: "task-2", state: "running" },
    ]),
  );
  assert.equal(
    retryBlockedReason(task, job, [
      task,
      {
        ...task,
        id: "task-2",
        state: "running",
        payload: { job_id: "job-1", source_hash: "older-v0" },
      },
    ]),
    null,
  );
  assert.ok(retryBlockedReason({ ...task, id: undefined }, job));
  assert.equal(
    retryBlockedReason({
      id: "refresh-1",
      kind: "refresh",
      state: "failed",
      payload: {},
    }),
    null,
  );
  assert.equal(
    retryBlockedReason({ ...task, kind: "produce", state: "partial" }, job),
    null,
  );
});

test("영상이 실패해도 완료된 블로그만 출고하며 빈 항목과 미완료 영상은 막는다", () => {
  const job = {
    state: "partial_release_review",
    selections: { blog: true, video: true, cards: false, pdf: false },
    manifest: {
      hash: "m1",
      files: [],
      completed_outputs: ["blog" as const],
      output_status: {
        blog: { state: "completed" },
        video: { state: "failed", error: "음성 실패" },
      },
    },
  };
  assert.deepEqual(completedOutputs(job), ["blog"]);
  assert.equal(validReleaseOutputs(job, ["blog"]), true);
  assert.equal(validReleaseOutputs(job, ["video"]), false);
  assert.equal(validReleaseOutputs(job, []), false);
  assert.deepEqual(
    completedOutputs({ ...job, manifest: { hash: "m1", files: [] } }),
    [],
  );
});

test("다른작업의늦은응답이현재검토중인문서를덮어쓰지않는다", () => {
  const current = { id: "job-b", state: "source_review" };
  assert.equal(
    acceptJobRefresh(current, { id: "job-a", state: "source_approved" }),
    current,
  );
  const update = { id: "job-b", state: "source_approved" };
  assert.equal(acceptJobRefresh(current, update), update);
  assert.equal(acceptJobRefresh(null, update), null);
});

test("뉴스 네 번째 선택을 막고 기존 선택은 해제할 수 있다", () => {
  assert.deepEqual(toggleArticle(["a", "b", "c"], "d"), ["a", "b", "c"]);
  assert.deepEqual(toggleArticle(["a", "b", "c"], "b"), ["a", "c"]);
  assert.deepEqual(toggleArticle(["a"], "b"), ["a", "b"]);
});

test("검수 전 원고·중대 오류·저장 안 된 변경은 승인할 수 없다", () => {
  const base = {
    source_hash: "hash-v1",
    state: "source_review",
    source_packet: {
      title: "기사",
      body: "본문",
      quality: { status: "passed", critical: false },
    },
  };
  assert.equal(canApproveSource(base), true);
  assert.equal(canApproveSource(base, true), false);
  assert.equal(canApproveSource({ ...base, source_hash: "" }), false);
  assert.equal(canApproveSource({ ...base, state: "drafting" }), false);
  assert.equal(
    canApproveSource({
      ...base,
      source_packet: {
        ...base.source_packet,
        quality: { status: "blocked", critical: true },
      },
    }),
    false,
  );
  assert.equal(
    canApproveSource({
      ...base,
      source_packet: {
        ...base.source_packet,
        quality: { status: "unverified", critical: false },
      },
    }),
    false,
  );
  assert.equal(
    canApproveSource({
      ...base,
      source_packet: { title: "기사", body: "본문" },
    }),
    false,
  );
});

test("산출물 미리보기는 로컬 API 경로만 허용한다", () => {
  assert.equal(
    safeArtifactUrl("/api/artifacts/video-1"),
    "/api/artifacts/video-1",
  );
  assert.equal(safeArtifactUrl("javascript:alert(1)"), null);
  assert.equal(safeArtifactUrl("https://outside.example/leak"), null);
  assert.equal(safeArtifactUrl("//outside.example/leak"), null);
  assert.equal(safeArtifactUrl("/api/artifacts/../session"), null);
});

test("남은 시간은 실제 마감으로 계산하고 마감 후에는 종료 표시한다", () => {
  const now = Date.parse("2026-10-25T17:20:00Z");
  assert.equal(remainingWindow("2026-10-25T23:20:00Z", now), "6시간 0분");
  assert.equal(remainingWindow("2026-10-25T17:19:59Z", now), "작업 시간 종료");
  assert.equal(remainingWindow(undefined, now), "마감 미설정");
});

test("승인 확인을 연 뒤 버전이 바뀌면 새 원고나 파일을 묵시 승인하지 않는다", () => {
  assert.equal(approvalIsCurrent("reviewed-v1", "reviewed-v1"), true);
  assert.equal(approvalIsCurrent("reviewed-v1", "new-v2"), false);
  assert.equal(approvalIsCurrent(undefined, undefined), false);
  assert.equal(approvalIsCurrent("", ""), false);
});
