import assert from "node:assert/strict";
import { readFileSync } from "node:fs";
import { resolve } from "node:path";

const root = resolve(import.meta.dirname, "..");
const read = (path) => readFileSync(resolve(root, path), "utf8");

const config = read("next.config.ts");
const guard = read("src/lib/server/request-guard.ts");
const demo = read("src/app/api/session/demo/route.ts");
const team = read("src/app/api/team-access/route.ts");
const packageJson = JSON.parse(read("package.json"));
const ciWorkflow = read("../.github/workflows/ci.yml");

for (const header of [
  "Content-Security-Policy",
  "Referrer-Policy",
  "X-Content-Type-Options",
  "X-Frame-Options",
  "Permissions-Policy",
  "Strict-Transport-Security",
]) {
  assert.match(config, new RegExp(header), `生产前端必须声明 ${header}`);
}
assert.match(config, /output: "standalone"/, "部署镜像必须使用 Next standalone 输出");
assert.match(guard, /createHash\("sha256"\)/, "限流键不得保存客户端地址明文");
assert.match(guard, /MAX_TRACKED_KEYS/, "进程内限流表必须有内存上限");
assert.match(guard, /sec-fetch-site[\s\S]*cross-site/, "写接口必须拒绝跨站请求");
for (const route of [demo, team]) {
  assert.match(route, /consumeAttempt/, "公网身份入口必须限制尝试次数");
  assert.match(route, /status: 429/, "超过限制必须返回 429");
  assert.match(route, /Retry-After/, "429 必须告诉客户端何时重试");
}
assert.equal(
  packageJson.scripts["test:e2e:spec"],
  "playwright test --config playwright.config.ts --list",
  "普通 CI 只能收集真实 E2E 用例，不得在未启动完整服务时伪造验收",
);
assert.match(
  ciWorkflow,
  /Validate browser E2E test collection[\s\S]*npm run test:e2e:spec/,
  "CI 必须校验 E2E 用例可收集",
);
assert.doesNotMatch(
  ciWorkflow,
  /run:\s*npm run test:e2e:real/,
  "真实 E2E 必须连接运行中的完整系统，不应在普通 CI Runner 中无条件执行",
);

console.log("PRODUCTION_SECURITY_CONTRACT_OK");
