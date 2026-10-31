import test from "node:test";
import assert from "node:assert/strict";
import {
  connectBlockedReason,
  connectionLabel,
  shortChannelId,
  withoutOAuthParams,
  youtubeOAuthResult,
  type YoutubeOAuthStatus,
} from "../lib/youtube-oauth.ts";
import { api } from "../lib/api.ts";

const ready: YoutubeOAuthStatus = {
  client_configured: true,
  public_origin_configured: true,
  redirect_uri: "https://office.example.com/api/youtube/oauth/callback",
  secrets_location_ok: true,
  channels: [],
};

test("콜백 결과 쿼리를 문구로 바꾼다", () => {
  const ok = youtubeOAuthResult("?youtube=connected&channel=youtube_main_ko");
  assert.equal(ok?.kind, "success");
  assert.equal(ok?.channel, "youtube_main_ko");
  assert.ok(ok?.message.includes("연결은 발행이 아니며") && ok.message.includes("출고 승인②"));
  const mismatch = youtubeOAuthResult("?youtube=error&reason=channel_mismatch&channel=youtube_english");
  assert.equal(mismatch?.kind, "error");
  assert.ok(mismatch?.message.startsWith("youtube_english: ") && mismatch.message.includes("저장하지 않았습니다"));
  assert.ok(youtubeOAuthResult("?youtube=error&reason=state")?.message.includes("만료"));
  assert.ok(youtubeOAuthResult("?youtube=error&reason=whatever")?.message.includes("저장한 것은 없습니다"));
  assert.equal(youtubeOAuthResult(""), null);
  assert.equal(youtubeOAuthResult("?view=news"), null);
});

test("이상한 채널 값은 표시하지 않는다", () => {
  const result = youtubeOAuthResult("?youtube=connected&channel=%3Cscript%3E");
  assert.equal(result?.channel, null);
  assert.ok(!result?.message.includes("<script>"));
});

test("YouTube 외 권한과 이전 연결 요청은 안전하게 다시 안내한다", () => {
  for (const reason of ["scope_unexpected", "scope_changed", "no_refresh_token"]) {
    const result = youtubeOAuthResult(`?youtube=error&reason=${reason}`);
    assert.equal(result?.kind, "error");
    assert.ok(result?.message.includes("Hermes"));
    assert.ok(!result?.message.includes("앱을 지운 뒤"));
  }
  assert.ok(youtubeOAuthResult("?youtube=error&reason=scope_unexpected")?.message.includes("저장하지 않았습니다"));
  assert.ok(youtubeOAuthResult("?youtube=error&reason=scope_changed")?.message.includes("다시 시작"));
});

test("결과 파라미터만 주소에서 지운다", () => {
  assert.equal(withoutOAuthParams("https://office.example.com/?youtube=connected&channel=youtube_main_ko"), "/");
  assert.equal(withoutOAuthParams("https://office.example.com/?youtube=error&reason=state&view=x#top"), "/?view=x#top");
  assert.equal(withoutOAuthParams("https://office.example.com/?youtube=error&reason=channel_mismatch&actual_channel=x&expected_channel=y&view=x"), "/?view=x");
});

test("채널 불일치는 유효한 두 공개 ID만 표시한다", () => {
  const actual = "UCc2CaOrPo-1dezowe7kklZA";
  const expected = "UCh9Oa74qc9mOvgmgMTXBFVw";
  const result = youtubeOAuthResult(`?youtube=error&reason=channel_mismatch&actual_channel=${actual}&expected_channel=${expected}`);
  assert.ok(result?.message.includes(actual) && result.message.includes(expected));
  assert.ok(result?.message.includes("토큰을 저장하지 않았습니다"));
  const invalid = youtubeOAuthResult(`?youtube=error&reason=channel_mismatch&actual_channel=%3Cscript%3E&expected_channel=${expected}`);
  assert.ok(!invalid?.message.includes("<script>"));
  const unrelated = youtubeOAuthResult(`?youtube=error&reason=state&actual_channel=${actual}&expected_channel=${expected}`);
  assert.ok(!unrelated?.message.includes(actual));
});

