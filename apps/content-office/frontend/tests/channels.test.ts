import test from "node:test";
import assert from "node:assert/strict";
import { channelMismatch, validChannelId, youtubeChannels, deliveryLabel, localeLabel } from "../lib/channels.ts";
import type { Channel } from "../lib/types.ts";

const ko: Channel = { key: "youtube_main_ko", platform: "youtube", label: "YouTube 메인", locale: "ko", public_url: "https://www.youtube.com/@heobrain", external_account_id: "", delivery: "youtube_api", publication_enabled: false, credentials_configured: true };
const en: Channel = { ...ko, key: "youtube_english", label: "YouTube 영어", locale: "en", external_account_id: "UCc2CaOrPo-1dezowe7kklZA", credentials_configured: false };
const ig: Channel = { ...ko, key: "instagram_main", platform: "instagram", delivery: "manual" };

test("브리프 언어와 채널 언어가 다르면 안내 문구를 돌려준다", () => {
  assert.equal(channelMismatch({ language: "ko" }, ko), null);
  const msg = channelMismatch({ language: "ko" }, en);
  assert.ok(msg && msg.includes("한국어") && msg.includes("영어"));
  assert.equal(channelMismatch(undefined, en), null);
  assert.equal(channelMismatch({ language: "en" }, { ...en, locale: "" }), null);
});

test("YouTube 채널 ID 형식", () => {
  assert.equal(validChannelId("UCc2CaOrPo-1dezowe7kklZA"), true);
  assert.equal(validChannelId(""), true);
  assert.equal(validChannelId("UCshort"), false);
  assert.equal(validChannelId("@heobrain"), false);
  assert.equal(validChannelId("UCc2CaOrPo-1dezowe7kklZA/evil"), false);
});

test("YouTube 채널만 고른다", () => {
  assert.deepEqual(youtubeChannels([ko, ig, en]).map((c) => c.key), ["youtube_main_ko", "youtube_english"]);
});

test("전달 방식·언어 표시", () => {
  assert.equal(deliveryLabel("youtube_api"), "공식 API 비공개 업로드");
  assert.equal(deliveryLabel("manual"), "수동 게시");
  assert.equal(deliveryLabel("notify"), "검토 알림만");
  assert.equal(deliveryLabel("other"), "other");
  assert.equal(localeLabel("ko"), "한국어");
  assert.equal(localeLabel("en"), "영어");
  assert.equal(localeLabel(""), "-");
});
