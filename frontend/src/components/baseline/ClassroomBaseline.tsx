"use client";

import Link from "next/link";
import { useRouter } from "next/navigation";
import { useCallback, useEffect, useState, type FormEvent } from "react";

import {
  ApiClientError,
  createClassroom,
  createCourse,
  deleteClassroom,
  listClassrooms,
  listCourses,
  startDemoSession,
} from "@/lib/api";
import type { ClassroomRead, CourseRead } from "@/types/contracts";

import { SiteChrome } from "./SiteChrome";

export function ClassroomBaseline() {
  const router = useRouter();
  const [errors, setErrors] = useState<Record<string, string>>({});
  const [submitting, setSubmitting] = useState(false);
  const [courses, setCourses] = useState<CourseRead[]>([]);
  const [classrooms, setClassrooms] = useState<ClassroomRead[]>([]);
  const [confirmDeleteId, setConfirmDeleteId] = useState<string | null>(null);
  const [managementMessage, setManagementMessage] = useState("");

  const refreshOwnedClassrooms = useCallback(async () => {
    try {
      await startDemoSession();
      const ownedCourses = await listCourses();
      const classroomGroups = await Promise.all(
        ownedCourses.map((course) => listClassrooms(course.id)),
      );
      setCourses(ownedCourses);
      setClassrooms(classroomGroups.flat());
    } catch {
      // Visitors may be logged out and production can disable the demo account.
      // The creation form shows the actionable authentication error on submit.
    }
  }, []);

  useEffect(() => {
    void refreshOwnedClassrooms();
  }, [refreshOwnedClassrooms]);

  async function removeClassroom(classroomId: string) {
    setManagementMessage("");
    try {
      await deleteClassroom(classroomId);
      setConfirmDeleteId(null);
      setManagementMessage("课堂及其关联资料已删除，并已留下审计记录。");
      await refreshOwnedClassrooms();
    } catch (error) {
      setManagementMessage(
        error instanceof ApiClientError
          ? error.message
          : "删除失败，请稍后重试。",
      );
    }
  }

  async function submit(event: FormEvent<HTMLFormElement>) {
    event.preventDefault();
    const data = new FormData(event.currentTarget);
    const courseName = String(data.get("courseName") ?? "").trim();
    const classroomName = String(data.get("classroomName") ?? "").trim();
    const language = String(data.get("language") ?? "zh");
    const classDate = String(data.get("classDate") ?? "");
    const next: Record<string, string> = {};

    if (!courseName) next.course = "请填写课程名称";
    if (!classroomName) next.classroom = "请填写本节课堂名称";
    if (data.get("permission") !== "on") {
      next.permission = "请先确认资料权利与隐私边界";
    }
    setErrors(next);
    if (Object.keys(next).length) return;

    setSubmitting(true);
    try {
      await startDemoSession();
      const course = await createCourse(courseName);
      const classroom = await createClassroom(course.id, {
        title: classroomName,
        description: [classDate, language].filter(Boolean).join(" · "),
      });
      sessionStorage.setItem("classroomName", classroom.title);
      sessionStorage.setItem("classroomId", classroom.id);
      router.push(`/tasks/${classroom.id}?from=classroom`);
    } catch (error) {
      const message =
        error instanceof ApiClientError
          ? `${error.message}${error.traceId ? `（追踪号：${error.traceId}）` : ""}`
          : "课堂创建失败，请确认前后端服务和数据库已经启动。";
      setErrors({ submit: message });
    } finally {
      setSubmitting(false);
    }
  }

  return (
    <SiteChrome>
      <section className="view active" aria-labelledby="classroom-title">
        <div className="page-shell narrow">
          <div className="page-heading" data-reveal>
            <Link className="back-link" href="/">
              ← 返回首页
            </Link>
            <p className="eyebrow">CREATE A CLASSROOM · 步骤 1 / 3</p>
            <h1 id="classroom-title">创建课程与课堂</h1>
            <p>
              课程用于归档，课堂代表本次需要复盘的单节真实教学活动。
            </p>
          </div>
          <div className="form-layout">
            <form
              className="creation-card"
              onSubmit={submit}
              data-reveal
              noValidate
            >
              <div className="section-title">
                <span>课程信息</span>
                <small>必填</small>
              </div>
              <label>
                课程名称
                <input
                  name="courseName"
                  placeholder="例如：人工智能导论"
                  autoComplete="off"
                />
                <span className="field-error">{errors.course}</span>
              </label>
              <label>
                本节课堂名称
                <input
                  name="classroomName"
                  placeholder="例如：第 3 讲 · 搜索与问题求解"
                  autoComplete="off"
                />
                <span className="field-error">{errors.classroom}</span>
              </label>
              <div className="field-row">
                <label>
                  授课语言
                  <select name="language">
                    <option value="zh">中文</option>
                    <option value="mixed">中英混合</option>
                    <option value="en">英文</option>
                  </select>
                </label>
                <label>
                  课堂日期
                  <input name="classDate" type="date" />
                </label>
              </div>
              <label className="permission-check">
                <input name="permission" type="checkbox" />
                <span>
                  我确认仅上传有权处理的公开课资料，且不包含学生隐私信息。
                </span>
              </label>
              <span className="field-error">{errors.permission}</span>
              {errors.submit && (
                <p className="upload-error" role="alert">
                  {errors.submit}
                </p>
              )}
              <button
                className="button primary wide"
                type="submit"
                disabled={submitting}
              >
                {submitting ? "正在建立安全会话并保存…" : "保存并说明复盘目标"}
                <span aria-hidden>→</span>
              </button>
              <p className="form-security-note">
                正式环境使用教师账号；仅在管理员主动启用时提供演示账号。访问令牌只保存在
                HttpOnly Cookie，不写入浏览器存储。
              </p>
            </form>
            <aside className="context-card" data-reveal>
              <div className="context-heading">
                <span className="context-icon" aria-hidden>
                  ◎
                </span>
                <span>
                  <small>WHY THIS STEP</small>
                  <h2>为什么先创建课堂？</h2>
                </span>
              </div>
              <p>
                文件、任务、逐字稿和报告都必须归属于正确的教师与课堂。这样才能更换输入、保留版本并隔离不同账号的数据。
              </p>
              <dl>
                <div>
                  <dt>课程</dt>
                  <dd>长期教学主题</dd>
                </div>
                <div>
                  <dt>课堂</dt>
                  <dd>一次具体授课</dd>
                </div>
                <div>
                  <dt>复盘任务</dt>
                  <dd>一次分析目标</dd>
                </div>
              </dl>
            </aside>
          </div>
          {classrooms.length > 0 && (
            <section className="owned-classrooms" id="owned-classrooms" aria-labelledby="owned-classrooms-title">
              <div className="section-title">
                <span id="owned-classrooms-title">我的已有课堂</span>
                <small>{classrooms.length} 节</small>
              </div>
              <p className="form-security-note">
                可继续进入复盘；删除会同时清理该课堂的数据库记录与对象存储文件，且不可撤销。
              </p>
              <div className="owned-classroom-list">
                {classrooms.map((classroom) => {
                  const course = courses.find((item) => item.id === classroom.course_id);
                  const confirming = confirmDeleteId === classroom.id;
                  return (
                    <article className="owned-classroom-row" key={classroom.id}>
                      <div>
                        <small>{course?.name ?? "未命名课程"}</small>
                        <h3>{classroom.title}</h3>
                      </div>
                      <div className="owned-classroom-actions">
                        <Link
                          className="button secondary compact"
                          href={`/tasks/${classroom.id}?from=classroom`}
                        >
                          进入复盘
                        </Link>
                        {!confirming ? (
                          <button
                            className="button danger-quiet compact"
                            type="button"
                            onClick={() => setConfirmDeleteId(classroom.id)}
                          >
                            删除课堂
                          </button>
                        ) : (
                          <span className="delete-confirmation" role="group" aria-label="确认删除">
                            <button
                              className="button danger compact"
                              type="button"
                              onClick={() => void removeClassroom(classroom.id)}
                            >
                              确认永久删除
                            </button>
                            <button
                              className="button secondary compact"
                              type="button"
                              onClick={() => setConfirmDeleteId(null)}
                            >
                              取消
                            </button>
                          </span>
                        )}
                      </div>
                    </article>
                  );
                })}
              </div>
              {managementMessage && (
                <p className="management-message" role="status">
                  {managementMessage}
                </p>
              )}
            </section>
          )}
        </div>
      </section>
    </SiteChrome>
  );
}
