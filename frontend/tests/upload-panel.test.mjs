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
assert.match(upload, /后端基础服务可达 · 上传接口待实现/, "健康检查不得冒充上传接口");
assert.match(upload, /逐字稿不能替代视频/, "必须保留真实视频处理门禁");
assert.match(upload, /上传服务尚未接通/, "后端未接通时必须明确标注");
assert.doesNotMatch(upload, /可选辅助材料/, "逐字稿用途文案应简洁显示为可选");
assert.match(upload, /支持 \{KIND_COPY\[kind\]\.formats\}/, "格式应独占一行");
assert.doesNotMatch(upload, /setInterval|setTimeout/, "不得伪造上传进度");
assert.match(upload, /upload-panel is-visible/, "动态插入的上传区必须立即可见");
assert.match(task, /<UploadPanel \/>/, "确认分析契约后应展示上传入口");

console.log("UPLOAD_PANEL_CONTRACT_OK");
