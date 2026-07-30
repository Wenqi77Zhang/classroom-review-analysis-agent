"use client";

import { FormEvent, useState } from "react";

function safeNextPath(value: string | null): string {
  if (!value || !value.startsWith("/") || value.startsWith("//")) {
    return "/";
  }
  return value;
}

export default function TeamAccessPage() {
  const [accessCode, setAccessCode] = useState("");
  const [message, setMessage] = useState("");
  const [submitting, setSubmitting] = useState(false);

  async function submitAccessCode(event: FormEvent<HTMLFormElement>) {
    event.preventDefault();
    setSubmitting(true);
    setMessage("");
    try {
      const response = await fetch("/api/team-access", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ accessCode }),
      });
      const result = (await response.json().catch(() => null)) as {
        detail?: string;
      } | null;
      if (!response.ok) {
        setMessage(result?.detail ?? "访问验证失败，请稍后重试。");
        return;
      }
      const nextPath = new URLSearchParams(window.location.search).get("next");
      window.location.assign(safeNextPath(nextPath));
    } catch {
      setMessage("暂时无法连接联调入口，请联系组长确认入口仍在运行。");
    } finally {
      setSubmitting(false);
    }
  }

  return (
    <main className="team-access-shell">
      <section className="team-access-card" aria-labelledby="team-access-title">
        <span className="team-access-mark" aria-hidden="true">联</span>
        <p className="team-access-eyebrow">临时团队联调环境</p>
        <h1 id="team-access-title">输入本次访问码</h1>
        <p>
          该入口运行在组长电脑上，仅供成员联调，不是最终部署环境。请勿上传包含学生身份、
          人脸或其他未经授权的信息。
        </p>
        <form onSubmit={submitAccessCode}>
          <label htmlFor="team-access-code">团队访问码</label>
          <input
            id="team-access-code"
            name="accessCode"
            type="password"
            autoComplete="one-time-code"
            minLength={16}
            maxLength={256}
            required
            value={accessCode}
            onChange={(event) => setAccessCode(event.target.value)}
          />
          <button type="submit" disabled={submitting}>
            {submitting ? "正在验证…" : "进入联调环境"}
          </button>
        </form>
        {message ? <p className="team-access-error" role="alert">{message}</p> : null}
        <small>访问码只应通过团队私聊发送，不要写入 Issue、PR、截图或仓库文件。</small>
      </section>
    </main>
  );
}
