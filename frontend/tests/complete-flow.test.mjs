import assert from "node:assert/strict";
import fs from "node:fs";
import test from "node:test";

const read = (path) =>
  fs.readFileSync(new URL(`../${path}`, import.meta.url), "utf8");

const task = read("src/components/baseline/ReviewTaskBaseline.tsx");
const upload = read("src/components/upload/UploadPanel.tsx");
const status = read("src/components/tasks/TaskStatusPanel.tsx");
const report = read("src/components/reports/ReportEditor.tsx");
const draft = read("src/lib/demo-report-draft.ts");

test("分析契约经过一次明确追问后才形成", () => {
  assert.match(task, /Agent 追问/);
  assert.match(task, /setConversationStep\(1\)/);
  assert.match(task, /setConversationStep\(2\)/);
  assert.match(task, /setContract\(true\)/);
});

test("没有课堂视频时不能越过任务状态门禁", () => {
  assert.match(upload, /onVideoReadinessChange\?\.\(hasVideo\)/);
  assert.match(task, /enabled=\{uploadOpen && hasVideo\}/);
  assert.match(status, /disabled=\{!enabled\}/);
});

test("本地复核结果通过会话状态交接给报告且不冒充后端持久化", () => {
  assert.match(task, /saveDemoReportDraft\(reviewStatus, reviewNote\)/);
  assert.match(draft, /sessionStorage\.setItem/);
  assert.match(report, /loadDemoReportDraft\(\)/);
  assert.match(report, /尚未保存到服务器/);
});

test("修改结论缺少说明时不能进入报告", () => {
  assert.match(task, /reviewStatus === "modified" && !reviewNote\.trim\(\)/);
  assert.match(task, /请先填写教师修改说明/);
});
