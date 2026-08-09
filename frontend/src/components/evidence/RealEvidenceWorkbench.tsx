"use client";

import { useCallback, useEffect, useMemo, useState } from "react";
import Link from "next/link";

import {
  ApiClientError,
  getAssetDownloadUrl,
  getConclusions,
  getTaskAssets,
  getTranscript,
  reviewConclusion,
  updateTranscriptSegment,
} from "@/lib/api";
import type {
  AnalysisConclusion,
  ReviewAction,
  TaskRead,
  TranscriptRead,
  TranscriptSegment,
} from "@/types/contracts";

import { TranscriptTimeline, type TranscriptItem } from "./TranscriptTimeline";
import { VideoPlayer } from "./VideoPlayer";

type WorkbenchData = {
  videoUrl?: string;
  transcript: TranscriptRead;
  conclusions: AnalysisConclusion[];
};

const conclusionLabels = {
  fact: "可核对事实",
  judgment: "分析判断",
  suggestion: "改进建议",
} as const;

const reviewLabels = {
  pending: "待教师复核",
  accepted: "教师已接受",
  modified: "教师已修改确认",
  rejected: "教师已驳回",
} as const;

function displayError(error: unknown) {
  if (error instanceof ApiClientError) {
    return `${error.message}${error.traceId ? `（Trace ${error.traceId}）` : ""}`;
  }
  return error instanceof Error ? error.message : "证据读取失败，请稍后重试。";
}

function formatTimestamp(timeMs?: number | null) {
  if (timeMs == null) return "未标注时间";
  const totalSeconds = Math.max(0, Math.floor(timeMs / 1000));
  return `${String(Math.floor(totalSeconds / 60)).padStart(2, "0")}:${String(
    totalSeconds % 60,
  ).padStart(2, "0")}`;
}

