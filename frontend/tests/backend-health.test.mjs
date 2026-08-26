import assert from "node:assert/strict";
import { readFileSync } from "node:fs";
import { resolve } from "node:path";

const root = resolve(import.meta.dirname, "..");
const route = readFileSync(
  resolve(root, "src/app/api/backend-health/route.ts"),
  "utf8",
);
const api = readFileSync(resolve(root, "src/lib/api.ts"), "utf8");
const contracts = readFileSync(
  resolve(root, "src/types/contracts.ts"),
  "utf8",
);

assert.match(route, /\/health\/ready/, "代理必须验证数据库与对象存储均真实就绪");
assert.match(route, /`\$\{backendUrl\}\/health`/, "代理必须先用快速存活检查区分进程故障与依赖降级");
assert.match(route, /response\.ok && payload\.status === "ready"/, "依赖未就绪时不得开放上传入口");
assert.match(route, /reachable: true/, "后端在线但依赖故障时仍应允许产品打开并展示降级状态");
assert.match(route, /AbortSignal\.timeout/, "健康检查必须设置超时");
assert.match(route, /cache: "no-store"/, "健康状态不得被静态缓存");
assert.doesNotMatch(route, /error\.message|String\(error\)/, "不得向前端泄露内部连接错误");
assert.doesNotMatch(api, /BUSINESS_API_NOT_IMPLEMENTED/, "业务 API 已接通后不得保留旧禁用开关");
assert.match(api, /\/api\/session\/demo/, "前端必须通过同源会话代理建立演示身份");
assert.match(api, /\/uploads\/presign/, "前端必须调用预签名上传接口");
assert.match(api, /completeUpload/, "对象直传后必须调用后端完成核验");
assert.match(contracts, /"video" \| "courseware" \| "transcript"/, "AssetKind 必须与后端一致");

console.log("BACKEND_HEALTH_CONTRACT_OK");
