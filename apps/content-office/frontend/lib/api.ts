import type { ArchitectureOverview } from "./architecture";
import type { ContentHistory } from "./version-history";
import type { ClipEstimate } from "./types";
import type { YoutubeOAuthChannel, YoutubeOAuthStatus } from "./youtube-oauth";
import type { DailyCollectPatch, DailyCollectStatus } from "./daily-collect";
import type { PublicLeadFormInfo } from "./public-lead";
import type {
  Dashboard,
  Job,
  JobBudget,
  SourcePacket,
  Selections,
  KnowledgeSearch,
  OutputKind,
  Idea,
  Lesson,
  PackagingBrief,
  GateReport,
  IdeaInput,
  IdeaSourcesInput,
  SnapshotChannel,
  SnapshotPeriod,
  StudioCsvResult,
  ProfileSummaries,
  Delivery,
  WindowStart,
  BriefPresets,
  BriefOverrides,
  Channel,
  ChannelPatch,
  Quiz,
  Cards,
  TaskAccepted,
  Calendar,
  ReaderQuestion,
  QuestionGroup,
  QuestionSource,
  Lead,
  LeadInput,
  LeadSummary,
  NewsletterIssue,
  OfferInput,
  ChannelStagingSnapshot,
} from "./types";

export class OfficeApiError extends Error {
  status: number;
  constructor(message: string, status: number) {
    super(message);
    this.name = "OfficeApiError";
    this.status = status;
  }
}

let csrf: string | undefined;
async function request<T>(
  path: string,
  method = "GET",
  body?: unknown,
): Promise<T> {
  if (method !== "GET" && !csrf) {
    const session = await request<{ csrf: string }>("/session");
    if (!session.csrf)
      throw new Error(
        "로컬 세션을 확인할 수 없습니다. 화면을 새로고침해 주세요.",
      );
    csrf = session.csrf;
  }
  let response: Response;
  try {
    response = await fetch(`/api${path}`, {
      method,
      credentials: "same-origin",
      cache: "no-store",
      headers: {
        Accept: "application/json",
        ...(method !== "GET"
          ? { "Content-Type": "application/json", "X-Office-CSRF": csrf! }
          : {}),
      },
      ...(body !== undefined ? { body: JSON.stringify(body) } : {}),
      signal: AbortSignal.timeout(30_000),
    });
  } catch (cause) {
    const message = cause instanceof Error ? cause.message : "네트워크 오류";
    throw new Error(
      method === "GET"
        ? `오피스 연결을 확인하세요. ${message}`
        : "서버의 요청 결과를 확인하지 못했습니다. 요청이 저장됐을 수 있으니 운영 기록을 확인한 후 다음 작업을 결정하세요.",
    );
  }
  let result: unknown;
  try {
    result = await response.json();
  } catch {
    throw new Error(
      `서버 응답을 읽지 못했습니다 (${response.status}). API 실행 상태를 확인하세요.`,
    );
  }
  if (!response.ok) {
    if (response.status === 403) csrf = undefined;
    const detail =
      (result as { detail?: unknown; error?: unknown }).detail ??
      (result as { error?: unknown }).error;
    throw new OfficeApiError(
      typeof detail === "string"
        ? detail
        : detail
          ? JSON.stringify(detail)
          : `요청 실패 (${response.status})`,
      response.status,
    );
  }
  return result as T;
}

