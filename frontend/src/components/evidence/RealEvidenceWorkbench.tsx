"use client";

import { useCallback, useEffect, useMemo, useState } from "react";
import Link from "next/link";

import {
  ApiClientError,
  getAssetDownloadUrl,
  getConclusions,
  getCoursewarePages,
  getTaskAssets,
  getTranscript,
  reviewConclusion,
  startDemoSession,
  updateTranscriptSegment,
} from "@/lib/api";
import type {
  AnalysisConclusion,
  AssetRead,
  CoursewarePageRead,
  EvidenceReference,
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
  coursewarePages: CoursewarePageRead[];
  coursewareAssets: Record<string, AssetRead>;
  coursewareUrls: Record<string, string>;
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

type ConclusionFilter = "all" | AnalysisConclusion["review_status"];
type ConclusionTrackToken = number | "ellipsis-start" | "ellipsis-end";

function buildConclusionTrack(
  total: number,
  activeIndex: number,
): ConclusionTrackToken[] {
  if (total <= 7) return Array.from({ length: total }, (_, index) => index);

  let start = Math.max(1, activeIndex - 2);
  let end = Math.min(total - 2, activeIndex + 2);
  while (end - start + 1 < 5 && start > 1) start -= 1;
  while (end - start + 1 < 5 && end < total - 2) end += 1;

  const tokens: ConclusionTrackToken[] = [0];
  if (start > 1) tokens.push("ellipsis-start");
  for (let index = start; index <= end; index += 1) tokens.push(index);
  if (end < total - 2) tokens.push("ellipsis-end");
  tokens.push(total - 1);
  return tokens;
}

function normalizeError(error: unknown): {
  message: string;
  traceId?: string;
  status?: number;
} {
  if (error instanceof ApiClientError) {
    return { message: error.message, traceId: error.traceId, status: error.status };
  }
  return {
    message: error instanceof Error ? error.message : "证据读取失败，请稍后重试。",
  };
}

function displayError(error: unknown) {
  const normalized = normalizeError(error);
  return `${normalized.message}${normalized.traceId ? `（追踪编号：${normalized.traceId}）` : ""}`;
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
  const [error, setError] = useState<{
    message: string;
    traceId?: string;
    status?: number;
  } | null>(null);
  const [reloadKey, setReloadKey] = useState(0);
  const [currentVideoTimeMs, setCurrentVideoTimeMs] = useState(0);
  const [seekToMs, setSeekToMs] = useState(0);
  const [selectedSegmentId, setSelectedSegmentId] = useState<string | null>(null);
  const [selectedCoursewarePageId, setSelectedCoursewarePageId] = useState<string | null>(null);
  const [activeConclusionIndex, setActiveConclusionIndex] = useState(0);
  const [queueFeedback, setQueueFeedback] = useState("");
  const [queueExpanded, setQueueExpanded] = useState(false);
  const [queueFilter, setQueueFilter] = useState<ConclusionFilter>("all");

  const loadWorkbench = useCallback(async () => {
    setLoading(true);
    setError(null);
    try {
      const [assets, transcript, classroomConclusions, coursewarePages] = await Promise.all([
        getTaskAssets(task.id),
        getTranscript(task.id),
        getConclusions(task.classroom_id),
        getCoursewarePages(task.id),
      ]);
      const video = assets.find((asset) => asset.kind === "video");
      const coursewareAssets = assets.filter((asset) => asset.kind === "courseware");
      const [download, coursewareDownloads] = await Promise.all([
        video ? getAssetDownloadUrl(video.id) : Promise.resolve(undefined),
        Promise.all(
          coursewareAssets.map(async (asset) => [
            asset.id,
            (await getAssetDownloadUrl(asset.id)).url,
          ] as const),
        ),
      ]);
      setData({
        videoUrl: download?.url,
        transcript,
        coursewarePages,
        coursewareAssets: Object.fromEntries(
          coursewareAssets.map((asset) => [asset.id, asset]),
        ),
        coursewareUrls: Object.fromEntries(coursewareDownloads),
        conclusions: classroomConclusions.filter(
          (conclusion) => conclusion.task_id === task.id,
        ),
      });
      setQueueFeedback("");
      setSelectedSegmentId((current) =>
        transcript.segments.some((segment) => segment.id === current)
          ? current
          : transcript.segments[0]?.id ?? null,
      );
      setSelectedCoursewarePageId((current) =>
        coursewarePages.some((page) => page.id === current)
          ? current
          : coursewarePages[0]?.id ?? null,
      );
    } catch (loadError) {
      setError(normalizeError(loadError));
    } finally {
      setLoading(false);
    }
  }, [task.classroom_id, task.id]);

  async function recoverDemoSession() {
    setLoading(true);
    setError(null);
    try {
      await startDemoSession();
      await loadWorkbench();
    } catch (sessionError) {
      setError(normalizeError(sessionError));
      setLoading(false);
    }
  }

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
  const selectedCoursewarePage = data?.coursewarePages.find(
    (page) => page.id === selectedCoursewarePageId,
  );
  const reviewedConclusionCount =
    data?.conclusions.filter((item) => item.review_status !== "pending").length ?? 0;
  const allConclusionsReviewed =
    (data?.conclusions.length ?? 0) > 0 &&
    reviewedConclusionCount === data?.conclusions.length;
  const hasReportableConclusion =
    data?.conclusions.some((item) =>
      ["accepted", "modified"].includes(item.review_status),
    ) ?? false;
  const conclusionTrack = useMemo(
    () => buildConclusionTrack(data?.conclusions.length ?? 0, activeConclusionIndex),
    [activeConclusionIndex, data?.conclusions.length],
  );
  const nextPendingConclusionIndex = useMemo(() => {
    const conclusions = data?.conclusions ?? [];
    const afterCurrent = conclusions.findIndex(
      (item, index) => index > activeConclusionIndex && item.review_status === "pending",
    );
    if (afterCurrent >= 0) return afterCurrent;
    return conclusions.findIndex(
      (item, index) => index !== activeConclusionIndex && item.review_status === "pending",
    );
  }, [activeConclusionIndex, data?.conclusions]);
  const filteredConclusions = useMemo(
    () =>
      (data?.conclusions ?? [])
        .map((conclusion, index) => ({ conclusion, index }))
        .filter(({ conclusion }) =>
          queueFilter === "all" ? true : conclusion.review_status === queueFilter,
        ),
    [data?.conclusions, queueFilter],
  );

  useEffect(() => {
    setActiveConclusionIndex((current) =>
      Math.min(current, Math.max((data?.conclusions.length ?? 1) - 1, 0)),
    );
  }, [data?.conclusions.length]);

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
    setQueueFeedback("");
    await reviewConclusion(conclusion.id, {
      action,
      editedContent: action === "modify" ? editedContent : null,
      note: note || null,
    });
    const refreshed = await getConclusions(task.classroom_id);
    const taskConclusions = refreshed.filter((item) => item.task_id === task.id);
    setData((current) =>
      current
        ? {
            ...current,
            conclusions: taskConclusions,
          }
        : current,
    );
    const reviewedIndex = taskConclusions.findIndex((item) => item.id === conclusion.id);
    const nextPendingAfter = taskConclusions.findIndex(
      (item, index) => index > reviewedIndex && item.review_status === "pending",
    );
    const firstPending = taskConclusions.findIndex(
      (item) => item.review_status === "pending",
    );
    const nextPendingIndex = nextPendingAfter >= 0 ? nextPendingAfter : firstPending;
    if (nextPendingIndex >= 0) {
      setActiveConclusionIndex(nextPendingIndex);
      setQueueFeedback(
        `第 ${reviewedIndex + 1} 条已保存，已进入第 ${nextPendingIndex + 1} 条。`,
      );
    } else {
      const hasReportable = taskConclusions.some((item) =>
        ["accepted", "modified"].includes(item.review_status),
      );
      setActiveConclusionIndex(Math.max(reviewedIndex, 0));
      setQueueFeedback(
        hasReportable
          ? `第 ${reviewedIndex + 1} 条已保存，全部结论已审核完成，可以进入报告编辑与导出。`
          : `第 ${reviewedIndex + 1} 条已保存，全部结论均已驳回；至少保留一条结论后才能进入报告。`,
      );
    }
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
    const sessionExpired = error?.status === 401;
    return (
      <section className="real-evidence-state error" role="alert">
        <strong>{sessionExpired ? "浏览器会话尚未建立" : "真实证据工作台暂时无法载入"}</strong>
        <p>
          {sessionExpired
            ? "当前浏览器没有有效的演示会话。建立会话后，系统会自动重新读取任务证据。"
            : error?.message || "后端没有返回可用证据。"}
        </p>
        {error?.traceId && <small>追踪编号：{error.traceId}</small>}
        <button
          className={`button ${sessionExpired ? "primary" : "secondary compact"}`}
          type="button"
          onClick={() => void (sessionExpired ? recoverDemoSession() : setReloadKey((key) => key + 1))}
        >
          {sessionExpired ? "建立演示会话并重试" : "重试读取"}
        </button>
      </section>
    );
  }

  return (
    <section className="evidence-workbench real" aria-labelledby="real-evidence-title">
      <header className="evidence-workbench-heading">
        <div>
            <span className="status-pill backend-reachable">真实任务证据 · 教师复核</span>
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
          <div className="evidence-video-frame">
            <VideoPlayer
              videoUrl={data.videoUrl}
              seekToMs={seekToMs}
              onTimeUpdate={setCurrentVideoTimeMs}
            />
          </div>
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
          {data.coursewarePages.length > 0 && (
            <CoursewareEvidencePanel
              pages={data.coursewarePages}
              assets={data.coursewareAssets}
              downloadUrls={data.coursewareUrls}
              selectedPageId={selectedCoursewarePage?.id ?? null}
              onSelectPage={setSelectedCoursewarePageId}
            />
          )}
        </div>

        <div className="evidence-review-column">
          {data.conclusions.length === 0 ? (
            <div className="real-evidence-empty">
              <strong>任务已完成，但没有可复核结论</strong>
              <p>请检查 Agent 运行记录；系统不会用固定样例冒充真实分析。</p>
            </div>
          ) : (
            <section className="conclusion-review-carousel" aria-label="分析结论逐条审核">
              <header className="conclusion-review-queue">
                <div className="conclusion-review-queue-topline">
                  <div className="conclusion-review-queue-copy">
                    <span>REVIEW QUEUE · 逐条审核</span>
                    <strong>第 {activeConclusionIndex + 1} 条，共 {data.conclusions.length} 条</strong>
                    <small>
                      已完成 {reviewedConclusionCount} / {data.conclusions.length} · 待审核 {data.conclusions.length - reviewedConclusionCount}
                    </small>
                  </div>
                  <div className="conclusion-queue-actions">
                    <button
                      type="button"
                      disabled={nextPendingConclusionIndex < 0}
                      onClick={() => {
                        if (nextPendingConclusionIndex < 0) return;
                        setActiveConclusionIndex(nextPendingConclusionIndex);
                        setQueueFeedback("");
                      }}
                    >
                      {nextPendingConclusionIndex < 0 ? "没有遗漏的待审核项" : "下一条待审核"}
                    </button>
                    <button
                      type="button"
                      aria-expanded={queueExpanded}
                      onClick={() => setQueueExpanded((current) => !current)}
                    >
                      {queueExpanded ? "收起完整清单" : "查看完整清单"}
                    </button>
                  </div>
                </div>
                <nav className="conclusion-progress-track" aria-label="选择要审核的分析结论">
                  {conclusionTrack.map((token) =>
                    typeof token === "number" ? (
                      <button
                        key={data.conclusions[token].id}
                        className={`${data.conclusions[token].review_status} ${token === activeConclusionIndex ? "active" : ""}`}
                        type="button"
                        aria-label={`第 ${token + 1} 条：${reviewLabels[data.conclusions[token].review_status]}`}
                        aria-current={token === activeConclusionIndex ? "step" : undefined}
                        onClick={() => {
                          setActiveConclusionIndex(token);
                          setQueueFeedback("");
                        }}
                      >
                        <span>{token + 1}</span>
                      </button>
                    ) : (
                      <span className="conclusion-track-ellipsis" aria-hidden key={token}>…</span>
                    ),
                  )}
                </nav>
                {queueExpanded && (
                  <section className="conclusion-queue-directory" aria-label="全部分析结论清单">
                    <div className="conclusion-queue-filters" role="group" aria-label="按审核状态筛选">
                      {(
                        [
                          ["all", "全部"],
                          ["pending", "待审核"],
                          ["accepted", "已接受"],
                          ["modified", "已修改"],
                          ["rejected", "已驳回"],
                        ] as const
                      ).map(([value, label]) => (
                        <button
                          type="button"
                          className={queueFilter === value ? "active" : ""}
                          aria-pressed={queueFilter === value}
                          key={value}
                          onClick={() => setQueueFilter(value)}
                        >
                          {label}
                        </button>
                      ))}
                    </div>
                    <div className="conclusion-queue-directory-list">
                      {filteredConclusions.length > 0 ? (
                        filteredConclusions.map(({ conclusion, index }) => (
                          <button
                            type="button"
                            key={conclusion.id}
                            className={index === activeConclusionIndex ? "active" : ""}
                            onClick={() => {
                              setActiveConclusionIndex(index);
                              setQueueExpanded(false);
                              setQueueFeedback("");
                            }}
                          >
                            <span>{index + 1}</span>
                            <strong>{conclusionLabels[conclusion.type]}</strong>
                            <small>{reviewLabels[conclusion.review_status]}</small>
                          </button>
                        ))
                      ) : (
                        <p>当前筛选条件下没有结论。</p>
                      )}
                    </div>
                  </section>
                )}
              </header>
              {queueFeedback && (
                <p className="conclusion-queue-feedback" role="status" aria-live="polite">
                  {queueFeedback}
                </p>
              )}
              <div className="conclusion-carousel-viewport">
                {data.conclusions.map((conclusion, index) => (
                  <div key={conclusion.id} hidden={index !== activeConclusionIndex}>
                    <ConclusionReviewCard
                      conclusion={conclusion}
                      onLocateEvidence={(reference) => {
                        if (reference.source_type === "courseware") {
                          const page = data.coursewarePages.find(
                            (item) =>
                              item.asset_id === reference.asset_id &&
                              item.page_no === reference.page_no,
                          );
                          if (page) {
                            setSelectedCoursewarePageId(page.id);
                            document
                              .getElementById("courseware-evidence-panel")
                              ?.scrollIntoView({ behavior: "smooth", block: "center" });
                          }
                          return;
                        }
                        if (reference.start_ms != null) {
                          setSeekToMs(reference.start_ms);
                          setCurrentVideoTimeMs(reference.start_ms);
                        }
                        if (reference.segment_id) {
                          setSelectedSegmentId(reference.segment_id);
                        }
                      }}
                      onReview={persistReview}
                    />
                  </div>
                ))}
              </div>
            </section>
          )}
          {data.conclusions.length > 0 && (
            <div className="real-report-boundary">
              {allConclusionsReviewed && hasReportableConclusion ? (
                <Link className="button primary wide" href={`/reports/${task.classroom_id}`}>
                  进入真实报告编辑与导出
                </Link>
              ) : (
                <button className="button primary wide" type="button" disabled>
                  {allConclusionsReviewed ? "至少保留一条结论后进入报告" : "完成全部结论审核后进入报告"}
                </button>
              )}
              <p>
                已审核 {reviewedConclusionCount} / {data.conclusions.length}；
                {allConclusionsReviewed
                  ? hasReportableConclusion
                    ? "报告将只组合教师接受或修改确认的结论。"
                    : "当前结论均已驳回，暂无内容可进入报告。"
                  : "请通过左右箭头逐条处理，待复核内容不会进入报告。"}
              </p>
            </div>
          )}
        </div>
      </div>
    </section>
  );
}

