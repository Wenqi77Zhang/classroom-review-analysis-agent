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

assert.match(route, /\/health/, "代理必须调用后端真实健康接口");
assert.match(route, /AbortSignal\.timeout/, "健康检查必须设置超时");
assert.match(route, /cache: "no-store"/, "健康状态不得被静态缓存");
assert.doesNotMatch(route, /error\.message|String\(error\)/, "不得向前端泄露内部连接错误");
assert.match(api, /BUSINESS_API_NOT_IMPLEMENTED = true/, "业务 API 未实现边界必须保留");
assert.match(contracts, /"video" \| "courseware" \| "transcript"/, "AssetKind 必须与后端一致");

console.log("BACKEND_HEALTH_CONTRACT_OK");