export const api = {
  discovery: () => request<import('./discovery').DiscoveryStatus>('/discovery'),
  saveDiscovery: (body: import('./discovery').ResearchConfig & { expected_hash: string }) => request<import('./discovery').DiscoveryStatus>('/discovery', 'PUT', body),
  versionHistory: (jobId: string) => request<ContentHistory>(`/jobs/${encodeURIComponent(jobId)}/history`),
  jobClipProfile: (jobId: string) => request<{source_hash:string|null;override_hash:string;effective:{id:string;paid:boolean};global_profile_id:string}>(`/jobs/${encodeURIComponent(jobId)}/clip-profile`),
  setJobClipProfile: (jobId: string, body: {source_hash:string;profile:"none"|"global";override_hash:string}) => request<Job>(`/jobs/${encodeURIComponent(jobId)}/clip-profile`,"PUT",body),
  improvementWorkspace: (jobId: string) => request<import("./improvements").ImprovementWorkspace>(`/jobs/${encodeURIComponent(jobId)}/improvements`),
  saveQualityReview: (jobId: string, body: Record<string, unknown>) => request(`/jobs/${encodeURIComponent(jobId)}/quality-reviews`, "POST", body),
  addExperience: (body: Record<string, unknown>) => request("/experiences", "POST", body),
  withdrawExperienceUse: (id: string, expectedHash: string) => request(`/experiences/${encodeURIComponent(id)}/withdraw-use`, "POST", {expected_hash:expectedHash}),
  saveLearningObservation: (jobId: string, body: Record<string, unknown>) => request(`/jobs/${encodeURIComponent(jobId)}/learning-observations`, "POST", body),
  learningToIdea: (jobId: string, observationId: string, sourceHash: string) => request(`/jobs/${encodeURIComponent(jobId)}/learning-observations/${encodeURIComponent(observationId)}/idea`, "POST", {source_hash:sourceHash}),
  saveChannelOutcome: (jobId: string, body: Record<string, unknown>) => request(`/jobs/${encodeURIComponent(jobId)}/channel-outcomes`, "POST", body),
  previewOwnedSource: (url:string) => request<{title:string;body:string;image_count:number}>("/owned-source/preview","POST",{url}),
  createOwnedSource: (input:{title:string;body:string;source_url:string;owner_confirmed:boolean}) => request<Job>("/owned-source/jobs","POST",input),
  setProfile: (kind: "text" | "voice" | "image" | "clip", profile: string) =>
    request<ProfileSummaries>("/settings/profiles", "POST", { kind, profile }),
  startWindow: (minutes: number) =>
    request<WindowStart>("/session/window", "POST", { minutes }),
  setAutoDeploy: (enabled: boolean) =>
    request<{ enabled: boolean }>("/dev/auto-deploy", "POST", { enabled }),
  deliveries: (id: string) =>
    request<{ deliveries: Delivery[]; youtube_configured: boolean }>(`/jobs/${encodeURIComponent(id)}/deliveries`),
  deliverYoutube: (id: string, channelKey = "youtube_main_ko") =>
    request<Delivery>(`/jobs/${encodeURIComponent(id)}/deliveries/youtube`, "POST", { channel_key: channelKey }),
  channelStaging: (id: string) =>
    request<ChannelStagingSnapshot>(`/jobs/${encodeURIComponent(id)}/staging`),
  recordChannelStaging: (id: string, expectedHash: string) =>
    request<ChannelStagingSnapshot>(`/jobs/${encodeURIComponent(id)}/staging`, "POST", { expected_hash: expectedHash }),
  briefs: () => request<BriefPresets>("/briefs"),
  architecture: () => request<ArchitectureOverview>("/architecture"),
  setJobBrief: (id: string, preset: string, overrides: BriefOverrides, expectedBriefHash: string) =>
    request<Job>(`/jobs/${encodeURIComponent(id)}/brief`, "PUT", { preset, overrides, expected_brief_hash: expectedBriefHash }),
  channels: () => request<{ channels: Channel[] }>("/channels"),
  updateChannel: (key: string, patch: ChannelPatch) =>
    request<Channel>(`/channels/${encodeURIComponent(key)}`, "PUT", patch),
  // 매일 아침 뉴스 자동 수집: 설정 저장만 하며 작업 시간을 열지 않습니다(실행은 서버 cron).
  dailyCollect: () => request<DailyCollectStatus>("/settings/daily-collect"),
  updateDailyCollect: (patch: Partial<DailyCollectPatch>) =>
    request<DailyCollectStatus>("/settings/daily-collect", "PUT", patch),
  // YouTube 채널 연결(OAuth): 시작하면 Google 동의 화면 주소만 받고, 토큰은 서버 비밀 파일에만 남습니다.
  youtubeOAuthStatus: () => request<YoutubeOAuthStatus>("/youtube/oauth/status"),
  youtubeOAuthStart: (channelKey: string) =>
    request<{ authorize_url: string; expires_in: number }>("/youtube/oauth/start", "POST", { channel_key: channelKey }),
  youtubeOAuthDisconnect: (channelKey: string) =>
    request<YoutubeOAuthChannel>("/youtube/oauth/disconnect", "POST", { channel_key: channelKey }),
  reconcileDelivery: (id: string, deliveryId: string) =>
    request<Delivery>(`/jobs/${encodeURIComponent(id)}/deliveries/${encodeURIComponent(deliveryId)}/reconcile`, "POST", {}),
  knowledge: (query = "") =>
    request<KnowledgeSearch>(`/knowledge?query=${encodeURIComponent(query)}`),
  registerEvidence: (id: string, sourceText: string, version: string | null, preserveOriginal = false) =>
    request<Job>(`/jobs/${encodeURIComponent(id)}/evidence`, "POST", {
      source_text: sourceText,
      version,
      preserve_original: preserveOriginal,
    }),
  retryTask: (id: string) =>
    request(`/tasks/${encodeURIComponent(id)}/retry`, "POST", {}),
  dashboard: () => request<Dashboard>("/dashboard?compact=true"),
  job: (id: string) => request<Job>(`/jobs/${encodeURIComponent(id)}`),
  jobBudget: (id: string) => request<JobBudget>(`/jobs/${encodeURIComponent(id)}/budget`),
  setJobBudget: (id: string, capKrw: number, expectedHash: string) =>
    request<JobBudget>(`/jobs/${encodeURIComponent(id)}/budget`, "PUT", { cap_krw: capKrw, expected_hash: expectedHash }),
  refresh: () => request("/refresh", "POST", {}),
  createJobs: (ids: string[]) =>
    request<{ jobs: Job[] }>("/jobs", "POST", { article_ids: ids }),
  draft: (id: string) =>
    request(`/jobs/${encodeURIComponent(id)}/draft`, "POST", {}),
  evaluate: (id: string) =>
    request(`/jobs/${encodeURIComponent(id)}/evaluate`, "POST", {}),
  saveSource: (id: string, packet: SourcePacket, version: string | null) =>
    request<Job>(`/jobs/${encodeURIComponent(id)}/source`, "PUT", {
      packet,
      version,
    }),
  reviewSource: (
    id: string,
    version: string,
    decision: "approved" | "rejected",
    selections: Selections,
    autoProduce = false,
  ) =>
    request<Job>(`/jobs/${encodeURIComponent(id)}/reviews/source`, "POST", {
      version,
      decision,
      selections,
      ...(autoProduce ? {auto_produce:true} : {}),
    }),
  produce: (id: string, confirmPaidClips = false) =>
    request(`/jobs/${encodeURIComponent(id)}/produce`, "POST", confirmPaidClips ? { confirm_paid_clips: true } : {}),
  productionEstimate: (id: string) =>
    request<{ clips: ClipEstimate }>(`/jobs/${encodeURIComponent(id)}/production-estimate`),
  reviewRelease: (
    id: string,
    version: string,
    decision: "approved" | "rejected",
    mediaReviewed = false,
    outputs?: OutputKind[],
    privateDeliveryChannel?: "youtube_main_ko" | "youtube_english",
  ) =>
    request<Job>(`/jobs/${encodeURIComponent(id)}/reviews/release`, "POST", {
      version,
      decision,
      media_reviewed: mediaReviewed,
      ...(outputs ? { outputs } : {}),
      ...(privateDeliveryChannel ? {private_delivery_channel:privateDeliveryChannel} : {}),
    }),
  selectThumbnail: (id: string, artifactId: string) =>
    request<Job>(`/jobs/${encodeURIComponent(id)}/thumbnail`, "POST", {
      artifact_id: artifactId,
    }),
  ideas: () => request<{ ideas: Idea[] }>("/ideas"),
  addIdea: (input: IdeaInput) => request<Idea>("/ideas", "POST", input),
  updateIdeaSources: (id: string, input: IdeaSourcesInput) =>
    request<Idea>(`/ideas/${encodeURIComponent(id)}/sources`, "PUT", input),
  uploadStudioCsv: (body: {
    channel: SnapshotChannel;
    period: SnapshotPeriod;
    csv: string;
    job_id?: string;
  }) => request<StudioCsvResult>("/analytics/studio-csv", "POST", body),
  selectIdea: (id: string, expectedHash: string) =>
    request<{ idea: Idea; job: Job }>(
      `/ideas/${encodeURIComponent(id)}/select`,
      "POST",
      { expected_hash: expectedHash },
    ),
  setPackaging: (jobId: string, brief: PackagingBrief) =>
    request(`/jobs/${encodeURIComponent(jobId)}/packaging`, "POST", brief),
  gates: (jobId: string) =>
    request<GateReport>(`/jobs/${encodeURIComponent(jobId)}/gates`),
  lessons: () => request<{ lessons: Lesson[] }>("/lessons"),
  reviewLesson: (id: string, decision: "approved" | "rejected") =>
    request<Lesson>(`/lessons/${encodeURIComponent(id)}/review`, "POST", {
      decision,
    }),
  // 퀴즈 · 카드뉴스: ① 원고 승인 뒤 요청(202 수락), 결과는 GET으로 확인
  requestQuiz: (id: string) =>
    request<TaskAccepted>(`/jobs/${encodeURIComponent(id)}/quiz`, "POST", {}),
  quiz: (id: string) =>
    request<{ quiz: Quiz | null }>(`/jobs/${encodeURIComponent(id)}/quiz`),
  requestCards: (id: string, images?: boolean) =>
    request<TaskAccepted>(`/jobs/${encodeURIComponent(id)}/cards`, "POST", images === undefined ? {} : { images }),
  cards: (id: string) =>
    request<{ cards: Cards | null }>(`/jobs/${encodeURIComponent(id)}/cards`),
  // 시험 일정 · 시의성
  calendar: (preset: string) =>
    request<Calendar>(`/calendar?preset=${encodeURIComponent(preset)}`),
  // 독자 질문
  questions: () =>
    request<{ questions: ReaderQuestion[]; groups: QuestionGroup[] }>("/questions"),
  addQuestion: (body: { source: QuestionSource; text: string; channel_key: string | null }) =>
    request<{ question: ReaderQuestion }>("/questions", "POST", body),
  questionToIdea: (id: string, body: { brief_preset: string | null; title: string | null }) =>
    request<{ idea: Idea }>(`/questions/${encodeURIComponent(id)}/idea`, "POST", body),
  // 리드마그넷 동의 장부 (이메일은 서버가 마스킹해 돌려줌)
  leads: () => request<{ leads: Lead[] }>("/leads"),
  leadSummary: () => request<LeadSummary>("/leads/summary"),
  addLead: (input: LeadInput) => request<{ lead: Lead }>("/leads", "POST", input),
  withdrawLead: (id: string) =>
    request<unknown>(`/leads/${encodeURIComponent(id)}/withdraw`, "POST", {}),
  markLeadSent: (id: string) =>
    request<unknown>(`/leads/${encodeURIComponent(id)}/sent`, "POST", {}),
  // 공개 신청 링크 재료(공개 주소·공개 자료·출처). 건수·이메일은 없음
  publicLeadForm: () => request<PublicLeadFormInfo>("/leads/public-form"),
  // 뉴스레터 ③: 승인은 발송이 아니며 발송은 오너 메일러에서 수동
  buildNewsletter: (jobId: string, body: { issue_key: string; subject: string }) =>
    request<NewsletterIssue>(`/jobs/${encodeURIComponent(jobId)}/newsletter`, "POST", body),
  newsletters: () => request<{ issues: NewsletterIssue[] }>("/newsletters"),
  newsletterExportUrl: (id: string) =>
    `/api/newsletters/${encodeURIComponent(id)}/export`,
  reviewNewsletter: (id: string, decision: "approve" | "reject", note: string, expectedHash: string) =>
    request<NewsletterIssue>(`/newsletters/${encodeURIComponent(id)}/review`, "POST", { decision, note, expected_hash: expectedHash }),
  rebuildNewsletter: (id: string) =>
    request<NewsletterIssue>(`/newsletters/${encodeURIComponent(id)}/rebuild`, "POST", {}),
  markNewsletterSent: (id: string, expectedHash: string) =>
    request<NewsletterIssue>(`/newsletters/${encodeURIComponent(id)}/sent`, "POST", { expected_hash: expectedHash }),
  // 오퍼 스냅샷
  setOffer: (jobId: string, offer: OfferInput) =>
    request<Job>(`/jobs/${encodeURIComponent(jobId)}/offer`, "PUT", offer),
  deleteOffer: (jobId: string, expectedHash: string | null) =>
    request<Job>(`/jobs/${encodeURIComponent(jobId)}/offer?expected_offer_hash=${encodeURIComponent(expectedHash ?? "null")}`, "DELETE"),
};
