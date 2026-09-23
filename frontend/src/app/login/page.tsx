"use client";

import Link from "next/link";
import { FormEvent, useState } from "react";
import { safeNextPath } from "@/lib/session-path";

type SessionResponse = {
  user?: { display_name?: string };
  detail?: string;
  error?: { message?: string };
};

async function readMessage(response: Response): Promise<string> {
  const payload = (await response.json().catch(() => null)) as SessionResponse | null;
  return payload?.error?.message ?? payload?.detail ?? "登录失败，请稍后重试。";
}

export default function LoginPage() {
  const [mode, setMode] = useState<"login" | "register">("login");
  const [email, setEmail] = useState("");
  const [displayName, setDisplayName] = useState("");
  const [password, setPassword] = useState("");
  const [passwordConfirmation, setPasswordConfirmation] = useState("");
  const [message, setMessage] = useState("");
  const [submitting, setSubmitting] = useState<"login" | "register" | "demo" | null>(null);

  function enterProduct() {
    const nextPath = new URLSearchParams(window.location.search).get("next");
    window.location.assign(safeNextPath(nextPath));
  }

  async function submitAccount(event: FormEvent<HTMLFormElement>) {
    event.preventDefault();
    if (mode === "register" && password !== passwordConfirmation) {
      setMessage("两次输入的密码不一致。");
      return;
    }
    setSubmitting(mode);
    setMessage("");
    try {
      const response = await fetch(`/api/session/${mode}`, {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify(
          mode === "register"
            ? { email, display_name: displayName, password }
            : { email, password },
        ),
      });
      if (!response.ok) {
        setMessage(await readMessage(response));
        return;
      }
      enterProduct();
    } catch {
      setMessage("暂时无法连接账号服务，请稍后重试。");
    } finally {
      setSubmitting(null);
    }
  }

  function switchMode(nextMode: "login" | "register") {
    setMode(nextMode);
    setMessage("");
    setPassword("");
    setPasswordConfirmation("");
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
        <p>注册后即可建立独立教师工作区，课堂资料、证据与报告按账号隔离；浏览器只保存短期 HttpOnly 会话，不接触数据库或对象存储密钥。</p>
        <div className="auth-mode-switch" aria-label="账号入口">
          <button type="button" className={mode === "login" ? "active" : ""} aria-pressed={mode === "login"} onClick={() => switchMode("login")}>登录</button>
          <button type="button" className={mode === "register" ? "active" : ""} aria-pressed={mode === "register"} onClick={() => switchMode("register")}>注册</button>
        </div>
        <form onSubmit={submitAccount}>
          {mode === "register" ? <>
            <label htmlFor="register-display-name">显示名称</label>
            <input id="register-display-name" name="display-name" type="text" autoComplete="name" maxLength={128} required value={displayName} onChange={(event) => setDisplayName(event.target.value)} />
          </> : null}
          <label htmlFor="login-email">教师邮箱</label>
          <input id="login-email" name="email" type="email" autoComplete="username" maxLength={320} required value={email} onChange={(event) => setEmail(event.target.value)} />
          <label htmlFor="login-password">密码</label>
          <input id="login-password" name="password" type="password" autoComplete={mode === "register" ? "new-password" : "current-password"} minLength={mode === "register" ? 12 : undefined} maxLength={mode === "register" ? 128 : 1024} required value={password} onChange={(event) => setPassword(event.target.value)} />
          {mode === "register" ? <>
            <small className="auth-field-help">至少 12 位，并同时包含字母和数字。</small>
            <label htmlFor="register-password-confirmation">确认密码</label>
            <input id="register-password-confirmation" name="password-confirmation" type="password" autoComplete="new-password" minLength={12} maxLength={128} required value={passwordConfirmation} onChange={(event) => setPasswordConfirmation(event.target.value)} />
          </> : null}
          <button type="submit" disabled={submitting !== null}>{submitting === mode ? (mode === "register" ? "正在创建工作区…" : "正在登录…") : (mode === "register" ? "注册并进入工作区" : "登录教师账号")}</button>
        </form>
        <div className="auth-divider"><span>或</span></div>
        <button className="auth-demo-button" type="button" disabled={submitting !== null} onClick={enterDemo}>{submitting === "demo" ? "正在建立会话…" : "免注册进入共享演示工作区"}</button>
        {message ? <p className="team-access-error" role="alert">{message}</p> : null}
        <small>共享演示工作区中的内容可能被其他访客看到，请只上传无隐私且已获授权的测试材料。需要保存私有资料时，请注册独立账号。</small>
        <Link className="auth-back-link" href="/">返回产品首页</Link>
      </section>
    </main>
  );
}
