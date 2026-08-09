import assert from "node:assert/strict";
import fs from "node:fs";
import test from "node:test";

const editor = fs.readFileSync(
  new URL("../src/components/reports/ReportEditor.tsx", import.meta.url),
  "utf8",
);
const realEditor = fs.readFileSync(
  new URL("../src/components/reports/RealReportEditor.tsx", import.meta.url),
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
  assert.match(editor, /classroomId !== "demo"/);
  assert.match(reportPage, /<ReportEditor classroomId=\{reportId\} \/>/);
});

test("真实报告首次读取、404 创建与标题保存均通过后端", () => {
  assert.match(realEditor, /await getReport\(classroomId\)/);
  assert.match(realEditor, /loadError\.status !== 404/);
  assert.match(realEditor, /updateReport\(classroomId, \{ title: "课堂复盘报告" \}\)/);
  assert.match(realEditor, /updateReport\(classroomId, \{ title: normalizedTitle \}\)/);
  assert.doesNotMatch(realEditor, /updateReport\([^)]*content/s);
  assert.match(realEditor, /前端只能修改标题/);
});

test("真实报告展示后端门禁正文并支持三种真实导出", () => {
  assert.match(realEditor, /report\.included_conclusion_ids\.length/);
  assert.match(realEditor, /reportLines\(report\?\.content/);
  assert.match(realEditor, /createReportExport\(report\.id, format\)/);
  assert.match(realEditor, /markdown: "Markdown"/);
  assert.match(realEditor, /html: "HTML"/);
  assert.match(realEditor, /pdf: "PDF"/);
  assert.match(realEditor, /短时有效/);
  assert.match(realEditor, /rel="noopener noreferrer"/);
  assert.doesNotMatch(realEditor, /localStorage|sessionStorage/);
});
