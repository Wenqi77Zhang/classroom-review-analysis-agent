"use client";

import Link from "next/link";
import { useCallback, useEffect, useMemo, useState, type FormEvent } from "react";

import { SiteChrome } from "@/components/baseline/SiteChrome";
import {
  ApiClientError,
  createImprovementAction,
  generateImprovementComparisons,
  getConclusions,
  getImprovementCycle,
  listClassrooms,
  reviewImprovementComparison,
  startDemoSession,
  updateImprovementAction,
  updateImprovementCycle,
} from "@/lib/api";
import type {
  AnalysisConclusion,
  ClassroomRead,
  ImprovementComparisonRead,
  ImprovementCycleRead,
  ReviewAction,
} from "@/types/contracts";

function describe(error: unknown) {
  return error instanceof ApiClientError
    ? `${error.message}${error.traceId ? `（追踪号：${error.traceId}）` : ""}`
    : "操作失败，请稍后重试。";
}

const outcomeText: Record<ImprovementComparisonRead["proposed_outcome"], string> = {
  improved: "观察到改进信号",
  unchanged: "暂未观察到明显变化",
  regressed: "观察到退步信号",
  insufficient_evidence: "证据不足",
};

function EvidenceCount({ comparison }: { comparison: ImprovementComparisonRead }) {
  return <p className="comparison-evidence-count">第一轮 {comparison.baseline_evidence.length} 条证据 · 第二轮 {comparison.followup_evidence.length} 条证据</p>;
}