export function RealEvidenceWorkbench({ task }: { task: TaskRead }) {
  const [data, setData] = useState<WorkbenchData | null>(null);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState("");
  const [reloadKey, setReloadKey] = useState(0);
  const [currentVideoTimeMs, setCurrentVideoTimeMs] = useState(0);
  const [seekToMs, setSeekToMs] = useState(0);
  const [selectedSegmentId, setSelectedSegmentId] = useState<string | null>(null);

  const loadWorkbench = useCallback(async () => {
    setLoading(true);
    setError("");
    try {
      const [assets, transcript, classroomConclusions] = await Promise.all([
        getTaskAssets(task.id),
        getTranscript(task.id),
        getConclusions(task.classroom_id),
      ]);
      const video = assets.find((asset) => asset.kind === "video");
      const download = video ? await getAssetDownloadUrl(video.id) : undefined;
      setData({
        videoUrl: download?.url,
        transcript,
        conclusions: classroomConclusions.filter(
          (conclusion) => conclusion.task_id === task.id,
        ),
      });
      setSelectedSegmentId((current) =>
        transcript.segments.some((segment) => segment.id === current)
          ? current
          : transcript.segments[0]?.id ?? null,
      );
    } catch (loadError) {
      setError(displayError(loadError));
    } finally {
      setLoading(false);
    }
  }, [task.classroom_id, task.id]);

  useEffect(() => {
    void loadWorkbench();
  }, [loadWorkbench, reloadKey]);

  const timelineItems = useMemo<TranscriptItem[]>(
    () =>
      (data?.transcript.segments ?? []).map((segment) => ({
        id: segment.id,
        startMs: segment.start_ms,
        endMs: segment.end_ms,
        speaker: segment.speaker || "说话人未标注",
        originalText: segment.text,
        translatedText: segment.translation || "暂无译文",
      })),
    [data?.transcript.segments],
  );
  const selectedSegment = data?.transcript.segments.find(
    (segment) => segment.id === selectedSegmentId,
  );

  async function saveSegment(
    segmentId: string,
    input: { text: string; speaker: string; translation: string },
  ) {
    const updated = await updateTranscriptSegment(segmentId, {
      text: input.text,
      speaker: input.speaker || null,
      translation: input.translation || null,
    });
    setData((current) =>
      current
        ? {
            ...current,
            transcript: {
              ...current.transcript,
              segments: current.transcript.segments.map((segment) =>
                segment.id === updated.id ? updated : segment,
              ),
            },
          }
        : current,
    );
  }

  async function persistReview(
    conclusion: AnalysisConclusion,
    action: ReviewAction,
    editedContent: string,
    note: string,
  ) {
    await reviewConclusion(conclusion.id, {
      action,
      editedContent: action === "modify" ? editedContent : null,
      note: note || null,
    });
    const refreshed = await getConclusions(task.classroom_id);
    setData((current) =>
      current
        ? {
            ...current,
            conclusions: refreshed.filter((item) => item.task_id === task.id),
          }
        : current,
    );
  }

  if (loading) {
    return (
      <section className="real-evidence-state" aria-live="polite">
        <strong>正在恢复真实课堂证据…</strong>
        <p>正在读取任务素材、带时间戳逐字稿与分析结论。</p>
      </section>
    );
  }

  if (error || !data) {
    return (
      <section className="real-evidence-state error" role="alert">
        <strong>真实证据工作台暂时无法载入</strong>
        <p>{error || "后端没有返回可用证据。"}</p>
        <button className="button secondary compact" type="button" onClick={() => setReloadKey((key) => key + 1)}>
          重试读取
        </button>
      </section>
    );
  }

  return (
    <section className="evidence-workbench real" aria-labelledby="real-evidence-title">
      <header className="evidence-workbench-heading">
        <div>
          <span className="mock-pill backend-reachable">真实任务证据 · 教师复核</span>
          <h2 id="real-evidence-title">逐条核对原文与画面，再决定是否进入报告</h2>
        </div>
        <div className="real-evidence-heading-actions">
          <p>视频地址为限时授权，不会写入浏览器存储或日志。</p>
          <button className="text-button" type="button" onClick={() => setReloadKey((key) => key + 1)}>
            刷新证据与授权
          </button>
        </div>
      </header>

      <div className="evidence-workbench-grid">
        <div className="evidence-media-column">
          <VideoPlayer
            videoUrl={data.videoUrl}
            seekToMs={seekToMs}
            onTimeUpdate={setCurrentVideoTimeMs}
          />
          <TranscriptTimeline
            items={timelineItems}
            currentTimeMs={currentVideoTimeMs}
            onSeek={(timeMs) => {
              setSeekToMs(timeMs);
              setCurrentVideoTimeMs(timeMs);
              const segment = data.transcript.segments.find(
                (item) => item.start_ms === timeMs,
              );
              setSelectedSegmentId(segment?.id ?? null);
            }}
          />
          {selectedSegment && (
            <TranscriptSegmentEditor segment={selectedSegment} onSave={saveSegment} />
          )}
        </div>

        <div className="evidence-review-column">
          {data.conclusions.length === 0 ? (
            <div className="real-evidence-empty">
              <strong>任务已完成，但没有可复核结论</strong>
              <p>请检查 Agent 运行记录；系统不会用固定样例冒充真实分析。</p>
            </div>
          ) : (
            data.conclusions.map((conclusion) => (
              <ConclusionReviewCard
                key={conclusion.id}
                conclusion={conclusion}
                onSeek={(timeMs, segmentId) => {
                  if (timeMs != null) {
                    setSeekToMs(timeMs);
                    setCurrentVideoTimeMs(timeMs);
                  }
                  if (segmentId) setSelectedSegmentId(segmentId);
                }}
                onReview={persistReview}
              />
            ))
          )}
          {data.conclusions.some((item) =>
            ["accepted", "modified"].includes(item.review_status),
          ) && (
            <div className="real-report-boundary">
              <Link className="button primary wide" href={`/reports/${task.classroom_id}`}>
                进入真实报告编辑与导出
              </Link>
              <p>报告只组合教师已接受或修改确认的结论，待复核与已驳回内容会被排除。</p>
            </div>
          )}
        </div>
      </div>
    </section>
  );
}

function TranscriptSegmentEditor({
  segment,
  onSave,
}: {
  segment: TranscriptSegment;
  onSave: (
    segmentId: string,
    input: { text: string; speaker: string; translation: string },
  ) => Promise<void>;
}) {
  const [speaker, setSpeaker] = useState(segment.speaker ?? "");
  const [text, setText] = useState(segment.text);
  const [translation, setTranslation] = useState(segment.translation ?? "");
  const [saving, setSaving] = useState(false);
  const [feedback, setFeedback] = useState("");

  useEffect(() => {
    setSpeaker(segment.speaker ?? "");
    setText(segment.text);
    setTranslation(segment.translation ?? "");
    setFeedback("");
  }, [segment]);

  async function submit() {
    if (!text.trim()) {
      setFeedback("逐字稿原文不能为空。");
      return;
    }
    setSaving(true);
    setFeedback("");
    try {
      await onSave(segment.id, {
        speaker: speaker.trim(),
        text: text.trim(),
        translation: translation.trim(),
      });
      setFeedback("修改已保存，并保留人工编辑状态。");
    } catch (error) {
      setFeedback(displayError(error));
    } finally {
      setSaving(false);
    }
  }

  return (
    <section className="transcript-editor" aria-labelledby="transcript-editor-title">
      <header>
        <div>
          <span className="evidence-kicker">HUMAN CORRECTION</span>
          <h3 id="transcript-editor-title">校订当前逐字稿片段</h3>
        </div>
        <small>{formatTimestamp(segment.start_ms)}–{formatTimestamp(segment.end_ms)}</small>
      </header>
      <label>
        说话人
        <input value={speaker} onChange={(event) => setSpeaker(event.target.value)} />
      </label>
      <label>
        课堂原文
        <textarea rows={4} value={text} onChange={(event) => setText(event.target.value)} />
      </label>
      <label>
        中文译文（可选）
        <textarea rows={3} value={translation} onChange={(event) => setTranslation(event.target.value)} />
      </label>
      <div className="transcript-editor-actions">
        <button className="button secondary compact" type="button" disabled={saving} onClick={() => void submit()}>
          {saving ? "正在保存…" : "保存人工校订"}
        </button>
        {feedback && <p role="status">{feedback}</p>}
      </div>
    </section>
  );
}

