import type { ClipEstimate, Delivery, Job, ProviderStatus } from "./types";

export type ProfileKind = "text" | "voice" | "image" | "clip";
export type ProfileOption = { id: string; label: string; paid: boolean; hint: string; disabled?: boolean; subscription?: boolean };

// Must match the server registries: text_selection.PROFILES, voice_selection.PROFILES, image_selection.PROFILES, video_selection.PROFILES.
export const PROFILE_OPTIONS: Record<ProfileKind, ProfileOption[]> = {
  text: [
    { id: "codex-subscription-text", label: "Codex 구독 · 글·검수", paid: false, subscription: true, hint: "ChatGPT 로그인 · 추가 API 과금 없음 · 구독 한도 사용. 원고·비평·평가·퀴즈·카드 문구까지 같은 경로로 실행합니다." },
    { id: "gpt-5.4-mini", label: "OpenAI gpt-5.4-mini", paid: true, hint: "원고·검수·퀴즈·카드 문구. 입력 $0.75 · 출력 $4.50 / 100만 토큰" },
    { id: "gpt-5.5", label: "OpenAI gpt-5.5 · 고비용", paid: true, hint: "입력 $5 · 출력 $30 / 100만 토큰. 원고 1편에 수천 원까지" },
    { id: "gemini-3.8-flash", label: "Gemini 3.8 Flash", paid: true, hint: "입력 $0.75 · 출력 $3.75 / 100만 토큰. 수요 폭주 시 503으로 멈출 수 있음" },
    { id: "gemini-3.5-flash-lite", label: "Gemini 3.5 Flash-Lite · 가벼움", paid: true, hint: "입력 $0.30 · 출력 $2.50 / 100만 토큰" },
  ],
  voice: [
    { id: "codex-voice-unsupported", label: "Codex 구독 음성", paid: false, disabled: true, hint: "구독 CLI의 음성 파일 자동 합성 경로는 지원하지 않습니다. 아래 로컬 음성 또는 별도 API를 선택하세요." },
    { id: "windows-heami", label: "Windows Heami · 로컬", paid: false, hint: "Windows PC에서만 생성됩니다. EC2(Linux)에서는 OpenAI 또는 Gemini 음성을 고르세요." },
    { id: "gemini-kore", label: "Gemini Flash TTS · Kore", paid: true, hint: "원고 승인① 뒤 승인 장면 대본만 합성 · 원고당 1,000원 상한 · 수요 폭주 시 503으로 멈출 수 있음" },
    { id: "openai-tts", label: "OpenAI gpt-4o-mini-tts · 한국어", paid: true, hint: "원고 승인① 뒤 승인 장면 대본만 합성 · 텍스트 $0.60 · 오디오 $12 / 100만 토큰 · 원고당 1,000원 상한" },
  ],
  image: [
    { id: "none", label: "생성 배경 없음 · 글자 카드", paid: false, hint: "지금처럼 로컬에서 글자 카드만 그립니다." },
    { id: "openai-gpt-image", label: "OpenAI gpt-image-2.5 배경", paid: true, hint: "장면마다 배경 한 장 · 장당 200원 예약 · 업무당 2,000원" },
    { id: "codex-subscription", subscription: true, label: "Codex 구독 배경 · ChatGPT 로그인", paid: false, hint: "장면·카드마다 한 장 · 추가 API 과금 없음 · 구독 한도 차감 · 앱 상한 하루 20장 · 실제 생성 지원·시간은 실행 계정에서 확인" },
  ],
  clip: [
    { id: "codex-video-unsupported", label: "Codex 구독 생성 영상", paid: false, disabled: true, hint: "구독의 영상 자동 생성 연결은 지원하지 않습니다. 정지 이미지 줌·자막 편집은 생성 영상 없이도 가능합니다." },
    { id: "none", label: "일반 영상 · 이미지 줌·자막 편집", paid: false, hint: "별도 생성 영상 API 없이 MP4를 만듭니다. 내레이션은 음성에서 선택한 방식과 비용을 따릅니다." },
    { id: "pexels-stock", label: "Pexels 무료 실사 영상", paid: false, hint: "무료 · 실제 촬영 영상 · PEXELS_API_KEY 필요 · 출처 표기" },
    { id: "runway-grok-lite", label: "Runway Grok Imagine 1.5 Lite · 추천", paid: true, hint: "가장 저렴 · 720p 초당 3크레딧+장면당 1 · 모든 장면을 장면 길이만큼 실사 영상으로(반복·끊김 없음)" },
    { id: "runway-gen4-turbo", label: "Runway Gen-4 Turbo", paid: true, hint: "5초 25크레딧(예약 500원) · 모든 장면, 5초 고정" },
    { id: "runway-gen4.5", label: "Runway Gen-4.5", paid: true, hint: "5초 60크레딧(예약 1,200원) · 모든 장면, 5초 고정" },
  ],
};

