"use client";

import { useRef, useState, type ChangeEvent } from "react";

import {
  ApiClientError,
  cancelTask,
  completeUpload,
  createTask,
  deleteAsset,
  getTaskAssets,
  presignUpload,
  putPresignedUpload,
} from "@/lib/api";
import type { TaskRead } from "@/types/contracts";

const MAX_TRANSLATION_BYTES = 32 * 1024 * 1024;
const CONTENT_TYPES: Record<string, string> = {
  ".srt": "application/x-subrip",
  ".vtt": "text/vtt",
};

type UploadPhase = "idle" | "uploading" | "verifying" | "creating";

function extensionOf(filename: string) {
  const index = filename.lastIndexOf(".");
  return index >= 0 ? filename.slice(index).toLowerCase() : "";
}

function displayError(error: unknown) {
  if (error instanceof ApiClientError) {
    return `${error.message}${error.traceId ? `（追踪编号：${error.traceId}）` : ""}`;
  }
  return error instanceof Error ? error.message : "补充译文上传失败，请稍后重试。";
}

export function SupplementalTranslationUpload({
  task,
  onTaskCreated,
}: {
  task: TaskRead;
  onTaskCreated: (task: TaskRead) => void;
}) {
  const inputRef = useRef<HTMLInputElement>(null);
  const [file, setFile] = useState<File | null>(null);
  const [phase, setPhase] = useState<UploadPhase>("idle");
  const [progress, setProgress] = useState(0);
  const [error, setError] = useState("");

  function chooseFile(event: ChangeEvent<HTMLInputElement>) {
    const selected = event.target.files?.[0] ?? null;
    event.target.value = "";
    setError("");
    if (!selected) return;
    const extension = extensionOf(selected.name);
    if (!(extension in CONTENT_TYPES)) {
      setFile(null);
      setError("补充译文只支持带时间轴的 SRT 或 VTT 文件。");
      return;
    }
    if (selected.size <= 0 || selected.size > MAX_TRANSLATION_BYTES) {
      setFile(null);
      setError("补充译文必须大于 0 字节且不超过 32 MiB。");
      return;
    }
    setFile(selected);
  }

  async function uploadAndRecreate() {
    if (!file) return;
    setError("");
    setProgress(0);
    let uploadedAssetId: string | null = null;
    let replacementCreated = false;
    try {
      const extension = extensionOf(file.name);
      setPhase("uploading");
      const upload = await presignUpload(task.classroom_id, {
        kind: "transcript",
        filename: file.name,
        contentType: CONTENT_TYPES[extension],
        sizeBytes: file.size,
      });
      uploadedAssetId = upload.asset_id;
      const etag = await putPresignedUpload(upload, file, setProgress);
      setPhase("verifying");
      const completed = await completeUpload(upload.asset_id, etag);

      setPhase("creating");
      const originalAssets = await getTaskAssets(task.id);
      const reusableAssets = originalAssets.filter((asset) => asset.kind !== "transcript");
      if (!reusableAssets.some((asset) => asset.kind === "video")) {
        throw new Error("原任务缺少可复用的课堂视频，不能创建补充译文任务。");
      }
      const replacement = await createTask(
        task.classroom_id,
        [...reusableAssets.map((asset) => asset.id), completed.id],
        {
          ...task.analysis_contract,
          bilingual_required: true,
          confirmed: true,
        },
      );
      replacementCreated = true;
      if (["pending", "queued", "running"].includes(task.status)) {
        await cancelTask(task.id).catch(() => undefined);
      }
      onTaskCreated(replacement);
    } catch (uploadError) {
      if (uploadedAssetId && !replacementCreated) {
        await deleteAsset(uploadedAssetId).catch(() => undefined);
      }
      setError(displayError(uploadError));
      setPhase("idle");
    }
  }

  const busy = phase !== "idle";
  const phaseText =
    phase === "uploading"
      ? `正在安全上传 ${progress}%`
      : phase === "verifying"
        ? "后端正在核验对象"
        : phase === "creating"
          ? "正在复用视频并创建新任务"
          : "上传译文并重新处理";

  return (
    <div className="supplemental-translation-upload">
      <div>
        <strong>本节包含英文或中英混合内容</strong>
        <p>
          请补充 UTF-8 编码的中文译文字幕。每个 SRT/VTT 时间片段都要包含中文，且时间轴需覆盖全部课堂语音；系统会继续以原视频 ASR 原文为主证据。
        </p>
      </div>
      <div className="supplemental-upload-actions">
        <button
          className="button secondary"
          type="button"
          disabled={busy}
          onClick={() => inputRef.current?.click()}
        >
          {file ? "更换译文字幕" : "选择 SRT / VTT 译文"}
        </button>
        <input
          ref={inputRef}
          className="sr-only"
          type="file"
          accept=".srt,.vtt,application/x-subrip,text/vtt"
          onChange={chooseFile}
        />
        <button
          className="button primary"
          type="button"
          disabled={!file || busy}
          onClick={() => void uploadAndRecreate()}
        >
          {phaseText}
        </button>
      </div>
      {file && (
        <small className="supplemental-file-name">
          已选择：{file.name} · {(file.size / 1024).toFixed(1)} KiB
        </small>
      )}
      {error && <p className="upload-error" role="alert">{error}</p>}
    </div>
  );
}
