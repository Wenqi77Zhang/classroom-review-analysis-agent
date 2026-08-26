import assert from "node:assert/strict";
import { readFileSync } from "node:fs";

const read = (path) => readFileSync(new URL(`../${path}`, import.meta.url), "utf8");

const hub = read("src/components/improvements/ImprovementHub.tsx");
const cycle = read("src/components/improvements/ImprovementCycleWorkspace.tsx");
const portfolio = read("src/components/portfolio/PortfolioDashboard.tsx");
const api = read("src/lib/api.ts");
const chrome = read("src/components/baseline/SiteChrome.tsx");

assert.match(hub, /合成轮次只验证系统机制，永不进入真实教学成效汇总/);
assert.match(cycle, /系统不会自动认定教学效果/);
assert.match(cycle, /只有第一轮中经教师接受或修改确认的建议/);
assert.match(cycle, /生成或重新生成证据对比/);
assert.match(cycle, /接受候选判断/);
assert.match(portfolio, /不是自动评分或全校管理平台/);
assert.match(portfolio, /导出 Markdown/);
assert.match(api, /generateImprovementComparisons/);
assert.match(api, /reviewImprovementComparison/);
assert.match(chrome, /改进循环/);
assert.match(chrome, /课程总览/);

console.log("M2/M3 improvement and portfolio UI contracts passed.");