export const PROFILE_COST_GUIDANCE = [
  "프로필 선택만으로는 유료 API를 호출하지 않습니다. 실패해도 다른 제공자로 자동 전환하지 않습니다.",
  "원고 승인① 전에도 근거 요약·원고 생성·비평·평가·국어 검수의 글 모델 API 또는 구독 호출이 실행될 수 있습니다. 구독은 사용 한도를 소모하고 API는 비용이 발생합니다. 작업 시간과 예산 조건을 확인하세요.",
  "원고 승인① 후에는 선택 제작에서 사용하는 유료 음성·배경 이미지·생성 영상에 별도 비용이 발생할 수 있습니다. 승인 자체는 제작이나 유료 호출을 시작하지 않습니다.",
];

export function textProfileConnection(provider: ProviderStatus | undefined) {
  const p = provider ?? {};
  const model = p.text?.id ?? p.text?.model ?? p.model ?? "gemini-3.8-flash";
  const env = model === "codex-subscription-text" ? "Codex ChatGPT 로그인" : model.startsWith("gpt-") ? "OPENAI_API_KEY" : model.startsWith("gemini-") ? "GEMINI_API_KEY" : null;
  const openai = p.image?.openai_configured ?? (p.image?.id === "codex-subscription" ? undefined : p.image?.configured);
  const configured = model === "codex-subscription-text" ? p.text?.configured : env ? p.text?.configured ?? (env === "OPENAI_API_KEY" ? openai : p.configured) : undefined;
  return { model, env, configured };
}

