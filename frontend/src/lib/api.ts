import type {
  AnalysisContract,
  AnalysisConclusion,
  ApiErrorBody,
  AssetKind,
  AssetRead,
  BackendHealthResponse,
  ClassroomRead,
  CourseRead,
  PresignResponse,
  ReportRead,
  ReviewAction,
  ReviewDecision,
  TaskRead,
  UserRef,
} from "@/types/contracts";

export class ApiClientError extends Error {
  readonly status: number;
  readonly code: string;
  readonly traceId?: string;

  constructor(status: number, error: Partial<ApiErrorBody>) {
    super(error.message ?? "请求失败，请稍后重试。");
    this.name = "ApiClientError";
    this.status = status;
    this.code = error.code ?? "INTERNAL_ERROR";
    this.traceId = error.trace_id;
  }
}

async function requestJson<T>(
  input: RequestInfo | URL,
  init?: RequestInit,
): Promise<T> {
  const response = await fetch(input, {
    ...init,
    cache: "no-store",
    headers: {
      Accept: "application/json",
      ...(init?.body ? { "Content-Type": "application/json" } : {}),
      ...init?.headers,
    },
  });
  const payload = (await response.json().catch(() => null)) as
    | T
    | { error?: Partial<ApiErrorBody> }
    | null;
  if (!response.ok) {
    const error =
      payload && typeof payload === "object" && "error" in payload
        ? payload.error
        : undefined;
    throw new ApiClientError(response.status, error ?? {});
  }
  return payload as T;
}

export async function getBackendHealth(
  signal?: AbortSignal,
): Promise<BackendHealthResponse> {
  const response = await fetch("/api/backend-health", {
    cache: "no-store",
    signal,
  });

  if (!response.ok) {
    throw new Error("后端健康检查代理返回异常状态。");
  }

  return (await response.json()) as BackendHealthResponse;
}

export async function startDemoSession(): Promise<{ user: UserRef }> {
  return requestJson("/api/session/demo", { method: "POST" });
}

export async function createCourse(name: string): Promise<CourseRead> {
  return requestJson("/api/courses", {
    method: "POST",
    body: JSON.stringify({ name }),
  });
}

export async function createClassroom(
  courseId: string,
  input: {
    title: string;
    description?: string;
    analysisContract?: Record<string, unknown>;
  },
): Promise<ClassroomRead> {
  return requestJson(`/api/courses/${encodeURIComponent(courseId)}/classrooms`, {
    method: "POST",
    body: JSON.stringify({
      title: input.title,
      description: input.description || null,
      analysis_contract: input.analysisContract ?? {},
    }),
  });
}

export async function presignUpload(
  classroomId: string,
  input: {
    kind: AssetKind;
    filename: string;
    contentType: string;
    sizeBytes: number;
  },
): Promise<PresignResponse> {
  return requestJson(
    `/api/classrooms/${encodeURIComponent(classroomId)}/uploads/presign`,
    {
      method: "POST",
      body: JSON.stringify({
        kind: input.kind,
        filename: input.filename,
        content_type: input.contentType,
        size_bytes: input.sizeBytes,
      }),
    },
  );
}

export async function completeUpload(
  assetId: string,
  etag?: string | null,
): Promise<AssetRead> {
  return requestJson(`/api/assets/${encodeURIComponent(assetId)}/complete`, {
    method: "POST",
    body: JSON.stringify({ etag: etag || null, checksum: null }),
  });
}

export function putPresignedUpload(
  upload: PresignResponse,
  file: File,
  onProgress: (percent: number) => void,
): Promise<string | null> {
  return new Promise((resolve, reject) => {
    const request = new XMLHttpRequest();
    request.open(upload.method, upload.upload_url);
    for (const [name, value] of Object.entries(upload.headers)) {
      request.setRequestHeader(name, value);
    }
    request.upload.addEventListener("progress", (event) => {
      if (event.lengthComputable && event.total > 0) {
        onProgress(Math.round((event.loaded / event.total) * 100));
      }
    });
    request.addEventListener("load", () => {
      if (request.status >= 200 && request.status < 300) {
        onProgress(100);
        resolve(request.getResponseHeader("ETag"));
        return;
      }
      reject(
        new Error(
          `对象存储上传失败（HTTP ${request.status || "未知"}），请检查 B2 CORS 与预签名配置。`,
        ),
      );
    });
    request.addEventListener("error", () =>
      reject(new Error("无法连接对象存储，请检查网络与 B2 CORS 配置。")),
    );
    request.addEventListener("abort", () =>
      reject(new Error("上传已取消。")),
    );
    request.send(file);
  });
}

export async function deleteAsset(assetId: string): Promise<void> {
  const response = await fetch(`/api/assets/${encodeURIComponent(assetId)}`, {
    method: "DELETE",
    cache: "no-store",
  });
  if (response.ok) return;
  const payload = (await response.json().catch(() => null)) as {
    error?: Partial<ApiErrorBody>;
  } | null;
  throw new ApiClientError(response.status, payload?.error ?? {});
}

export async function createTask(
  classroomId: string,
  assetIds: string[],
  analysisContract: AnalysisContract,
): Promise<TaskRead> {
  return requestJson(`/api/classrooms/${encodeURIComponent(classroomId)}/tasks`, {
    method: "POST",
    body: JSON.stringify({
      asset_ids: assetIds,
      privacy_mode: "local",
      analysis_contract: analysisContract,
    }),
  });
}

export async function getTask(taskId: string): Promise<TaskRead> {
  return requestJson(`/api/tasks/${encodeURIComponent(taskId)}`);
}

export async function getConclusions(
  classroomId: string,
): Promise<AnalysisConclusion[]> {
  return requestJson(
    `/api/classrooms/${encodeURIComponent(classroomId)}/conclusions`,
  );
}

export async function reviewConclusion(
  conclusionId: string,
  input: {
    action: ReviewAction;
    editedContent?: string | null;
    note?: string | null;
  },
): Promise<AnalysisConclusion> {
  return requestJson(
    `/api/conclusions/${encodeURIComponent(conclusionId)}/review`,
    {
      method: "POST",
      body: JSON.stringify({
        action: input.action,
        edited_content: input.editedContent ?? null,
        note: input.note ?? null,
      }),
    },
  );
}

export async function getReviewHistory(
  conclusionId: string,
): Promise<ReviewDecision[]> {
  return requestJson(
    `/api/conclusions/${encodeURIComponent(conclusionId)}/history`,
  );
}

export async function getReport(classroomId: string): Promise<ReportRead> {
  return requestJson(`/api/classrooms/${encodeURIComponent(classroomId)}/report`);
}

export async function updateReport(
  classroomId: string,
  input: { title?: string; content?: string },
): Promise<ReportRead> {
  return requestJson(`/api/classrooms/${encodeURIComponent(classroomId)}/report`, {
    method: "PUT",
    body: JSON.stringify(input),
  });
}
