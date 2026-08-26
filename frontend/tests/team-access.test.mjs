import assert from "node:assert/strict";
import { readFileSync } from "node:fs";
import { resolve } from "node:path";

const frontendRoot = resolve(import.meta.dirname, "..");
const repositoryRoot = resolve(frontendRoot, "..");
const readFrontend = (path) => readFileSync(resolve(frontendRoot, path), "utf8");

const helper = readFrontend("src/lib/server/team-access.ts");
const proxy = readFrontend("src/proxy.ts");
const route = readFrontend("src/app/api/team-access/route.ts");
const guard = readFrontend("src/lib/server/request-guard.ts");
const page = readFrontend("src/app/team-access/page.tsx");
const script = readFileSync(
  resolve(repositoryRoot, "scripts/start-team-tunnel.ps1"),
  "utf8",
);
const corsScript = readFileSync(
  resolve(repositoryRoot, "scripts/configure-team-tunnel-cors.py"),
  "utf8",
);

assert.match(
  proxy,
  /if \(!expectedAccessCode \|\| PUBLIC_PATHS\.has/,
  "未配置访问码时，本地开发必须保持可用",
);
assert.match(proxy, /pathname\.startsWith\("\/api\/"\)/, "未授权 API 不得重定向为 HTML");
assert.match(proxy, /status: 401/, "未授权 API 必须返回 401");
assert.match(proxy, /NextResponse\.redirect/, "未授权页面必须进入访问码页面");
assert.match(proxy, /"\/team-access", "\/api\/team-access"/, "验证页面与接口必须可公开访问");
assert.match(helper, /createHash\("sha256"\)/, "Cookie 不得保存访问码明文");
assert.match(helper, /timingSafeEqual/, "访问码和 Cookie 比较必须使用恒定时间比较");
assert.match(route, /httpOnly: true/, "访问会话 Cookie 必须为 HttpOnly");
assert.match(route, /sameSite: "strict"/, "访问会话 Cookie 必须阻止跨站发送");
assert.match(
  route,
  /secure: true/,
  "联调入口必须始终使用 Secure Cookie",
);
assert.match(route, /"Cache-Control": "no-store"/, "验证响应不得缓存");
assert.match(
  guard,
  /sec-fetch-site[\s\S]*cross-site[\s\S]*x-forwarded-host[\s\S]*new URL\(origin\)\.host === requestHost/,
  "反向代理后的来源校验必须拒绝跨站请求并核对外部主机名",
);
assert.match(route, /consumeAttempt/, "访问码入口必须启用失败尝试限流");
assert.match(
  route,
  /TEAM_TUNNEL_INSTANCE_ID[\s\S]*\{ enabled: true, instanceId \}/,
  "本地预检必须能核对脚本启动的唯一前端实例",
);
assert.doesNotMatch(
  `${route}\n${page}`,
  /localStorage|sessionStorage/,
  "访问码或访问会话不得写入浏览器存储",
);
assert.match(page, /value\.startsWith\("\/\/"\)/, "返回路径必须拦截协议相对开放重定向");
assert.match(page, /未经授权的信息/, "联调入口必须显示隐私提醒");
assert.match(
  script,
  /RandomNumberGenerator\]::Fill/,
  "启动脚本必须使用密码学安全随机数生成访问码",
);
assert.match(
  script,
  /if \(\$PreflightOnly\)[\s\S]*未创建公网入口/,
  "启动脚本必须支持不创建公网入口的本地预检",
);
assert.match(
  script,
  /TcpListener[\s\S]*LocalEndpoint[\s\S]*nextCli[\s\S]*"-H", "127\.0\.0\.1"/,
  "脚本必须为自己启动的前端选择独立本地端口",
);
assert.match(
  script,
  /TEAM_TUNNEL_INSTANCE_ID[\s\S]*\/api\/team-access[\s\S]*probe\.instanceId -eq \$instanceId/,
  "创建隧道前必须验证目标是脚本刚启动的门禁前端",
);
assert.match(
  script,
  /Start-Process[\s\S]*\$cloudflaredPath[\s\S]*-UseNewEnvironment/,
  "cloudflared 必须在干净环境中启动，避免继承并打印访问码或其他进程秘密",
);
assert.doesNotMatch(
  script,
  /cloudflared.+(?:localhost|127\.0\.0\.1):8000/i,
  "后端端口不得直接暴露到 Quick Tunnel",
);
assert.match(corsScript, /hostname\.endswith\("\.trycloudflare\.com"\)/, "B2 CORS 只允许 Quick Tunnel HTTPS 来源");
assert.match(corsScript, /def is_team_tunnel_rule[\s\S]*"PUT" in rule\.get/, "B2 不保留规则 ID 时仍须精确识别临时规则");
assert.match(corsScript, /other_rules[\s\S]*\[\*other_rules, staging_rule\]/, "更新临时 CORS 时必须保留已有规则");
assert.match(corsScript, /AllowedOrigins": \[origin\]/, "B2 CORS 必须使用本次精确来源");
assert.match(corsScript, /Access-Control-Request-Method": "PUT"[\s\S]*B2_CORS_PREFLIGHT_OK/, "必须支持不上传对象的真实浏览器 CORS 预检");
assert.doesNotMatch(corsScript, /print\([^)]*signed_url/, "日志不得输出 B2 预签名 URL");
assert.match(corsScript, /delete_bucket_cors|CORSRules": other_rules/, "临时入口关闭后必须支持移除专用规则");

console.log("TEAM_TUNNEL_ACCESS_GATE_OK");
