import type {
  Artifact,
  ThumbnailCandidate,
  Task,
  Job,
  OutputKind,
} from "./types";

export function completedOutputs(
  job: Pick<Job, "state" | "selections" | "manifest">,
): OutputKind[] {
  const selected = (["blog", "video", "pdf", "cards"] as OutputKind[]).filter(
    (key) => job.selections?.[key],
  );
  const manifest = job.manifest;
  if (!manifest) return [];
  if (manifest.completed_outputs)
    return selected.filter(
      (key) =>
        manifest.completed_outputs?.includes(key) &&
        (!manifest.output_status?.[key] ||
          manifest.output_status[key]?.state === "completed"),
    );
  if (manifest.output_status)
    return selected.filter(
      (key) => manifest.output_status?.[key]?.state === "completed",
    );
  return ["release_review", "release_approved"].includes(job.state) &&
    manifest.files.length
    ? selected
    : [];
}
export function validReleaseOutputs(
  job: Pick<Job, "state" | "selections" | "manifest">,
  outputs: OutputKind[],
): boolean {
  return (
    outputs.length > 0 &&
    outputs.every((key) => completedOutputs(job).includes(key))
  );
}

export function evidenceInputAllowed(job: {
  state: string;
  article?: { evidence?: unknown[] };
  source_packet?: { evidence?: unknown[] } | null;
}): boolean {
  return (
    ["research_ready", "failed"].includes(job.state) ||
    !(job.source_packet?.evidence ?? job.article?.evidence ?? []).length
  );
}
export function retryBlockedReason(
  task: Task,
  job?: Pick<Job, "id" | "state" | "source_hash">,
  tasks: Task[] = [],
): string | null {
  if (
    !task.id ||
    !["draft", "evaluate", "produce", "refresh"].includes(task.kind || "") ||
    !["failed", "unknown", "partial"].includes(task.state || "")
  )
    return "등록된 실패·미완료 작업만 다시 요청할 수 있습니다.";
  const payload = task.payload ?? {};
  if (payload.job_id) {
    if (!job || job.id !== payload.job_id)
      return "현재 작업을 다시 조회하세요.";
    const recorded = Object.hasOwn(payload, "source_hash")
      ? payload.source_hash
      : payload._source_hash_at_claim;
    if (recorded === undefined || recorded !== (job.source_hash ?? null))
      return "이전 원고 버전의 실패입니다. 현재 원고의 다음 행동을 선택하세요.";
    if (job.state === "needs_reconciliation")
      return "결과와 원가 대사를 마친 뒤 다시 요청할 수 있습니다.";
  } else if (task.kind !== "refresh")
    return "작업의 버전 정보를 확인할 수 없습니다.";
  const expectedVersion = Object.hasOwn(payload, "source_hash")
    ? payload.source_hash
    : payload._source_hash_at_claim;
  if (
    tasks.some(
      (candidate) =>
        (!payload.job_id ||
          (Object.hasOwn(candidate.payload ?? {}, "source_hash")
            ? candidate.payload?.source_hash
            : candidate.payload?._source_hash_at_claim) === expectedVersion) &&
        candidate.id !== task.id &&
        candidate.kind === task.kind &&
        ["queued", "running"].includes(candidate.state || "") &&
        (candidate.payload?.job_id ?? null) === (payload.job_id ?? null),
    )
  )
    return "같은 작업이 이미 대기 또는 실행 중입니다.";
  return null;
}

export function acceptJobRefresh<T extends { id: string }>(
  current: T | null,
  incoming: T,
): T | null {
  return current?.id === incoming.id ? incoming : current;
}

export function thumbnailArtifact(candidate: ThumbnailCandidate): Artifact {
  return "artifact" in candidate ? candidate.artifact : candidate;
}

export function toggleArticle(selected: string[], id: string): string[] {
  if (selected.includes(id)) return selected.filter((item) => item !== id);
  return selected.length < 3 ? [...selected, id] : selected;
}

export function canApproveSource(job: unknown, dirty = false): boolean {
  const value = job as {
    source_hash?: string;
    state?: string;
    source_packet?: {
      body?: string;
      quality?: { status?: string; critical?: boolean };
    };
  } | null;
  return Boolean(
    !dirty &&
      value?.state === "source_review" &&
      value.source_hash &&
      value.source_packet?.body?.trim() &&
      value.source_packet.quality?.status === "passed" &&
      value.source_packet.quality.critical === false,
  );
}

export function safeArtifactUrl(url: string): string | null {
  if (!/^\/api\/artifacts\/[a-zA-Z0-9._-]+(?:\/[a-zA-Z0-9._-]+)*$/.test(url))
    return null;
  if (url.split("/").some((part) => part === "." || part === "..")) return null;
  return url;
}

export function remainingWindow(
  end: string | undefined,
  now = Date.now(),
): string {
  if (!end || !Number.isFinite(Date.parse(end))) return "마감 미설정";
  const minutes = Math.ceil((Date.parse(end) - now) / 60_000);
  if (minutes <= 0) return "작업 시간 종료";
  return `${Math.floor(minutes / 60)}시간 ${minutes % 60}분`;
}

