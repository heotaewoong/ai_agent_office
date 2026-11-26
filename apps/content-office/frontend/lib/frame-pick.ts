// 내 영상에서 썸네일 장면 고르기(0원). 서버 office/frame_focus.py와 /thumbnail-studio/frame 경로에 맞춘다.

export type FrameProvenance = {
  kind?: string;
  provider?: string;
  model?: string;
  t?: number;
  requested_at?: number;
  sharpness?: number;
  crop_by?: "operator" | "opencv" | "given" | "center" | string;
  cost_krw?: number;
};

/** "75", "75.5", "1:15", "01:02:03" 를 초로 바꾼다. 형식이 틀리거나 10시간을 넘으면 null. */
export function parseAt(value: string): number | null {
  const text = value.trim();
  if (/^\d+(\.\d+)?$/.test(text)) {
    const seconds = Number(text);
    return seconds <= 36000 ? seconds : null;
  }
  const match = /^(?:(\d{1,2}):)?(\d{1,2}):(\d{2})(\.\d+)?$/.exec(text);
  if (!match) return null;
  const [, hours, minutes, seconds, fraction] = match;
  if (Number(seconds) >= 60 || (hours !== undefined && Number(minutes) >= 60)) return null;
  const total = Number(hours ?? 0) * 3600 + Number(minutes) * 60 + Number(seconds) + Number(fraction ?? 0);
  return total <= 36000 ? total : null;
}

/** 초를 "1:15"처럼 보여 준다. */
export function clock(seconds: number): string {
  const whole = Math.max(0, Math.round(seconds));
  const minutes = Math.floor(whole / 60);
  return `${minutes}:${String(whole % 60).padStart(2, "0")}`;
}

const CROP_LABELS: Record<string, string> = {
  operator: "내가 고른 위치",
  opencv: "얼굴을 찾아 오른쪽에 둠",
  given: "알려 준 얼굴 위치",
  center: "얼굴을 못 찾아 가운데를 지킴",
};

/** 후보 카드 밑줄: 어디서 왔고 얼마였는지. 내 영상 장면이 아니면 null. */
export function frameNote(provenance: FrameProvenance | undefined): string | null {
  if (!provenance || provenance.kind !== "owner_video_frame") return null;
  const parts = [`내 영상 ${clock(provenance.t ?? 0)}`];
  if (provenance.requested_at != null && Math.abs((provenance.t ?? 0) - provenance.requested_at) >= 0.5) parts.push(`요청 ${clock(provenance.requested_at)} 근처에서 더 선명한 장면`);
  parts.push(CROP_LABELS[provenance.crop_by ?? ""] ?? "자른 방법 기록 없음");
  parts.push("0원");
  return parts.join(" · ");
}
