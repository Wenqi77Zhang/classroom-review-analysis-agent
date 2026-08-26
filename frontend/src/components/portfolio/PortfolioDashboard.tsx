"use client";

import Link from "next/link";
import { useEffect, useState } from "react";

import { SiteChrome } from "@/components/baseline/SiteChrome";
import {
  ApiClientError,
  getAggregateReport,
  getPortfolioOverview,
  startDemoSession,
} from "@/lib/api";
import type { AggregateReportRead, PortfolioOverview } from "@/types/contracts";

function describe(error: unknown) {
  return error instanceof ApiClientError
    ? `${error.message}${error.traceId ? `（追踪号：${error.traceId}）` : ""}`
    : "多课程视图暂时无法载入。";
}

export function PortfolioDashboard() {
  const [overview, setOverview] = useState<PortfolioOverview | null>(null);
  const [report, setReport] = useState<AggregateReportRead | null>(null);
  const [error, setError] = useState("");

  useEffect(() => {
    void (async () => {
      try {
        await startDemoSession();
        const [overviewRow, reportRow] = await Promise.all([
          getPortfolioOverview(),
          getAggregateReport(),
        ]);
        setOverview(overviewRow);
        setReport(reportRow);
      } catch (caught) {
        setError(describe(caught));
      }
    })();
  }, []);

  function downloadMarkdown() {
    if (!report) return;
    const blob = new Blob([report.content], { type: "text/markdown;charset=utf-8" });
    const url = URL.createObjectURL(blob);
    const anchor = document.createElement("a");
    anchor.href = url;
    anchor.download = "多课程教学改进汇总.md";
    anchor.click();
    URL.revokeObjectURL(url);
  }

  return (
    <SiteChrome>
      <section className="view active portfolio-page" aria-labelledby="portfolio-title">
        <div className="page-shell">
          <div className="page-heading portfolio-heading" data-reveal>
            <p className="eyebrow">COURSE PORTFOLIO · M3</p>
            <h1 id="portfolio-title">多门课程，在同一条证据边界内被看见</h1>
            <p>按课程组织课堂、复盘与改进循环；这是教师个人工作台，不是自动评分或全校管理平台。</p>
          </div>
          {error && <p className="upload-error" role="alert">{error}</p>}
          {overview ? (
            <>
              <section className="portfolio-stats" data-reveal aria-label="课程总览">
                <article><strong>{overview.course_count}</strong><span>门课程</span></article>
                <article><strong>{overview.classroom_count}</strong><span>节课堂</span></article>
                <article><strong>{overview.completed_cycle_count}</strong><span>个真实或验证循环已闭环</span></article>
              </section>
              <section className="portfolio-courses" data-reveal>
                {overview.courses.map((course) => (
                  <article className="portfolio-course" key={course.id}>
                    <header><div><small>COURSE</small><h2>{course.name}</h2></div><span>{course.classroom_count} 节课堂 · {course.completed_cycle_count} 个闭环</span></header>
                    <div className="portfolio-classrooms">
                      {course.classrooms.map((classroom) => (
                        <article className="portfolio-classroom" key={classroom.id}>
                          <strong>{classroom.title}</strong>
                          <span>{classroom.succeeded_task_count}/{classroom.task_count} 个任务成功</span>
                          <span>{classroom.reviewed_conclusion_count} 条结论经教师确认</span>
                          <span>{classroom.report_ready ? "报告可用" : "报告未形成"}</span>
                          {classroom.latest_task_id ? <Link href={`/tasks/${classroom.latest_task_id}`}>查看最近任务 →</Link> : <span>尚无处理任务</span>}
                        </article>
                      ))}
                      {!course.classrooms.length && <p>这门课程还没有课堂。</p>}
                    </div>
                  </article>
                ))}
                {!overview.courses.length && <div className="empty-state"><strong>尚无课程数据</strong><p>先完成一节课堂的 M1 复盘。</p></div>}
              </section>
            </>
          ) : !error && <p>正在载入课程总览…</p>}

          {report && (
            <section className="aggregate-report" data-reveal>
              <header><div><small>AGGREGATE REPORT</small><h2>{report.title}</h2></div><button className="button primary compact" onClick={downloadMarkdown} disabled={!report.included_cycle_ids.length}>导出 Markdown</button></header>
              <p className="boundary-note">{report.evidence_boundary}</p>
              <pre>{report.content}</pre>
              <footer>生成时间：{new Date(report.generated_at).toLocaleString("zh-CN")} · 纳入 {report.included_cycle_ids.length} 个真实改进循环</footer>
            </section>
          )}
        </div>
      </section>
    </SiteChrome>
  );
}
