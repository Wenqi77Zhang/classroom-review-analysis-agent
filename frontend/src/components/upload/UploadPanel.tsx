"use client";

import {
  useEffect,
  useRef,
  useState,
  type ChangeEvent,
  type DragEvent,
} from "react";

import {
  ApiClientError,
  completeUpload,
  createTask,
  deleteAsset,
  getBackendHealth,
  presignUpload,
  putPresignedUpload,
} from "@/lib/api";
import type {
  AnalysisContract,
  AssetKind,
  PresignResponse,
  TaskRead,
} from "@/types/contracts";

type BackendHealthState = "checking" | "reachable" | "degraded" | "unreachable";
type UploadPhase =
  | "pending"
  | "presigning"
  | "uploading"
  | "verifying"
  | "uploaded"
  | "failed";

type SelectedAsset = {
  id: string;
  file: File;
  kind: AssetKind;
  phase: UploadPhase;
  progress: number;
  assetId?: string;
  error?: string;
};

type UploadPanelProps = {
  classroomId: string;
  analysisContract: AnalysisContract;
  onVideoReadinessChange?: (hasVideo: boolean) => void;
  onTaskCreated?: (task: TaskRead) => void;
};

const ACCEPTED_EXTENSIONS: Record<AssetKind, string[]> = {
  video: [".mp4", ".mov", ".webm", ".mkv"],
  courseware: [".pdf", ".ppt", ".pptx"],
  transcript: [".txt", ".docx", ".srt", ".vtt"],
};

const CONTENT_TYPES: Record<string, string> = {
  ".mp4": "video/mp4",
  ".mov": "video/quicktime",
  ".webm": "video/webm",
  ".mkv": "video/x-matroska",
  ".pdf": "application/pdf",
  ".ppt": "application/vnd.ms-powerpoint",
  ".pptx":
    "application/vnd.openxmlformats-officedocument.presentationml.presentation",
  ".txt": "text/plain",
  ".docx":
    "application/vnd.openxmlformats-officedocument.wordprocessingml.document",
  ".srt": "application/x-subrip",
  ".vtt": "text/vtt",
};

const MAX_BYTES: Record<AssetKind, number> = {
  video: 4 * 1024 * 1024 * 1024,
  courseware: 128 * 1024 * 1024,
  transcript: 32 * 1024 * 1024,
};

const KIND_COPY: Record<
  AssetKind,
  { label: string; purpose: string; formats: string; limit: string }
> = {
  video: {
    label: "课堂视频",
    purpose: "M1 真实处理链路必需",
    formats: "MP4、MOV、WEBM、MKV",
    limit: "最大 4 GiB",
  },
  courseware: {
    label: "课堂课件",
    purpose: "可选",
    formats: "PDF、PPT、PPTX",
    limit: "最大 128 MiB",
  },
  transcript: {
    label: "已有逐字稿",
    purpose: "可选",
    formats: "TXT、DOCX、SRT、VTT",
    limit: "最大 32 MiB",
  },
};

const PHASE_COPY: Record<UploadPhase, string> = {
  pending: "等待上传",
  presigning: "正在申请安全上传地址",
  uploading: "正在直传对象存储",
  verifying: "后端正在核验文件",
  uploaded: "上传并核验完成",
  failed: "上传失败，可重试",
};

function extensionOf(name: string) {
  const index = name.lastIndexOf(".");
  return index >= 0 ? name.slice(index).toLowerCase() : "";
}

function classifyFile(file: File): AssetKind | null {
  const extension = extensionOf(file.name);
  return (
    (Object.entries(ACCEPTED_EXTENSIONS).find(([, extensions]) =>
      extensions.includes(extension),
    )?.[0] as AssetKind | undefined) ?? null
  );
}

function contentTypeOf(file: File) {
  return CONTENT_TYPES[extensionOf(file.name)] ?? file.type;
}

function formatBytes(bytes: number) {
  if (bytes >= 1024 * 1024 * 1024) {
    return `${(bytes / (1024 * 1024 * 1024)).toFixed(2)} GB`;
  }
  if (bytes >= 1024 * 1024) {
    return `${(bytes / (1024 * 1024)).toFixed(1)} MB`;
  }
  return `${Math.max(1, Math.round(bytes / 1024))} KB`;
}

function displayError(error: unknown) {
  if (error instanceof ApiClientError) {
    return `${error.message}${error.traceId ? `（追踪号：${error.traceId}）` : ""}`;
  }
  return error instanceof Error ? error.message : "上传失败，请稍后重试。";
}

