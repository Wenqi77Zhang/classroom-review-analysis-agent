"use client";

import { useEffect, useState } from "react";
import { ApiClientError, createReportExport, getReport, updateReport } from "@/lib/api";
import { redirectToLogin } from "@/lib/session-path";
import type { AnalysisConclusion, ReportExportFormat, ReportExportResponse, ReportRead } from "@/types/contracts";

const labels: Record<ReportExportFormat, string> = { markdown: "Markdown", html: "HTML", pdf: "PDF" };
const typeLabels = { fact: "事实", judgment: "判断", suggestion: "建议" };
const contentOf = (item: AnalysisConclusion) => item.review_status === "modified" ? item.reviewed_content ?? "" : item.content;
const errorOf = (error: unknown) => error instanceof ApiClientError
  ? { message: error.message, status: error.status, traceId: error.traceId }
  : { message: "报告服务暂时不可用，请稍后重试。", status: undefined, traceId: undefined };

export function RealReportEditor({ classroomId }: { classroomId: string }) {
  const [report, setReport] = useState<ReportRead | null>(null);
  const [conclusions, setConclusions] = useState<AnalysisConclusion[]>([]);
  const [drafts, setDrafts] = useState<Record<string, string>>({});
  const [title, setTitle] = useState("课堂复盘报告");
  const [mode, setMode] = useState<"edit" | "preview">("edit");
  const [loading, setLoading] = useState(true);
  const [saving, setSaving] = useState(false);
  const [exporting, setExporting] = useState<ReportExportFormat | null>(null);
  const [download, setDownload] = useState<ReportExportResponse | null>(null);
  const [feedback, setFeedback] = useState("");
  const [error, setError] = useState<ReturnType<typeof errorOf> | null>(null);
  const edits = conclusions.filter(item => (drafts[item.id] ?? contentOf(item)).trim() !== contentOf(item));
  const dirty = Boolean(report && (title.trim() !== report.title || edits.length > 0));
  const valid = title.trim().length > 0 && conclusions.every(item => (drafts[item.id] ?? contentOf(item)).trim().length > 0);

  async function loadReport() {
    setLoading(true);
    setError(null);
    setDownload(null);
    try {
      let saved: ReportRead;
      try { saved = await getReport(classroomId); }
      catch (caught) {
        if (!(caught instanceof ApiClientError) || caught.status !== 404) throw caught;
        saved = await updateReport(classroomId, { title: "课堂复盘报告" });
      }
      const included = saved.conclusions;
      setReport(saved);
      setTitle(saved.title);
      setConclusions(included);
      setDrafts(Object.fromEntries(included.map(item => [item.id, contentOf(item)])));
    } catch (caught) { setError(errorOf(caught)); }
    finally { setLoading(false); }
  }

  useEffect(() => { void loadReport(); }, [classroomId]); // Each ID identifies a different owned report.
  useEffect(() => {
    if (!dirty) return;
    const warn = (event: BeforeUnloadEvent) => { event.preventDefault(); event.returnValue = ""; };
    window.addEventListener("beforeunload", warn);
    return () => window.removeEventListener("beforeunload", warn);
  }, [dirty]);

  async function save() {
    if (!valid || saving) return;
    setSaving(true);
    setError(null);
    setDownload(null);
    try {
      const saved = await updateReport(classroomId, {
        title: title.trim(),
        conclusion_edits: edits.map(item => ({
          id: item.id, content: drafts[item.id].trim(), previous_content: contentOf(item),
        })),
      });
      setReport(saved);
      setTitle(saved.title);
      setConclusions(saved.conclusions);
      setDrafts(Object.fromEntries(saved.conclusions.map(item => [item.id, contentOf(item)])));
      setFeedback("报告已保存。正文修改已记入教师复核历史，证据来源保持关联。");
    } catch (caught) { setError(errorOf(caught)); }
    finally { setSaving(false); }
  }

  async function exportReport(format: ReportExportFormat) {
    if (!report || dirty || saving) return;
    setExporting(format);
    setDownload(null);
    setError(null);
    try { setDownload(await createReportExport(report.id, format)); }
    catch (caught) { setError(errorOf(caught)); }
    finally { setExporting(null); }
  }

  if (loading) return <section className="report-editor report-state-panel" role="status"><h1>正在载入复盘报告</h1><p>正在读取已复核结论及其来源。</p></section>;

  return <section className="report-editor" aria-labelledby="real-report-title">
    <header className="report-editor-heading">
      <div><span className="eyebrow">TEACHING REVIEW</span><h1 id="real-report-title">编辑、预览与导出复盘报告</h1>
        <p>可以修改标题和已确认的结论；保存正文时会追加教师复核记录，并保留证据定位与原文摘录。</p></div>
      {report && <div className="report-mode-switch" role="group" aria-label="报告模式">
        <button type="button" className={mode === "edit" ? "active" : ""} aria-pressed={mode === "edit"} onClick={() => setMode("edit")}>编辑</button>
        <button type="button" className={mode === "preview" ? "active" : ""} aria-pressed={mode === "preview"} onClick={() => setMode("preview")}>预览</button>
      </div>}
    </header>
    {error && <div className="report-transfer-warning" role="alert">
      <p>{error.status === 401 ? "登录已失效，请使用原教师账号登录后继续。" : error.message}
        {error.traceId && <small> 追踪编号：{error.traceId}</small>}</p>
      {error.status === 401
        ? <button className="button primary" type="button" onClick={redirectToLogin}>登录并返回</button>
        : !dirty && <button className="button secondary" type="button" onClick={() => void loadReport()}>重新加载</button>}
      {error.status === 409 && <p>草稿仍保留在编辑框中。请先复制需要保留的修改，再刷新核对最新内容。</p>}
    </div>}
    {feedback && <p role="status">{feedback}</p>}
    {report && <>
      <div className="report-gate-summary" role="status"><span className="gate-ok">✓</span><p>已纳入 {report.included_conclusion_ids.length} 条教师确认的结论；待复核和已驳回的内容不会进入报告。</p></div>
      {mode === "edit" ? <div className="report-edit-form">
        <label>报告标题<input value={title} maxLength={255} disabled={saving} onChange={event => { setTitle(event.target.value); setDownload(null); }} /></label>
        <section className="report-server-content" aria-label="编辑已复核结论">
          {conclusions.map((item, index) => <div className="report-conclusion-edit" key={item.id}>
            <label htmlFor={`report-conclusion-${item.id}`}>{index + 1}. {typeLabels[item.type]} · {item.review_status === "modified" ? "教师修改确认" : "教师接受"}</label>
            <textarea id={`report-conclusion-${item.id}`} rows={4} maxLength={20000} value={drafts[item.id] ?? contentOf(item)} disabled={saving}
              onChange={event => { setDrafts(current => ({ ...current, [item.id]: event.target.value })); setDownload(null); }} />
            <details><summary>核对 {item.evidence_refs.length} 条证据来源</summary>
              {item.evidence_refs.map((ref, i) => <p key={ref.id ?? i}>
                {ref.page_no ? `第 ${ref.page_no} 页` : ref.start_ms != null ? `${(ref.start_ms ?? 0) / 1000}–${(ref.end_ms ?? ref.start_ms ?? 0) / 1000} 秒` : "画面证据"}
                {" · "}{ref.quote || "请在证据工作台查看原始画面"}
              </p>)}
            </details>
          </div>)}
          {!conclusions.length && <p>尚无已确认结论。请先在证据工作台接受或修改至少一条结论。</p>}
        </section>
        <div className="report-title-actions"><button className="button primary" type="button" disabled={saving || !dirty || !valid} onClick={() => void save()}>{saving ? "正在保存…" : "保存报告与复核修改"}</button>
          <button className="button secondary" type="button" disabled={saving || dirty} onClick={() => void loadReport()}>刷新复核结果</button></div>
      </div> : <article className="report-paper">
        <h2>{report.title}</h2>
        <p>已保存版本 · {report.included_conclusion_ids.length} 条教师确认结论</p>
        <div className="report-source-body">{report.content ? report.content.split(/\r?\n/).map((line, i) => {
          const text = line.replace(/^\s*-\s+/, "").replace(/\\([\\`*_{}\[\]<>#+!|])/g, "$1");
          return line.startsWith("## ") ? <h3 key={i}>{line.slice(3)}</h3> : line.trim() ? <p className={line.startsWith("  ") ? "report-source-detail" : ""} key={i}>{text}</p> : null;
        }) : "暂无已确认结论。"}</div>
      </article>}
      {dirty && <p className="report-transfer-warning" role="status">有尚未保存的修改。预览显示已保存版本；保存后即可导出。</p>}
      <footer className="report-export-bar report-export-real"><div><strong>导出报告</strong><p>包含结论、证据定位、摘录、人工复核状态及分析来源。下载链接短时有效。</p></div>
        <div className="report-export-actions">{(Object.keys(labels) as ReportExportFormat[]).map(format =>
          <button className={format === "pdf" ? "button primary" : "button secondary"} key={format} type="button" disabled={dirty || saving || Boolean(exporting) || !report.included_conclusion_ids.length} onClick={() => void exportReport(format)}>
            {exporting === format ? "正在生成…" : `导出 ${labels[format]}`}
          </button>)}</div>
      </footer>
      {download && !dirty && <div className="report-download-result" role="status">
        <p>{labels[download.format]} 已生成，链接有效期至 {new Date(download.expires_at).toLocaleString("zh-CN")}。</p>
        <a className="button primary" href={download.download_url} target="_blank" rel="noopener noreferrer">下载文件</a>
      </div>}
    </>}
  </section>;
}