export const states: Record<
  string,
  { label: string; tone: string; next: string }
> = {
  research_ready: {
    label: "근거 준비",
    tone: "neutral",
    next: "원고를 생성해 검수하세요",
  },
  drafting: {
    label: "원고·검수 중",
    tone: "orange",
    next: "생성과 독립 검수 결과를 기다리고 있어요",
  },
  source_review: {
    label: "원고 검토 대기",
    tone: "orange",
    next: "원고와 근거를 읽고 승인하거나 거절하세요",
  },
  source_approved: {
    label: "원고 승인",
    tone: "green",
    next: "선택한 채널의 제작을 시작할 수 있어요",
  },
  source_rejected: {
    label: "원고 거절",
    tone: "red",
    next: "원고를 수정하고 다시 검수하세요",
  },
  production_queued: {
    label: "제작 대기",
    tone: "orange",
    next: "작업자가 제작 요청을 가져올 예정이에요",
  },
  producing: {
    label: "제작 중",
    tone: "orange",
    next: "파일과 영상이 완성되면 출고 검토로 이동해요",
  },
  release_review: {
    label: "출고 검토 대기",
    tone: "orange",
    next: "파일을 미리 보고 현재 버전을 출고 승인하세요",
  },
  partial_release_review: {
    label: "일부 제작 완료",
    tone: "orange",
    next: "완료된 출력부터 출고하고 미완료 부분은 따로 다시 요청할 수 있어요",
  },
  release_approved: {
    label: "출고 승인",
    tone: "green",
    next: "파일을 내려받아 각 채널에 직접 게시하세요",
  },
  blocked: {
    label: "확인 필요",
    tone: "red",
    next: "검수·제공자·예산 조건을 확인하세요",
  },
  needs_reconciliation: {
    label: "호출 결과 확인 필요",
    tone: "red",
    next: "결과가 불명확한 외부 호출을 먼저 확인하세요",
  },
  failed: {
    label: "실패",
    tone: "red",
    next: "실패 원인과 마지막 성공 결과를 확인하세요",
  },
};

export function statusInfo(state: string) {
  return (
    states[state] ?? {
      label: state || "상태 미확인",
      tone: "neutral",
      next: "운영 기록에서 현재 상태를 확인하세요",
    }
  );
}

export function formatDate(date?: string, time = false): string {
  if (!date || !Number.isFinite(Date.parse(date))) return "날짜 미확인";
  return new Intl.DateTimeFormat("ko-KR", {
    timeZone: "Asia/Seoul",
    month: "long",
    day: "numeric",
    ...(time ? { hour: "2-digit", minute: "2-digit", hour12: false } : {}),
  }).format(new Date(date));
}

export function formatMoney(value?: number) {
  return new Intl.NumberFormat("ko-KR").format(value ?? 0);
}
export function formatBytes(size?: number) {
  return size == null
    ? "크기 미확인"
    : size > 1048576
      ? `${(size / 1048576).toFixed(1)} MB`
      : `${Math.ceil(size / 1024)} KB`;
}

export function approvalIsCurrent(
  expected?: string,
  current?: string,
): boolean {
  return Boolean(expected && expected === current);
}

/** ① 원고 승인이 끝난 상태. 퀴즈·카드뉴스·뉴스레터처럼 승인 원고에서 파생하는 산출물의 조건. */
export function sourceApproved(state: string | undefined): boolean {
  return [
    "source_approved",
    "production_queued",
    "producing",
    "release_review",
    "partial_release_review",
    "release_approved",
  ].includes(state ?? "");
}

export type DraftStatus = {
  state: "idle" | "queued" | "running" | "completed" | "failed" | "unknown";
  label: string;
  detail: string;
};

/** The latest draft task of this job, in words the operator can read next to the button. */
export function draftStatus(tasks: Task[] | undefined, job: Pick<Job, "id">): DraftStatus {
  const mine = (tasks ?? [])
    .filter((t) => t.kind === "draft" && (t.payload?.job_id ?? null) === job.id)
    .sort((a, b) => (b.created_at ?? "").localeCompare(a.created_at ?? ""));
  const latest = mine[0];
  if (!latest) return { state: "idle", label: "아직 요청 전", detail: "" };
  const error = latest.result?.error ?? latest.error ?? "";
  switch (latest.state) {
    case "queued":
      return { state: "queued", label: "대기 중", detail: "작업자가 곧 가져갑니다. 작업 시간이 열려 있어야 해요." };
    case "running":
      return { state: "running", label: "진행 중 · 모델 호출", detail: "원고·비평·평가가 끝나면 아래에 원고가 나타나요." };
    case "completed":
      return { state: "completed", label: "완료", detail: "" };
    case "unknown":
      return { state: "unknown", label: "결과 불명 · 대사 필요", detail: error };
    case "failed":
      return { state: "failed", label: "실패", detail: error };
    default:
      return { state: "idle", label: latest.state ?? "상태 없음", detail: error };
  }
}
