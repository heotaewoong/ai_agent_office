/** YouTube 채널 연결(OAuth) 화면 도우미. 서버는 설정 여부만 알려 주며 토큰·비밀값은 화면에 오지 않습니다. */

export type YoutubeOAuthChannel = {
  key: string;
  label: string;
  /** env: 실행 환경 파일 토큰 사용 · file: 'YouTube 연결'로 저장한 토큰 · null: 없음 */
  source: "env" | "file" | "owner_pc" | null;
  connected: boolean;
  file_stored: boolean;
  channel_id: string | null;
  connected_at: string | null;
};

export type YoutubeOAuthStatus = {
  auth_location?: "owner_pc" | "server";
  client_configured: boolean;
  public_origin_configured: boolean;
  redirect_uri: string | null;
  secrets_location_ok: boolean;
  channels: YoutubeOAuthChannel[];
};

export type YoutubeOAuthResult = { kind: "success" | "error"; message: string; channel: string | null };

const RESULT_PARAMS = ["youtube", "reason", "channel", "actual_channel", "expected_channel"];

const REASONS: Record<string, string> = {
  state: "연결 요청이 만료됐거나 이미 사용됐습니다. 설정 화면에서 'YouTube 연결'을 다시 누르세요.",
  session: "연결을 시작한 브라우저와 돌아온 브라우저가 다릅니다. 같은 브라우저에서 다시 시도하세요.",
  denied: "Google 동의 화면에서 취소했습니다. 저장한 것은 없습니다.",
  google_error: "Google이 오류를 돌려줬습니다. 저장한 것은 없습니다. 잠시 뒤 다시 시도하세요.",
  config: "서버의 YouTube 연결 설정(클라이언트 ID·비밀값·공개 주소·토큰 파일 위치)이 바뀌었습니다. 설정을 확인하세요.",
  token_exchange: "Google 토큰 교환에 실패했습니다. 리디렉션 URI와 클라이언트 설정을 확인하세요. 저장한 것은 없습니다.",
  scope_missing: "업로드·채널 조회 권한 중 일부를 허용하지 않았습니다. 다시 연결하며 두 권한을 모두 체크하세요.",
  scope_unexpected: "YouTube 외 권한이 포함돼 연결을 저장하지 않았습니다. 기존 Hermes 권한을 삭제하지 말고 오피스 전용 Google 프로젝트 설정을 확인하세요.",
  scope_changed: "YouTube 전용 연결 방식으로 바뀌었습니다. 설정 화면에서 'YouTube 연결'을 다시 시작하세요. 기존 Hermes 연결은 유지됩니다.",
  no_refresh_token: "Google이 장기 토큰을 주지 않았습니다. 기존 Hermes 권한을 삭제하지 말고 클라이언트 설정을 확인하세요. 필요하면 오피스 전용 Google 프로젝트를 사용하세요.",
  channel_lookup: "로그인한 계정의 YouTube 채널을 조회하지 못했습니다. YouTube Data API v3가 켜져 있는지 확인하세요.",
  no_channel: "로그인한 계정에 YouTube 채널이 없습니다. 채널을 가진 계정(브랜드 계정)을 고르세요.",
  channel_ambiguous: "로그인한 계정에서 채널이 여러 개 조회됐습니다. Google 계정 선택 화면에서 채널(브랜드 계정)을 하나만 고르세요.",
  channel_mismatch: "로그인한 계정의 채널이 이 키에 등록된 채널 ID와 다릅니다. 저장하지 않았습니다. 올바른 채널로 다시 로그인하세요.",
  channel_in_use: "이 채널은 이미 다른 YouTube 키에 등록돼 있습니다. 저장하지 않았습니다.",
  save_failed: "토큰 파일을 쓰지 못했습니다. 서버의 OFFICE_SECRETS_FILE 위치와 권한을 확인하세요.",
};

function safeKey(value: string | null): string | null {
  return value && /^[a-z0-9_]{1,64}$/.test(value) ? value : null;
}

