import test from "node:test";
import assert from "node:assert/strict";
import { channelHandoffStatus, deliveryRecordLabel, packetLanguage, requirePrivateUploadResult, sourceChannelMismatch, youtubePreflight } from "../lib/delivery-readiness.ts";

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