export function UploadPanel({
  classroomId,
  analysisContract,
  onVideoReadinessChange,
  onTaskCreated,
}: UploadPanelProps) {
  const inputRef = useRef<HTMLInputElement>(null);
  const [assets, setAssets] = useState<SelectedAsset[]>([]);
  const [error, setError] = useState("");
  const [dragging, setDragging] = useState(false);
  const [submitting, setSubmitting] = useState(false);
  const [taskCreated, setTaskCreated] = useState(false);
  const [backendHealth, setBackendHealth] =
    useState<BackendHealthState>("checking");

  useEffect(() => {
    const controller = new AbortController();
    getBackendHealth(controller.signal)
      .then((health) => {
        if (!health.reachable) setBackendHealth("unreachable");
        else setBackendHealth(health.status === "ok" ? "reachable" : "degraded");
      })
      .catch(() => setBackendHealth("unreachable"));
    return () => controller.abort();
  }, []);

  function updateAsset(
    id: string,
    patch: Partial<Omit<SelectedAsset, "id" | "file" | "kind">>,
  ) {
    setAssets((current) =>
      current.map((asset) => (asset.id === id ? { ...asset, ...patch } : asset)),
    );
  }

  function addFiles(files: File[]) {
    const next: SelectedAsset[] = [];
    for (const file of files) {
      const kind = classifyFile(file);
      if (!kind) {
        setError(`“${file.name}”格式不支持，请按页面列出的格式重新选择。`);
        return;
      }
      if (!contentTypeOf(file)) {
        setError(`无法识别“${file.name}”的 Content-Type。`);
        return;
      }
      if (file.size > MAX_BYTES[kind]) {
        setError(
          `“${file.name}”大小为 ${formatBytes(file.size)}，超过${KIND_COPY[kind].label}限制。`,
        );
        return;
      }
      const duplicate = [...assets, ...next].some(
        (asset) =>
          asset.file.name === file.name &&
          asset.file.size === file.size &&
          asset.file.lastModified === file.lastModified,
      );
      if (!duplicate) {
        next.push({
          id: `${file.name}-${file.size}-${file.lastModified}`,
          file,
          kind,
          phase: "pending",
          progress: 0,
        });
      }
    }
    setAssets((current) => [...current, ...next]);
    setError(next.length ? "" : "这些文件已经在待上传列表中。");
  }

  function handleInput(event: ChangeEvent<HTMLInputElement>) {
    addFiles(Array.from(event.target.files ?? []));
    event.target.value = "";
  }

  function handleDrop(event: DragEvent<HTMLDivElement>) {
    event.preventDefault();
    setDragging(false);
    addFiles(Array.from(event.dataTransfer.files));
  }

  async function removeSelectedAsset(asset: SelectedAsset) {
    if (asset.assetId) {
      setSubmitting(true);
      setError("");
      try {
        await deleteAsset(asset.assetId);
      } catch (removeError) {
        setError(displayError(removeError));
        setSubmitting(false);
        return;
      }
      setSubmitting(false);
    }
    setAssets((current) => current.filter((item) => item.id !== asset.id));
  }

  const hasVideo = assets.some((asset) => asset.kind === "video");
  const allUploaded =
    assets.length > 0 && assets.every((asset) => asset.phase === "uploaded");

  useEffect(() => {
    onVideoReadinessChange?.(hasVideo);
  }, [hasVideo, onVideoReadinessChange]);

  async function uploadAndCreateTask() {
    if (!hasVideo || !classroomId || backendHealth !== "reachable") return;
    setSubmitting(true);
    setError("");
    const completedAssetIds: string[] = assets
      .filter((asset) => asset.phase === "uploaded" && asset.assetId)
      .map((asset) => asset.assetId as string);

    try {
      for (const asset of assets) {
        if (asset.phase === "uploaded" && asset.assetId) continue;
        let upload: PresignResponse | undefined;
        try {
          updateAsset(asset.id, {
            phase: "presigning",
            progress: 0,
            error: undefined,
          });
          upload = await presignUpload(classroomId, {
            kind: asset.kind,
            filename: asset.file.name,
            contentType: contentTypeOf(asset.file),
            sizeBytes: asset.file.size,
          });
          updateAsset(asset.id, {
            phase: "uploading",
            assetId: upload.asset_id,
          });
          const etag = await putPresignedUpload(upload, asset.file, (progress) =>
            updateAsset(asset.id, { progress }),
          );
          updateAsset(asset.id, { phase: "verifying", progress: 100 });
          const completed = await completeUpload(upload.asset_id, etag);
          completedAssetIds.push(completed.id);
          updateAsset(asset.id, {
            phase: "uploaded",
            progress: 100,
            assetId: completed.id,
          });
        } catch (assetError) {
          if (upload?.asset_id) {
            await deleteAsset(upload.asset_id).catch(() => undefined);
          }
          const message = displayError(assetError);
          updateAsset(asset.id, {
            phase: "failed",
            progress: 0,
            assetId: undefined,
            error: message,
          });
          throw assetError;
        }
      }

      const task = await createTask(
        classroomId,
        completedAssetIds,
        analysisContract,
      );
      setTaskCreated(true);
      onTaskCreated?.(task);
    } catch (uploadError) {
      setError(displayError(uploadError));
    } finally {
      setSubmitting(false);
    }
  }

  return (
    <section
      className="upload-panel is-visible"
      aria-labelledby="upload-title"
      data-reveal
    >
      <div className="upload-heading">
        <div>
          <span
            className={`mock-pill backend-${backendHealth}`}
            aria-live="polite"
          >
            {backendHealth === "checking"
              ? "正在检查后端"
              : backendHealth === "reachable"
                ? "数据库与安全上传服务已就绪"
                : backendHealth === "degraded"
                  ? "后台在线，安全上传依赖暂不可用"
                  : "课堂后台暂不可达"}
          </span>
          <h2 id="upload-title">上传课堂资料</h2>
          <p>
            文件将通过限时预签名地址直接上传到私有对象存储；长期密钥不会进入浏览器，后端会在创建任务前执行
            HEAD 核验。
          </p>
        </div>
        <span className="upload-step">步骤 3 / 3</span>
      </div>

      <div
        className={`upload-dropzone ${dragging ? "dragging" : ""}`}
        onDragEnter={(event) => {
          event.preventDefault();
          setDragging(true);
        }}
        onDragOver={(event) => event.preventDefault()}
        onDragLeave={() => setDragging(false)}
        onDrop={handleDrop}
      >
        <span className="upload-symbol" aria-hidden>
          ↑
        </span>
        <div>
          <strong>拖入文件，或从电脑选择</strong>
          <p>课堂视频为真实分析链路必需；课件和逐字稿可以补充证据。</p>
        </div>
        <button
          className="button primary upload-select-button"
          type="button"
          disabled={submitting}
          onClick={() => inputRef.current?.click()}
        >
          <span aria-hidden>＋</span>
          选择课堂视频与资料
        </button>
        <input
          ref={inputRef}
          className="sr-only"
          type="file"
          multiple
          accept={Object.values(ACCEPTED_EXTENSIONS).flat().join(",")}
          onChange={handleInput}
        />
      </div>

      <div className="upload-kinds" aria-label="支持的资料类型">
        {(Object.keys(KIND_COPY) as AssetKind[]).map((kind) => (
          <article key={kind}>
            <span>{KIND_COPY[kind].label}</span>
            <p>
              <strong>{KIND_COPY[kind].purpose}</strong>
              <small>支持 {KIND_COPY[kind].formats}</small>
              <small>{KIND_COPY[kind].limit}</small>
            </p>
          </article>
        ))}
      </div>

      {error && (
        <p className="upload-error" role="alert">
          {error}
        </p>
      )}

      {assets.length > 0 && (
        <div className="upload-selection">
          <div className="upload-selection-heading">
            <strong>待上传资料</strong>
            <span>{assets.length} 个文件</span>
          </div>
          <ul>
            {assets.map((asset) => (
              <li key={asset.id}>
                <span className={`asset-kind ${asset.kind}`}>
                  {KIND_COPY[asset.kind].label}
                </span>
                <span className="asset-name">
                  <strong>{asset.file.name}</strong>
                  <small>
                    {formatBytes(asset.file.size)} · {PHASE_COPY[asset.phase]}
                    {asset.phase === "uploading"
                      ? ` ${asset.progress}%`
                      : ""}
                  </small>
                  {asset.error && <small className="asset-error">{asset.error}</small>}
                  {asset.phase === "uploading" && (
                    <progress max={100} value={asset.progress}>
                      {asset.progress}%
                    </progress>
                  )}
                </span>
                <button
                  type="button"
                  disabled={submitting || taskCreated}
                  onClick={() => void removeSelectedAsset(asset)}
                  aria-label={`移除 ${asset.file.name}`}
                >
                  移除
                </button>
              </li>
            ))}
          </ul>
        </div>
      )}

      <div className="upload-gate">
        <div>
          <span className={hasVideo ? "gate-ok" : "gate-wait"}>
            {hasVideo ? "✓" : "○"}
          </span>
          <span>
            <strong>
              {allUploaded
                ? "全部文件已通过后端核验"
                : hasVideo
                  ? "视频校验通过，可开始真实上传"
                  : "等待课堂视频"}
            </strong>
            <small>
              已有逐字稿不能替代视频生成时间戳证据的真实处理链路。
            </small>
          </span>
        </div>
        <button
          className="button primary"
          type="button"
          disabled={
            submitting ||
            taskCreated ||
            !hasVideo ||
            !classroomId ||
            backendHealth !== "reachable"
          }
          onClick={uploadAndCreateTask}
        >
          {submitting
            ? "正在上传并核验…"
            : taskCreated
              ? "处理任务已创建"
              : "上传并创建处理任务"}
        </button>
      </div>

      <p className="upload-security">
        隐私提示：不要上传学生姓名、学号、人脸或未经授权的课堂资料；长期对象存储密钥不会进入前端。
      </p>
    </section>
  );
}
