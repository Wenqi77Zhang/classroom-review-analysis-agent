import assert from "node:assert/strict";
import fs from "node:fs";
import test from "node:test";

const read = path => fs.readFileSync(new URL(`../${path}`, import.meta.url), "utf8");
const editor = read("src/components/reports/RealReportEditor.tsx");
const route = read("src/app/reports/[reportId]/page.tsx");

// These are wiring checks; database and browser checks verify real behavior separately.
test("报告直接使用真实资源入口及统一编辑器", () => {
  assert.match(route, /UUID_PATTERN\.test\(reportId\)/);
  assert.match(route, /<RealReportEditor/);
  assert.doesNotMatch(editor, /demoConclusions|startDemoSession|sessionStorage|localStorage/);
});
test("正文修改提交旧版本并保留人工复核门禁", () => {
  assert.match(editor, /saved.conclusions/);
  assert.match(editor, /conclusion_edits:/);
  assert.match(editor, /previous_content:/);
  assert.match(editor, /error.status === 409/);
  assert.match(editor, /dirty \|\| saving/);
});
test("导出使用后端三格式文件且登录恢复不切换身份", () => {
  assert.match(editor, /createReportExport\(report.id, format\)/);
  assert.match(editor, /markdown: "Markdown"/);
  assert.match(editor, /html: "HTML"/);
  assert.match(editor, /pdf: "PDF"/);
  assert.match(editor, /redirectToLogin/);
  assert.match(editor, /rel="noopener noreferrer"/);
});
