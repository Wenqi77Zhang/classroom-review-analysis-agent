"use client";

import { useEffect, useMemo, useState } from "react";

import {
  ApiClientError,
  createReportExport,
  getReport,
  startDemoSession,
  updateReport,
} from "@/lib/api";
import type {
  ReportExportFormat,
  ReportExportResponse,
  ReportRead,
} from "@/types/contracts";

type RealReportEditorProps = {
  classroomId: string;
};

const exportLabels: Record<ReportExportFormat, string> = {
  markdown: "Markdown",
  html: "HTML",
  pdf: "PDF",
};

function normalizeError(error: unknown): {
  message: string;
  traceId?: string;
  status?: number;
} {
  if (error instanceof ApiClientError) {
    return { message: error.message, traceId: error.traceId, status: error.status };
  }
  return { message: "报告服务暂时不可用，请稍后重试。" };
}

function reportLines(content: string): string[] {
  return content
    .split(/\r?\n/)
    .map((line) => line.replace(/^\s*-\s+/, "").trim())
    .filter(Boolean);
}

export function RealReportEditor({ classroomId }: RealReportEditorProps) {
  const [report, setReport] = useState<ReportRead | null>(null);
  const [title, setTitle] = useState("课堂复盘报告");
  const [mode, setMode] = useState<"edit" | "preview">("edit");
  const [loading, setLoading] = useState(true);
  const [saving, setSaving] = useState(false);
  const [exporting, setExporting] = useState<ReportExportFormat | null>(null);
  const [exportResult, setExportResult] = useState<ReportExportResponse | null>(null);
  const [feedback, setFeedback] = useState<string | null>(null);
  const [error, setError] = useState<{
    message: string;
    traceId?: string;
    status?: number;
  } | null>(null);

  async function loadOrCreateReport() {
    setLoading(true);
    setError(null);
    setExportResult(null);
    try {
      let nextReport: ReportRead;
      try {
        nextReport = await getReport(classroomId);
      } catch (loadError) {
        if (!(loadError instanceof ApiClientError) || loadError.status !== 404) {
          throw loadError;
        }
        nextReport = await updateReport(classroomId, { title: "课堂复盘报告" });
      }
      setReport(nextReport);
      setTitle(nextReport.title);
    } catch (loadError) {
      setError(normalizeError(loadError));
    } finally {
      setLoading(false);
    }
  }

  useEffect(() => {
    void loadOrCreateReport();
    // classroomId changes identify an entirely different report resource.
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [classroomId]);

  async function recoverDemoSession() {
    setLoading(true);
    setError(null);
    try {
      await startDemoSession();
      await loadOrCreateReport();
    } catch (sessionError) {
      setError(normalizeError(sessionError));
      setLoading(false);
    }
  }

  const lines = useMemo(() => reportLines(report?.content ?? ""), [report?.content]);
  const titleChanged = Boolean(report && title.trim() !== report.title);

  async function saveTitle() {
    const normalizedTitle = title.trim();
    if (!normalizedTitle || !report) {
      setFeedback("报告标题不能为空。");
      return;
    }
    setSaving(true);
    setFeedback(null);
    setError(null);
    try {
      const nextReport = await updateReport(classroomId, { title: normalizedTitle });
      setReport(nextReport);
      setTitle(nextReport.title);
      setExportResult(null);
      setFeedback("标题已保存。报告正文已按最新人工复核状态重新生成。");
    } catch (saveError) {
      setError(normalizeError(saveError));
    } finally {
      setSaving(false);
    }
  }

  async function exportReport(format: ReportExportFormat) {
    if (!report) return;
    setExporting(format);
    setExportResult(null);
    setFeedback(null);
    setError(null);
    try {
      const result = await createReportExport(report.id, format);
      setExportResult(result);
      setFeedback(`${exportLabels[format]} 文件已生成，可在链接过期前下载。`);
    } catch (exportError) {
      setError(normalizeError(exportError));
    } finally {
      setExporting(null);
    }
  }

  if (loading) {
    return (
      <section className="report-editor report-state-panel" aria-live="polite">
        <span className="eyebrow">REAL REPORT · SERVER GATED</span>
        <h1>正在生成复盘报告</h1>
        <p>系统正在读取教师已接受或已修改的结论。</p>
      </section>
    );
  }

  if (error && !report) {
    const sessionExpired = error.status === 401;
    return (
      <section className="report-editor report-state-panel" role="alert">
        <span className="eyebrow">{sessionExpired ? "SESSION REQUIRED" : "REPORT SERVICE"}</span>
        <h1>{sessionExpired ? "浏览器会话尚未建立" : "报告暂时无法载入"}</h1>
        <p>
          {sessionExpired
            ? "当前浏览器没有有效的演示会话。重新建立会话后，系统会自动载入这份报告。"
            : error.message}
        </p>
        {error.traceId && <small>追踪编号：{error.traceId}</small>}
        <button
          className="button primary"
          type="button"
          onClick={() => void (sessionExpired ? recoverDemoSession() : loadOrCreateReport())}
        >
          {sessionExpired ? "建立演示会话并重试" : "重新加载"}
        </button>
      </section>
    );
  }

  if (!report) return null;

  return (
    <section className="report-editor" aria-labelledby="real-report-title">
      <header className="report-editor-heading">
        <div>
          <span className="eyebrow">REAL REPORT · SERVER GATED</span>
          <h1 id="real-report-title">编辑、预览与导出复盘报告</h1>
          <p>
            正文由服务器根据人工复核结果生成；前端只能修改标题，无法绕过复核门禁写入结论。
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
          <strong>复核门禁已由后端应用</strong>
          <p>
            当前报告纳入 {report.included_conclusion_ids.length} 条已接受或已修改结论；待复核与已驳回内容不会进入正文或导出文件。
          </p>
        </div>
      </div>

      {error && (
        <div className="report-transfer-warning" role="alert">
          <span>
            {error.status === 401 ? "浏览器会话已失效，请重新建立会话后继续。" : error.message}
            {error.traceId ? `（追踪编号：${error.traceId}）` : ""}
          </span>
          {error.status === 401 && (
            <button className="button secondary" type="button" onClick={() => void recoverDemoSession()}>
              重新建立演示会话
            </button>
          )}
        </div>
      )}
      {feedback && <p className="report-transfer-ok" role="status">{feedback}</p>}

      {mode === "edit" ? (
        <div className="report-edit-form">
          <label>
            报告标题
            <input
              value={title}
              onChange={(event) => setTitle(event.target.value)}
              maxLength={255}
              aria-describedby="report-title-boundary"
            />
          </label>
          <p id="report-title-boundary" className="report-server-note">
            可编辑范围仅限标题。正文与纳入结论编号由服务器维护，修改教师复核结果后重新打开或保存标题即可刷新。
          </p>
          <div className="report-title-actions">
            <div className="report-export-actions">
              <button
                className="button primary"
                type="button"
                disabled={saving || !title.trim() || !titleChanged}
                onClick={() => void saveTitle()}
              >
                {saving ? "正在保存…" : "保存标题并刷新正文"}
              </button>
              <button className="button secondary" type="button" onClick={() => void loadOrCreateReport()}>
                刷新复核结果
              </button>
            </div>
            <span>{report.updated_at ? `服务器更新时间：${new Date(report.updated_at).toLocaleString("zh-CN")}` : "服务器已生成报告"}</span>
          </div>
          <ReportBody lines={lines} />
        </div>
      ) : (
        <ReportPaper title={title} lines={lines} includedCount={report.included_conclusion_ids.length} />
      )}

      <footer className="report-export-bar report-export-real">
        <div>
          <strong>真实导出</strong>
          <p>文件由后端按相同复核门禁重新生成；下载链接短时有效，页面不会持久化保存该链接。</p>
        </div>
        <div className="report-export-actions" aria-label="报告导出格式">
          {(Object.keys(exportLabels) as ReportExportFormat[]).map((format) => (
            <button
              className={format === "pdf" ? "button primary" : "button secondary"}
              type="button"
              disabled={Boolean(exporting) || titleChanged}
              key={format}
              onClick={() => void exportReport(format)}
            >
              {exporting === format ? "生成中…" : `导出 ${exportLabels[format]}`}
            </button>
          ))}
          <button className="button secondary" type="button" onClick={() => window.print()}>
            浏览器打印
          </button>
        </div>
      </footer>

      {titleChanged && (
        <p className="report-transfer-warning" role="status">
          标题尚未保存。请先保存标题，再生成与当前预览一致的导出文件。
        </p>
      )}

      {exportResult && (
        <div className="report-download-result" role="status">
          <div>
            <strong>{exportLabels[exportResult.format]} 已就绪</strong>
            <p>链接有效期至 {new Date(exportResult.expires_at).toLocaleString("zh-CN")}，过期后请重新生成。</p>
          </div>
          <a
            className="button primary"
            href={exportResult.download_url}
            target="_blank"
            rel="noopener noreferrer"
          >
            下载文件
          </a>
        </div>
      )}
    </section>
  );
}

function ReportBody({ lines }: { lines: string[] }) {
  return (
    <section className="report-server-content" aria-labelledby="server-report-content-title">
      <div>
        <span>SERVER-CONTROLLED CONTENT</span>
        <h2 id="server-report-content-title">已复核结论</h2>
      </div>
      {lines.length ? (
        <ol className="report-conclusion-list">
          {lines.map((line, index) => (
            <li key={`${index}-${line}`}>
              <span>{String(index + 1).padStart(2, "0")}</span>
              <div><strong>{line}</strong></div>
            </li>
          ))}
        </ol>
      ) : (
        <p className="report-empty-state">暂无可进入报告的结论。请先在证据工作台接受或修改至少一条分析结论。</p>
      )}
    </section>
  );
}

function ReportPaper({
  title,
  lines,
  includedCount,
}: {
  title: string;
  lines: string[];
  includedCount: number;
}) {
  return (
    <article className="report-paper">
      <span>课堂复盘与教学分析系统 · EVIDENCE-LED TEACHING REVIEW</span>
      <h2>{title.trim() || "未命名课堂复盘报告"}</h2>
      <p className="report-paper-summary">本报告共纳入 {includedCount} 条经教师确认的结论。</p>
      <ReportBody lines={lines} />
      <footer>服务器生成 · 仅包含已接受或已修改的教学分析结论</footer>
    </article>
  );
}
