import test from "node:test";
import assert from "node:assert/strict";
import { requirePrivateDeliveryResult } from "../lib/delivery-readiness.ts";

test("PC 전달 대기는 업로드 완료와 구분하고 다른 채널·가짜 대기를 허용하지 않는다", () => {
  const pending = {id:"delivery_0123456789abcdef",state:"pending_owner",auth_location:"owner_pc",channel_key:"youtube_main_ko",visibility:"private"};
  assert.equal(requirePrivateDeliveryResult(pending as never,"youtube_main_ko"),"pending_owner");
  assert.throws(()=>requirePrivateDeliveryResult(pending as never,"youtube_english"));
  assert.throws(()=>requirePrivateDeliveryResult({...pending,auth_location:undefined} as never,"youtube_main_ko"));
  assert.throws(()=>requirePrivateDeliveryResult({...pending,external_id:"unexpected"} as never,"youtube_main_ko"));
});
import { channelHandoffStatus, deliveryRecordLabel, packetLanguage, requirePrivateUploadResult, requireStagingSnapshot, sourceChannelMismatch, stagingExternalLabel, stagingLocalLabel, youtubePreflight } from "../lib/delivery-readiness.ts";

const job = { id: "fixture", source_hash: "source1", source_packet: { title: "가상 원고", body: "가상 본문", audience: { language: "ko" } }, selections: { video: true }, brief: { language: "ko" }, manifest: { hash: "m1", source_hash: "source1", files: [{ name: "short.mp4", outputs: ["video"] }, { name: "tistory.html", outputs: ["blog"] }] }, release_approval: { decision: "approved", version: "m1", outputs: ["video", "blog"] } };
const channel = { label: "가상 채널", locale: "ko", credentials_configured: true, publication_enabled: true };

test("YouTube 요청은 선택 채널·허용·현재 승인·작업창이 모두 필요하다", () => {
  assert.equal(youtubePreflight(job as never, channel as never).ok, true);
  assert.equal(youtubePreflight(job as never, undefined).ok, false);
  assert.match(youtubePreflight(job as never, { ...channel, publication_enabled: false } as never).reason, /허용이 꺼져/);
  assert.match(youtubePreflight(job as never, channel as never, "작업 시간이 종료됐습니다").reason, /종료/);
  assert.equal(youtubePreflight(job as never, { ...channel, credentials_configured: false } as never).ok, false);
  assert.equal(youtubePreflight(job as never, { ...channel, locale: "en" } as never).ok, false);
  assert.equal(youtubePreflight({ ...job, release_approval: { ...job.release_approval, version: "m0" } } as never, channel as never).ok, false);
  assert.match(youtubePreflight({ ...job, source_hash: "new-source" } as never, channel as never).reason, /부모 원고/);
});

test("다음 브리프를 영어로 바꿔도 승인된 한국어 제작물을 영어 채널 준비로 표시하지 않는다", () => {
  const nextEnglish = { ...job, brief: { language: "en" } };
  assert.equal(packetLanguage(nextEnglish as never), "ko");
  assert.equal(sourceChannelMismatch(nextEnglish as never, channel as never), null);
  assert.match(sourceChannelMismatch(nextEnglish as never, { ...channel, locale: "en" } as never) ?? "", /원고는 한국어.*영어 채널.*기존 콘텐츠가 번역되지는/);
  assert.equal(youtubePreflight(nextEnglish as never, channel as never).ok, true);
  assert.equal(youtubePreflight(nextEnglish as never, { ...channel, locale: "en" } as never).ok, false);
});

test("과거 원고의 언어 기록이 없거나 지원 밖이면 브리프 추정 대신 재검수를 요구한다", () => {
  for (const source_packet of [undefined, { ...job.source_packet, audience: undefined }, { ...job.source_packet, audience: { language: "" } }, { ...job.source_packet, audience: { language: "fr" } }]) {
    const legacy = { ...job, source_packet };
    assert.equal(packetLanguage(legacy as never), null);
    assert.match(sourceChannelMismatch(legacy as never, channel as never) ?? "", /언어 기록.*재검수/);
    assert.equal(youtubePreflight(legacy as never, channel as never).ok, false);
  }
});

test("앱 파일 준비를 플랫폼 임시저장이나 업로드로 표시하지 않고 X 보류를 우선한다", () => {
  const row = { status: "local_ready", local_ready: true, platform: "threads", external_state: "not_connected", external_draft_created: false, external_id: null } as const;
  assert.match(stagingLocalLabel(row), /준비됨.*앱 내부/);
  assert.match(stagingExternalLabel(row), /플랫폼 미연결.*임시저장 없음/);
  assert.match(stagingLocalLabel({ ...row, status: "paused" }), /보류/);
  assert.match(stagingLocalLabel({ ...row, status: "blocked", local_ready: false }), /미완료/);
  assert.match(stagingExternalLabel({ ...row, external_draft_created: true }), /임시저장 없음/);
});

