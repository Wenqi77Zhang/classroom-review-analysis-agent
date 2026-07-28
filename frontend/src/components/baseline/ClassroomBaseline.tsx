"use client";

import Link from "next/link";
import { useRouter } from "next/navigation";
import { useState, type FormEvent } from "react";
import { SiteChrome } from "./SiteChrome";

export function ClassroomBaseline() {
  const router = useRouter();
  const [errors, setErrors] = useState<Record<string,string>>({});
  function submit(event: FormEvent<HTMLFormElement>) {
    event.preventDefault();
    const data = new FormData(event.currentTarget);
    const next: Record<string,string> = {};
    if (!String(data.get("courseName") ?? "").trim()) next.course = "请填写课程名称";
    if (!String(data.get("classroomName") ?? "").trim()) next.classroom = "请填写本节课堂名称";
    if (data.get("permission") !== "on") next.permission = "请先确认资料权利与隐私边界";
    setErrors(next);
    if (Object.keys(next).length) return;
    sessionStorage.setItem("classroomName", String(data.get("classroomName")));
    router.push("/tasks/demo-review");
  }
  return <SiteChrome><section className="view active" aria-labelledby="classroom-title"><div className="page-shell narrow">
    <div className="page-heading" data-reveal><Link className="back-link" href="/">← 返回首页</Link><p className="eyebrow">CREATE A CLASSROOM · 步骤 1 / 3</p><h1 id="classroom-title">创建课程与课堂</h1><p>课程用于归档，课堂代表本次需要复盘的单节真实教学活动。</p></div>
    <div className="form-layout"><form className="creation-card" onSubmit={submit} data-reveal noValidate>
      <div className="section-title"><span>课程信息</span><small>必填</small></div>
      <label>课程名称<input name="courseName" placeholder="例如：人工智能导论" autoComplete="off" /><span className="field-error">{errors.course}</span></label>
      <label>本节课堂名称<input name="classroomName" placeholder="例如：第 3 讲 · 搜索与问题求解" autoComplete="off" /><span className="field-error">{errors.classroom}</span></label>
      <div className="field-row"><label>授课语言<select name="language"><option value="zh">中文</option><option value="mixed">中英混合</option><option value="en">英文</option></select></label><label>课堂日期<input name="classDate" type="date" /></label></div>
      <label className="permission-check"><input name="permission" type="checkbox" /><span>我确认仅上传有权处理的公开课资料，且不包含学生隐私信息。</span></label><span className="field-error">{errors.permission}</span>
      <button className="button primary wide" type="submit">保存并说明复盘目标 <span aria-hidden>→</span></button>
    </form>
    <aside className="context-card" data-reveal><div className="context-heading"><span className="context-icon" aria-hidden>◎</span><span><small>WHY THIS STEP</small><h2>为什么先创建课堂？</h2></span></div><p>文件、任务、逐字稿和报告都必须归属于正确的教师与课堂。这样才能更换输入、保留版本并隔离不同账号的数据。</p><dl><div><dt>课程</dt><dd>长期教学主题</dd></div><div><dt>课堂</dt><dd>一次具体授课</dd></div><div><dt>复盘任务</dt><dd>一次分析目标</dd></div></dl></aside></div>
  </div></section></SiteChrome>;
}
