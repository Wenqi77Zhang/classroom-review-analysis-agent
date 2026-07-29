"use client";

import {
  useEffect,
  useRef,
  useState,
  type ChangeEvent,
  type DragEvent,
} from "react";

import { getBackendHealth } from "@/lib/api";
import type { AssetKind } from "@/types/contracts";

type BackendHealthState = "checking" | "reachable" | "unreachable";

type SelectedAsset = {
  id: string;
  file: File;
  kind: AssetKind;
};

const ACCEPTED_EXTENSIONS: Record<AssetKind, string[]> = {
  video: [".mp4", ".mov", ".webm", ".mkv"],
  courseware: [".pdf", ".ppt", ".pptx"],
  transcript: [".txt", ".docx", ".srt", ".vtt"],
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

function formatBytes(bytes: number) {
  if (bytes >= 1024 * 1024 * 1024) {
    return `${(bytes / (1024 * 1024 * 1024)).toFixed(2)} GB`;
  }
  if (bytes >= 1024 * 1024) {
    return `${(bytes / (1024 * 1024)).toFixed(1)} MB`;
  }
  return `${Math.max(1, Math.round(bytes / 1024))} KB`;
}

export function UploadPanel({
  onVideoReadinessChange,
}: {
  onVideoReadinessChange?: (hasVideo: boolean) => void;
}) {
  const inputRef = useRef<HTMLInputElement>(null);
  const [assets, setAssets] = useState<SelectedAsset[]>([]);
  const [error, setError] = useState("");
  const [dragging, setDragging] = useState(false);
  const [backendHealth, setBackendHealth] =
    useState<BackendHealthState>("checking");

  useEffect(() => {
    const controller = new AbortController();

    getBackendHealth(controller.signal)
      .then((health) =>
        setBackendHealth(health.reachable ? "reachable" : "unreachable"),
      )
      .catch(() => setBackendHealth("unreachable"));

    return () => controller.abort();
  }, []);

  function addFiles(files: File[]) {
    const next: SelectedAsset[] = [];

    for (const file of files) {
      const kind = classifyFile(file);
      if (!kind) {
        setError(`“${file.name}”格式不支持，请按页面列出的格式重新选择。`);
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

  const hasVideo = assets.some((asset) => asset.kind === "video");

  useEffect(() => {
    onVideoReadinessChange?.(hasVideo);
  }, [hasVideo, onVideoReadinessChange]);

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
              ? "正在检查后端 · 本地校验可用"
              : backendHealth === "reachable"
                ? "后端基础服务可达 · 上传接口待实现"
                : "后端服务未运行 · 本地校验可用"}
          </span>
          <h2 id="upload-title">上传课堂资料</h2>
          <p>
            文件现在只在浏览器中选择和校验，不会被发送或持久保存。健康检查可用不代表上传接口已实现；
            成员 3 完成预签名接口后再启用真实上传。
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
            <span>{assets.length} 个文件仅保留在当前页面</span>
          </div>
          <ul>
            {assets.map((asset) => (
              <li key={asset.id}>
                <span className={`asset-kind ${asset.kind}`}>
                  {KIND_COPY[asset.kind].label}
                </span>
                <span className="asset-name">
                  <strong>{asset.file.name}</strong>
                  <small>{formatBytes(asset.file.size)}</small>
                </span>
                <button
                  type="button"
                  onClick={() =>
                    setAssets((current) =>
                      current.filter((item) => item.id !== asset.id),
                    )
                  }
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
            <strong>{hasVideo ? "视频校验通过" : "等待课堂视频"}</strong>
            <small>
              已有逐字稿不能替代视频生成时间戳证据的真实处理链路。
            </small>
          </span>
        </div>
        <button className="button primary" type="button" disabled>
          上传服务尚未接通
        </button>
      </div>

      <p className="upload-security">
        隐私提示：不要上传学生姓名、学号、人脸或未经授权的课堂资料；长期对象存储密钥不会进入前端。
      </p>
    </section>
  );
}
