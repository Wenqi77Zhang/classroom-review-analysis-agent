"use client";

export type TaskPreviewState = "empty" | "processing" | "failure" | "ready";

type TaskStatusPanelProps = {
  enabled: boolean;
  state: TaskPreviewState;
  onStateChange: (state: TaskPreviewState) => void;
};

const stages = [
  "资料上传",
  "音频抽取",
  "语音识别",
  "双语对齐",
  "证据分析",
] as const;

const stateCopy: Record<TaskPreviewState, { title: string; detail: string }> = {
  empty: {
    title: "尚未创建真实处理任务",
    detail: "请先确认分析契约并选择课堂视频；当前后端尚未提供任务创建接口。",
  },
  processing: {
    title: "本地预览：处理中",
    detail: "这些阶段仅用于检查界面，不代表后台正在处理，也不会自动增加进度。",
  },
  failure: {
    title: "本地预览：处理失败",
    detail: "示例原因：语音识别服务不可用。真实版本必须保存失败阶段、原因和重试次数。",
  },
  ready: {
    title: "本地预览：待教师复核",
    detail: "以下证据是演示数据；只有真实任务完成后才可进入教师复核。",
  },
};

export function TaskStatusPanel({
  enabled,
  state,
  onStateChange,
}: TaskStatusPanelProps) {
  const copy = stateCopy[state];
  const activeIndex =
    state === "empty"
      ? -1
      : state === "processing" || state === "failure"
        ? 2
        : stages.length - 1;

  return (
    <section className="task-status-panel" aria-labelledby="task-status-title">
      <header className="task-status-heading">
        <div>
          <span className="mock-pill">本地状态预览 · 非真实任务</span>
          <h2 id="task-status-title">课堂处理任务</h2>
          <p>
            {!enabled
              ? "先完成契约并选择课堂视频，才能查看任务状态预览。"
              : "后端任务 API 接通后，本面板才会读取真实阶段、错误和重试结果。"}
          </p>
        </div>
        <span className={`status-badge ${state}`}>{copy.title}</span>
      </header>

      <ol className="task-stage-list">
        {stages.map((stage, index) => {
          const status =
            state === "failure" && index === 2
              ? "failed"
              : index < activeIndex || state === "ready"
                ? "complete"
                : index === activeIndex
                  ? "active"
                  : "waiting";
          return (
            <li className={status} key={stage}>
              <span aria-hidden>
                {status === "complete"
                  ? "✓"
                  : status === "failed"
                    ? "!"
                    : status === "active"
                      ? "↻"
                      : "○"}
              </span>
              <strong>{stage}</strong>
              <small>
                {status === "complete"
                  ? "预览完成"
                  : status === "failed"
                    ? "预览失败"
                    : status === "active"
                      ? "预览处理中"
                      : "等待前序阶段"}
              </small>
            </li>
          );
        })}
      </ol>

      <div className={`task-status-summary ${state}`} role="status">
        <div>
          <strong>{copy.title}</strong>
          <p>{copy.detail}</p>
        </div>
        {state === "failure" && (
          <button
            className="button secondary compact"
            type="button"
            onClick={() => onStateChange("processing")}
          >
            预览安全重试
          </button>
        )}
      </div>

      <div className="task-preview-controls" aria-label="本地状态预览控制">
        {(
          [
            ["empty", "未创建"],
            ["processing", "处理中"],
            ["failure", "失败"],
            ["ready", "待复核"],
          ] as const
        ).map(([value, label]) => (
          <button
            type="button"
            key={value}
            className={state === value ? "active" : ""}
            aria-pressed={state === value}
            disabled={!enabled}
            onClick={() => enabled && onStateChange(value)}
          >
            {label}
          </button>
        ))}
      </div>
    </section>
  );
}
