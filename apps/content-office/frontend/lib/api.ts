import type {
  Dashboard,
  Job,
  SourcePacket,
  Selections,
  KnowledgeSearch,
  OutputKind,
  Idea,
  Lesson,
  PackagingBrief,
  GateReport,
  IdeaInput,
  SnapshotChannel,
  SnapshotPeriod,
  StudioCsvResult,
  ProfileSummaries,
  Delivery,
  WindowStart,
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
  setProfile: (kind: "voice" | "image" | "clip", profile: string) =>
    request<ProfileSummaries>("/settings/profiles", "POST", { kind, profile }),
  startWindow: (minutes: number) =>
    request<WindowStart>("/session/window", "POST", { minutes }),
  deliveries: (id: string) =>
    request<{ deliveries: Delivery[]; youtube_configured: boolean }>(`/jobs/${encodeURIComponent(id)}/deliveries`),
  deliverYoutube: (id: string) =>
    request<Delivery>(`/jobs/${encodeURIComponent(id)}/deliveries/youtube`, "POST", {}),
  reconcileDelivery: (id: string, deliveryId: string) =>
    request<Delivery>(`/jobs/${encodeURIComponent(id)}/deliveries/${encodeURIComponent(deliveryId)}/reconcile`, "POST", {}),
  knowledge: (query = "") =>
    request<KnowledgeSearch>(`/knowledge?query=${encodeURIComponent(query)}`),
  registerEvidence: (id: string, sourceText: string, version: string | null) =>
    request<Job>(`/jobs/${encodeURIComponent(id)}/evidence`, "POST", {
      source_text: sourceText,
      version,
    }),
  retryTask: (id: string) =>
    request(`/tasks/${encodeURIComponent(id)}/retry`, "POST", {}),
  dashboard: () => request<Dashboard>("/dashboard"),
  job: (id: string) => request<Job>(`/jobs/${encodeURIComponent(id)}`),
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
  ) =>
    request<Job>(`/jobs/${encodeURIComponent(id)}/reviews/source`, "POST", {
      version,
      decision,
      selections,
    }),
  produce: (id: string) =>
    request(`/jobs/${encodeURIComponent(id)}/produce`, "POST", {}),
  reviewRelease: (
    id: string,
    version: string,
    decision: "approved" | "rejected",
    mediaReviewed = false,
    outputs?: OutputKind[],
  ) =>
    request<Job>(`/jobs/${encodeURIComponent(id)}/reviews/release`, "POST", {
      version,
      decision,
      media_reviewed: mediaReviewed,
      ...(outputs ? { outputs } : {}),
    }),
  selectThumbnail: (id: string, artifactId: string) =>
    request<Job>(`/jobs/${encodeURIComponent(id)}/thumbnail`, "POST", {
      artifact_id: artifactId,
    }),
  ideas: () => request<{ ideas: Idea[] }>("/ideas"),
  addIdea: (input: IdeaInput) => request<Idea>("/ideas", "POST", input),
  uploadStudioCsv: (body: {
    channel: SnapshotChannel;
    period: SnapshotPeriod;
    csv: string;
    job_id?: string;
  }) => request<StudioCsvResult>("/analytics/studio-csv", "POST", body),
  selectIdea: (id: string) =>
    request<{ idea: Idea; job: Job }>(
      `/ideas/${encodeURIComponent(id)}/select`,
      "POST",
      {},
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
};
