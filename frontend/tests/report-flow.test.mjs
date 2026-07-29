import assert from "node:assert/strict";
import fs from "node:fs";
import test from "node:test";

const editor = fs.readFileSync(
  new URL("../src/components/reports/ReportEditor.tsx", import.meta.url),
  "utf8",
);
const reportPage = fs.readFileSync(
  new URL("../src/app/reports/[reportId]/page.tsx", import.meta.url),
  "utf8",
);
const css = fs.readFileSync(
  new URL("../src/app/globals.css", import.meta.url),
  "utf8",
);

test("报告门禁只允许已接受或已修改内容", () => {
  assert.match(editor, /allowedStatuses.*accepted.*modified/s);
  assert.match(editor, /filter\(\(item\) => allowedStatuses\.has\(item\.status\)\)/);
  assert.match(editor, /自动排除/);
});

test("报告页面支持本地编辑、预览和真实浏览器打印", () => {
  assert.match(editor, /"edit" \| "preview"/);
  assert.match(editor, /window\.print\(\)/);
  assert.match(editor, /if \(!printRequested \|\| mode !== "preview"\) return;/);
  assert.match(editor, /setPrintRequested\(true\);\s*setMode\("preview"\)/);
  assert.match(editor, /内置浏览器可能会禁用打印弹窗/);
  assert.match(editor, /Ctrl\+P/);
  assert.match(editor, /另存为 PDF/);
  assert.match(editor, /DOCX 导出等待后端/);
});

test("打印版只保留报告正文", () => {
  assert.match(
    css,
    /@media print[\s\S]*\.prototype-banner,[\s\S]*\.site-header,[\s\S]*\.report-transfer-warning,[\s\S]*\.report-transfer-ok,[\s\S]*\.report-print-fallback,[\s\S]*\.report-export-bar/,
  );
  assert.doesNotMatch(css, /@media print[\s\S]*\.site-nav,/);
});

test("报告页面明确演示数据和未持久化边界", () => {
  assert.match(editor, /本地演示草稿 · 未保存到后端/);
  assert.match(editor, /不代表真实课堂分析/);
  assert.match(reportPage, /<ReportEditor \/>/);
});
