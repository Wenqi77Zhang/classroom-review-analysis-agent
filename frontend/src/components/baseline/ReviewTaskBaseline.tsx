"use client";

import Link from "next/link";
import { useRouter } from "next/navigation";
import { useCallback, useEffect, useState, type FormEvent } from "react";
import {
  ApiClientError,
  cancelTask,
  clarifyReviewGoal,
  createTask,
  getTask,
  getTaskAssets,
  listTasksForClassroom,
  startDemoSession,
} from "@/lib/api";
import { saveDemoReportDraft } from "@/lib/demo-report-draft";
import type { AnalysisContract, ReviewDialogueResponse, TaskRead } from "@/types/contracts";
import { EvidenceCard } from "../evidence/EvidenceCard";
import { RealEvidenceWorkbench } from "../evidence/RealEvidenceWorkbench";
import {
  ReviewControls,
  type ReviewStatus,
} from "../evidence/ReviewControls";
import {
  TranscriptTimeline,
  type TranscriptItem,
} from "../evidence/TranscriptTimeline";
import { VideoPlayer } from "../evidence/VideoPlayer";
import { UploadPanel } from "../upload/UploadPanel";
import { SupplementalTranslationUpload } from "../upload/SupplementalTranslationUpload";
import {
  TaskStatusPanel,
  type TaskPreviewState,
} from "../tasks/TaskStatusPanel";
import { SiteChrome } from "./SiteChrome";

const demoTranscript: TranscriptItem[] = [
  {
    id: "demo-1",
    startMs: 12_000,
    endMs: 18_000,
    speaker: "Teacher",
    originalText: "What evidence supports your answer?",
    translatedText: "什么证据可以支持你的答案？",
  },
  {
    id: "demo-2",
    startMs: 18_000,
    endMs: 23_000,
    speaker: "Class",
    originalText: "[Five seconds of classroom silence]",
    translatedText: "[课堂沉默五秒]",
  },
  {
    id: "demo-3",
    startMs: 23_000,
    endMs: 31_000,
    speaker: "Student",
    originalText: "The repeated phrase shows the character is uncertain.",
    translatedText: "反复出现的短语说明人物并不确定。",
  },
];

const UUID_PATTERN =
  /^[0-9a-f]{8}-[0-9a-f]{4}-[1-5][0-9a-f]{3}-[89ab][0-9a-f]{3}-[0-9a-f]{12}$/i;

type DialogueEntry = {
  role: "teacher" | "agent";
  content: string;
  modelName?: string;
  traceId?: string;
};

function linesFromEditor(value: string): string[] {
  return value
    .split(/\r?\n/)
    .map((item) => item.trim())
    .filter(Boolean);
}

