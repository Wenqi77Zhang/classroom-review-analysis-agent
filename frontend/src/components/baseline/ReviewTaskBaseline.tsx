"use client";

import { useEffect, useState, type FormEvent } from "react";
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
import { SiteChrome } from "./SiteChrome";

type PreviewState = "empty" | "processing" | "failure" | "ready";
const stateCopy: Record<PreviewState, [string,string,string]> = {
  empty: ["○", "尚未开始处理", "请先完成分析契约并上传课堂资料。"],
  processing: ["↻", "正在处理课堂资料", "真实版本将在这里显示上传、转写、翻译与分析状态。"],
  failure: ["!", "处理失败，可安全重试", "页面必须展示失败原因，不伪造完成结果。"],
  ready: ["✓", "待教师复核", "结论仍需逐条核对证据并由教师确认。"],
};

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

export function ReviewTaskBaseline() {
  const [classroom, setClassroom] = useState("尚未创建课堂");
  const [messages, setMessages] = useState<string[]>([]);
  const [goal, setGoal] = useState("");
  const [contract, setContract] = useState(false);
  const [confirmed, setConfirmed] = useState(false);
  const [uploadOpen, setUploadOpen] = useState(false);
  const [preview, setPreview] = useState<PreviewState>("empty");
  const [currentVideoTimeMs, setCurrentVideoTimeMs] = useState(12_000);
  const [seekToMs, setSeekToMs] = useState(12_000);
  const [reviewStatus, setReviewStatus] =
    useState<ReviewStatus>("pending");
  const [reviewNote, setReviewNote] = useState("");
  useEffect(() => setClassroom(sessionStorage.getItem("classroomName") || "演示课堂 · 尚未保存到后端"), []);
  function send(event: FormEvent) { event.preventDefault(); if (!goal.trim()) return; setMessages((list) => [...list, goal.trim()]); setGoal(""); setContract(true); }
  const state = stateCopy[preview];
  return <SiteChrome><section className="view active" aria-labelledby="workspace-title"><div className="workspace-shell">
    <div className="workspace-header" data-reveal><div><p className="eyebrow">DEFINE THE REVIEW · 步骤 2 / 3</p><h1 id="workspace-title">说清这次想复盘什么</h1></div><div className="classroom-context"><small>当前课堂</small><strong>{classroom}</strong></div></div>
    <div className="workspace-grid"><section className="conversation-panel" data-reveal aria-label="与 Agent 对话"><div className="panel-heading"><div><span className="agent-avatar">A</span><span><strong>复盘 Agent</strong><small>仅协助，不替代教师判断</small></span></div><span className="mock-pill">Mock 对话</span></div>
      <div className="messages" aria-live="polite"><article className="message agent"><div className="message-label">Agent</div><p>请用自然语言说明这次最想复盘的问题。我会在开始处理前确认范围、证据条件和输出形式。</p></article>{messages.map((message, index) => <article className="message teacher" key={`${message}-${index}`}><div className="message-label">教师</div><p>{message}</p></article>)}{contract && <article className="message agent"><div className="message-label">Agent</div><p>我已整理为右侧分析契约。请核对范围、证据条件和隐私边界后再确认。</p></article>}</div>
      <form className="composer" onSubmit={send}><label htmlFor="goal-input" className="sr-only">复盘目标</label><textarea id="goal-input" rows={3} value={goal} onChange={(event) => setGoal(event.target.value)} placeholder="例如：请分析内容组织、讲解清晰度和提问后的等待时间……" /><div className="composer-footer"><button className="text-button" type="button" onClick={() => setGoal("请分析整节课堂的内容组织、讲解清晰度和提问后的等待时间，并为每条判断附上原文证据。")}>使用示例目标</button><button className="button primary compact" type="submit">发送目标</button></div></form>
    </section>
    <aside className="contract-panel" data-reveal aria-labelledby="contract-title"><div className="panel-heading"><div><span className="contract-icon">✓</span><span><strong id="contract-title">分析契约</strong><small>教师确认后才开始处理</small></span></div><span className={`status-badge ${confirmed ? "ready" : "pending"}`}>{confirmed ? "已确认" : contract ? "待确认" : "待补充"}</span></div>
      {!contract ? <div className="contract-empty"><span aria-hidden>✦</span><strong>尚未形成契约</strong><p>Agent 完成必要追问后，这里将展示可修改的分析范围与证据条件。</p></div> : <form className="contract-form"><label>分析范围<select><option>整节课堂</option><option>指定时间范围</option></select></label><fieldset><legend>关注维度</legend><label><input type="checkbox" defaultChecked /> 内容组织</label><label><input type="checkbox" defaultChecked /> 讲解清晰度</label><label><input type="checkbox" defaultChecked /> 提问等待时间</label></fieldset><div className="contract-rule"><span>证据条件</span><strong>每条判断必须连接视频时间或课堂原文</strong></div><div className="contract-rule"><span>双语要求</span><strong>保留英文原文并提供逐句中文翻译</strong></div><label className="permission-check compact-check"><input type="checkbox" checked={confirmed} onChange={(event) => { setConfirmed(event.target.checked); if (!event.target.checked) setUploadOpen(false); }} /><span>我已核对范围、证据条件和隐私边界</span></label><button className="button primary wide" type="button" disabled={!confirmed} onClick={() => { setUploadOpen(true); setPreview("empty"); requestAnimationFrame(() => document.getElementById("upload-title")?.scrollIntoView({ behavior: "smooth", block: "center" })); }}>确认契约，进入资料上传</button></form>}
    </aside></div>
    {uploadOpen && <UploadPanel />}
    <section className="state-lab" data-reveal aria-labelledby="state-lab-title"><div><span className="mock-pill">原型控制台</span><h2 id="state-lab-title">人工查看关键状态</h2><p>状态由用户手动切换，不用计时器伪造真实处理进度。</p></div><div className="state-buttons">{(["empty","processing","failure","ready"] as PreviewState[]).map((item) => <button type="button" key={item} className={preview === item ? "active" : ""} onClick={() => setPreview(item)}>{{empty:"空状态",processing:"处理中",failure:"失败可重试",ready:"待教师复核"}[item]}</button>)}</div><div className={`state-preview ${preview}`}><span className="state-symbol">{state[0]}</span><div><strong>{state[1]}</strong><p>{state[2]}</p></div></div></section>
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
          </div>
        </div>
      </section>
    )}
  </div></section></SiteChrome>;
}
