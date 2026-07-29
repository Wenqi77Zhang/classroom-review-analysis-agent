import assert from "node:assert/strict";
import { readFileSync, existsSync } from "node:fs";
import { resolve } from "node:path";
const root = resolve(import.meta.dirname, "..");
const required = [
  "src/app/globals.css",
  "src/components/baseline/SiteChrome.tsx",
  "src/components/baseline/HomeBaseline.tsx",
  "src/components/baseline/ClassroomBaseline.tsx",
  "src/components/baseline/ReviewTaskBaseline.tsx",
  "public/assets/mist-bamboo-glass-v2.png",
];
required.forEach((file) => assert.equal(existsSync(resolve(root, file)), true, `缺少 UI 基准文件：${file}`));
const css = readFileSync(resolve(root, "src/app/globals.css"), "utf8");
assert.match(css, /font-size:\s*15px/, "正文基准字号应不小于 15px");
assert.match(css, /small\s*\{[^}]*font-size:\s*13px/s, "最小辅助字号应不小于 13px");
assert.match(css, /mist-bamboo-glass-v2\.png/, "应使用已确认的 v2 竹影背景");
assert.match(
  css,
  /\[data-reveal\]\s*\{[^}]*opacity:\s*1/s,
  "核心内容在动画脚本执行前必须默认可见",
);
assert.match(
  css,
  /\.reveal-enabled\s+\[data-reveal\]\s*\{[^}]*opacity:\s*0/s,
  "只有确认支持动画后才能隐藏待显现内容",
);
const chrome = readFileSync(resolve(root, "src/components/baseline/SiteChrome.tsx"), "utf8");
assert.match(chrome, /未连接真实后端/, "Mock 能力必须明确标注");
assert.match(chrome, /prefers-reduced-motion:\s*reduce/, "应尊重用户的减少动态效果设置");
assert.match(chrome, /classList\.add\("reveal-enabled"\)/, "动画能力确认后才启用显现效果");
console.log("UI_BASELINE_V1_OK");
