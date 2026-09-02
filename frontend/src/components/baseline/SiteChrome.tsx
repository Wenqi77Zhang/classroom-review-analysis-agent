"use client";

import Link from "next/link";
import { usePathname } from "next/navigation";
import { useEffect, useLayoutEffect, useState, type ReactNode } from "react";

type SessionUser = { id: string; display_name: string };

export function SiteChrome({ children }: { children: ReactNode }) {
  const pathname = usePathname();
  const [sessionUser, setSessionUser] = useState<SessionUser | null>(null);
  const [sessionKnown, setSessionKnown] = useState(false);

  useEffect(() => {
    let active = true;
    const refreshSession = async () => {
      try {
        const response = await fetch("/api/session/me", { cache: "no-store" });
        const user = response.ok ? ((await response.json()) as SessionUser) : null;
        if (active) setSessionUser(user);
      } catch {
        if (active) setSessionUser(null);
      } finally {
        if (active) setSessionKnown(true);
      }
    };
    void refreshSession();
    addEventListener("classroom-session-changed", refreshSession);
    return () => {
      active = false;
      removeEventListener("classroom-session-changed", refreshSession);
    };
  }, [pathname]);

  const logout = async () => {
    await fetch("/api/session/logout", { method: "POST" }).catch(() => null);
    window.location.assign("/login");
  };
  useLayoutEffect(() => {
    // Route transitions can retain the previous page's scroll offset. Reset it
    // before measuring reveal targets so the next page starts with its primary
    // controls in view instead of leaving them above the observer viewport.
    window.scrollTo({ top: 0, left: 0, behavior: "auto" });

    const revealEnabled =
      "IntersectionObserver" in window &&
      !window.matchMedia("(prefers-reduced-motion: reduce)").matches;
    const registeredItems = new Set<HTMLElement>();
    const observer = revealEnabled
      ? new IntersectionObserver(
          (entries) =>
            entries.forEach((entry) => {
              if (!entry.isIntersecting) return;
              entry.target.classList.add("is-visible");
              observer?.unobserve(entry.target);
            }),
          { threshold: 0.12 },
        )
      : null;
    const registerRevealItem = (item: HTMLElement) => {
      if (registeredItems.has(item)) return;
      registeredItems.add(item);
      if (item.getBoundingClientRect().top <= window.innerHeight) {
        item.classList.add("is-visible");
      }
      observer?.observe(item);
    };
    const registerRevealTree = (node: Node) => {
      if (!(node instanceof HTMLElement)) return;
      if (node.matches("[data-reveal]")) registerRevealItem(node);
      node
        .querySelectorAll<HTMLElement>("[data-reveal]")
        .forEach(registerRevealItem);
    };
    const mutationObserver = revealEnabled
      ? new MutationObserver((records) => {
          records.forEach((record) =>
            record.addedNodes.forEach(registerRevealTree),
          );
        })
      : null;
    let revealFallback: number | undefined;
    if (observer) {
      document.documentElement.classList.add("reveal-enabled");
      document
        .querySelectorAll<HTMLElement>("[data-reveal]")
        .forEach(registerRevealItem);
      // Task pages replace their loading state with real controls after the
      // task lookup finishes. Observe those later insertions as well as the
      // elements that existed during the first layout pass.
      mutationObserver?.observe(document.body, { childList: true, subtree: true });
      // Motion is decorative. If the browser throttles or drops observer
      // callbacks, reveal every control instead of blocking the workflow.
      revealFallback = window.setTimeout(() => {
        document
          .querySelectorAll<HTMLElement>("[data-reveal]")
          .forEach((item) => item.classList.add("is-visible"));
      }, 1_200);
    }
    const onScroll = () => {
      const max = document.documentElement.scrollHeight - innerHeight;
      document.documentElement.style.setProperty("--scroll-progress", `${max > 0 ? scrollY / max : 0}`);
      document.documentElement.style.setProperty("--parallax-y", `${Math.min(scrollY * 0.06, 30)}px`);
    };
    onScroll();
    addEventListener("scroll", onScroll, { passive: true });
    return () => {
      observer?.disconnect();
      mutationObserver?.disconnect();
      if (revealFallback !== undefined) window.clearTimeout(revealFallback);
      document.documentElement.classList.remove("reveal-enabled");
      removeEventListener("scroll", onScroll);
    };
  }, [pathname]);

  const active = (href: string) => pathname === href || (href !== "/" && pathname.startsWith(href));
  return <>
    <div className="ambient-scene" aria-hidden="true"><span className="noise-layer" /></div>
    <div className="scroll-progress" aria-hidden="true"><span /></div>
      <div className="prototype-banner" role="status"><span>M1–M3 证据链 · 教师最终确认</span><strong>复盘、改进行动、两轮对比与多课程汇总均保留来源；合成验证会单独标注</strong></div>
    <header className="site-header">
      <Link className="brand" href="/" aria-label="返回产品首页"><span className="brand-mark" aria-hidden="true">课</span><span><strong>课堂复盘 Agent</strong><small>Evidence-led teaching review</small></span></Link>
      <nav aria-label="主导航">
        <Link className={`nav-link ${active("/") ? "active" : ""}`} href="/">产品首页</Link>
        <Link className={`nav-link ${active("/classrooms") ? "active" : ""}`} href="/classrooms">创建课堂</Link>
        <Link className={`nav-link ${active("/tasks") ? "active" : ""}`} href="/tasks/demo-review">复盘任务</Link>
        <Link className={`nav-link ${active("/improvements") ? "active" : ""}`} href="/improvements">改进循环</Link>
        <Link className={`nav-link ${active("/portfolio") ? "active" : ""}`} href="/portfolio">课程总览</Link>
      </nav>
      {sessionUser ? (
        <button className="user-chip" type="button" aria-label={`当前账号：${sessionUser.display_name}；点击退出`} onClick={logout} title="退出当前账号">
          <span>{sessionUser.display_name.slice(0, 1)}</span>{sessionUser.display_name}<small>退出</small>
        </button>
      ) : (
        <Link className="user-chip user-login-link" href={`/login?next=${encodeURIComponent(pathname)}`} aria-label="登录教师账号">
          <span>{sessionKnown ? "入" : "…"}</span>{sessionKnown ? "教师登录" : "检查会话"}
        </Link>
      )}
    </header>
    <main>{children}</main>
  </>;
}
