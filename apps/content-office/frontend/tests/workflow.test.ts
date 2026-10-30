import test from "node:test";
import assert from "node:assert/strict";
import {
  mainVideoFile,
  draftStatus,
  acceptJobRefresh,
  createJobRefreshGuard,
  evidenceInputAllowed,
  retryBlockedReason,
  completedOutputs,
  validReleaseOutputs,
  toggleArticle,
  canApproveSource,
  safeArtifactUrl,
  remainingWindow,
  workWindowBlockedReason,
  approvalIsCurrent,
  sourceApproved,
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

test("목록용 작업 메타데이터만으로 재요청 판본·대사 차단을 보존한다", () => {
  const task = { id: "task-metadata", kind: "draft", state: "failed", payload: { job_id: "job-metadata", source_hash: null } };
  const job = { id: "job-metadata", title: "편입", state: "failed", updated_at: "2026-10-30T01:00:00Z", source_hash: null, has_source: false };
  assert.equal(retryBlockedReason(task, job, [task]), null);
  assert.ok(retryBlockedReason(task, { ...job, source_hash: "a".repeat(64) }, [task]));
  assert.ok(retryBlockedReason(task, { ...job, state: "needs_reconciliation" }, [task]));
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

test("작업 조회는 중첩하지 않고 실패 뒤에도 다음 조회를 허용한다", () => {
  const guard = createJobRefreshGuard();
  guard.select("job-a");
  const failed = guard.begin("job-a");
  assert.ok(failed);
  assert.equal(guard.begin("job-a"), null);
  assert.equal(guard.settle(failed), true);
  assert.ok(guard.begin("job-a"));
});

test("작업을 바꾸면 예전 성공·오류가 새 작업의 진행 중 조회를 해제하지 않는다", () => {
  const guard = createJobRefreshGuard();
  guard.select("job-a");
  const old = guard.begin("job-a");
  assert.ok(old);
  guard.select("job-b");
  const current = guard.begin("job-b");
  assert.ok(current);
  assert.equal(guard.settle(old), false);
  assert.equal(guard.begin("job-b"), null);
  assert.equal(guard.invalidate("job-a"), false);
  assert.equal(guard.settle(current), true);
  assert.equal(guard.activeId, "job-b");
});

test("저장 뒤 옛 GET이 역순 도착해도 저장 결과와 새 조회를 덮지 않는다", async () => {
  const guard = createJobRefreshGuard();
  guard.select("job-a");
  let resolveOld!: (value: string) => void;
  const oldResponse = new Promise<string>((resolve) => { resolveOld = resolve; });
  let displayed = "v1";
  const old = guard.begin("job-a");
  assert.ok(old);
  const pendingOld = oldResponse.then((value) => { if (guard.settle(old)) displayed = value; });
  assert.equal(guard.invalidate("job-a"), true);
  displayed = "saved-v2";
  const fresh = guard.begin("job-a");
  assert.ok(fresh);
  if (guard.settle(fresh)) displayed = "fresh-v2";
  resolveOld("stale-v1");
  await pendingOld;
  assert.equal(displayed, "fresh-v2");
  assert.ok(guard.begin("job-a"));
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

test("① 원고 승인 이후 상태만 승인 원고 파생물을 만들 수 있다", () => {
  for (const state of ["source_approved", "production_queued", "producing", "release_review", "partial_release_review", "release_approved"])
    assert.equal(sourceApproved(state), true, state);
  for (const state of ["draft", "source_review", "source_rejected", "blocked", "failed", ""]) assert.equal(sourceApproved(state), false, state);
});

test("draftStatus reports the latest draft task of this job in plain words", () => {
  const job = { id: "job_a", source_hash: null };
  assert.deepEqual(draftStatus([], job), { state: "idle", label: "아직 요청 전", detail: "" });
  const tasks = [
    { id: "t1", kind: "draft", state: "failed", created_at: "2026-10-30T00:00:00Z", payload: { job_id: "job_a", source_hash: null }, result: { error: "모델 제공자가 HTTP 503를 반환했습니다" } },
    { id: "t2", kind: "draft", state: "queued", created_at: "2026-10-30T00:05:00Z", payload: { job_id: "job_a", source_hash: null } },
    { id: "t9", kind: "draft", state: "running", created_at: "2026-10-30T00:06:00Z", payload: { job_id: "job_other", source_hash: null } },
  ];
  assert.equal(draftStatus(tasks, job).state, "queued");
  assert.equal(draftStatus(tasks, job).label, "대기 중");
  const running = draftStatus([{ ...tasks[1], state: "running", owner: "worker_1" }], job);
  assert.equal(running.state, "running");
  assert.ok(running.label.includes("진행 중"));
  const failed = draftStatus([tasks[0]], job);
  assert.equal(failed.state, "failed");
  assert.equal(failed.label, "실패");
  assert.ok(failed.detail.includes("503"));
  const unknown = draftStatus([{ ...tasks[0], state: "unknown" }], job);
  assert.equal(unknown.state, "unknown");
  assert.ok(unknown.label.includes("결과 불명"));
  const done = draftStatus([{ ...tasks[0], state: "completed", result: {} }], job);
  assert.equal(done.state, "completed");
  assert.equal(done.label, "완료");
});

test("생성 작업 시간은 종료·미설정·손상된 시각을 차단하고 열린 창만 허용한다", () => {
  const now = Date.parse("2026-10-30T00:00:00Z");
  assert.ok(workWindowBlockedReason(undefined, now));
  assert.ok(workWindowBlockedReason({ authorized_end: "bad" }, now));
  assert.ok(workWindowBlockedReason({ authorized_end: "2026-10-29T23:59:59Z" }, now));
  assert.ok(workWindowBlockedReason({ authorized_end: "2026-10-30T01:00:00Z", status: "closed" }, now));
  assert.equal(workWindowBlockedReason({ authorized_end: "2026-10-30T01:00:00Z", status: "open" }, now), undefined);
});

test("영상 보기는 장면 클립보다 완성 영상(short.mp4)을 먼저 고른다", () => {
  const files = [
    { name: "generated-01.mp4", kind: "video" },
    { name: "clip-01.mp4", kind: "video" },
    { name: "short.mp4", kind: "video" },
  ];
  assert.equal(mainVideoFile(files)?.name, "short.mp4");
  assert.equal(mainVideoFile([{ name: "generated-01.mp4", kind: "video" }])?.name, "generated-01.mp4");
  assert.equal(mainVideoFile([{ name: "a.txt" }]), undefined);
});
