"use client";

import Link from "next/link";
import { useRouter } from "next/navigation";
import { useEffect, useMemo, useState, type FormEvent } from "react";

import {
  ApiClientError,
  createImprovementCycle,
  listClassrooms,
  listCourses,
  listImprovementCycles,
  startDemoSession,
} from "@/lib/api";
import type {
  ClassroomRead,
  CourseRead,
  ImprovementCycleRead,
  ValidationMode,
} from "@/types/contracts";

import { SiteChrome } from "@/components/baseline/SiteChrome";

function message(error: unknown) {
  return error instanceof ApiClientError
    ? `${error.message}${error.traceId ? `（追踪号：${error.traceId}）` : ""}`
    : "暂时无法载入改进循环，请确认服务已启动。";
}

const statusText: Record<ImprovementCycleRead["status"], string> = {
  draft: "待建立行动",
  actions_ready: "行动已就绪",
  followup_linked: "已关联第二轮",
  ready_to_compare: "待生成对比",
  reviewing: "待教师复核",
  completed: "已完成",
};

export function ImprovementHub() {
  const router = useRouter();
  const [courses, setCourses] = useState<CourseRead[]>([]);
  const [classrooms, setClassrooms] = useState<ClassroomRead[]>([]);
  const [cycles, setCycles] = useState<ImprovementCycleRead[]>([]);
  const [courseId, setCourseId] = useState("");
  const [busy, setBusy] = useState(true);
  const [error, setError] = useState("");

  useEffect(() => {
    void (async () => {
      try {
        await startDemoSession();
        const [courseRows, cycleRows] = await Promise.all([
          listCourses(),
          listImprovementCycles(),
        ]);
        setCourses(courseRows);
        setCycles(cycleRows);
        setCourseId(courseRows[0]?.id ?? "");
      } catch (caught) {
        setError(message(caught));
      } finally {
        setBusy(false);
      }
    })();
  }, []);

  useEffect(() => {
    if (!courseId) {
      setClassrooms([]);
      return;
    }
    void listClassrooms(courseId).then(setClassrooms).catch((caught) => setError(message(caught)));
  }, [courseId]);

  const courseNames = useMemo(
    () => new Map(courses.map((course) => [course.id, course.name])),
    [courses],
  );

  async function submit(event: FormEvent<HTMLFormElement>) {
    event.preventDefault();
    setError("");
    const data = new FormData(event.currentTarget);
    const baselineClassroomId = String(data.get("baselineClassroomId") ?? "");
    const title = String(data.get("title") ?? "").trim();
    const objective = String(data.get("objective") ?? "").trim();
    const validationMode = String(data.get("validationMode") ?? "real") as ValidationMode;
    if (!baselineClassroomId || !title || !objective) {
      setError("请选择基线课堂，并填写循环名称与改进目标。");
      return;
    }
    setBusy(true);
    try {
      const cycle = await createImprovementCycle({
        baselineClassroomId,
        title,
        objective,
        validationMode,
      });
      router.push(`/improvements/${cycle.id}`);
    } catch (caught) {
      setError(message(caught));
      setBusy(false);
    }
  }

  return (
    <SiteChrome>
      <section className="view active improvement-page" aria-labelledby="improvement-title">
        <div className="page-shell">
          <div className="page-heading improvement-heading" data-reveal>
            <p className="eyebrow">IMPROVEMENT LOOP · M2</p>
            <h1 id="improvement-title">把复盘建议，变成下一轮可验证的行动</h1>
            <p>行动继承原结论与证据；第二轮仍需真实处理，系统只提出对比候选，教师保留最终判断权。</p>
          </div>
          {error && <p className="upload-error" role="alert">{error}</p>}
          <div className="improvement-grid">
            <form className="creation-card improvement-create" onSubmit={submit} data-reveal>
              <div className="section-title"><span>建立改进循环</span><small>基线 → 行动 → 第二轮</small></div>
              <label>课程
                <select value={courseId} onChange={(event) => setCourseId(event.target.value)}>
                  <option value="">请选择课程</option>
                  {courses.map((course) => <option key={course.id} value={course.id}>{course.name}</option>)}
                </select>
              </label>
              <label>第一轮基线课堂
                <select name="baselineClassroomId" defaultValue="">
                  <option value="">请选择已完成复盘的课堂</option>
                  {classrooms.map((classroom) => <option key={classroom.id} value={classroom.id}>{classroom.title}</option>)}
                </select>
              </label>
              <label>循环名称<input name="title" placeholder="例如：提问等待时间改进循环" /></label>
              <label>改进目标<textarea name="objective" rows={4} placeholder="说明下一轮希望发生的可观察变化。" /></label>
              <fieldset className="mode-choice">
                <legend>证据属性</legend>
                <label><input type="radio" name="validationMode" value="real" defaultChecked />真实轮次</label>
                <label><input type="radio" name="validationMode" value="synthetic" />合成机制验证</label>
              </fieldset>
              <p className="boundary-note">合成轮次只验证系统机制，永不进入真实教学成效汇总。</p>
              <button className="button primary wide" disabled={busy || !courses.length}>建立循环 <span aria-hidden>→</span></button>
              {!courses.length && !busy && <p>尚无课程。请先<Link href="/classrooms">创建课堂</Link>并完成一次 M1 复盘。</p>}
            </form>
            <section className="cycle-list" aria-label="已有改进循环" data-reveal>
              <div className="section-title"><span>已有循环</span><small>{cycles.length} 个</small></div>
              {busy && <p>正在载入…</p>}
              {!busy && !cycles.length && <div className="empty-state"><strong>还没有改进循环</strong><p>先从一条教师确认过的建议开始。</p></div>}
              {cycles.map((cycle) => (
                <Link className="cycle-card" href={`/improvements/${cycle.id}`} key={cycle.id}>
                  <span className={`mode-badge ${cycle.validation_mode}`}>{cycle.validation_mode === "real" ? "真实轮次" : "合成验证"}</span>
                  <h2>{cycle.title}</h2>
                  <p>{courseNames.get(cycle.course_id) ?? "课程"} · {cycle.objective}</p>
                  <footer><span>{statusText[cycle.status]}</span><span>{cycle.actions.length} 项行动 · {cycle.comparisons.length} 项对比</span></footer>
                </Link>
              ))}
            </section>
          </div>
        </div>
      </section>
    </SiteChrome>
  );
}
