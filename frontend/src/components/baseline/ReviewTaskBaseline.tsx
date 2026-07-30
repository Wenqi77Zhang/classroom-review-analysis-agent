"use client";

import Link from "next/link";
import { useEffect, useState, type FormEvent } from "react";
import { getTask } from "@/lib/api";
import { saveDemoReportDraft } from "@/lib/demo-report-draft";
import type { TaskRead } from "@/types/contracts";
import { EvidenceCard } from "../evidence/EvidenceCard";
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
import {
  TaskStatusPanel,
  type TaskPreviewState,
} from "../tasks/TaskStatusPanel";
import { SiteChrome } from "./SiteChrome";

const UUID_PATTERN =
  /^[0-9a-f]{8}-[0-9a-f]{4}-[1-5][0-9a-f]{3}-[89ab][0-9a-f]{3}-[0-9a-f]{12}$/i;

export function ReviewTaskBaseline({ classroomId }: { classroomId: string }) {
  // 1. 数据源置空，等待真实数据接口联调
  const [demoTranscript, setDemoTranscript] = useState<TranscriptItem[]>([]);
  
  // 2. 删除了 fetch("/assets/ai.json") 的危险数据加载

  const [classroom, setClassroom] = useState("尚未创建课堂");
  const [messages, setMessages] = useState<string[]>([]);
  const [conversationStep, setConversationStep] = useState<0 | 1 | 2>(0);
  const [goal, setGoal] = useState("");
  const [contract, setContract] = useState(false);
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
  const realClassroomId = UUID_PATTERN.test(classroomId) ? classroomId : "";

  useEffect(() => setClassroom(sessionStorage.getItem("classroomName") || "演示课堂 · 尚未保存到后端"), []);
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
  function send(event: FormEvent) {
    event.preventDefault();
    if (!goal.trim() || conversationStep === 2) return;
    setMessages((list) => [...list, goal.trim()]);
    setGoal("");
    if (conversationStep === 0) {
      setConversationStep(1);
    } else {
      setConversationStep(2);
      setContract(true);
    }
  }
  return <SiteChrome><section className="view active" aria-labelledby="workspace-title"><div className="workspace-shell">
    <div className="workspace-header" data-reveal><div><p className="eyebrow">DEFINE THE REVIEW · 步骤 2 / 3</p><h1 id="workspace-title">说清这次想复盘什么</h1></div><div className="classroom-context"><small>当前课堂</small><strong>{classroom}</strong></div></div>
    <div className="workspace-grid"><section className="conversation-panel" data-reveal aria-label="与 Agent 对话"><div className="panel-heading"><div><span className="agent-avatar">A</span><span><strong>复盘 Agent</strong><small>仅协助，不替代教师判断</small></span></div><span className="mock-pill">Mock 对话</span></div>
      <div className="messages" aria-live="polite"><article className="message agent"><div className="message-label">Agent</div><p>请用自然语言说明这次最想复盘的问题。我会在开始处理前确认范围、证据条件和输出形式。</p></article>{messages[0] && <article className="message teacher"><div className="message-label">教师</div><p>{messages[0]}</p></article>}{conversationStep >= 1 && <article className="message agent"><div className="message-label">Agent 追问</div><p>你希望分析整节课堂还是指定片段？哪些证据必须保留，是否需要中英双语？</p></article>}{messages[1] && <article className="message teacher"><div className="message-label">教师</div><p>{messages[1]}</p></article>}{contract && <article className="message agent"><div className="message-label">Agent</div><p>我已根据两轮输入整理为右侧分析契约。请核对范围、证据条件和隐私边界后再确认。</p></article>}</div>
      <form className="composer" onSubmit={send}><label htmlFor="goal-input" className="sr-only">复盘目标</label><textarea id="goal-input" rows={3} value={goal} disabled={conversationStep === 2} onChange={(event) => setGoal(event.target.value)} placeholder={conversationStep === 0 ? "例如：请分析内容组织、讲解清晰度和提问后的等待时间……" : conversationStep === 1 ? "例如：分析整节课堂，每条判断保留时间戳和中英原文……" : "分析契约已形成；如需修改，请重新开始本地演示。"} /><div className="composer-footer"><button className="text-button" type="button" disabled={conversationStep === 2} onClick={() => setGoal(conversationStep === 0 ? "请分析整节课堂的内容组织、讲解清晰度和提问后的等待时间，并为每条判断附上原文证据。" : "分析整节课堂；每条判断必须保留时间戳、课堂原文和中文翻译。")}>使用示例回答</button><button className="button primary compact" type="submit" disabled={conversationStep === 2}>{conversationStep === 0 ? "发送目标" : "回答追问"}</button></div></form>
    </section>
    <aside className="contract-panel" data-reveal aria-labelledby="contract-title"><div className="panel-heading"><div><span className="contract-icon">✓</span><span><strong id="contract-title">分析契约</strong><small>教师确认后才开始处理</small></span></div><span className={`status-badge ${confirmed ? "ready" : "pending"}`}>{confirmed ? "已确认" : contract ? "待确认" : "待补充"}</span></div>
      {!contract ? <div className="contract-empty"><span aria-hidden>✦</span><strong>尚未形成契约</strong><p>Agent 完成必要追问后，这里将展示可修改的分析范围与证据条件。</p></div> : <form className="contract-form"><label>分析范围<select><option>整节课堂</option><option>指定时间范围</option></select></label><fieldset><legend>关注维度</legend><label><input type="checkbox" defaultChecked /> 内容组织</label><label><input type="checkbox" defaultChecked /> 讲解清晰度</label><label><input type="checkbox" defaultChecked /> 提问等待时间</label></fieldset><div className="contract-rule"><span>证据条件</span><strong>每条判断必须连接视频时间或课堂原文</strong></div><div className="contract-rule"><span>双语要求</span><strong>保留英文原文并提供逐句中文翻译</strong></div><label className="permission-check compact-check"><input type="checkbox" checked={confirmed} onChange={(event) => { setConfirmed(event.target.checked); if (!event.target.checked) setUploadOpen(false); }} /><span>我已核对范围、证据条件和隐私边界</span></label><button className="button primary wide" type="button" disabled={!confirmed} onClick={() => { setUploadOpen(true); setPreview("empty"); requestAnimationFrame(() => document.getElementById("upload-title")?.scrollIntoView({ behavior: "smooth", block: "center" })); }}>确认契约，进入资料上传</button></form>}
    </aside></div>
    {uploadOpen && (
      <UploadPanel
        classroomId={realClassroomId}
        analysisContract={{
          scope: "full_class",
          focus: ["content_structure", "clarity", "wait_time"],
          bilingual: true,
          teacher_goal: messages[0] ?? "",
          teacher_constraints: messages[1] ?? "",
        }}
        onVideoReadinessChange={setHasVideo}
        onTaskCreated={(task) => {
          setRealTask(task);
          setPreview("processing");
        }}
      />
    )}
    <TaskStatusPanel
      enabled={uploadOpen && hasVideo}
      state={preview}
      onStateChange={setPreview}
      task={realTask}
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
            {/* 3. 视频路径暂时留空，等待真实 upload_url 接口 */}
            <VideoPlayer
              videoUrl=""
              seekToMs={seekToMs}
              onTimeUpdate={setCurrentVideoTimeMs}
            />
            {/* 4. 将 demoTranscript 作为占位，等待真实 getTranscript 接口数据 */}
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
            {/* 5. 删除了硬编码的固定事实、判断和建议文本，保留为属性占位 */}
            <EvidenceCard
              fact=""
              judgment=""
              suggestion=""
              sourceLabel=""
              reviewStatus={reviewStatus}
              isDemo
              onSeekEvidence={() => {
                // 暂不执行任何跳转，等待真实数据
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
            {/* 6. 暂时删除了“查看报告”的 Link，等待 PR #22 修复后使用真实跳转 */}
          </div>
        </div>
      </section>
    )}
  </div></section></SiteChrome>;
}