import assert from "node:assert/strict";
import { readFileSync } from "node:fs";

const read = (path) => readFileSync(new URL(`../${path}`, import.meta.url), "utf8");

const hub = read("src/components/improvements/ImprovementHub.tsx");
const cycle = read("src/components/improvements/ImprovementCycleWorkspace.tsx");
const portfolio = read("src/components/portfolio/PortfolioDashboard.tsx");
const api = read("src/lib/api.ts");
const chrome = read("src/components/baseline/SiteChrome.tsx");

assert.match(hub, /历史合成验证仍单独标注，不进入教学成效汇总/);
assert.match(cycle, /系统不会自动认定教学效果/);
assert.match(cycle, /自我声明本身不是效果证明/);
assert.match(cycle, /第二轮是独立发生的再次授课/);
assert.match(cycle, /只有第一轮中经教师接受或修改确认的建议/);
assert.match(cycle, /生成证据对比/);
assert.match(cycle, /接受候选判断/);
assert.match(portfolio, /不是自动评分或全校管理平台/);
assert.match(portfolio, /个真实循环符合汇总门禁/);
assert.match(portfolio, /M3 教学效果门禁未满足/);
assert.match(portfolio, /门课程具备效果证据/);
assert.match(portfolio, /个循环符合汇总门禁/);
assert.doesNotMatch(portfolio, /真实或验证循环已闭环/);
assert.match(portfolio, /导出 Markdown/);
assert.match(api, /generateImprovementComparisons/);
assert.match(api, /reviewImprovementComparison/);
assert.match(chrome, /改进循环/);
assert.match(chrome, /课程总览/);

console.log("M2/M3 improvement and portfolio UI contracts passed.");
