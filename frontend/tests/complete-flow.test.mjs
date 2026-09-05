import assert from "node:assert/strict";
import fs from "node:fs";
import test from "node:test";

const read = (path) =>
  fs.readFileSync(new URL(`../${path}`, import.meta.url), "utf8");

const task = read("src/components/baseline/ReviewTaskBaseline.tsx");
const upload = read("src/components/upload/UploadPanel.tsx");
const supplementalUpload = read(
  "src/components/upload/SupplementalTranslationUpload.tsx",
);
const status = read("src/components/tasks/TaskStatusPanel.tsx");

test("分析契约由真实复盘 Agent 按需追问后形成", () => {
  assert.match(task, /await clarifyReviewGoal\(/);
  assert.match(task, /response\.assistant_message/);
  assert.match(task, /setContractDraft\(response\.analysis_contract\)/);
  assert.match(task, /setClarificationNeeded\(response\.clarification_needed\)/);
  assert.doesNotMatch(task, /setConversationStep|setContract\(true\)/);
});

test("没有课堂视频时不能越过任务状态门禁", () => {
  assert.match(upload, /onVideoReadinessChange\?\.\(hasVideo\)/);
  assert.match(upload, /if \(!hasVideo \|\| !classroomId \|\| backendHealth !== "reachable"\) return/);
  assert.match(upload, /!hasVideo/);
  assert.match(task, /任务创建前不会展示模拟进度或分析结果/);
});

test("真实课堂、上传和任务链路使用后端资源 ID", () => {
  assert.match(task, /UUID_PATTERN\.test\(resourceId\)/);
  assert.match(task, /getTask\(resourceId\)/);
  assert.match(task, /listTasksForClassroom\(resourceId\)/);
  assert.match(task, /resourceKind === "classroom"/);
  assert.match(task, /classroomId=\{realClassroomId\}/);
  assert.match(upload, /completedAssetIds/);
  assert.match(upload, /createTask\(/);
  assert.match(status, /task\.id/);
  assert.match(status, /task\.progress/);
});

test("任务提交使用后端与 Agent 共用的已确认分析契约", () => {
  assert.match(task, /setContractDraft\(response\.analysis_contract\)/);
  assert.match(task, /updateContractDraft\(changes: Partial<AnalysisContract>\)/);
  assert.match(task, /analysisContract=\{\{ \.\.\.contractDraft!, confirmed: true \}\}/);
  assert.match(task, /contractDraft\.focus_areas\.length > 0/);
  assert.match(task, /课堂内容仅路由到本机模型/);
  assert.doesNotMatch(task, /teacher_goal:/);
  assert.doesNotMatch(task, /scope: "full_class"/);
});

test("普通任务入口不再包含本地状态、证据或报告模拟链路", () => {
  assert.doesNotMatch(task, /Mock 证据工作台|demoTranscript|saveDemoReportDraft/);
  assert.doesNotMatch(status, /本地状态预览|预览安全重试|TaskPreviewState/);
});

test("真实任务会话缺失时可自助恢复而不暴露令牌", () => {
  assert.match(task, /ApiClientError/);
  assert.match(task, /taskLoadError\.status === 401/);
  assert.match(task, /await startDemoSession\(\)/);
  assert.match(task, /await loadTask\(\)/);
  assert.match(task, /建立演示会话并重试/);
  assert.doesNotMatch(task, /document\.cookie|localStorage/);
});

test("上传创建任务并切换 URL 后恢复真实进度而不是回到上传步骤", () => {
  assert.match(task, /setTaskLookupPending\(true\)/);
  assert.match(task, /applyTask\(await getTask\(resourceId\)\)/);
  assert.match(task, /router\.replace\(`\/tasks\/\$\{latestTask\.id\}`\)/);
  assert.match(task, /if \(realTask\)/);
  assert.match(task, /<TaskStatusPanel[\s\S]*task=\{realTask\}/);
  assert.match(task, /课堂资料已提交/);
  assert.match(task, /不会要求重复上传/);
});

test("双语要求必须显式选择且选错后可复用原资料修正", () => {
  assert.match(task, /需要中英双语证据/);
  assert.match(task, /纯中文课堂不要勾选/);
  assert.match(task, /updateContractDraft\(\{ bilingual_required: event\.target\.checked \}\)/);
  assert.doesNotMatch(task, /\/双语\|翻译\|英文原文\//);
  assert.match(task, /await getTaskAssets\(task\.id\)/);
  assert.match(task, /await cancelTask\(task\.id\)/);
  assert.match(task, /bilingual_required: false/);
  assert.match(task, /本节为纯中文，关闭双语并重新处理/);
});

test("非纯中文课堂可补充带时间轴译文并复用原视频重建任务", () => {
  assert.match(task, /<SupplementalTranslationUpload/);
  assert.match(task, /realTask\.status === "failed"/);
  assert.match(supplementalUpload, /accept="\.srt,\.vtt/);
  assert.match(supplementalUpload, /kind: "transcript"/);
  assert.match(supplementalUpload, /await putPresignedUpload/);
  assert.match(supplementalUpload, /await completeUpload/);
  assert.match(supplementalUpload, /asset\.kind !== "transcript"/);
  assert.match(supplementalUpload, /asset\.kind === "video"/);
  assert.match(supplementalUpload, /bilingual_required: true/);
  assert.match(supplementalUpload, /系统会继续以原视频 ASR 原文为主证据/);
  assert.doesNotMatch(supplementalUpload, /localStorage|document\.cookie/);
});
