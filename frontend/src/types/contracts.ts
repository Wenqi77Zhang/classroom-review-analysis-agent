// 与 backend/app/schemas/ 和 docs/interface-contracts.md 对齐。
export type AssetKind = "video" | "courseware" | "transcript";
export type ReviewStatus = "pending" | "accepted" | "modified" | "rejected";
export type ConclusionType = "fact" | "judgment" | "suggestion";
export type UploadStatus = "pending" | "uploaded" | "failed";
export type TaskStatus =
  | "pending"
  | "queued"
  | "running"
  | "succeeded"
  | "failed"
  | "cancelled";
export type TaskStage =
  | "uploaded"
  | "extract_audio"
  | "segment"
  | "transcribe"
  | "translate"
  | "parse_courseware"
  | "build_evidence_index"
  | "analyze";

export type AnalysisContract = {
  goal: string;
  scope: "full_lesson" | "time_range";
  start_ms?: number | null;
  end_ms?: number | null;
  focus_areas: string[];
  judgment_criteria: string[];
  evidence_requirements: string[];
  bilingual_required: boolean;
  privacy_mode: "local" | "cloud";
  course_domain: "general" | "computer_ai" | "humanities";
  confirmed: boolean;
};

export type BackendHealthResponse = {
  reachable: boolean;
  status: "ok" | "unavailable";
  appEnv?: "development" | "test" | "production";
  traceId?: string;
};

export type UserRef = { id: string; display_name: string };
export type CourseRead = {
  id: string;
  name: string;
  description?: string | null;
  created_at: string;
  updated_at?: string | null;
};
export type ClassroomRead = {
  id: string;
  course_id: string;
  title: string;
  description?: string | null;
  analysis_contract: Record<string, unknown>;
  created_at: string;
  updated_at?: string | null;
};
export type PresignResponse = {
  asset_id: string;
  object_key: string;
  upload_url: string;
  method: "PUT";
  headers: Record<string, string>;
  expires_at: string;
};
export type DownloadUrlResponse = { url: string; expires_at: string };
export type AssetRead = {
  id: string;
  classroom_id: string;
  kind: AssetKind;
  filename: string;
  content_type: string;
  size_bytes: number;
  upload_status: UploadStatus;
  object_key: string;
  created_at: string;
};
export type TaskRead = {
  id: string;
  classroom_id: string;
  status: TaskStatus;
  stage: TaskStage;
  progress: number;
  privacy_mode: "local" | "cloud";
  retry_count: number;
  last_error_code?: string | null;
  last_error_message?: string | null;
  trace_id?: string | null;
  created_at: string;
  updated_at?: string | null;
  finished_at?: string | null;
};
export type ApiErrorBody = {
  code: string;
  message: string;
  details: Record<string, unknown>;
  trace_id: string;
};

export type TranscriptSegment = {
  id: string;
  task_id: string;
  index: number;
  start_ms: number;
  end_ms: number;
  speaker: string | null;
  text: string;
  source_language: string;
  translation: string | null;
  translation_language: string | null;
  is_edited: boolean;
  edited_at: string | null;
};
export type TranscriptRead = {
  task_id: string;
  source_language: string;
  has_translation: boolean;
  segment_count: number;
  duration_ms: number;
  segments: TranscriptSegment[];
};
export type TranscriptSegmentUpdate = {
  text?: string | null;
  speaker?: string | null;
  translation?: string | null;
};

export type EvidenceSourceType =
  | "video"
  | "transcript"
  | "courseware"
  | "frame";
export type EvidenceReference = {
  id?: string | null;
  source_type: EvidenceSourceType;
  asset_id?: string | null;
  segment_id?: string | null;
  start_ms?: number | null;
  end_ms?: number | null;
  page_no?: number | null;
  image_ref?: string | null;
  quote?: string | null;
};
export type AnalysisConclusion = {
  id: string;
  classroom_id: string;
  task_id: string;
  type: ConclusionType;
  content: string;
  evidence_refs: EvidenceReference[];
  review_status: ReviewStatus;
  reviewed_content?: string | null;
  created_at: string;
  trace_id: string;
  model_name?: string | null;
  skill?: string | null;
  prompt_version?: string | null;
};
export type ReviewAction = "accept" | "modify" | "reject";
export type ReviewDecision = {
  id: string;
  conclusion_id: string;
  action: ReviewAction;
  resulting_status: ReviewStatus;
  previous_content?: string | null;
  edited_content?: string | null;
  note?: string | null;
  decided_by: UserRef;
  created_at: string;
};
export type ReportRead = {
  id: string;
  classroom_id: string;
  title: string;
  content: string;
  included_conclusion_ids: string[];
  updated_at?: string | null;
};
