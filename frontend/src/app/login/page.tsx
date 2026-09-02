"use client";

import Link from "next/link";
import { FormEvent, useState } from "react";

type SessionResponse = {
  user?: { display_name?: string };
  detail?: string;
  error?: { message?: string };
};

function safeNextPath(value: string | null): string {
  if (!value || !value.startsWith("/") || value.startsWith("//")) return "/classrooms";
  return value;
}

async function readMessage(response: Response): Promise<string> {
  const payload = (await response.json().catch(() => null)) as SessionResponse | null;
  return payload?.error?.message ?? payload?.detail ?? "登录失败，请稍后重试。";
}

export default function LoginPage() {
  const [email, setEmail] = useState("");
  const [password, setPassword] = useState("");
  const [message, setMessage] = useState("");
  const [submitting, setSubmitting] = useState<"account" | "demo" | null>(null);

  function enterProduct() {
    const nextPath = new URLSearchParams(window.location.search).get("next");
    window.location.assign(safeNextPath(nextPath));
  }

  async function submitAccount(event: FormEvent<HTMLFormElement>) {
    event.preventDefault();
    setSubmitting("account");
    setMessage("");
    try {
      const response = await fetch("/api/session/login", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ email, password }),
      });
      if (!response.ok) {
        setMessage(await readMessage(response));
        return;
      }
      enterProduct();
    } catch {
      setMessage("暂时无法连接登录服务，请确认服务器仍在运行。");
    } finally {
      setSubmitting(null);
    }
  }

  async function enterDemo() {
    setSubmitting("demo");
    setMessage("");
    try {
      const response = await fetch("/api/session/demo", { method: "POST" });
      if (!response.ok) {
        setMessage(await readMessage(response));
        return;
      }
      enterProduct();
    } catch {
      setMessage("演示会话暂时不可用，请稍后重试。");
    } finally {
      setSubmitting(null);
    }
  }

  return (
    <main className="team-access-shell auth-shell">
      <section className="team-access-card auth-card" aria-labelledby="login-title">
        <span className="team-access-mark" aria-hidden="true">课</span>
        <p className="team-access-eyebrow">SECURE TEACHER SESSION · 教师工作区</p>
        <h1 id="login-title">进入课堂复盘</h1>
        <p>账号由部署管理员创建。课堂资料、证据与报告按账号隔离；浏览器只保存短期 HttpOnly 会话，不接触数据库或对象存储密钥。</p>
        <form onSubmit={submitAccount}>
          <label htmlFor="login-email">教师邮箱</label>
          <input id="login-email" name="email" type="email" autoComplete="username" maxLength={320} required value={email} onChange={(event) => setEmail(event.target.value)} />
          <label htmlFor="login-password">密码</label>
          <input id="login-password" name="password" type="password" autoComplete="current-password" maxLength={1024} required value={password} onChange={(event) => setPassword(event.target.value)} />
          <button type="submit" disabled={submitting !== null}>{submitting === "account" ? "正在登录…" : "登录教师账号"}</button>
        </form>
        <div className="auth-divider"><span>或</span></div>
        <button className="auth-demo-button" type="button" disabled={submitting !== null} onClick={enterDemo}>{submitting === "demo" ? "正在建立会话…" : "使用受控演示账号"}</button>
        {message ? <p className="team-access-error" role="alert">{message}</p> : null}
        <small>正式部署可关闭演示账号。请勿使用真实课堂账号密码作为团队访问码，也不要在群聊、Issue 或截图中发送口令。</small>
        <Link className="auth-back-link" href="/">返回产品首页</Link>
      </section>
    </main>
  );
}
