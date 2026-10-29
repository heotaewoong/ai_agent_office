export type Article = {
  id: string;
  title: string;
  url: string;
  feed_name: string;
  published_at: string;
  summary?: string;
  score: number;
  score_reasons?: string[];
  selected?: boolean;
  editorial_title?: string;
  category?: string;
  evidence?: Evidence[];
  limitations?: string[];
  origin?: string;
};
export type Review = {
  role: string;
  score?: number;
  passed: boolean;
  critical_issues?: string[];
  minor_issues?: string[];
  summary?: string;
};
export type Evidence = {
  id?: string;
  claim?: string;
  statement?: string;
  statement_ko?: string;
  url?: string;
  evidence_url?: string;
  source_url?: string;
  scope?: string;
  limitation?: string;
  [key: string]: unknown;
};
export type SourcePacket = {
  title: string;
  body: string;
  packaging_hash?: string;
  evidence?: Evidence[];
  quality?: {
    status: string;
    critical: boolean;
    reviews?: Review[];
    refine_count?: number;
    note?: string;
    gates?: GateReport;
    deterministic_checks?: {
      passed?: boolean;
      issues?: string[];
      checks?: string[];
    };
  };
  video?: {
    title?: string;
    description?: string;
    tags?: string[];
    scenes?: {
      caption?: string;
      narration?: string;
      visual?: string;
      direction?: string;
      [key: string]: unknown;
    }[];
  };
  [key: string]: unknown;
};
export type EditorialDraft = {
  id: string;
  job_id: string;
  title: string;
  body: string;
  video?: SourcePacket["video"];
  status: string;
  note?: string;
  created_at?: string;
  evidence_ids_cited?: string[];
  evidence_ids_missing?: string[];
  source_files?: { name: string; sha256: string }[];
};
export type Artifact = {
  id: string;
  name: string;
  kind: string;
  url: string;
  size?: number;
  sha256?: string;
  outputs?: string[];
};
export type ThumbnailCandidate = (Artifact | { artifact: Artifact }) & {
  title?: string;
  subtitle?: string;
  angle?: string;
  layout?: string;
  scores?: Record<string, number>;
};
export type Selections = {
  blog: boolean;
  video: boolean;
  pdf: boolean;
  cards: boolean;
};
export type OutputKind = keyof Selections;
export type Task = {
  id?: string;
  kind?: string;
  state?: string;
  error?: string;
  created_at?: string;
  updated_at?: string;
  payload?: {
    job_id?: string;
    source_hash?: string | null;
    _source_hash_at_claim?: string | null;
    [key: string]: unknown;
  };
  [key: string]: unknown;
};
export type Event = {
  id?: string;
  kind?: string;
  event?: string;
  message?: string;
  state?: string;
  created_at?: string;
  at?: string;
  payload?: unknown;
  data?: unknown;
  [key: string]: unknown;
};
export type Job = {
  id: string;
  article: Article;
  title: string;
  state: string;
  error?: string | null;
  source_hash?: string;
  source_packet?: SourcePacket | null;
  packaging?: PackagingRecord | null;
  manifest?: {
    hash: string;
    files: Artifact[];
    thumbnail_candidates?: ThumbnailCandidate[];
    best_candidate_id?: string;
    selected_thumbnail_id?: string;
    completed_outputs?: OutputKind[];
    output_status?: Partial<
      Record<
        OutputKind,
        {
          state: string;
          files?: number;
          error?: string;
          successful_assets_preserved?: boolean;
        }
      >
    >;
  } | null;
  selections?: Selections;
  updated_at?: string;
  events?: Event[];
  tasks?: Task[];
  drafts?: EditorialDraft[];
  release_approval?: {
    outputs?: OutputKind[];
    version?: string;
    decision?: string;
  };
  brief?: Brief | null;
};
export type Feed = {
  id?: string;
  name?: string;
  url?: string;
  status?: string | number;
  count?: number;
  item_count?: number;
  error?: string | null;
  fetched_at?: string;
  retrieved_at?: string;
  checked_at?: string;
  state?: string;
  latest_published_at?: string;
  [key: string]: unknown;
};
export type Agent = {
  name?: string;
  role?: string;
  state?: string;
  status?: string;
  detail?: string;
  description?: string;
  mode?: string;
  [key: string]: unknown;
};
export type VoiceProfile = {id?:string;name?:string;paid?:boolean;automatic_fallback?:boolean;job_cap_krw?:number;note?:string};
export type ProviderProfile = {
  id?: string;
  name?: string;
  paid?: boolean;
  configured?: boolean;
  model?: string | null;
  job_cap_krw?: number;
  max_clips_per_job?: number;
  automatic_fallback?: boolean;
  key_source?: string | null;
  note?: string;
};
export type ProviderStatus = {
  model?: string;
  configured?: boolean;
  paid_fallback?: boolean;
  voice?: VoiceProfile;
  image?: ProviderProfile;
  clip?: ProviderProfile;
  youtube?: { configured?: boolean; visibility?: string; automatic_retry?: boolean; channels?: string[] };
};
export type ProfileSummaries = { voice: VoiceProfile; image: ProviderProfile; clip: ProviderProfile };
export type Delivery = {
  id: string;
  channel: string;
  channel_key?: string;
  locale?: string;
  job_id: string;
  state: string;
  visibility?: string;
  title?: string;
  external_id?: string;
  session_uri?: string;
  upload_status?: string;
  privacy_status?: string;
  processing_status?: string;
  reason?: string | null;
  created_at?: string;
  updated_at?: string;
  reconciled_at?: string;
};
export type WindowStart = { work_window: { authorized_end?: string }; services: { started: string[]; running: string[]; note: string } };
export type Dashboard = {
  articles: Article[];
  jobs: Job[];
  feeds: Feed[];
  budget: {
    cap_krw: number;
    spent_krw: number;
    reserved_krw: number;
    remaining_krw: number;
    fx_note?: string;
    pricing_as_of?: string;
  };
  agents: Agent[];
  window?: {
    start?: string;
    end?: string;
    started_at?: string;
    ends_at?: string;
    end_at?: string;
    authorized_end?: string;
    [key: string]: unknown;
  };
  worker?: { state?: string; heartbeat?: string; owner?: string };
  provider?: ProviderStatus;
  tasks?: Task[];
  [key: string]: unknown;
};