test("연결 버튼을 막는 이유는 설정 여부만 말한다", () => {
  assert.equal(connectBlockedReason(ready), null);
  assert.ok(connectBlockedReason({ ...ready, client_configured: false })?.includes("YOUTUBE_CLIENT_ID"));
  const both = connectBlockedReason({ ...ready, client_configured: false, public_origin_configured: false });
  assert.ok(both?.includes("YOUTUBE_CLIENT_SECRET") && both.includes("OFFICE_PUBLIC_ORIGIN"));
  assert.ok(connectBlockedReason({ ...ready, secrets_location_ok: false })?.includes("OFFICE_SECRETS_FILE"));
  assert.ok(connectBlockedReason(null));
});

test("연결 상태 문구", () => {
  const base = { key: "youtube_main_ko", label: "YouTube 메인", channel_id: "UCc2CaOrPo-1dezowe7kklZA", connected_at: null };
  assert.equal(connectionLabel(undefined), "연결 안 됨");
  assert.equal(connectionLabel({ ...base, source: null, connected: false, file_stored: false }), "연결 안 됨");
  assert.equal(connectionLabel({ ...base, source: "file", connected: true, file_stored: true }), "연결됨 · UCc2CaOr… (로그인 연결)");
  assert.equal(connectionLabel({ ...base, source: "env", connected: true, file_stored: false, channel_id: null }), "연결됨 (환경 파일 토큰)");
  assert.ok(connectionLabel({ ...base, source: "file", connected: false, file_stored: true }).includes("클라이언트 설정 필요"));
  assert.equal(shortChannelId("UCshort"), "UCshort");
  assert.equal(shortChannelId(null), "");
});

test("연결 시작·해제는 CSRF 토큰과 채널 키만 보낸다", async (t) => {
  const originalFetch = globalThis.fetch;
  const requests: { url: string; method?: string; csrf?: string; body: unknown }[] = [];
  t.after(() => { globalThis.fetch = originalFetch; });
  globalThis.fetch = async (input, init) => {
    if (String(input) === "/api/session") return Response.json({ csrf: "isolated-oauth-token" });
    const headers = (init?.headers ?? {}) as Record<string, string>;
    requests.push({ url: String(input), method: init?.method, csrf: headers["X-Office-CSRF"], body: init?.body ? JSON.parse(String(init.body)) : null });
    return Response.json(String(input).endsWith("/start") ? { authorize_url: "https://accounts.google.com/o/oauth2/v2/auth?state=x", expires_in: 600 } : { key: "youtube_main_ko" });
  };
  const started = await api.youtubeOAuthStart("youtube_main_ko");
  assert.ok(started.authorize_url.startsWith("https://accounts.google.com/"));
  await api.youtubeOAuthDisconnect("youtube_main_ko");
  await api.youtubeOAuthStatus();
  assert.deepEqual(requests, [
    { url: "/api/youtube/oauth/start", method: "POST", csrf: "isolated-oauth-token", body: { channel_key: "youtube_main_ko" } },
    { url: "/api/youtube/oauth/disconnect", method: "POST", csrf: "isolated-oauth-token", body: { channel_key: "youtube_main_ko" } },
    { url: "/api/youtube/oauth/status", method: "GET", csrf: undefined, body: null },
  ]);
});
test("PC 인증 모드는 서버에 키를 넣도록 안내하거나 연결 완료를 꾸미지 않는다", async () => {
  const {connectBlockedReason,connectionLabel}=await import("../lib/youtube-oauth.ts");
  assert.match(connectBlockedReason({auth_location:"owner_pc"} as never)!,/본인 PC/);
  assert.match(connectionLabel({source:"owner_pc",connected:true} as never),/본인 PC 인증 연결됨/);
  assert.match(connectionLabel({source:"owner_pc",connected:false} as never),/연결 필요/);
});
