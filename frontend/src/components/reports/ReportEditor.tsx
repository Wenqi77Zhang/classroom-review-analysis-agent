"use client";

import { useEffect, useMemo, useState } from "react";

import { loadDemoReportDraft, type DemoReportDraft } from "@/lib/demo-report-draft";
import type { ReviewStatus } from "@/types/contracts";

type ReportConclusion = {
  id: string;
  status: ReviewStatus;
  kind: "事实" | "判断" | "建议";
  content: string;
  source: string;
};

const demoConclusions: ReportConclusion[] = [
  {
    id: "accepted-fact",
    status: "accepted",
    kind: "事实",
    content: "教师提出证据追问后，课堂出现约五秒等待时间。",
    source: "演示逐字稿 00:12–00:23",
  },
  {
    id: "modified-suggestion",
    status: "modified",
    kind: "建议",
    content: "保留等待时间，并在学生回答后继续追问其文本依据。",
    source: "演示逐字稿 00:23–00:31 · 教师已修改",
  },
  {
    id: "pending-judgment",
    status: "pending",
    kind: "判断",
    content: "等待时间提升了课堂参与度。",
    source: "尚待教师复核",
  },
  {
    id: "rejected-suggestion",
    status: "rejected",
    kind: "建议",
    content: "将所有提问后的等待时间固定为五秒。",
    source: "教师已驳回",
  },
];

const allowedStatuses = new Set<ReviewStatus>(["accepted", "modified"]);

export function ReportEditor() {
  const [draft, setDraft] = useState<DemoReportDraft | null>(null);
  const [draftChecked, setDraftChecked] = useState(false);
  const [title, setTitle] = useState("课堂复盘报告（本地演示草稿）");
  const [summary, setSummary] = useState(
    "本报告用于验证编辑、预览和复核门禁。当前内容全部来自演示数据，不代表真实课堂分析。",
  );
  const [mode, setMode] = useState<"edit" | "preview">("edit");
  useEffect(() => {
    setDraft(loadDemoReportDraft());
    setDraftChecked(true);
  }, []);
  const sourceConclusions = useMemo(() => {
    if (!draft) return demoConclusions;
    return demoConclusions.map((item) =>
      item.id === "modified-suggestion"
        ? {
            ...item,
            status: draft.status,
            content: draft.note || item.content,
            source: `演示逐字稿 00:23–00:31 · 本地复核已交接`,
          }
        : item,
    );
  }, [draft]);
  const included = useMemo(
    () => sourceConclusions.filter((item) => allowedStatuses.has(item.status)),
    [sourceConclusions],
  );
  const excludedCount = sourceConclusions.length - included.length;

  return (
    <section className="report-editor" aria-labelledby="report-editor-title">
      <header className="report-editor-heading">
        <div>
          <span className="mock-pill">本地演示草稿 · 未保存到后端</span>
          <h1 id="report-editor-title">编辑与预览复盘报告</h1>
          <p>
            报告门禁会排除待复核和已驳回结论；真实持久化与 DOCX
            导出等待成员 3、5 的报告 API。
          </p>
        </div>
        <div className="report-mode-switch" role="group" aria-label="报告模式">
          <button
            type="button"
            className={mode === "edit" ? "active" : ""}
            aria-pressed={mode === "edit"}
            onClick={() => setMode("edit")}
          >
            编辑
          </button>
          <button
            type="button"
            className={mode === "preview" ? "active" : ""}
            aria-pressed={mode === "preview"}
            onClick={() => setMode("preview")}
          >
            预览
          </button>
        </div>
      </header>

      <div className="report-gate-summary" role="status">
        <span className="gate-ok">✓</span>
        <div>
          <strong>复核门禁已应用</strong>
          <p>
            已纳入 {included.length} 条已接受或已修改内容；自动排除{" "}
            {excludedCount} 条待复核或已驳回内容。
          </p>
        </div>
      </div>
      {draftChecked && !draft && (
        <p className="report-transfer-warning" role="alert">
          当前会话没有从证据工作台带入复核结果；以下仅展示固定门禁样例。
        </p>
      )}
      {draft && (
        <p className="report-transfer-ok">
          已接收当前浏览器会话中的本地复核结果；尚未保存到服务器。
        </p>
      )}

      {mode === "edit" ? (
        <div className="report-edit-form">
          <label>
            报告标题
            <input
              value={title}
              onChange={(event) => setTitle(event.target.value)}
              maxLength={80}
            />
          </label>
          <label>
            教师摘要
            <textarea
              rows={5}
              value={summary}
              onChange={(event) => setSummary(event.target.value)}
              maxLength={800}
            />
          </label>
          <section aria-labelledby="included-conclusions-title">
            <h2 id="included-conclusions-title">允许进入报告的内容</h2>
            <ReportConclusionList items={included} />
          </section>
        </div>
      ) : (
        <article className="report-paper">
          <span>课堂复盘与教学分析系统</span>
          <h2>{title.trim() || "未命名课堂复盘报告"}</h2>
          <p className="report-paper-summary">{summary}</p>
          <h3>已复核结论</h3>
          <ReportConclusionList items={included} />
          <footer>
            本地演示预览 · 未连接真实课堂、复核记录或报告数据库
          </footer>
        </article>
      )}

      <footer className="report-export-bar">
        <div>
          <strong>导出边界</strong>
          <p>浏览器打印可真实执行；请在打印窗口选择“另存为 PDF”。</p>
        </div>
        <button
          className="button primary"
          type="button"
          onClick={() => {
            setMode("preview");
            window.setTimeout(() => window.print(), 0);
          }}
        >
          打印 / 另存为 PDF
        </button>
        <button className="button secondary" type="button" disabled>
          DOCX 导出等待后端
        </button>
      </footer>
    </section>
  );
}

function ReportConclusionList({ items }: { items: ReportConclusion[] }) {
  return (
    <ol className="report-conclusion-list">
      {items.map((item) => (
        <li key={item.id}>
          <span>{item.kind}</span>
          <div>
            <strong>{item.content}</strong>
            <small>{item.source}</small>
          </div>
        </li>
      ))}
    </ol>
  );
}
