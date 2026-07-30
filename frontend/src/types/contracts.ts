// 与 backend/app/schemas/ 和 docs/interface-contracts.md 对齐。
// TODO(成员 2，契约成员 3/5)：后续补齐全部业务类型，并建立自动生成或漂移检查。

// ============================================================
// 现有基础类型 (保持不变)
// ============================================================

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

export type BackendHealthResponse = {
  reachable: boolean;
  status: "ok" | "unavailable";
  appEnv?: "development" | "test" | "production";
  traceId?: string;
};

export type UserRef = {
  id: string;
  display_name: string;
};

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

// ============================================================
// 新增：真实业务链路类型 (匹配后端 snake_case 最终修正版)
// ============================================================

// 视频下载地址响应
export interface DownloadUrlResponse {
  url: string;            // 预签名播放地址
  expires_at: string;     // 过期时间
}

// 真实转录读取
export interface TranscriptRead {
  segments: TranscriptSegment[];
  task_id: string;        // 新增：所属任务 ID
  source_language: string; // 新增：源语言
  segment_count: number;   // 新增：片段总数
  duration_ms: number;     // 新增：总时长（毫秒）
}

// 单个逐字稿片段
export interface TranscriptSegment {
  id: string;
  index: number;
  start_ms: number;
  end_ms: number;
  speaker: string | null;
  text: string;           // 修正：原为 original_text
  translation: string | null; // 修正：原为 translated_text
  is_edited: boolean;
  confidence: number | null; // 修正：保持 confidence 字段，后端允许 null
}

// 逐字稿更新请求
export interface TranscriptSegmentUpdate {
  speaker?: string | null;
  text?: string | null;          // 修正：原为 original_text
  translation?: string | null;   // 修正：原为 translated_text
}

// 逐字稿修订记录
export interface TranscriptSegmentRevision {
  id: string;
  segment_id: string;
  user_id: string;
  changed_at: string;
  old_speaker: string | null;
  old_text: string | null;           // 修正：原为 old_original_text
  old_translation: string | null;    // 修正：原为 old_translated_text
  new_speaker: string | null;
  new_text: string | null;           // 修正：原为 new_original_text
  new_translation: string | null;    // 修正：原为 new_translated_text
}

// 证据引用
export interface EvidenceReference {
  source_type: "video" | "transcript" | "frame" | "courseware"; // 修正：原为 type
  asset_id?: string;
  start_ms?: number;
  segment_id?: string;
  page_no?: number;
  image_ref?: string;
}

// 分析结论 (事实/判断/建议)
export interface AnalysisConclusion {
  id: string;
  task_id: string;
  type: "fact" | "judgment" | "suggestion";
  content: string;
  reviewed_content: string | null;
  review_status: "pending" | "accepted" | "modified" | "rejected";
  evidence_refs: EvidenceReference[];
  model_name: string;
  skill: string;
  prompt_version: string;
  trace_id: string;
  created_at: string;
  updated_at: string;
}

// 复核请求 (修正：状态字段改为 action)
export interface ReviewRequest {
  action: "accept" | "modify" | "reject"; // 修正：原为 status
  edited_content?: string | null;
  note?: string | null;
}

// 复核决定记录 (用于历史) (修正：状态字段改为 action)
export interface ReviewDecision {
  id: string;
  conclusion_id: string;
  user_id: string;
  action: "accept" | "modify" | "reject"; // 修正：原为 status
  edited_content: string | null;
  note: string | null;
  created_at: string;
}