test("빈·다른 작업·중복·손상 준비표를 기록 가능한 현재 판본으로 사용하지 않는다", () => {
  const row = { channel_key: "threads_main", label: "Threads", platform: "threads", locale: "ko", local_ready: true, blockers: [], required_files: ["threads-main.txt"], files: [{ name: "threads-main.txt", sha256: "b".repeat(64) }] };
  const valid = { job_id: "synthetic", stage_hash: "a".repeat(64), current_release: true, recorded_current: false, blockers: [], notes: [], channels: [row] };
  assert.doesNotThrow(() => requireStagingSnapshot(valid as never, "synthetic"));
  for (const invalid of [null, {}, { ...valid, channels: [] }, { ...valid, channels: [row, row] }, { ...valid, channels: [{ ...row, required_files: null }] }, { ...valid, channels: [{ ...row, files: [{ name: "f", sha256: "bad" }] }] }])
    assert.throws(() => requireStagingSnapshot(invalid as never, "synthetic"), /비어 있거나.*판본/);
  assert.throws(() => requireStagingSnapshot(valid as never, "other-job"), /판본/);
});

test("외부 상태는 실제 ID 있는 비공개 기록·불명·확인 필요를 각각 표시한다", () => {
  const row = { platform: "youtube", external_state: "private", external_draft_created: false, external_id: "fixture_vid" } as const;
  assert.match(stagingExternalLabel(row), /비공개 확인 기록/);
  assert.match(stagingExternalLabel({ ...row, external_id: null }), /ID 확인 필요/);
  assert.match(stagingExternalLabel({ ...row, external_state: "unknown" }), /불명.*대사/);
  assert.match(stagingExternalLabel({ ...row, external_state: "needs_review" }), /확인 필요/);
  assert.match(stagingExternalLabel({ ...row, external_state: "not_attempted", external_id: null }), /전송 미실행.*임시저장 없음/);
});

test("HTTP 성공이어도 private·실제 공개범위·영상 ID가 없는 업로드를 완료로 표시하지 않는다", () => {
  const completed = { state: "private", privacy_status: "private", external_id: "fixture_vid" };
  assert.doesNotThrow(() => requirePrivateUploadResult(completed as never));
  for (const state of ["created", "accepted", "unknown", "needs_review", "failed", "published"])
    assert.throws(() => requirePrivateUploadResult({ ...completed, state } as never), /완료로 처리하지/);
  for (const privacy_status of [undefined, "public", "unlisted"])
    assert.throws(() => requirePrivateUploadResult({ ...completed, privacy_status } as never), /확인 필요/);
  assert.throws(() => requirePrivateUploadResult({ ...completed, external_id: undefined } as never), /확인 필요/);
  assert.match(deliveryRecordLabel({ ...completed, privacy_status: undefined } as never), /확인 필요/);
});

test("출고 묶음은 현재 승인된 실제 파일만 준비로 표시하고 소셜 임시저장을 주장하지 않는다", () => {
  assert.match(channelHandoffStatus(job as never, "tistory"), /앱 출고 묶음 준비/);
  assert.match(channelHandoffStatus(job as never, "naver"), /파일 없음/);
  assert.match(channelHandoffStatus({ ...job, source_hash: "new-source" } as never, "tistory"), /부모 원고.*불일치/);
  assert.match(channelHandoffStatus({ ...job, source_hash: undefined } as never, "youtube"), /부모 원고.*미확인/);
  assert.match(channelHandoffStatus({ ...job, release_approval: { ...job.release_approval, version: "old" } } as never, "tistory"), /승인② 필요/);
  assert.match(channelHandoffStatus({ ...job, manifest: { ...job.manifest, files: [{ name: "tistory.html", outputs: ["video"] }] } } as never, "tistory"), /파일 없음/);
  for (const platform of ["threads", "linkedin", "x", "instagram"]) assert.match(channelHandoffStatus(job as never, platform), /검토 초안 없음/);
  const withSocial = { ...job, manifest: { ...job.manifest, files: [...job.manifest.files, { name: "threads-main.txt", outputs: ["blog"] }, { name: "instagram-main-caption.txt", outputs: ["blog"] }, { name: "channel-handoff.json", outputs: ["blog"] }] } };
  assert.match(channelHandoffStatus(withSocial as never, "threads"), /검토 초안 있음.*플랫폼 임시저장 미연결/);
  assert.match(channelHandoffStatus(withSocial as never, "instagram"), /캡션만/);
  assert.match(channelHandoffStatus(withSocial as never, "instagram", "instagram_english"), /초안 없음/);
});