export function ImprovementCycleWorkspace({ cycleId }: { cycleId: string }) {
  const [cycle, setCycle] = useState<ImprovementCycleRead | null>(null);
  const [suggestions, setSuggestions] = useState<AnalysisConclusion[]>([]);
  const [classrooms, setClassrooms] = useState<ClassroomRead[]>([]);
  const [notice, setNotice] = useState("");
  const [error, setError] = useState("");
  const [busy, setBusy] = useState(true);

  const reload = useCallback(async () => {
    const current = await getImprovementCycle(cycleId);
    setCycle(current);
    const [conclusions, classroomRows] = await Promise.all([
      getConclusions(current.baseline_classroom_id),
      listClassrooms(current.course_id),
    ]);
    setSuggestions(
      conclusions.filter(
        (item) =>
          item.type === "suggestion" &&
          (item.review_status === "accepted" || item.review_status === "modified"),
      ),
    );
    setClassrooms(classroomRows);
  }, [cycleId]);

  useEffect(() => {
    void (async () => {
      try {
        await startDemoSession();
        await reload();
      } catch (caught) {
        setError(describe(caught));
      } finally {
        setBusy(false);
      }
    })();
  }, [reload]);

  const usedSuggestionIds = useMemo(
    () => new Set(cycle?.actions.map((item) => item.source_conclusion_id) ?? []),
    [cycle],
  );
  const availableSuggestions = suggestions.filter((item) => !usedSuggestionIds.has(item.id));
  const followupChoices = classrooms.filter((item) => item.id !== cycle?.baseline_classroom_id);

  async function addAction(event: FormEvent<HTMLFormElement>) {
    event.preventDefault();
    const data = new FormData(event.currentTarget);
    setBusy(true); setError(""); setNotice("");
    try {
      await createImprovementAction(cycleId, {
        sourceConclusionId: String(data.get("sourceConclusionId") ?? ""),
        actionText: String(data.get("actionText") ?? ""),
        successCriterion: String(data.get("successCriterion") ?? ""),
        priority: Number(data.get("priority") ?? 2),
      });
      event.currentTarget.reset();
      await reload();
      setNotice("改进行动已保存，并保留了来源结论与证据链。 ");
    } catch (caught) { setError(describe(caught)); } finally { setBusy(false); }
  }

  function chooseSuggestion(id: string, form: HTMLFormElement) {
    const item = suggestions.find((suggestion) => suggestion.id === id);
    const action = form.elements.namedItem("actionText") as HTMLTextAreaElement | null;
    if (item && action) action.value = item.reviewed_content || item.content;
  }

  async function linkFollowup(event: FormEvent<HTMLFormElement>) {
    event.preventDefault();
    const id = String(new FormData(event.currentTarget).get("followupClassroomId") ?? "");
    setBusy(true); setError("");
    try { await updateImprovementCycle(cycleId, { followupClassroomId: id }); await reload(); setNotice("第二轮课堂已关联。完成该课堂的 M1 处理与教师复核后即可生成对比。"); }
    catch (caught) { setError(describe(caught)); } finally { setBusy(false); }
  }

  async function generate() {
    setBusy(true); setError("");
    try { await generateImprovementComparisons(cycleId); await reload(); setNotice("已生成证据对比候选。请逐条核对，系统不会自动认定教学效果。"); }
    catch (caught) { setError(describe(caught)); } finally { setBusy(false); }
  }

  async function review(comparison: ImprovementComparisonRead, action: ReviewAction, editedSummary?: string) {
    setBusy(true); setError("");
    try {
      await reviewImprovementComparison(comparison.id, { action, editedSummary });
      await reload();
      setNotice(`对比结论已${action === "reject" ? "驳回" : "确认"}，审计记录已保存。`);
    } catch (caught) { setError(describe(caught)); } finally { setBusy(false); }
  }

  if (busy && !cycle) return <SiteChrome><section className="view active"><div className="page-shell"><p>正在恢复改进循环…</p></div></section></SiteChrome>;
  if (!cycle) return <SiteChrome><section className="view active"><div className="page-shell"><p className="upload-error">{error || "改进循环不存在。"}</p></div></section></SiteChrome>;

  const reviewedCount = cycle.comparisons.filter((item) => item.review_status !== "pending").length;
  return (
    <SiteChrome>
      <section className="view active improvement-page" aria-labelledby="cycle-title">
        <div className="page-shell">
          <div className="page-heading cycle-heading" data-reveal>
            <Link className="back-link" href="/improvements">← 返回改进循环</Link>
            <p className="eyebrow">EVIDENCE COMPARISON · M2</p>
            <h1 id="cycle-title">{cycle.title}</h1>
            <p>{cycle.objective}</p>
            <div className="cycle-meta"><span className={`mode-badge ${cycle.validation_mode}`}>{cycle.validation_mode === "real" ? "真实轮次" : "合成机制验证"}</span><span>状态：{cycle.status}</span><span>{cycle.actions.length} 项行动</span><span>{reviewedCount}/{cycle.comparisons.length} 项对比已复核</span></div>
          </div>
          {notice && <p className="success-notice" role="status">{notice}</p>}
          {error && <p className="upload-error" role="alert">{error}</p>}
          <div className="cycle-workflow">
            <section className="workflow-card" data-reveal>
              <header><span>01</span><div><small>ACTION PLAN</small><h2>把教师确认的建议转成行动</h2></div></header>
              <div className="action-stack">
                {cycle.actions.map((action) => (
                  <article className="action-row" key={action.id}>
                    <strong>P{action.priority} · {action.action_text}</strong>
                    <p>成功标准：{action.success_criterion}</p>
                    <select aria-label="行动进度" value={action.progress} onChange={(event) => void updateImprovementAction(action.id, { progress: event.target.value as typeof action.progress }).then(reload).catch((caught) => setError(describe(caught)))}>
                      <option value="planned">计划中</option><option value="in_progress">执行中</option><option value="completed">已执行</option><option value="dropped">不再执行</option>
                    </select>
                  </article>
                ))}
              </div>
              {availableSuggestions.length ? (
                <form className="inline-action-form" onSubmit={addAction}>
                  <label>来源建议<select name="sourceConclusionId" required defaultValue="" onChange={(event) => chooseSuggestion(event.target.value, event.currentTarget.form!)}><option value="">选择一条已确认建议</option>{availableSuggestions.map((item) => <option value={item.id} key={item.id}>{item.reviewed_content || item.content}</option>)}</select></label>
                  <label>具体行动<textarea name="actionText" required rows={3} /></label>
                  <label>可观察的成功标准<textarea name="successCriterion" required rows={3} placeholder="例如：关键提问后保留至少 5 秒等待，并在逐字稿中出现学生回应。" /></label>
                  <label>优先级<select name="priority" defaultValue="2"><option value="1">P1 高</option><option value="2">P2 中</option><option value="3">P3 低</option></select></label>
                  <button className="button primary compact" disabled={busy}>保存行动</button>
                </form>
              ) : <p className="boundary-note">没有更多可转化的建议。只有第一轮中经教师接受或修改确认的建议会出现在这里。</p>}
            </section>

            <section className="workflow-card" data-reveal>
              <header><span>02</span><div><small>FOLLOW-UP ROUND</small><h2>关联同一课程的第二轮课堂</h2></div></header>
              <p>第二轮须单独上传并完成 M1 处理。不同课程不能放进同一个改进循环。</p>
              <form className="followup-form" onSubmit={linkFollowup}>
                <select name="followupClassroomId" required defaultValue={cycle.followup_classroom_id ?? ""}><option value="">选择第二轮课堂</option>{followupChoices.map((item) => <option value={item.id} key={item.id}>{item.title}</option>)}</select>
                <button className="button secondary compact" disabled={busy}>保存关联</button>
                <Link className="button secondary compact" href="/classrooms">创建新课堂</Link>
              </form>
            </section>

            <section className="workflow-card comparison-stage" data-reveal>
              <header><span>03</span><div><small>COMPARE & REVIEW</small><h2>核对两轮证据，再确认是否发生变化</h2></div></header>
              <div className="comparison-gate"><p>生成按钮只在已有行动、已关联第二轮且第二轮真实处理成功后通过后端门禁。</p><button className="button primary compact" onClick={() => void generate()} disabled={busy || !cycle.actions.length || !cycle.followup_classroom_id}>生成或重新生成证据对比</button></div>
              {!cycle.comparisons.length && <div className="empty-state"><strong>尚无对比结论</strong><p>系统不会因为关联了课堂就假定教学已经改进。</p></div>}
              <div className="comparison-list">
                {cycle.comparisons.map((comparison, index) => (
                  <article className="comparison-card" key={comparison.id}>
                    <div className="comparison-title"><span>{String(index + 1).padStart(2, "0")}</span><div><small>{outcomeText[comparison.proposed_outcome]} · 待教师判断</small><h3>{comparison.summary}</h3></div></div>
                    <EvidenceCount comparison={comparison} />
                    <textarea id={`comparison-${comparison.id}`} defaultValue={comparison.reviewed_summary || comparison.summary} aria-label={`第 ${index + 1} 条对比结论修改稿`} rows={4} />
                    <div className="review-actions">
                      <button className="button review-accept compact" disabled={busy} onClick={() => void review(comparison, "accept")}>接受候选判断</button>
                      <button className="button review-modify compact" disabled={busy} onClick={() => { const field = document.getElementById(`comparison-${comparison.id}`) as HTMLTextAreaElement; void review(comparison, "modify", field.value); }}>修改确认</button>
                      <button className="button review-reject compact" disabled={busy} onClick={() => void review(comparison, "reject")}>驳回</button>
                    </div>
                    <footer>复核状态：{comparison.review_status} · Trace {comparison.trace_id} · {comparison.skill}/{comparison.prompt_version}</footer>
                  </article>
                ))}
              </div>
            </section>
          </div>
        </div>
      </section>
    </SiteChrome>
  );
}