export type KnowledgeSummary = {
  documents?: number;
  unique_documents?: number;
  duplicate_documents?: number;
  sections?: number;
  manifest_sha256?: string;
};
export type KnowledgeResult = {
  path: string;
  sha256: string;
  section_id: string;
  section: string;
  heading_path?: string[];
  start_line: number;
  end_line: number;
  excerpt: string;
  duplicate_paths?: string[];
  contracts?: {
    contract_id: string;
    title: string;
    line: number;
    status: string;
    excerpt?: string;
  }[];
};
export type KnowledgeSearch = {
  summary: KnowledgeSummary;
  results: KnowledgeResult[];
};

export type Idea = {
  id: string;
  title: string;
  source_url?: string;
  state: "candidate" | "selected";
  score: number;
  outlier_band: string;
  reasons: string[];
  blocked: string[];
  brief?: Brief | null;
};
export type Lesson = {
  id: string;
  kind: string;
  hypothesis: string;
  state: "proposed" | "approved" | "rejected";
  weight_change?: { factor: string; delta: number } | null;
};
export type PackagingBrief = {
  titles: string[];
  thumbnails: { text: string; visual: string }[];
  hook: string;
  logline: string;
  reasons: string[];
  chosen_title?: string;
};
export type PackagingRecord = PackagingBrief & {
  packaging_hash: string;
  selected_by?: string;
};
export type GateReport = {
  status: "pass" | "warn" | "block";
  items: { level: "warn" | "block"; rule: string; message: string }[];
  disclosure: { youtube_altered_content: boolean; reasons: string[] };
};
export type IdeaInput = {
  title: string;
  source_url: string;
  views?: number | null;
  channel_avg_views?: number | null;
  demand: number;
  primary_sources: number;
  fit: number;
  covered_before: boolean;
  policy_flags: string[];
  brief_preset?: string;
  brief?: BriefOverrides;
};
export type BriefLanguage = "ko" | "en";
export type BriefAxis = "A" | "B";
export type BriefPreset = {
  id: string;
  axis: BriefAxis;
  label: string;
  topic: string;
  reader: string;
  prior_knowledge: string;
  problem: string;
  outcome: string;
  tone: string;
  language: BriefLanguage;
  cta: string;
};
export type BriefPresets = { default: string; presets: BriefPreset[] };
export type BriefOverrides = {
  reader?: string;
  problem?: string;
  outcome?: string;
  cta?: string;
  language?: BriefLanguage;
  topic?: string;
  prior_knowledge?: string;
  tone?: string;
};
export type Brief = {
  preset: string;
  axis: string;
  label: string;
  topic: string;
  reader: string;
  prior_knowledge: string;
  problem: string;
  outcome: string;
  tone: string;
  language: string;
  cta: string;
};
export type ChannelDelivery = "youtube_api" | "manual" | "notify";
export type Channel = {
  key: string;
  platform: string;
  label: string;
  locale: string;
  public_url: string;
  external_account_id: string;
  delivery: ChannelDelivery;
  publication_enabled: boolean;
  credentials_configured: boolean;
};
export type ChannelPatch = { external_account_id?: string; publication_enabled?: boolean; public_url?: string };
export type SnapshotChannel =
  | "youtube_long"
  | "shorts"
  | "blog_tistory"
  | "blog_naver"
  | "newsletter";
export type SnapshotPeriod = "24h" | "7d" | "28d";
export type StudioCsvResult = {
  snapshots: { id: string; external_id: string; period: string }[];
  lessons: Lesson[];
};

export type Action = (
  label: string,
  execute: () => Promise<unknown>,
  success: string,
) => Promise<void | boolean | string>;
