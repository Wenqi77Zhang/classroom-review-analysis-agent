import assert from "node:assert/strict";
import { readFileSync } from "node:fs";
import { resolve } from "node:path";

const root = resolve(import.meta.dirname, "..");
const upload = readFileSync(
  resolve(root, "src/components/upload/UploadPanel.tsx"),
  "utf8",
);
const task = readFileSync(
  resolve(root, "src/components/baseline/ReviewTaskBaseline.tsx"),
  "utf8",
);

for (const extension of [
  ".mp4",
  ".mov",
  ".webm",
  ".mkv",
  ".pdf",
  ".ppt",
  ".pptx",
  ".txt",
  ".docx",
  ".srt",
  ".vtt",
]) {
  assert.ok(
    upload.includes(`"${extension}"`) || upload.includes(`'${extension}'`),
    `缺少支持格式：${extension}`,
  );
}

assert.match(upload, /4 \* 1024 \* 1024 \* 1024/, "视频限制应为 4 GiB");
assert.match(upload, /courseware: 128 \* 1024 \* 1024/, "课件限制应为 128 MiB");
assert.match(upload, /transcript: 32 \* 1024 \* 1024/, "逐字稿限制应为 32 MiB");
assert.doesNotMatch(upload, /type AssetKind =/, "上传类型必须复用冻结的共享契约");
assert.match(upload, /数据库与安全上传服务已就绪/, "真实依赖接通后应显示准确状态");
assert.match(upload, /后台在线，安全上传依赖暂不可用/, "依赖故障时应显示可恢复的降级状态");
assert.match(upload, /逐字稿不能替代视频/, "必须保留真实视频处理门禁");
assert.doesNotMatch(upload, /上传服务尚未接通/, "不得继续显示已经过期的禁用文案");
assert.match(upload, /presignUpload/, "必须先申请限时预签名地址");
assert.match(upload, /putPresignedUpload/, "文件必须直传对象存储");
assert.match(upload, /completeUpload/, "直传后必须由后端 HEAD 核验");
assert.match(upload, /createTask/, "全部文件核验后必须创建真实任务");
assert.match(upload, /deleteAsset/, "失败的预签名对象必须尽力清理");
assert.match(
  upload,
  /await deleteAsset\(asset\.assetId\)/,
  "移除已上传但未关联任务的文件时必须同步清理对象存储",
);
assert.match(
  upload,
  /taskCreated \|\|/,
  "任务创建成功后必须禁用重复创建入口",
);
assert.doesNotMatch(upload, /可选辅助材料/, "逐字稿用途文案应简洁显示为可选");
assert.match(upload, /支持 \{KIND_COPY\[kind\]\.formats\}/, "格式应独占一行");
assert.doesNotMatch(upload, /setInterval|setTimeout/, "上传进度必须来自 XHR progress，不得由计时器伪造");
assert.match(upload, /upload-panel is-visible/, "动态插入的上传区必须立即可见");
assert.match(task, /classroomId=\{realClassroomId\}/, "上传必须绑定真实课堂 ID");
assert.match(task, /onTaskCreated=\{\(task\) => \{/, "上传完成后必须把真实任务交给页面");

console.log("UPLOAD_PANEL_CONTRACT_OK");
