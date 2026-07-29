"use client";

import { useEffect, useState, type FormEvent } from "react";
import { VideoPlayer } from "@/components/evidence/VideoPlayer";
import { EvidenceCard } from "@/components/evidence/EvidenceCard";
import { ReviewControls } from "@/components/evidence/ReviewControls";
import { TranscriptTimeline } from "@/components/evidence/TranscriptTimeline";
import { UploadPanel } from "../upload/UploadPanel";
import { SiteChrome } from "./SiteChrome";

type PreviewState = "empty" | "processing" | "failure" | "ready";
const stateCopy: Record<PreviewState, [string, string, string]> = {
  empty: ["○", "尚未开始处理", "请先完成分析契约并上传课堂资料。"],
  processing: ["↻", "正在处理课堂资料", "真实版本将在这里显示上传、转写、翻译与分析状态。"],
  failure: ["!", "处理失败，可安全重试", "页面必须展示失败原因，不伪造完成结果。"],
  ready: ["✓", "待教师复核", "结论仍需逐条核对证据并由教师确认。"],
};

export function ReviewTaskBaseline() {
  const [classroom, setClassroom] = useState("尚未创建课堂");
  const [messages, setMessages] = useState<string[]>([]);
  const [goal, setGoal] = useState("");
  const [contract, setContract] = useState(false);
  const [confirmed, setConfirmed] = useState(false);
  const [uploadOpen, setUploadOpen] = useState(false);
  const [preview, setPreview] = useState<PreviewState>("empty");
  const [currentVideoTime, setCurrentVideoTime] = useState(0);

  useEffect(
    () =>
      setClassroom(
        sessionStorage.getItem("classroomName") || "演示课堂 · 尚未保存到后端"
      ),
    []
  );

  function send(event: FormEvent) {
    event.preventDefault();
    if (!goal.trim()) return;
    setMessages((list) => [...list, goal.trim()]);
    setGoal("");
    setContract(true);
  }

  const state = stateCopy[preview];

  return (
    <SiteChrome>
      <section className="view active" aria-labelledby="workspace-title">
        <div className="workspace-shell">
          <div className="workspace-header" data-reveal>
            <div>
              <p className="eyebrow">DEFINE THE REVIEW · 步骤 2 / 3</p>
              <h1 id="workspace-title">说清这次想复盘什么</h1>
            </div>
            <div className="classroom-context">
              <small>当前课堂</small>
              <strong>{classroom}</strong>
            </div>
          </div>

          <div className="workspace-grid">
            <section className="conversation-panel" data-reveal aria-label="与 Agent 对话">
              <div className="panel-heading">
                <div>
                  <span className="agent-avatar">A</span>
                  <span>
                    <strong>复盘 Agent</strong>
                    <small>仅协助，不替代教师判断</small>
                  </span>
                </div>
                <span className="mock-pill">Mock 对话</span>
              </div>

              <div className="messages" aria-live="polite">
                <article className="message agent">
                  <div className="message-label">Agent</div>
                  <p>请用自然语言说明这次最想复盘的问题。我会在开始处理前确认范围、证据条件和输出形式。</p>
                </article>

                {messages.map((message, index) => (
                  <article className="message teacher" key={`${message}-${index}`}>
                    <div className="message-label">教师</div>
                    <p>{message}</p>
                  </article>
                ))}

                {contract && (
                  <article className="message agent">
                    <div className="message-label">Agent</div>
                    <p>我已整理为右侧分析契约。请核对范围、证据条件和隐私边界后再确认。</p>
                  </article>
                )}
              </div>

              <form className="composer" onSubmit={send}>
                <label htmlFor="goal-input" className="sr-only">
                  复盘目标
                </label>
                <textarea
                  id="goal-input"
                  rows={3}
                  value={goal}
                  onChange={(event) => setGoal(event.target.value)}
                  placeholder="例如：请分析内容组织、讲解清晰度和提问后的等待时间……"
                />
                <div className="composer-footer">
                  <button
                    className="text-button"
                    type="button"
                    onClick={() =>
                      setGoal(
                        "请分析整节课堂的内容组织、讲解清晰度和提问后的等待时间，并为每条判断附上原文证据。"
                      )
                    }
                  >
                    使用示例目标
                  </button>
                  <button className="button primary compact" type="submit">
                    发送目标
                  </button>
                </div>
              </form>
            </section>

            <aside className="contract-panel" data-reveal aria-labelledby="contract-title">
              <div className="panel-heading">
                <div>
                  <span className="contract-icon">✓</span>
                  <span>
                    <strong id="contract-title">分析契约</strong>
                    <small>教师确认后才开始处理</small>
                  </span>
                </div>
                <span className={`status-badge ${confirmed ? "ready" : "pending"}`}>
                  {confirmed ? "已确认" : contract ? "待确认" : "待补充"}
                </span>
              </div>

              {!contract ? (
                <div className="contract-empty">
                  <span aria-hidden>✦</span>
                  <strong>尚未形成契约</strong>
                  <p>Agent 完成必要追问后，这里将展示可修改的分析范围与证据条件。</p>
                </div>
              ) : (
                <>
                  <form className="contract-form">
                    <label>
                      分析范围
                      <select>
                        <option>整节课堂</option>
                        <option>指定时间范围</option>
                      </select>
                    </label>
                    <fieldset>
                      <legend>关注维度</legend>
                      <label>
                        <input type="checkbox" defaultChecked /> 内容组织
                      </label>
                      <label>
                        <input type="checkbox" defaultChecked /> 讲解清晰度
                      </label>
                      <label>
                        <input type="checkbox" defaultChecked /> 提问等待时间
                      </label>
                    </fieldset>
                    <div className="contract-rule">
                      <span>证据条件</span>
                      <strong>每条判断必须连接视频时间或课堂原文</strong>
                    </div>
                    <div className="contract-rule">
                      <span>双语要求</span>
                      <strong>保留英文原文并提供逐句中文翻译</strong>
                    </div>
                    <label className="permission-check compact-check">
                      <input
                        type="checkbox"
                        checked={confirmed}
                        onChange={(event) => {
                          setConfirmed(event.target.checked);
                          if (!event.target.checked) setUploadOpen(false);
                        }}
                      />
                      <span>我已核对范围、证据条件和隐私边界</span>
                    </label>
                    <button
                      className="button primary wide"
                      type="button"
                      disabled={!confirmed}
                      onClick={() => {
                        setUploadOpen(true);
                        setPreview("empty");
                        requestAnimationFrame(() =>
                          document
                            .getElementById("upload-title")
                            ?.scrollIntoView({ behavior: "smooth", block: "center" })
                        );
                      }}
                    >
                      确认契约，进入资料上传
                    </button>
                  </form>

                  {/* ===== 证据区域 (已完美移入右侧) ===== */}
                  <div style={{ marginTop: '24px', padding: '0 20px 20px 20px' }}>
                    <EvidenceCard 
                      fact="教师提问后，课堂沉默了 5 秒，随后有 3 名学生举手回答。"
                      judgment="教师给予了充分的思考时间，属于高质量的提问策略。"
                      suggestion="建议在其他复杂问题上继续保持这种沉默等待的节奏。"
                    />

                    <div style={{ marginTop: '12px' }}>
                      <ReviewControls />
                    </div>

                    <div style={{ marginTop: '16px' }}>
                      <TranscriptTimeline 
                        currentTime={currentVideoTime}
                        onSeek={(time) => {
                          if (Math.abs(currentVideoTime - time) > 0.5) {
                            setCurrentVideoTime(time);
                          }
                        }}
                        items={[
                          { time: "00:05", speaker: "教师", text: "同学们，我们来看一下黑板上这道关于二次函数的题目。" },
                          { time: "00:15", speaker: "学生A", text: "老师，这里的顶点坐标是怎么求出来的？" },
                          { time: "00:25", speaker: "教师", text: "很好的问题，我们可以通过配方的方法来找到顶点。" },
                          { time: "00:35", speaker: "学生B", text: "哦！我明白了，原来系数不一样会导致开口方向不同。" }
                        ]} 
                      />
                    </div>

                    <div style={{ marginTop: '16px', borderTop: '1px solid #eee', paddingTop: '16px' }}>
                      <VideoPlayer 
                        videoUrl="/assets/test.mp4"
                        onTimeUpdate={(time) => setCurrentVideoTime(time)}
                        seekTo={currentVideoTime}
                      />
                    </div>
                  </div>
                  {/* ===== 证据区域结束 ===== */}
                </>
              )}
            </aside>
          </div>

          {uploadOpen && <UploadPanel />}
        </div>
      </section>
    </SiteChrome>
  );
}