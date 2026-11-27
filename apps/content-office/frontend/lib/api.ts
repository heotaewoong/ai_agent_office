import type { ArchitectureOverview } from "./architecture";
import type {LibraryAction, LibraryInventory, LibraryQuote, LibraryResult} from './artifact-library';
import type {ThumbnailState} from "../app/thumbnail-studio";
import type { ContentHistory } from "./version-history";
import type { ClipEstimate } from "./types";
import type { YoutubeOAuthChannel, YoutubeOAuthStatus } from "./youtube-oauth";
import type { DailyCollectPatch, DailyCollectStatus } from "./daily-collect";
import type {
  ResearchChoice, ResearchKind, ResearchPlan, ResearchRequest, ResearchResult, ResearchTopic, SourceEntry, SourceHit, SourceItem, SourceItemDetail, SourceLane, SourceLibrary, SourceLinkResult, SourcePatch,
  TrustedSource,
} from "./source-library";
import type { PublicLeadFormInfo } from "./public-lead";
import type {
  Dashboard,
  Job,
  JobBudget,
  SourcePacket,
  Selections,
  KnowledgeSearch,
  ContentDiagnostics,
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
  MemoryStory,
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
  NewsletterEditorial,
  NewsletterInputs,
  NewsletterConnection,
  NewsletterPrepared,
  OfferInput,
  ChannelStagingSnapshot,
} from "./types";

export class OfficeApiError extends Error {
  status: number;
  code?: string;
  constructor(message: string, status: number, code?: unknown) {
    super(message);
    this.name = "OfficeApiError";
    this.status = status;
    if (typeof code === 'string' && /^[a-z][a-z0-9_]{0,79}$/.test(code)) this.code = code;
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
      (result as { code?: unknown }).code,
    );
  }
  return result as T;
}

