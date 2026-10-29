import type { Brief, Channel } from "./types";
import { LANGUAGE_LABELS } from "./briefs.ts";

const DELIVERY_LABELS: Record<string, string> = {
  youtube_api: "공식 API 비공개 업로드",
  manual: "수동 게시",
  notify: "검토 알림만",
};

export function deliveryLabel(delivery: string): string {
  return DELIVERY_LABELS[delivery] ?? delivery;
}

export function localeLabel(locale: string | undefined): string {
  if (!locale) return "-";
  return LANGUAGE_LABELS[locale] ?? locale;
}

/** 브리프 언어와 채널 언어가 다르면 업로드 전에 보여줄 문구. 같거나 알 수 없으면 null. */
export function channelMismatch(brief: Pick<Brief, "language"> | null | undefined, channel: Pick<Channel, "locale" | "label">): string | null {
  const language = brief?.language;
  if (!language || !channel.locale || language === channel.locale) return null;
  return `원고 언어는 ${localeLabel(language)}인데 ${channel.label} 채널은 ${localeLabel(channel.locale)} 채널입니다. 서버가 업로드를 막으니 작업 브리프의 언어나 채널을 바꾸세요.`;
}

/** YouTube channelId 형식. 비워 두는 것은 허용합니다(등록 전). */
export function validChannelId(value: string): boolean {
  const v = value.trim();
  return v === "" || /^UC[A-Za-z0-9_-]{22}$/.test(v);
}

export function youtubeChannels(channels: Channel[]): Channel[] {
  return channels.filter((c) => c.platform === "youtube");
}