/** 콜백이 붙인 ?youtube=connected|error&reason=…&channel=… 를 화면 문구로 바꿉니다. 없으면 null. */
export function youtubeOAuthResult(search: string): YoutubeOAuthResult | null {
  const params = new URLSearchParams(search);
  const outcome = params.get("youtube");
  const channel = safeKey(params.get("channel"));
  if (outcome === "connected") {
    return {
      kind: "success",
      channel,
      message: `${channel ?? "YouTube"} 채널을 연결했습니다. 연결은 발행이 아니며, 업로드는 출고 승인② 뒤 운영자가 요청할 때 비공개로만 올라갑니다.`,
    };
  }
  if (outcome === "error") {
    const reason = params.get("reason") ?? "";
    let detail = REASONS[reason] ?? "YouTube 연결에 실패했습니다. 저장한 것은 없습니다.";
    const actual = params.get("actual_channel") ?? "";
    const expected = params.get("expected_channel") ?? "";
    if (reason === "channel_mismatch" && /^UC[\w-]{22}$/.test(actual) && /^UC[\w-]{22}$/.test(expected)) {
      detail = `Google이 돌려준 채널: ${actual} / 오피스 등록 채널: ${expected}. 서로 달라 토큰을 저장하지 않았습니다. Google의 YouTube 채널 선택 단계에서 등록된 채널을 선택하세요. 선택이 맞았다면 이 두 ID로 확인할 수 있습니다.`;
    }
    return { kind: "error", channel, message: channel ? `${channel}: ${detail}` : detail };
  }
  return null;
}

/** 결과 표시 뒤 주소창에서 연결 결과 파라미터만 지운 경로(+남은 쿼리·해시). */
export function withoutOAuthParams(href: string): string {
  const url = new URL(href);
  for (const name of RESULT_PARAMS) url.searchParams.delete(name);
  const query = url.searchParams.toString();
  return `${url.pathname}${query ? `?${query}` : ""}${url.hash}`;
}

/** 연결 버튼을 막는 이유. 막을 이유가 없으면 null. 값은 받지 않고 설정 여부만 봅니다. */
export function connectBlockedReason(status: YoutubeOAuthStatus | null): string | null {
  if (!status) return "연결 상태를 불러오지 못했습니다.";
  if (status.auth_location === "owner_pc") return "소셜 로그인 정보는 본인 PC에만 저장합니다. PC 인증 실행기에서 연결하세요.";
  const missing: string[] = [];
  if (!status.client_configured) missing.push("YOUTUBE_CLIENT_ID·YOUTUBE_CLIENT_SECRET");
  if (!status.public_origin_configured) missing.push("OFFICE_PUBLIC_ORIGIN(https 공개 주소)");
  if (missing.length) return `서버 실행 환경 파일에 ${missing.join(", ")}이(가) 없어 연결할 수 없습니다.`;
  if (!status.secrets_location_ok) return "OFFICE_SECRETS_FILE이 상태 폴더나 저장소 안을 가리킵니다. 밖으로 옮기세요.";
  return null;
}

export function shortChannelId(id: string | null | undefined): string {
  if (!id) return "";
  return id.length > 10 ? `${id.slice(0, 8)}…` : id;
}

/** 채널 행에 붙일 연결 상태 문구. */
export function connectionLabel(entry: YoutubeOAuthChannel | undefined): string {
  if (!entry || !entry.source) return "연결 안 됨";
  if (entry.source === "owner_pc") return entry.connected ? "본인 PC 인증 연결됨" : "본인 PC 인증 실행기 연결 필요";
  const id = shortChannelId(entry.channel_id);
  const where = entry.source === "env" ? "환경 파일 토큰" : "로그인 연결";
  if (!entry.connected) return `${where} 있음 · 클라이언트 설정 필요`;
  return `연결됨${id ? ` · ${id}` : ""} (${where})`;
}