export const api = {
  artifactLibrary: () => request<LibraryInventory>('/library'),
  artifactLibraryQuote: (ids: string[], action: LibraryAction) => request<LibraryQuote>('/library/quote', 'POST', {ids, action}),
  artifactLibraryChange: (ids: string[], action: LibraryAction, quote: string, request_id: string) => request<LibraryResult>('/library/change', 'POST', {ids, action, quote, request_id}),
  trashJobs: () => request<{jobs: Pick<Job,'id'|'title'|'updated_at'>[]}>('/trash/jobs'),
  trashJob: (id:string,updatedAt:string) => request<Job>(`/jobs/${encodeURIComponent(id)}/trash`,'POST',{expected_updated_at:updatedAt}),
  restoreJob: (id:string,updatedAt:string) => request<Job>(`/jobs/${encodeURIComponent(id)}/restore`,'POST',{expected_updated_at:updatedAt}),
  assistantReports: () => request<unknown>("/assistant/reports"),
  createAssistantRequest: (body: import('./assistant-requests').AssistantSubmission) => request<unknown>('/assistant/requests', 'POST', body),
  assistantRequest: (id: string) => request<unknown>(`/assistant/requests/${encodeURIComponent(id)}`),
  saveAssistantContentJob: async (id: string, body: import('./assistant-requests').AssistantContentSubmission) =>
    (await request<{content: unknown}>(`/assistant/requests/${encodeURIComponent(id)}/content-job`, 'POST', body)).content,
  thumbnailStudio:(id:string)=>request<ThumbnailState>(`/jobs/${encodeURIComponent(id)}/thumbnail-studio`),
  generateThumbnails:(id:string,body:{source_hash:string;revision:string;confirm_paid:boolean;edit_id?:string;instruction?:string})=>request(`/jobs/${encodeURIComponent(id)}/thumbnail-studio/generate`,"POST",body),
  chooseStudioThumbnail:(id:string,candidate_id:string,revision:string,finalize:boolean,format:"landscape"|"shorts"="landscape")=>request<ThumbnailState>(`/jobs/${encodeURIComponent(id)}/thumbnail-studio/choose`,"POST",{candidate_id,revision,finalize,format}),
  // 내 영상의 한 장면을 썸네일 후보로(0원): 요청 시각 앞뒤에서 가장 선명한 장면, 얼굴을 오른쪽에
  thumbnailFrame:(id:string,body:{source_hash:string;revision:string;video_id:string;at:number;x?:number})=>request<ThumbnailState>(`/jobs/${encodeURIComponent(id)}/thumbnail-studio/frame`,"POST",body),
  setVideoPlatforms: (id: string, platforms: ("youtube_shorts" | "instagram_reels")[], version: string) => request<Job>(`/jobs/${encodeURIComponent(id)}/video-platforms`, "PUT", {platforms, version}),
  prepareExternalMedia: (jobId: string, body: {version:string;draft_id:string}) => request<Job>(`/jobs/${encodeURIComponent(jobId)}/external-media/prepare`, "POST", body),
  adoptExternalMedia: (jobId: string, body: {version:string;reviewed:boolean}) => request<Job>(`/jobs/${encodeURIComponent(jobId)}/external-media/adopt`, "POST", body),
  platformNews: () => request<import('./platform-news').PlatformNews>('/platform-news'),
  savePlatformNewsIdea: (input: { platform: string; url: string; expected_hash: string }) =>
    request<{ idea: Idea }>('/platform-news/ideas', 'POST', input),
  discovery: () => request<import('./discovery').DiscoveryStatus>('/discovery'),
  trendSignals: () => request<import('./trend-signals').TrendStatus>('/trend-signals'),
  saveTrendSignals: (body: import('./trend-signals').TrendSettings) => request<import('./trend-signals').TrendStatus>('/trend-signals', 'PUT', body),
  refreshTrendSignals: () => request<{ id: string; kind: string; state: string }>('/trend-signals/refresh', 'POST'),
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
  createOwnedSource: (input:{title:string;body:string;source_url:string;owner_confirmed:boolean;brief_preset?:string;experience_first?:true}) => request<Job>("/owned-source/jobs","POST",input),
  setProfile: (kind: "text" | "voice" | "image" | "clip", profile: string) =>
    request<ProfileSummaries>("/settings/profiles", "POST", { kind, profile }),
  startWindow: (minutes: number) =>
    request<WindowStart>("/session/window", "POST", { minutes }),
  setAutoDeploy: (enabled: boolean) =>
    request<{ enabled: boolean }>("/dev/auto-deploy", "POST", { enabled }),
  refreshStocks: () =>
    request<{ started: boolean; message: string }>("/stocks/refresh", "POST"),
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
  sourceLibrary: () => request<SourceLibrary>("/source-library"),
  searchSourceLibrary: (q: string, area = "", evidenceOnly = false) =>
    request<{ query: string; results: SourceHit[] }>(`/source-library/search?${new URLSearchParams({ q, ...(area ? { area } : {}), ...(evidenceOnly ? { evidence_only: "true" } : {}) })}`),
  sourceItem: (id: string) => request<SourceItemDetail>(`/source-library/items/${encodeURIComponent(id)}`),
  addSourceLinks: (urls: string[], entry: SourceEntry, title?: string) =>
    request<SourceLibrary & { results: SourceLinkResult[] }>("/source-library/links", "POST", { urls, ...(title ? { title } : {}), ...entry }),
  addSourceMemo: (title: string, text: string, entry: SourceEntry) =>
    request<SourceLibrary & { item: SourceItem }>("/source-library/memos", "POST", { title, text, ...entry }),
  addSourceFile: (name: string, content_base64: string, entry: SourceEntry) =>
    request<SourceLibrary & { item: SourceItem }>("/source-library/files", "POST", { name, content_base64, ...entry }),
  updateSourceItem: (id: string, patch: SourcePatch) =>
    request<SourceLibrary & { item: SourceItem }>(`/source-library/items/${encodeURIComponent(id)}`, "PATCH", patch),
  retrySourceItem: (id: string) => request<SourceLibrary & { item: SourceItem }>(`/source-library/items/${encodeURIComponent(id)}/retry`, "POST"),
  deleteSourceItem: (id: string) => request<SourceLibrary & { deleted: string }>(`/source-library/items/${encodeURIComponent(id)}`, "DELETE"),
  fillSourceText: (id: string, text: string, title?: string) =>
    request<SourceLibrary & { item: SourceItem }>(`/source-library/items/${encodeURIComponent(id)}/text`, "POST", { text, ...(title ? { title } : {}) }),
  setSourceEvidence: (ids: string[], value: boolean) =>
    request<SourceLibrary & { changed: number; skipped: number }>("/source-library/evidence", "POST", { ids, use_as_evidence: value }),
  // 외부 조사: 무료 공개 출처에서 후보만 찾는다. 고른 후보는 addSourceLinks로 창고에 넣는다.
  runResearch: (body: ResearchRequest) => request<ResearchResult>("/source-library/research", "POST", body),
  tavilyUsage: () => request<import("./source-library").TavilyUsage>("/source-library/research/tavily"),
  runTavily: (body: { id?: string; title: string; query?: string }) =>
    request<import("./source-library").TavilyResult>("/source-library/research/tavily", "POST", body),
  // 조사 기준만 다시 계산한다. 밖으로 나가는 요청은 없다.
  researchPlans: (topics: ResearchTopic[]) =>
    request<{ plans: (ResearchPlan & { id: string | null })[] }>("/source-library/research/plans", "POST", { topics }),
  // 사람이 고른 글 유형과 분야를 기획마다 저장한다. 기획 카드와 승인은 바꾸지 않는다.
  saveResearchChoice: (ideaId: string, choice: { kind: ResearchKind; area: string }) =>
    request<{ choice: ResearchChoice }>(`/source-library/research/choices/${encodeURIComponent(ideaId)}`, "PUT", choice),
  // 자료 창고 판정이 맞았는지 사람이 승인⓪에서 매긴 답(맞음, 틀림, 연습). 기획 카드와 승인은 바꾸지 않는다.
  researchLabel: (ideaId: string) =>
    request<import("./source-library").VerdictLabelState>(`/source-library/research/labels/${encodeURIComponent(ideaId)}`),
  saveResearchLabel: (ideaId: string, label: import("./source-library").VerdictLabel) =>
    request<import("./source-library").VerdictLabelState>(`/source-library/research/labels/${encodeURIComponent(ideaId)}`, "PUT", { label }),
  trustedSources: () => request<{ sources: TrustedSource[] }>("/source-library/trusted"),
  addTrustedSource: (body: { url: string; area: string; lane: SourceLane; name?: string }) =>
    request<{ source: TrustedSource; sources: TrustedSource[] }>("/source-library/trusted", "POST", body),
  deleteTrustedSource: (id: string) =>
    request<{ deleted: string; sources: TrustedSource[] }>(`/source-library/trusted/${encodeURIComponent(id)}`, "DELETE"),
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
  contentDiagnostics: (jobId:string) => request<ContentDiagnostics>(`/jobs/${encodeURIComponent(jobId)}/content-diagnostics`),
  registerEvidence: (id: string, sourceText: string, version: string | null, preserveOriginal = false) =>
    request<Job>(`/jobs/${encodeURIComponent(id)}/evidence`, "POST", {
      source_text: sourceText,
      version,
      preserve_original: preserveOriginal,
    }),
  retryTask: (id: string) =>
    request(`/tasks/${encodeURIComponent(id)}/retry`, "POST", {}),
  dashboard: () => request<Dashboard>("/dashboard?compact=true&task_results=false"),
  job: (id: string) => request<Job>(`/jobs/${encodeURIComponent(id)}`),
  jobBudget: (id: string) => request<JobBudget>(`/jobs/${encodeURIComponent(id)}/budget`),
  setJobBudget: (id: string, capKrw: number, expectedHash: string) =>
    request<JobBudget>(`/jobs/${encodeURIComponent(id)}/budget`, "PUT", { cap_krw: capKrw, expected_hash: expectedHash }),
  refresh: () => request("/refresh", "POST", {}),
  createJobs: (ids: string[], startDraft = false) =>
    request<{ jobs: Job[]; draft_requests?: { job_id:string; state:string; reason?:string }[] }>("/jobs", "POST", { article_ids: ids, ...(startDraft ? {start_draft:true} : {}) }),
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
    confirmPaid = false,
    draftTargets?: string[],
    reasons?: string[],
    note?: string,
  ) =>
    request<Job>(`/jobs/${encodeURIComponent(id)}/reviews/source`, "POST", {
      version,
      decision,
      selections,
      ...(autoProduce ? {auto_produce:true} : {}),
      ...(autoProduce && confirmPaid ? {confirm_paid_clips:true,confirm_paid_thumbnails:true} : {}),
      ...(draftTargets !== undefined ? {draft_targets:draftTargets} : {}),
      ...(reasons && reasons.length ? {reasons} : {}),
      ...(note ? {note} : {}),
    }),
  requestReleasedDraft: (id:string, version:string, channelKey:string, target:Pick<Channel,"key"|"platform"|"locale"|"public_url"|"external_account_id"|"publication_enabled">) => request<{items:{id:string;channel_key:string;state:string;reason?:string}[]}>(`/jobs/${encodeURIComponent(id)}/owner-drafts/request`, "POST", {version,channel_key:channelKey,target}),
  ownerDrafts: (id:string) => request<{items:{id:string;channel_key:string;state:string;reason?:string}[];host?:{online:boolean;last_seen:string|null}}>(`/jobs/${encodeURIComponent(id)}/owner-drafts`),
  produce: (id: string, confirmPaidClips = false, stage?: "video") =>
    request(`/jobs/${encodeURIComponent(id)}/produce`, "POST", {...(confirmPaidClips ? { confirm_paid_clips: true, confirm_paid_thumbnails:true } : {}), ...(stage ? {stage} : {})}),
  productionEstimate: (id: string, video?: boolean, stage?: "video") =>
    request<{ clips: ClipEstimate; thumbnail_artwork?:boolean }>(`/jobs/${encodeURIComponent(id)}/production-estimate${stage ? `?stage=${stage}` : video == null ? '' : `?video=${video}`}`),
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
  benchmarks: () => request<import('./benchmarks').BenchmarkOverview>('/benchmarks'),
  saveBenchmarks: (input: import('./benchmarks').BenchmarkRegistryInput) => request<import('./benchmarks').BenchmarkOverview>('/benchmarks', 'PUT', input),
  refreshBenchmarks: (input: { expected_hash: string }) => request<import('./benchmarks').BenchmarkRefreshResult>('/benchmarks/refresh', 'POST', input),
  saveBenchmarkIdea: (input: import('./benchmarks').BenchmarkIdeaInput) => request<import('./benchmarks').BenchmarkIdea>('/benchmarks/ideas', 'POST', input),
  benchmarkResearchPacket: (input: import('./benchmarks').BenchmarkResearchInput) => request<import('./benchmarks').BenchmarkResearchPacket>('/benchmarks/research-packet', 'POST', input),
  startBenchmarkResearch: (input: import('./benchmark-research').BenchmarkResearchInputRun) => request<unknown>('/benchmarks/research-runs', 'POST', input),
  benchmarkResearch: (id: string) => request<unknown>(`/benchmarks/research-runs/${encodeURIComponent(id)}`),
  benchmarkResearchIdea: (id: string, input: import('./benchmark-research').BenchmarkResearchIdea) => request<import('./benchmarks').BenchmarkIdea>(`/benchmarks/research-runs/${encodeURIComponent(id)}/ideas`, 'POST', input),
  addIdea: (input: IdeaInput) => request<Idea>("/ideas", "POST", input),
  updateIdeaSources: (id: string, input: IdeaSourcesInput) =>
    request<Idea>(`/ideas/${encodeURIComponent(id)}/sources`, "PUT", input),
  searchIdeaPublicEvidence: (id: string, expectedHash: string) =>
    request<Idea>(`/ideas/${encodeURIComponent(id)}/public-evidence`, "POST", { expected_hash: expectedHash }),
  searchIdeaBookEvidence: (id: string, expectedHash: string) =>
    request<Idea>(`/ideas/${encodeURIComponent(id)}/book-evidence`, "POST", { expected_hash: expectedHash }),
  approveIdeaPublicEvidence: (id: string, expectedHash: string, evidenceIds: readonly string[], bookEvidenceIds: readonly string[] = []) =>
    request<{ idea: Idea; job: Job }>(
      `/ideas/${encodeURIComponent(id)}/public-evidence/approve`, "POST",
      { expected_hash: expectedHash, public_evidence_ids: evidenceIds, ...(bookEvidenceIds.length ? { book_evidence_ids: bookEvidenceIds } : {}) },
    ),
  uploadStudioCsv: (body: {
    channel: SnapshotChannel;
    period: SnapshotPeriod;
    csv: string;
    job_id?: string;
  }) => request<StudioCsvResult>("/analytics/studio-csv", "POST", body),
  selectIdea: (id: string, expectedHash: string, publicEvidenceIds: readonly string[] = [], bookEvidenceIds: readonly string[] = []) =>
    request<{ idea: Idea; job: Job }>(
      `/ideas/${encodeURIComponent(id)}/select`,
      "POST",
      { expected_hash: expectedHash, ...(publicEvidenceIds.length ? { public_evidence_ids: publicEvidenceIds } : {}),
        ...(bookEvidenceIds.length ? { book_evidence_ids: bookEvidenceIds } : {}) },
    ),
  // 제목 3안과 훅 제안(모델 1회). 저장하지 않고, 고른 것만 setPackaging으로 저장해요.
  suggestPackaging: (jobId: string) => request<{ suggestion: { titles: string[]; hooks: string[]; hook: string; thumbnails: { text: string; visual: string }[]; logline: string; reasons: string[] }; issues: string[][]; version: string }>(`/jobs/${encodeURIComponent(jobId)}/packaging/suggest`, "POST", {}),
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
  // 그림 기억 이야기: 글은 모델, 그림은 코드(0원). 운영자가 누를 때만 줄 세운다.
  requestStory: (id: string) =>
    request<TaskAccepted>(`/jobs/${encodeURIComponent(id)}/story`, "POST", {}),
  story: (id: string) =>
    request<{ story: MemoryStory | null }>(`/jobs/${encodeURIComponent(id)}/story`),
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
  buildNewsletter: (jobId: string, body: { issue_key: string; subject: string; editorial?: NewsletterEditorial }) =>
    request<NewsletterIssue>(`/jobs/${encodeURIComponent(jobId)}/newsletter`, "POST", body),
  newsletters: () => request<{ issues: NewsletterIssue[] }>("/newsletters"),
  newsletterInputs: () => request<NewsletterInputs>("/newsletter-inputs"),
  newsletterConnections: () => request<{ mode: string; destinations: NewsletterConnection[] }>("/newsletter-connections"),
  newsletterPrepared: (id: string) => request<{ prepared: NewsletterPrepared | null }>(`/newsletters/${encodeURIComponent(id)}/prepared`),
  prepareNewsletter: (id: string, expectedHash: string) => request<NewsletterPrepared>(`/newsletters/${encodeURIComponent(id)}/prepare`, "POST", { expected_hash: expectedHash }),
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