function ConclusionReviewCard({
  conclusion,
  onSeek,
  onReview,
}: {
  conclusion: AnalysisConclusion;
  onSeek: (timeMs?: number | null, segmentId?: string | null) => void;
  onReview: (
    conclusion: AnalysisConclusion,
    action: ReviewAction,
    editedContent: string,
    note: string,
  ) => Promise<void>;
}) {
  const [editedContent, setEditedContent] = useState(
    conclusion.reviewed_content || conclusion.content,
  );
  const [note, setNote] = useState("");
  const [saving, setSaving] = useState(false);
  const [feedback, setFeedback] = useState("");

  useEffect(() => {
    setEditedContent(conclusion.reviewed_content || conclusion.content);
  }, [conclusion.content, conclusion.reviewed_content]);

  async function submit(action: ReviewAction) {
    if (action === "modify" && !editedContent.trim()) {
      setFeedback("修改确认前，请填写非空的教师修改稿。");
      return;
    }
    if (action === "reject" && !note.trim()) {
      setFeedback("驳回前请简要填写原因，便于追溯和改进 Agent。");
      return;
    }
    setSaving(true);
    setFeedback("");
    try {
      await onReview(conclusion, action, editedContent.trim(), note.trim());
      setFeedback("复核结果已写入后端并保留历史记录。");
    } catch (error) {
      setFeedback(displayError(error));
    } finally {
      setSaving(false);
    }
  }

  return (
    <article className={`real-conclusion-card ${conclusion.type}`}>
      <header>
        <span>{conclusionLabels[conclusion.type]}</span>
        <strong className={`status-badge ${conclusion.review_status}`}>
          {reviewLabels[conclusion.review_status]}
        </strong>
      </header>
      <p className="real-conclusion-content">{conclusion.content}</p>
      {conclusion.reviewed_content && (
        <p className="real-reviewed-content">
          <strong>教师确认稿：</strong>{conclusion.reviewed_content}
        </p>
      )}
      <div className="real-evidence-references" aria-label="结论证据">
        {conclusion.evidence_refs.map((reference, index) => (
          <button
            type="button"
            key={reference.id ?? `${conclusion.id}-${index}`}
            onClick={() => onSeek(reference.start_ms, reference.segment_id)}
          >
            <strong>
              证据 {index + 1} · {reference.source_type} · {formatTimestamp(reference.start_ms)}
            </strong>
            <span>{reference.quote || "点击定位到对应原文或画面"}</span>
          </button>
        ))}
      </div>
      <label>
        教师修改稿
        <textarea rows={4} value={editedContent} onChange={(event) => setEditedContent(event.target.value)} />
      </label>
      <label>
        复核说明（驳回时必填）
        <textarea rows={2} value={note} onChange={(event) => setNote(event.target.value)} />
      </label>
      <div className="real-review-actions">
        <button type="button" disabled={saving} onClick={() => void submit("accept")}>接受原结论</button>
        <button type="button" disabled={saving} onClick={() => void submit("modify")}>修改后确认</button>
        <button type="button" disabled={saving} onClick={() => void submit("reject")}>驳回</button>
      </div>
      {feedback && <p className="real-review-feedback" role="status">{feedback}</p>}
      <footer>
        <small>Trace {conclusion.trace_id}</small>
        <small>{conclusion.model_name || "模型未记录"} · {conclusion.skill || "Skill 未记录"} · {conclusion.prompt_version || "Prompt 版本未记录"}</small>
      </footer>
    </article>
  );
}