export function ReviewTaskBaseline({
  resourceId,
  resourceKind = "unknown",
}: {
  resourceId: string;
  resourceKind?: "classroom" | "unknown";
}) {
  const router = useRouter();
  const [classroom, setClassroom] = useState("尚未创建课堂");
  const [teacherMessages, setTeacherMessages] = useState<string[]>([]);
  const [dialogueEntries, setDialogueEntries] = useState<DialogueEntry[]>([]);
  const [goal, setGoal] = useState("");
  const [contractDraft, setContractDraft] = useState<AnalysisContract | null>(null);
  const [clarificationNeeded, setClarificationNeeded] = useState(true);
  const [agentPending, setAgentPending] = useState(false);
  const [dialogueError, setDialogueError] = useState<{
    message: string;
    traceId?: string;
  } | null>(null);
  const [confirmed, setConfirmed] = useState(false);
  const [uploadOpen, setUploadOpen] = useState(false);
  const [hasVideo, setHasVideo] = useState(false);
  const [preview, setPreview] = useState<TaskPreviewState>("empty");
  const [currentVideoTimeMs, setCurrentVideoTimeMs] = useState(12_000);
  const [seekToMs, setSeekToMs] = useState(12_000);
  const [reviewStatus, setReviewStatus] =
    useState<ReviewStatus>("pending");
  const [reviewNote, setReviewNote] = useState("");
  const [realTask, setRealTask] = useState<TaskRead | null>(null);
  const [taskLoadError, setTaskLoadError] = useState<{
    message: string;
    traceId?: string;
    status?: number;
  } | null>(null);
  const [taskLookupPending, setTaskLookupPending] = useState(
    UUID_PATTERN.test(resourceId),
  );
  const [recoveringSession, setRecoveringSession] = useState(false);
  const [correctingContract, setCorrectingContract] = useState(false);
  const [contractCorrectionError, setContractCorrectionError] = useState("");
  const realClassroomId = realTask?.classroom_id ?? (UUID_PATTERN.test(resourceId) ? resourceId : "");
  const needsBilingualRecovery =
    realTask?.status === "failed" &&
    realTask.analysis_contract.bilingual_required &&
    ["BILINGUAL_EVIDENCE_INCOMPLETE", "TRANSLATION_SCHEMA_INVALID"].includes(
      realTask.last_error_code ?? "",
    );

  useEffect(() => setClassroom(sessionStorage.getItem("classroomName") || "演示课堂 · 尚未保存到后端"), []);
  const applyTask = useCallback((task: TaskRead) => {
    setRealTask(task);
    setTaskLoadError(null);
    setPreview(
      task.status === "succeeded"
        ? "ready"
        : task.status === "failed"
          ? "failure"
          : "processing",
    );
  }, []);
  const loadTask = useCallback(async () => {
    if (!UUID_PATTERN.test(resourceId)) return;
    setTaskLookupPending(true);
    setTaskLoadError(null);
    try {
      const isKnownClassroom =
        resourceKind === "classroom" ||
        sessionStorage.getItem("classroomId") === resourceId;
      if (isKnownClassroom) {
        const [latestTask] = await listTasksForClassroom(resourceId);
        if (latestTask) {
          applyTask(latestTask);
          router.replace(`/tasks/${latestTask.id}`);
        }
        return;
      }
      applyTask(await getTask(resourceId));
    } catch (error) {
      if (error instanceof ApiClientError && error.status !== 404) {
        setTaskLoadError({
          message: error.message,
          traceId: error.traceId,
          status: error.status,
        });
      } else if (!(error instanceof ApiClientError)) {
        setTaskLoadError({ message: "真实任务暂时无法读取，请确认前后端服务已启动。" });
      }
      // A UUID can also identify a newly created classroom, so a task 404 is
      // expected here and must not be presented as a broken task.
    } finally {
      setTaskLookupPending(false);
    }
  }, [applyTask, resourceId, resourceKind, router]);
  useEffect(() => {
    void loadTask();
  }, [loadTask]);
  useEffect(() => {
    if (!realTask || ["succeeded", "failed", "cancelled"].includes(realTask.status)) {
      return;
    }
    const timer = window.setInterval(() => {
      getTask(realTask.id)
        .then(setRealTask)
        .catch(() => undefined);
    }, 2_000);
    return () => {
      window.clearInterval(timer);
    };
  }, [realTask]);
  async function send(event: FormEvent) {
    event.preventDefault();
    const teacherMessage = goal.trim();
    if (!teacherMessage || agentPending || !clarificationNeeded) return;
    if (!UUID_PATTERN.test(realClassroomId)) {
      setDialogueError({ message: "请先创建真实课堂，再使用复盘 Agent 形成分析契约。" });
      return;
    }
    const nextTeacherMessages = [...teacherMessages, teacherMessage];
    setGoal("");
    setAgentPending(true);
    setDialogueError(null);
    try {
      const response: ReviewDialogueResponse = await clarifyReviewGoal(
        realClassroomId,
        nextTeacherMessages,
      );
      setTeacherMessages(nextTeacherMessages);
      setDialogueEntries((entries) => [
        ...entries,
        { role: "teacher", content: teacherMessage },
        {
          role: "agent",
          content: response.assistant_message,
          modelName: response.model_name,
          traceId: response.trace_id,
        },
      ]);
      setContractDraft(response.analysis_contract);
      setClarificationNeeded(response.clarification_needed);
      setConfirmed(false);
      setUploadOpen(false);
    } catch (error) {
      setGoal(teacherMessage);
      setDialogueError(
        error instanceof ApiClientError
          ? { message: error.message, traceId: error.traceId }
          : { message: "复盘 Agent 暂时无法连接，请稍后重试。" },
      );
    } finally {
      setAgentPending(false);
    }
  }
  function updateContractDraft(changes: Partial<AnalysisContract>) {
    setContractDraft((current) =>
      current ? { ...current, ...changes, confirmed: false } : current,
    );
    setConfirmed(false);
    setUploadOpen(false);
  }
  async function recoverTaskSession() {
    setRecoveringSession(true);
    setTaskLoadError(null);
    try {
      await startDemoSession();
      await loadTask();
    } catch (error) {
      setTaskLoadError(
        error instanceof ApiClientError
          ? { message: error.message, traceId: error.traceId, status: error.status }
          : { message: "安全演示会话暂时无法建立，请确认后端和数据库已启动。" },
      );
    } finally {
      setRecoveringSession(false);
    }
  }
  async function recreateAsChineseOnly(task: TaskRead) {
    setCorrectingContract(true);
    setContractCorrectionError("");
    try {
      const assets = await getTaskAssets(task.id);
      if (assets.length === 0) {
        throw new Error("原任务没有可复用的课堂资料。请联系管理员并提供 Trace ID。");
      }
      if (["pending", "queued", "running"].includes(task.status)) {
        await cancelTask(task.id);
      }
      const replacement = await createTask(
        task.classroom_id,
        assets.map((asset) => asset.id),
        {
          ...task.analysis_contract,
          bilingual_required: false,
          confirmed: true,
        },
      );
      applyTask(replacement);
      router.replace(`/tasks/${replacement.id}`);
    } catch (error) {
      setContractCorrectionError(
        error instanceof ApiClientError
          ? `${error.message}${error.traceId ? `（追踪编号：${error.traceId}）` : ""}`
          : error instanceof Error
            ? error.message
            : "契约修正失败，请稍后重试。",
      );
    } finally {
      setCorrectingContract(false);
    }
  }
  if (taskLookupPending) {
    return (
      <SiteChrome>
        <section className="real-evidence-state session-recovery-state" aria-live="polite">
          <span className="eyebrow">RESTORE TASK · 状态恢复</span>
          <strong>正在恢复真实课堂任务…</strong>
          <p>系统正在读取后端任务阶段和处理进度，不会要求重复上传课堂视频。</p>
        </section>
      </SiteChrome>
    );
  }
  if (taskLoadError) {
    const sessionExpired = taskLoadError.status === 401;
    return (
      <SiteChrome>
        <section className="real-evidence-state error session-recovery-state" role="alert">
          <span className="eyebrow">{sessionExpired ? "SESSION REQUIRED · 安全访问" : "TASK SERVICE · 任务读取"}</span>
          <strong>{sessionExpired ? "浏览器会话尚未建立" : "真实任务暂时无法读取"}</strong>
          <p>{sessionExpired ? "当前浏览器没有有效的演示会话。建立会话后，系统会自动重新读取这项真实复盘任务。" : taskLoadError.message}</p>
          {taskLoadError.traceId && <small>追踪编号：{taskLoadError.traceId}</small>}
          <button
            className="button primary"
            type="button"
            disabled={recoveringSession}
            onClick={() => void (sessionExpired ? recoverTaskSession() : loadTask())}
          >
            {recoveringSession ? "正在建立安全会话…" : sessionExpired ? "建立演示会话并重试" : "重新读取任务"}
          </button>
        </section>
      </SiteChrome>
    );
  }
  if (realTask) {
    return (
      <SiteChrome>
        <section className="view active" aria-labelledby="restored-task-title">
          <div className="workspace-shell">
            <header className="workspace-header" data-reveal>
              <div>
                <p className="eyebrow">REAL TASK · 步骤 3 / 3</p>
                <h1 id="restored-task-title">课堂资料已提交</h1>
                <p>页面已恢复真实任务状态；刷新或重新打开此地址都不会要求重复上传。</p>
              </div>
              <div className="classroom-context">
                <small>任务状态</small>
                <strong>{realTask.status === "succeeded" ? "待教师复核" : "后台处理中"}</strong>
              </div>
            </header>
            <TaskStatusPanel
              enabled
              state={preview}
              onStateChange={setPreview}
              task={realTask}
            />
            {needsBilingualRecovery && (
              <section className="contract-correction-card" role="note" aria-labelledby="bilingual-correction-title">
                <div>
                  <span className="eyebrow">BILINGUAL EVIDENCE · 契约提醒</span>
                  <h2 id="bilingual-correction-title">当前任务要求中英双语证据</h2>
                  <p>
                    仅当课堂包含英文或中英混合内容，并且需要保留英文原文与中文译文时开启。
                    纯中文课堂无需开启；缺少译文时系统会停止分析，不会伪造翻译或静默忽略要求。
                  </p>
                </div>
                <button
                  className="button secondary"
                  type="button"
                  disabled={correctingContract}
                  onClick={() => void recreateAsChineseOnly(realTask)}
                >
                  {correctingContract ? "正在复用资料并创建新任务…" : "本节为纯中文，关闭双语并重新处理"}
                </button>
                {realTask.status === "failed" && (
                  <SupplementalTranslationUpload
                    task={realTask}
                    onTaskCreated={(replacement) => {
                      applyTask(replacement);
                      router.replace(`/tasks/${replacement.id}`);
                    }}
                  />
                )}
                {contractCorrectionError && <p className="upload-error" role="alert">{contractCorrectionError}</p>}
              </section>
            )}
            {realTask.status === "succeeded" && <RealEvidenceWorkbench task={realTask} />}
          </div>
        </section>
      </SiteChrome>
    );
  }
  const latestAgentEntry = dialogueEntries.slice().reverse().find((entry) => entry.role === "agent");
  const contractReady = Boolean(
    contractDraft &&
      !clarificationNeeded &&
      contractDraft.goal.trim() &&
      contractDraft.focus_areas.length > 0 &&
      (contractDraft.scope === "full_lesson" ||
        ((contractDraft.end_ms ?? 0) > (contractDraft.start_ms ?? 0))),
  );
  return <SiteChrome><section className="view active" aria-labelledby="workspace-title"><div className="workspace-shell">
    <div className="workspace-header" data-reveal><div><p className="eyebrow">DEFINE THE REVIEW · 步骤 2 / 3</p><h1 id="workspace-title">说清这次想复盘什么</h1></div><div className="classroom-context"><small>当前课堂</small><strong>{classroom}</strong></div></div>
    <div className="workspace-grid"><section className="conversation-panel" data-reveal aria-label="与 Agent 对话"><div className="panel-heading"><div><span className="agent-avatar">A</span><span><strong>复盘 Agent</strong><small>真实本地模型 · 仅协助，不替代教师判断</small></span></div><span className="mock-pill backend-reachable">目标澄清</span></div>
      <div className="messages" aria-live="polite">
        <article className="message agent"><div className="message-label">系统引导</div><p>请用自然语言说明这次最想复盘的问题。发送后，本地模型会根据你的实际目标决定是否追问，并生成可修改的分析契约草案。</p></article>
        {dialogueEntries.map((entry, index) => <article className={`message ${entry.role}`} key={`${entry.role}-${index}`}><div className="message-label">{entry.role === "teacher" ? "教师" : "Agent"}</div><p>{entry.content}</p>{entry.role === "agent" && <small className="agent-response-meta">{entry.modelName} · Trace {entry.traceId}</small>}</article>)}
        {agentPending && <article className="message agent agent-thinking" role="status"><div className="message-label">Agent 正在理解</div><p>正在结合本课堂信息分析你的目标并生成结构化契约…</p></article>}
        {dialogueError && <article className="message agent dialogue-error" role="alert"><div className="message-label">智能服务未完成</div><p>{dialogueError.message}</p>{dialogueError.traceId && <small>Trace {dialogueError.traceId}</small>}</article>}
      </div>
      <form className="composer" onSubmit={send}><label htmlFor="goal-input" className="sr-only">复盘目标</label><textarea id="goal-input" rows={3} value={goal} disabled={agentPending || !clarificationNeeded} onChange={(event) => setGoal(event.target.value)} placeholder={!clarificationNeeded ? "分析契约草案已形成；请在右侧核对和修改。" : teacherMessages.length === 0 ? "例如：请重点分析我讲解算法时，概念顺序是否清楚……" : "请回答 Agent 刚才针对本节课提出的问题……"} /><div className="composer-footer"><button className="text-button" type="button" disabled={agentPending || !clarificationNeeded} onClick={() => setGoal(teacherMessages.length === 0 ? "请分析整节课堂中知识点的讲解顺序是否清楚，并为每条判断附上原文或课件证据。" : "分析整节课堂；优先保留课堂原文和课件页码，不需要中英双语。")}>使用示例回答</button><button className="button primary compact" type="submit" disabled={agentPending || !clarificationNeeded || !goal.trim()}>{agentPending ? "Agent 处理中…" : !clarificationNeeded ? "契约已形成" : teacherMessages.length === 0 ? "发送给 Agent" : "回答 Agent"}</button></div></form>
    </section>
    <aside className="contract-panel" data-reveal aria-labelledby="contract-title"><div className="panel-heading"><div><span className="contract-icon">✓</span><span><strong id="contract-title">分析契约</strong><small>模型生成草案，教师修改确认后才开始处理</small></span></div><span className={`status-badge ${confirmed ? "ready" : "pending"}`}>{confirmed ? "已确认" : contractDraft ? clarificationNeeded ? "待回答" : "待确认" : "待生成"}</span></div>
      {!contractDraft ? <div className="contract-empty"><span aria-hidden>✦</span><strong>尚未生成契约</strong><p>发送复盘目标后，真实本地模型会给出针对性回复与可编辑契约；模型不可用时这里不会伪造结果。</p></div> : <form className="contract-form">
        <label>复盘目标<textarea rows={3} value={contractDraft.goal} onChange={(event) => updateContractDraft({ goal: event.target.value })} /></label>
        <label>分析范围<select value={contractDraft.scope} onChange={(event) => updateContractDraft(event.target.value === "time_range" ? { scope: "time_range", start_ms: 0, end_ms: 60_000 } : { scope: "full_lesson", start_ms: null, end_ms: null })}><option value="full_lesson">整节课堂</option><option value="time_range">指定时间范围</option></select></label>
        {contractDraft.scope === "time_range" && <div className="contract-time-range"><label>开始（秒）<input type="number" min={0} value={Math.round((contractDraft.start_ms ?? 0) / 1000)} onChange={(event) => updateContractDraft({ start_ms: Math.max(0, Number(event.target.value) * 1000) })} /></label><label>结束（秒）<input type="number" min={1} value={Math.round((contractDraft.end_ms ?? 0) / 1000)} onChange={(event) => updateContractDraft({ end_ms: Math.max(0, Number(event.target.value) * 1000) })} /></label></div>}
        <label>关注维度<small>每行一项，可直接修改</small><textarea rows={4} value={contractDraft.focus_areas.join("\n")} onChange={(event) => updateContractDraft({ focus_areas: linesFromEditor(event.target.value) })} /></label>
        <label>判断标准<small>每行一项</small><textarea rows={3} value={contractDraft.judgment_criteria.join("\n")} onChange={(event) => updateContractDraft({ judgment_criteria: linesFromEditor(event.target.value) })} /></label>
        <label>证据要求<small>每行一项</small><textarea rows={3} value={contractDraft.evidence_requirements.join("\n")} onChange={(event) => updateContractDraft({ evidence_requirements: linesFromEditor(event.target.value) })} /></label>
        <label>课程领域<select value={contractDraft.course_domain} onChange={(event) => updateContractDraft({ course_domain: event.target.value as AnalysisContract["course_domain"] })}><option value="general">通用</option><option value="computer_ai">计算机 / 人工智能</option><option value="humanities">人文社科</option></select></label>
        <label className="permission-check compact-check bilingual-contract-choice"><input type="checkbox" checked={contractDraft.bilingual_required} onChange={(event) => updateContractDraft({ bilingual_required: event.target.checked })} /><span><strong>需要中英双语证据</strong><small>仅用于英文或中英混合课堂；纯中文课堂不要勾选。</small></span></label>
        <div className="contract-rule"><span>隐私与来源</span><strong>{confirmed ? "课堂内容仅路由到本机模型；教师已确认当前契约" : "课堂内容仅路由到本机模型；草案尚未经教师确认"}</strong></div>
        {latestAgentEntry && <div className="contract-provenance"><span>{latestAgentEntry.modelName}</span><span>clarification-v1</span><span>Trace {latestAgentEntry.traceId}</span></div>}
        {clarificationNeeded && <p className="contract-guidance">Agent 仍需一项关键信息。请先回答左侧追问，再确认契约。</p>}
        <label className="permission-check compact-check"><input type="checkbox" checked={confirmed} disabled={!contractReady} onChange={(event) => { setConfirmed(event.target.checked); if (!event.target.checked) setUploadOpen(false); }} /><span>我已核对并修改分析范围、证据条件和隐私边界</span></label>
        <button className="button primary wide" type="button" disabled={!confirmed || !contractReady} onClick={() => { setUploadOpen(true); setPreview("empty"); requestAnimationFrame(() => document.getElementById("upload-title")?.scrollIntoView({ behavior: "smooth", block: "center" })); }}>确认真实契约，进入资料上传</button>
      </form>}
    </aside></div>
    {uploadOpen && (
      <UploadPanel
          classroomId={realClassroomId}
          analysisContract={{ ...contractDraft!, confirmed: true }}
        onVideoReadinessChange={setHasVideo}
        onTaskCreated={(task) => {
          setRealTask(task);
          setPreview("processing");
          router.replace(`/tasks/${task.id}`);
        }}
      />
    )}
    <TaskStatusPanel
      enabled={uploadOpen && hasVideo}
      state={preview}
      onStateChange={setPreview}
      task={null}
    />
    {preview === "ready" && (
      <section
        className="evidence-workbench"
        aria-labelledby="evidence-workbench-title"
      >
        <header className="evidence-workbench-heading">
          <div>
            <span className="mock-pill">Mock 证据工作台</span>
            <h2 id="evidence-workbench-title">逐条核对证据，再决定是否进入报告</h2>
          </div>
          <p>以下内容全部是交互演示数据，不代表真实课堂处理已经完成。</p>
        </header>
        <div className="evidence-workbench-grid">
          <div className="evidence-media-column">
            <VideoPlayer
              seekToMs={seekToMs}
              onTimeUpdate={setCurrentVideoTimeMs}
            />
            <TranscriptTimeline
              items={demoTranscript}
              currentTimeMs={currentVideoTimeMs}
              onSeek={(timeMs) => {
                setSeekToMs(timeMs);
                setCurrentVideoTimeMs(timeMs);
              }}
            />
          </div>
          <div className="evidence-review-column">
            <EvidenceCard
              fact="教师提出证据追问后，课堂出现约五秒等待时间，随后学生给出文本依据。"
              judgment="该片段可作为“提问后留出思考时间”的候选证据，但仍需教师结合完整上下文判断。"
              suggestion="复核前后片段并确认时间边界；若上下文一致，可保留等待时间并继续追问证据。"
              sourceLabel="演示逐字稿 00:12–00:31"
              reviewStatus={reviewStatus}
              isDemo
              onSeekEvidence={() => {
                const evidenceStartMs = demoTranscript[0].startMs;
                setSeekToMs(evidenceStartMs);
                setCurrentVideoTimeMs(evidenceStartMs);
              }}
            />
            <ReviewControls
              status={reviewStatus}
              note={reviewNote}
              onStatusChange={(nextStatus) => {
                setReviewStatus(nextStatus);
                if (nextStatus === "accepted") {
                  setReviewNote("");
                }
              }}
              onNoteChange={setReviewNote}
            />
            {(reviewStatus === "accepted" || reviewStatus === "modified") && (
              <Link
                className="button primary wide"
                href="/reports/demo"
                aria-disabled={reviewStatus === "modified" && !reviewNote.trim()}
                onClick={(event) => {
                  if (reviewStatus === "modified" && !reviewNote.trim()) {
                    event.preventDefault();
                    return;
                  }
                  saveDemoReportDraft(reviewStatus, reviewNote);
                }}
              >
                查看报告编辑与预览
              </Link>
            )}
            {reviewStatus === "modified" && !reviewNote.trim() && (
              <p className="review-transfer-note" role="alert">
                请先填写教师修改说明，再将修改后的内容带入报告。
              </p>
            )}
          </div>
        </div>
      </section>
    )}
  </div></section></SiteChrome>;
}
