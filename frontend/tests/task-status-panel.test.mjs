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

test("任务状态面板明确区分本地预览和真实后台任务", () => {
  assert.match(panel, /本地状态预览 · 非真实任务/);
  assert.match(panel, /真实后台任务/);
  assert.match(panel, /状态来自后端任务记录/);
  assert.match(panel, /后端任务 API 接通后/);
  assert.match(panel, /不会自动增加进度/);
});

test("任务状态面板覆盖处理阶段、失败原因和安全重试", () => {
  for (const stage of [
    "资料上传",
    "音频抽取",
    "语音识别",
    "双语对齐",
    "证据分析",
  ]) {
    assert.match(panel, new RegExp(stage));
  }
  assert.match(panel, /示例原因：语音识别服务不可用/);
  assert.match(panel, /预览安全重试/);
  assert.match(
    panel,
    /state === "processing" \|\| state === "failure"\s*\? 2/,
    "语音识别失败时必须停在第三阶段，后续阶段保持等待",
  );
});

test("复盘流程使用共享任务状态面板并仅在待复核预览展示证据", () => {
  assert.match(
    workspace,
    /<TaskStatusPanel[\s\S]*enabled=\{uploadOpen && hasVideo\}[\s\S]*task=\{realTask\}/,
  );
  assert.match(workspace, /preview === "ready"/);
});
