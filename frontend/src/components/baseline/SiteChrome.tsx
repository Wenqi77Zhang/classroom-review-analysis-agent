"use client";

import Link from "next/link";
import { usePathname } from "next/navigation";
import { useLayoutEffect, type ReactNode } from "react";

export function SiteChrome({ children }: { children: ReactNode }) {
  const pathname = usePathname();
  useLayoutEffect(() => {
    const items = Array.from(document.querySelectorAll<HTMLElement>("[data-reveal]"));
    const revealEnabled =
      "IntersectionObserver" in window &&
      !window.matchMedia("(prefers-reduced-motion: reduce)").matches;
    const observer = revealEnabled
      ? new IntersectionObserver(
          (entries) =>
            entries.forEach(
              (entry) =>
                entry.isIntersecting &&
                entry.target.classList.add("is-visible"),
            ),
          { threshold: 0.12 },
        )
      : null;
    if (observer) {
      document.documentElement.classList.add("reveal-enabled");
      items.forEach((item) => observer.observe(item));
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
      document.documentElement.classList.remove("reveal-enabled");
      removeEventListener("scroll", onScroll);
    };
  }, [pathname]);

  const active = (href: string) => pathname === href || (href !== "/" && pathname.startsWith(href));
  return <>
    <div className="ambient-scene" aria-hidden="true"><span className="noise-layer" /></div>
    <div className="scroll-progress" aria-hidden="true"><span /></div>
    <div className="prototype-banner" role="status"><span>第一版界面基准 · Mock 数据</span><strong>未连接真实后端，不代表核心功能已经实现</strong></div>
    <header className="site-header">
      <Link className="brand" href="/" aria-label="返回产品首页"><span className="brand-mark" aria-hidden="true">课</span><span><strong>课堂复盘 Agent</strong><small>Evidence-led teaching review</small></span></Link>
      <nav aria-label="主导航">
        <Link className={`nav-link ${active("/") ? "active" : ""}`} href="/">产品首页</Link>
        <Link className={`nav-link ${active("/classrooms") ? "active" : ""}`} href="/classrooms">创建课堂</Link>
        <Link className={`nav-link ${active("/tasks") ? "active" : ""}`} href="/tasks/demo-review">复盘任务</Link>
      </nav>
      <button className="user-chip" type="button" aria-label="当前为演示身份"><span>演</span>演示教师</button>
    </header>
    <main>{children}</main>
  </>;
}