function CoursewareEvidencePanel({
  pages,
  assets,
  downloadUrls,
  selectedPageId,
  onSelectPage,
}: {
  pages: CoursewarePageRead[];
  assets: Record<string, AssetRead>;
  downloadUrls: Record<string, string>;
  selectedPageId: string | null;
  onSelectPage: (pageId: string) => void;
}) {
  const selectedPage =
    pages.find((page) => page.id === selectedPageId) ?? pages[0];
  if (!selectedPage) return null;
  const asset = assets[selectedPage.asset_id];
  const baseUrl = downloadUrls[selectedPage.asset_id];
  const isPdf = asset?.content_type === "application/pdf";
  const sourceUrl = baseUrl
    ? `${baseUrl}${isPdf ? `#page=${selectedPage.page_no}` : ""}`
    : undefined;

  return (
    <section
      className="courseware-evidence-panel"
      id="courseware-evidence-panel"
      aria-labelledby="courseware-evidence-title"
    >
      <header>
        <div>
          <span className="evidence-kicker">COURSEWARE EVIDENCE</span>
          <h3 id="courseware-evidence-title">课件原页证据</h3>
          <p>{asset?.filename ?? "课堂课件"} · 第 {selectedPage.page_no} 页</p>
        </div>
        {sourceUrl && (
          <a href={sourceUrl} target="_blank" rel="noreferrer">
            {isPdf ? "打开原文件并定位此页" : "打开原课件核对此页"}
          </a>
        )}
      </header>
      <nav aria-label="选择课件证据页">
        {pages.map((page) => (
          <button
            type="button"
            key={page.id}
            className={page.id === selectedPage.id ? "active" : ""}
            aria-current={page.id === selectedPage.id ? "page" : undefined}
            onClick={() => onSelectPage(page.id)}
          >
            {assets[page.asset_id]?.filename ?? "课件"} · 第 {page.page_no} 页
          </button>
        ))}
      </nav>
      <blockquote>{selectedPage.text}</blockquote>
      <small>页码与文字来自当前任务的真实课件解析结果，可回到原文件人工核对。</small>
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
  onLocateEvidence,
  onReview,
}: {
  conclusion: AnalysisConclusion;
  onLocateEvidence: (reference: EvidenceReference) => void;
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
            onClick={() => onLocateEvidence(reference)}
          >
            <strong>
              证据 {index + 1} · {reference.source_type === "courseware" ? "课件" : reference.source_type} · {reference.source_type === "courseware" ? `第 ${reference.page_no ?? "?"} 页` : formatTimestamp(reference.start_ms)}
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
        <button className="accept-review" type="button" disabled={saving} onClick={() => void submit("accept")}>
          <span>接受并继续</span><span aria-hidden>→</span>
        </button>
        <button className="modify-review" type="button" disabled={saving} onClick={() => void submit("modify")}>
          <span>修改确认并继续</span><span aria-hidden>→</span>
        </button>
        <button className="reject-review" type="button" disabled={saving} onClick={() => void submit("reject")}>
          <span>驳回并继续</span><span aria-hidden>→</span>
        </button>
      </div>
      {feedback && <p className="real-review-feedback" role="status">{feedback}</p>}
      <footer>
        <small>Trace {conclusion.trace_id}</small>
        <small>{conclusion.model_name || "模型未记录"} · {conclusion.skill || "Skill 未记录"} · {conclusion.prompt_version || "Prompt 版本未记录"}</small>
      </footer>
    </article>
  );
}
