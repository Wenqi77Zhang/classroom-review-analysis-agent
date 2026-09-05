"use client";

import type { TaskRead, TaskStage } from "@/types/contracts";

type TaskStatusPanelProps = {
  task: TaskRead;
};

const realStages: Array<{ value: TaskStage; label: string }> = [
  { value: "uploaded", label: "资料上传" },
  { value: "extract_audio", label: "音频抽取" },
  { value: "segment", label: "媒体分段" },
  { value: "transcribe", label: "语音识别" },
  { value: "translate", label: "双语对齐" },
  { value: "parse_courseware", label: "课件解析" },
  { value: "build_evidence_index", label: "证据索引" },
  { value: "analyze", label: "证据分析" },
];

const realStatusCopy: Record<TaskRead["status"], string> = {
  pending: "待入队",
  queued: "等待 Worker",
  running: "处理中",
  succeeded: "处理完成",
  failed: "处理失败",
  cancelled: "已取消",
};

function getNextAction(task: TaskRead): string {
  if (task.status === "succeeded") {
    return "下一步：进入证据工作台，逐条核对原文、画面和课件页，再决定是否进入报告。";
  }
  if (task.status === "cancelled") {
    return "下一步：返回资料区检查分析范围与输入文件，再创建一个新任务；已取消任务不会被静默恢复。";
  }
  if (task.status !== "failed") {
    return task.status === "queued"
      ? "系统正在等待媒体 Worker 领取任务；页面会自动同步真实状态，无需重复上传。"
      : "系统正在处理当前阶段；可以保留此页面，任务 ID 与 Trace ID 可用于故障追踪。";
  }

  const code = (task.last_error_code ?? "").toUpperCase();
  if (code.includes("TRANSLATION") || code.includes("BILINGUAL")) {
    return "恢复建议：若课堂含英文，请补充 SRT/VTT 中文译文后重试；若实际为纯中文，请关闭双语要求后重新处理。";
  }
  if (code.includes("OBJECT_STORAGE") || code.includes("UPLOAD")) {
    return "恢复建议：不要重复上传。先检查网络与对象存储授权，再使用原资料重新创建任务。";
  }
  if (code.includes("TRANSCRIBE") || code.includes("MEDIA") || code.includes("FFMPEG")) {
    return "恢复建议：确认视频可正常播放且格式受支持，再使用原资料重试；失败仍会保留 Trace ID。";
  }
  return "恢复建议：保留任务 ID 与 Trace ID，检查下方原始错误后重试；系统不会把失败任务伪装成完成。";
}

export function TaskStatusPanel({ task }: TaskStatusPanelProps) {
  const activeIndex = realStages.findIndex((stage) => stage.value === task.stage);
  const nextAction = getNextAction(task);

  return (
    <section className="task-status-panel" aria-labelledby="task-status-title">
      <header className="task-status-heading">
        <div>
          <span className="status-pill backend-reachable">真实后台任务</span>
          <h2 id="task-status-title">课堂处理任务</h2>
          <p>
            状态来自后端任务记录，不使用前端计时器伪造进度。任务 ID：
            <code>{task.id}</code>
          </p>
          {task.trace_id && (
            <p>
              Trace ID：<code>{task.trace_id}</code>
            </p>
          )}
        </div>
        <span className={`status-badge ${task.status}`}>
          {realStatusCopy[task.status]}
        </span>
      </header>

      <ol className="task-stage-list">
        {realStages.map((stage, index) => {
          const stageState =
            task.status === "failed" && index === activeIndex
              ? "failed"
              : task.status === "succeeded" || index < activeIndex
                ? "complete"
                : index === activeIndex
                  ? "active"
                  : "waiting";
          return (
            <li className={stageState} key={stage.value}>
              <span aria-hidden>
                {stageState === "complete"
                  ? "✓"
                  : stageState === "failed"
                    ? "!"
                    : stageState === "active"
                      ? "↻"
                      : "○"}
              </span>
              <strong>{stage.label}</strong>
              <small>
                {stageState === "active"
                  ? `${Math.round(task.progress * 100)}%`
                  : stageState === "complete"
                    ? "完成"
                    : stageState === "failed"
                      ? "失败"
                      : "等待"}
              </small>
            </li>
          );
        })}
      </ol>

      <div
        className={`task-status-summary ${
          task.status === "failed" ? "failure" : "processing"
        }`}
        role="status"
      >
        <div>
          <strong>{realStatusCopy[task.status]}</strong>
          <p>
            {task.last_error_message ??
              `当前阶段：${task.stage}；真实进度 ${Math.round(task.progress * 100)}%。`}
          </p>
          <p className="task-next-action">{nextAction}</p>
          {task.retry_count > 0 && (
            <small>已记录重试 {task.retry_count} 次；每次尝试均保留在审计链中。</small>
          )}
        </div>
      </div>
    </section>
  );
}