export function settingsWarnings(provider: ProviderStatus | undefined): string[] {
  const p = provider ?? {};
  const warnings: string[] = [];
  const text = textProfileConnection(p);
  const geminiConfigured = text.env === "GEMINI_API_KEY" ? text.configured ?? p.configured : p.configured;
  if (text.model === "codex-subscription-text") {
    if (!p.text?.configured) warnings.push("Codex 구독 글을 실행할 앱 계정의 ChatGPT 로그인이 확인되지 않았습니다. 서버에서 codex login status를 확인하세요. 이 PC와 EC2 로그인은 별개입니다.");
  } else if (!text.env || text.configured === undefined)
    warnings.push(`선택 글 모델(${text.model})의 연결 여부를 확인하지 못했습니다. 설정 상태를 다시 조회하세요.`);
  else if (!text.configured)
    warnings.push(`선택 글 모델(${text.model})에 필요한 ${text.env} 연결이 없습니다. 글 모델을 사용하는 근거 요약·원고·비평·평가·국어 검수 요청을 시작할 수 없습니다.`);
  if (p.voice?.id === "gemini-kore" && !geminiConfigured)
    warnings.push("Gemini 음성을 골랐지만 GEMINI_API_KEY가 없어 영상 음성을 만들 수 없습니다.");
  if (p.voice?.id === "openai-tts" && p.voice.configured === false)
    warnings.push("OpenAI 음성을 골랐지만 OPENAI_API_KEY가 서버에 없어 영상 음성을 만들 수 없습니다.");
  if (p.image?.id === "codex-subscription" && !p.image.configured)
    warnings.push("Codex 구독 배경을 골랐지만 서버의 앱 계정에 codex 설치·로그인이 없습니다. 영상·카드 제작이 실패합니다.");
  else if (p.image?.id && p.image.id !== "none" && !p.image.configured)
    warnings.push("배경 이미지를 켰지만 OPENAI_API_KEY가 서버에 없습니다. 영상·카드 제작이 실패합니다.");
  if (p.clip?.id === "pexels-stock") {
    if (!p.clip.configured && !p.clip.pexels_configured)
      warnings.push("Pexels 실사 영상을 골랐지만 PEXELS_API_KEY가 서버에 없습니다. 장면은 정지 화면으로 만들어집니다.");
  } else if (p.clip?.id && p.clip.id !== "none") {
    if (!p.clip.configured)
      warnings.push("생성 영상을 켰지만 RUNWAYML_API_SECRET이 서버에 없습니다.");
    if (!p.image?.id || p.image.id === "none")
      warnings.push("생성 영상은 배경 이미지 프로필이 함께 켜져 있어야 합니다. 지금은 유료 영상 호출 전에 거부됩니다.");
  }
  warnings.push(...unavailableSelectionWarnings(p));
  return warnings;
}

const KIND_TITLES: Record<ProfileKind, string> = { text: "글 모델", voice: "음성", image: "배경 이미지", clip: "생성 영상" };

function selectedId(p: ProviderStatus, kind: ProfileKind): string | undefined {
  return kind === "text" ? p.text?.id ?? p.text?.model ?? p.model : p[kind]?.id;
}

// Keep registered choices discoverable when a key or platform connection is unavailable.
export function visibleProfileOptions(provider: ProviderStatus | undefined, kind: ProfileKind): ProfileOption[] {
  const states = provider?.availability?.[kind];
  return PROFILE_OPTIONS[kind].filter(option => option.id === "none" || (!option.disabled && !states?.[option.id]?.retired)).map(option => {
    const state = states?.[option.id];
    return option.id !== "none" && state?.available === false
      ? {...option, disabled:true, hint:`${option.hint} 현재 실행 불가: ${state.reason}`}
      : option;
  });
}

// One clear line when the saved selection can no longer run, naming it and the fix.
export function unavailableSelectionWarnings(provider: ProviderStatus | undefined): string[] {
  const p = provider ?? {};
  const lines: string[] = [];
  for (const kind of ["text", "voice", "image", "clip"] as ProfileKind[]) {
    const id = selectedId(p, kind);
    const state = id ? p.availability?.[kind]?.[id] : undefined;
    if (id && id !== "none" && state && !state.available) {
      const label = PROFILE_OPTIONS[kind].find((o) => o.id === id)?.label ?? id;
      lines.push(`${KIND_TITLES[kind]}: 저장된 선택 '${label}'은(는) 지금 이 서버에서 실행할 수 없습니다 — ${state.reason}. 아래 목록에서 실행 가능한 항목을 고르세요.`);
    }
  }
  return lines;
}

export const PROFILE_CHANGE_NOTE = "다음 제작부터 적용됩니다. 이미 만든 영상은 작업실의 '현재 설정으로 다시 제작'으로 다시 만들 수 있어요.";

export function dailyClipUsage(provider: ProviderStatus | undefined): string | null {
  const clip = provider?.clip;
  if (!clip?.paid) return null;
  const cap = clip.clip_limits?.daily_paid_clips ?? 15;
  const perVideo = clip.clip_limits?.max_clips_per_video ?? 12;
  return `오늘 유료 클립 ${clip.paid_clips_today ?? 0}/${cap}개 사용 · 영상당 최대 ${perVideo}개`;
}

