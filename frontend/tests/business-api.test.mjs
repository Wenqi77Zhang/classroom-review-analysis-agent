import assert from "node:assert/strict";
import { readFileSync } from "node:fs";
import { resolve } from "node:path";

const root = resolve(import.meta.dirname, "..");
const read = (path) => readFileSync(resolve(root, path), "utf8");

const sessionRoute = read("src/app/api/session/demo/route.ts");
const presignRoute = read(
  "src/app/api/classrooms/[classroomId]/uploads/presign/route.ts",
);
const assetRoute = read("src/app/api/assets/[assetId]/route.ts");
const downloadRoute = read(
  "src/app/api/assets/[assetId]/download-url/route.ts",
);
const transcriptRoute = read(
  "src/app/api/tasks/[taskId]/transcript/route.ts",
);
const transcriptSegmentRoute = read(
  "src/app/api/transcript-segments/[segmentId]/route.ts",
);
const serverBackend = read("src/lib/server/backend.ts");
const classroom = read("src/components/baseline/ClassroomBaseline.tsx");
const api = read("src/lib/api.ts");
const contracts = read("src/types/contracts.ts");

assert.match(sessionRoute, /httpOnly: true/, "JWT 必须保存在 HttpOnly Cookie");
assert.match(sessionRoute, /sameSite: "lax"/, "会话 Cookie 必须限制跨站发送");
assert.match(
  sessionRoute,
  /secure: process\.env\.NODE_ENV === "production"/,
  "生产环境 Cookie 必须启用 Secure",
);
assert.doesNotMatch(
  `${sessionRoute}\n${serverBackend}\n${api}`,
  /localStorage\.setItem|sessionStorage\.setItem\([^,]*(token|access)/i,
  "访问令牌不得进入浏览器存储",
);
assert.match(serverBackend, /Authorization: `Bearer \$\{token\}`/, "BFF 必须在服务端附加 Bearer 令牌");
assert.match(serverBackend, /cache: "no-store"/, "鉴权业务响应不得缓存");
assert.match(
  presignRoute,
  /\/uploads\/presign/,
  "干净检出必须包含预签名上传 BFF 路由",
);
assert.match(
  assetRoute,
  /export async function DELETE/,
  "删除素材 BFF 不得被播放地址读取覆盖",
);
assert.doesNotMatch(
  assetRoute,
  /export async function GET/,
  "素材根路由不得冒充下载地址路由",
);
assert.match(
  downloadRoute,
  /export async function GET/,
  "必须提供独立的下载地址 BFF 路由",
);
assert.match(
  downloadRoute,
  /\/download-url/,
  "下载地址 BFF 必须代理正确后端路径",
);
assert.match(
  transcriptRoute,
  /\/tasks\/.*\/transcript/,
  "必须提供任务逐字稿读取 BFF",
);
assert.match(
  transcriptSegmentRoute,
  /export async function PATCH/,
  "必须提供带 segmentId 的逐字稿编辑 BFF",
);
assert.match(
  api,
  /Promise<DownloadUrlResponse>/,
  "播放地址客户端必须使用完整响应类型",
);
assert.match(api, /Promise<TranscriptRead>/, "逐字稿读取不得返回 any");
assert.match(
  api,
  /input: TranscriptSegmentUpdate/,
  "逐字稿修改必须复用后端对齐契约",
);
assert.doesNotMatch(
  api,
  /original_text|translated_text/,
  "逐字稿字段不得偏离后端 text/translation 契约",
);
assert.match(
  contracts,
  /has_translation: boolean/,
  "逐字稿响应必须包含双语显示门禁",
);
assert.match(
  contracts,
  /translation_language: string \| null/,
  "逐字稿片段必须保留译文语言",
);
assert.match(
  serverBackend,
  /\[204, 205, 304\]\.includes\(response\.status\)/,
  "无内容响应不得被代理附加空字符串 body",
);
assert.match(
  serverBackend,
  /new Response\(null, \{ status: response\.status, headers \}\)/,
  "204/205/304 必须转发为真正的无 body 响应",
);
assert.match(classroom, /await startDemoSession\(\)/, "创建课堂前必须建立演示会话");
assert.match(classroom, /await createCourse\(courseName\)/, "必须创建真实课程");
assert.match(classroom, /await createClassroom\(course\.id/, "课堂必须绑定真实课程 ID");
assert.match(classroom, /sessionStorage\.setItem\("classroomId"/, "页面导航必须保存真实课堂 ID");
assert.match(classroom, /router\.push\(`\/tasks\/\$\{classroom\.id\}`\)/, "复盘页面 URL 必须携带真实课堂 ID");

console.log("BUSINESS_API_CONTRACT_OK");
