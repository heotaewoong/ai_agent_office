import type { Channel, Delivery, Job } from "./types";
import { channelMismatch, localeLabel } from "./channels.ts";
import { deliveryStateLabel, studioUrl, uploadReadiness } from "./settings.ts";

export function packetLanguage(job: Pick<Job, "source_packet">): "ko" | "en" | null {
  const language = job.source_packet?.audience?.language;
  return language === "ko" || language === "en" ? language : null;
}

/** 편집 중인 다음 브리프가 기존 제작물의 실제 언어를 바꾸지는 않는다. */
export function sourceChannelMismatch(job: Pick<Job, "source_packet">, channel: Pick<Channel, "locale" | "label">): string | null {
  const language = packetLanguage(job);
  if (!language) return "제작물에 연결된 원고의 언어 기록을 확인하지 못했습니다. 원고를 재검수하세요. 브리프만 바꿔도 기존 콘텐츠가 번역되지는 않습니다.";
  if (!channelMismatch({ language }, channel)) return null;
  return `제작물의 원고는 ${localeLabel(language)}인데 ${channel.label}은 ${localeLabel(channel.locale)} 채널입니다. 채널에 맞는 새 원고·제작물과 승인이 필요합니다. 다음 브리프만 바꿔도 기존 콘텐츠가 번역되지는 않습니다.`;
}

export function youtubePreflight(job: Job, channel: Channel | undefined, requestBlockedReason?: string) {
  if (requestBlockedReason) return { ok: false, reason: requestBlockedReason };
  if (!channel) return { ok: false, reason: "선택한 채널 설정을 읽지 못했습니다. 제작 설정의 채널 정보를 확인하세요." };
  const readiness = uploadReadiness(job, channel.credentials_configured);
  if (!readiness.ok) return readiness;
  if (!job.source_hash || job.manifest?.source_hash !== job.source_hash)
    return { ok: false, reason: "제작물의 부모 원고 판본이 현재 원고와 일치하지 않습니다. 현재 원고로 제작·출고 검토를 다시 하세요." };
  const mismatch = sourceChannelMismatch(job, channel);
  if (mismatch) return { ok: false, reason: mismatch };
  if (!channel.publication_enabled) return { ok: false, reason: "이 채널의 업로드 허용이 꺼져 있습니다. 제작 설정 → 채널에서 소유 채널과 전송 범위를 확인하세요." };
  return { ok: true, reason: "현재 영상 출고 승인②·채널 설정을 확인했습니다. 실제 OAuth와 YouTube 처리 결과는 업로드 후 장부에서 확인합니다." };
}

/** HTTP 202나 과거 예약 기록만으로 업로드 완료를 알리지 않는다. */
export function requirePrivateUploadResult(record: Delivery): void {
  if (record.state !== "private" || record.privacy_status !== "private" || !studioUrl(record.external_id))
    throw new Error(`YouTube 기록: ${deliveryRecordLabel(record)}. 완료로 처리하지 않았습니다. 업로드 장부와 Studio를 확인하고 결과가 불명이면 대사하세요.`);
}

export function deliveryRecordLabel(record: Pick<Delivery, "state" | "privacy_status" | "external_id">): string {
  if (record.state === "private" && (record.privacy_status !== "private" || !studioUrl(record.external_id)))
    return "업로드 기록 있음 · 비공개 범위/영상 ID 확인 필요";
  return deliveryStateLabel(record.state);
}

/** 파일 존재와 현재 출고 승인②를 구별하며 플랫폼 임시저장 성공으로 승격하지 않는다. */
export function channelHandoffStatus(job: Job, platform: string, channelKey?: string): string {
  const manifest = job.manifest;
  if (!manifest) return "제작물 없음";
  if (!job.source_hash || manifest.source_hash !== job.source_hash) return "제작물의 부모 원고 판본 미확인/불일치 · 현재 원고로 제작·출고 검토 필요";
  const outputs = new Set(job.release_approval?.decision === "approved" && job.release_approval.version === manifest.hash ? job.release_approval.outputs ?? [] : []);
  const file = (name: string, output: string) => manifest.files.some((entry) => entry.name === name && (entry.outputs ?? []).includes(output));
  if (platform === "tistory" || platform === "naver" || platform === "naver_blog") {
    if (!file(platform === "tistory" ? "tistory.html" : "naver.txt", "blog")) return "블로그 파일 없음";
    return outputs.has("blog") ? "앱 출고 묶음 준비 · 플랫폼 편집기에 직접 전달" : "앱에 블로그 파일 있음 · 현재 출고 승인② 필요";
  }
  if (platform === "youtube") {
    if (!file("short.mp4", "video")) return "영상 파일 없음";
    return outputs.has("video") ? "앱 영상 출고 준비 · 실제 업로드 결과는 아래 장부에서 확인" : "앱에 영상 파일 있음 · 현재 출고 승인② 필요";
  }
  const socialFile = platform === "instagram" ? channelKey === "instagram_english" ? "instagram-english-caption.txt" : "instagram-main-caption.txt" : ({ threads: "threads-main.txt", linkedin: "linkedin-personal.txt", x: "x-main.txt" } as Record<string, string>)[platform];
  if (socialFile) {
    if (!file(socialFile, "blog") || !file("channel-handoff.json", "blog")) return "채널별 검토 초안 없음 · 블로그 제작에서 함께 준비";
    const stage = outputs.has("blog") ? "앱 출고 묶음에 검토 초안 있음" : "앱에 검토 초안 있음 · 블로그 출고 승인② 필요";
    return `${stage} · ${platform === "instagram" ? "캡션만, 이미지/영상 별도 선택·검토" : "문구·길이·언어·채널 검토 필요"} · 플랫폼 임시저장 미연결`;
  }
  if (platform === "store") return "구매 링크 연결용 · 스토어 상품·쿠폰 발급은 별도";
  return "자동 전달 미구현 · 채널 용도 확인 필요";
}