// The produce button shows the paid items first and needs a second, in-page click to confirm.
export function paidProduceNotice(estimate: ClipEstimate | null | undefined): string | null {
  return estimate?.paid && estimate.clips > 0 ? estimate.label : null;
}

export function keyChips(provider: ProviderStatus | undefined): { label: string; env: string; ok: boolean }[] {
  const p = provider ?? {};
  const text = textProfileConnection(p);
  const chips = [
    { label: "Gemini", env: "GEMINI_API_KEY", ok: Boolean(text.env === "GEMINI_API_KEY" ? text.configured : p.configured) },
    { label: "OpenAI", env: "OPENAI_API_KEY", ok: Boolean(text.env === "OPENAI_API_KEY" ? text.configured : p.image?.openai_configured ?? (p.image?.id === "codex-subscription" ? false : p.image?.configured)) },
    { label: "Runway", env: "RUNWAYML_API_SECRET", ok: Boolean(p.clip?.runway_configured ?? (p.clip?.id === "pexels-stock" ? false : p.clip?.configured)) },
    { label: "Pexels", env: "PEXELS_API_KEY", ok: Boolean(p.clip?.pexels_configured) },
    { label: "YouTube", env: "Google 계정 연결", ok: Boolean(p.youtube?.configured) },
  ];
  if(p.text?.id === "codex-subscription-text" || p.image?.id === "codex-subscription") chips.push({label:"Codex 구독",env:"앱 계정의 ChatGPT 로그인",ok:Boolean(p.text?.id === "codex-subscription-text" ? p.text.configured : p.image?.configured)});
  return chips;
}

export function validWindowMinutes(value: string): number | null {
  const text = value.trim();
  if (!/^\d+$/.test(text)) return null;
  const minutes = Number(text);
  return minutes >= 1 && minutes <= 360 ? minutes : null;
}

export function uploadReadiness(job: Pick<Job, "selections" | "manifest" | "release_approval">, youtubeConfigured: boolean): { ok: boolean; reason: string } {
  if (!job.selections?.video) return { ok: false, reason: "영상 제작을 선택한 작업만 업로드할 수 있습니다." };
  const release = job.release_approval;
  if (!release || release.decision !== "approved" || release.version !== job.manifest?.hash || !(release.outputs ?? []).includes("video"))
    return { ok: false, reason: "영상에 대한 현재 출고 승인②가 필요합니다. 제작물을 검토하고 영상을 포함해 출고 승인하세요." };
  if (!youtubeConfigured)
    return { ok: false, reason: "YouTube 자격(YOUTUBE_CLIENT_ID·YOUTUBE_CLIENT_SECRET·채널 키별 YOUTUBE_<KEY>_REFRESH_TOKEN)이 이 채널에 설정되지 않았습니다." };
  return { ok: true, reason: "소유 채널에 비공개(private)로 올립니다. 공개 여부는 YouTube Studio에서 직접 정합니다." };
}

const DELIVERY_LABELS: Record<string, string> = {
  created: "준비",
  accepted: "전송 중",
  private: "비공개 업로드 완료",
  published: "공개됨",
  failed: "실패",
  unknown: "결과 불명 · 대사 필요",
  needs_review: "확인 필요",
};

export function deliveryStateLabel(state: string): string {
  return DELIVERY_LABELS[state] ?? state;
}

export function canReconcile(delivery: Pick<Delivery, "state" | "session_uri" | "external_id">): boolean {
  if ((delivery.state === "accepted" || delivery.state === "unknown") && delivery.session_uri) return true;
  return Boolean(delivery.external_id);
}

export function studioUrl(externalId: string | undefined | null): string | null {
  return externalId && /^[A-Za-z0-9_-]{5,64}$/.test(externalId) ? `https://studio.youtube.com/video/${externalId}/edit` : null;
}
