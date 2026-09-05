import assert from "node:assert/strict";
import fs from "node:fs";
import test from "node:test";

const panel = fs.readFileSync(
  new URL("../src/components/tasks/TaskStatusPanel.tsx", import.meta.url),
  "utf8",
);
const workspace = fs.readFileSync(
  new URL("../src/components/baseline/ReviewTaskBaseline.tsx", import.meta.url),
  "utf8",
);

test("任务状态面板只接受真实后台任务", () => {
  assert.match(panel, /真实后台任务/);
  assert.match(panel, /状态来自后端任务记录/);
  assert.match(panel, /task: TaskRead/);
  assert.doesNotMatch(panel, /TaskPreviewState|本地预览|onStateChange/);
});

test("任务状态面板覆盖真实处理阶段", () => {
  for (const stage of [
    "资料上传",
    "音频抽取",
    "媒体分段",
    "语音识别",
    "双语对齐",
    "课件解析",
    "证据索引",
    "证据分析",
  ]) {
    assert.match(panel, new RegExp(stage));
  }
  assert.match(panel, /task\.status === "failed" && index === activeIndex/);
});

test("真实任务面板展示后端可回溯 trace_id", () => {
  assert.match(panel, /task\.trace_id/);
  assert.match(panel, /Trace ID：/);
});

test("真实任务面板提供与错误类型匹配的恢复建议并披露重试次数", () => {
  assert.match(panel, /补充 SRT\/VTT 中文译文后重试/);
  assert.match(panel, /不要重复上传/);
  assert.match(panel, /确认视频可正常播放且格式受支持/);
  assert.match(panel, /task\.retry_count/);
  assert.match(panel, /每次尝试均保留在审计链中/);
});

test("复盘流程只在真实任务成功后展示真实证据", () => {
  assert.match(
    workspace,
    /<TaskStatusPanel task=\{realTask\}/,
    "已创建任务必须向共享状态面板传入真实后端记录",
  );
  assert.match(workspace, /realTask\.status === "succeeded" && <RealEvidenceWorkbench/);
  assert.doesNotMatch(workspace, /preview === "ready"|Mock 证据工作台|task=\{null\}/);
});
