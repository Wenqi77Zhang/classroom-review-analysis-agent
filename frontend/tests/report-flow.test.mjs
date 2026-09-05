import assert from "node:assert/strict";
import fs from "node:fs";
import test from "node:test";

const read = (path) =>
  fs.readFileSync(new URL(`../${path}`, import.meta.url), "utf8");

const editor = read("src/components/reports/ReportEditor.tsx");
const realEditor = read("src/components/reports/RealReportEditor.tsx");
const reportPage = read("src/app/reports/[reportId]/page.tsx");
const css = read("src/app/globals.css");

test("报告入口只允许真实课堂资源，不再提供本地演示报告", () => {
  assert.match(editor, /<RealReportEditor classroomId=\{classroomId\} \/>/);
  assert.doesNotMatch(editor, /DemoReportEditor|demoConclusions|sessionStorage/);
  assert.match(reportPage, /UUID_PATTERN\.test\(reportId\)/);
  assert.match(reportPage, /redirect\("\/classrooms#owned-classrooms"\)/);
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

test("真实报告在浏览器会话缺失时可安全恢复并自动重试", () => {
  assert.match(realEditor, /startDemoSession/);
  assert.match(realEditor, /error\.status === 401/);
  assert.match(realEditor, /await startDemoSession\(\)/);
  assert.match(realEditor, /await loadOrCreateReport\(\)/);
  assert.match(realEditor, /建立演示会话并重试/);
  assert.match(realEditor, /HttpOnly|浏览器没有有效的演示会话|浏览器会话尚未建立/);
  assert.doesNotMatch(realEditor, /document\.cookie|localStorage|sessionStorage/);
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

test("报告支持真实预览、浏览器打印且打印版只保留正文", () => {
  assert.match(realEditor, /"edit" \| "preview"/);
  assert.match(realEditor, /window\.print\(\)/);
  assert.match(
    css,
    /@media print[\s\S]*\.prototype-banner,[\s\S]*\.site-header,[\s\S]*\.report-transfer-warning,[\s\S]*\.report-transfer-ok,[\s\S]*\.report-print-fallback,[\s\S]*\.report-export-bar/,
  );
});
