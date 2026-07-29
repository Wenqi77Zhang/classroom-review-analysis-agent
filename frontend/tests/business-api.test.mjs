import assert from "node:assert/strict";
import { readFileSync } from "node:fs";
import { resolve } from "node:path";

const root = resolve(import.meta.dirname, "..");
const read = (path) => readFileSync(resolve(root, path), "utf8");

const sessionRoute = read("src/app/api/session/demo/route.ts");
const serverBackend = read("src/lib/server/backend.ts");
const classroom = read("src/components/baseline/ClassroomBaseline.tsx");
const api = read("src/lib/api.ts");

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
