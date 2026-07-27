"use client";

import Link from "next/link";
import { useState } from "react";
import { SiteChrome } from "./SiteChrome";

export function HomeBaseline() {
  const [playing, setPlaying] = useState(false);
  return <SiteChrome><section className="view active" aria-labelledby="home-title">
    <div className="hero">
      <div className="hero-copy" data-reveal>
        <p className="eyebrow">AI 版中国大学 MOOC · 课堂复盘</p>
        <h1 className="editorial-title" id="home-title"><span className="cn-primary">让课堂</span><span className="en-aside">SEE THE<br />CLASSROOM</span><span className="cn-secondary">被重新看见。</span><span className="en-foot">ANEW · REFLECT · IMPROVE</span><span className="cn-tail">让改进，有迹可循。</span></h1>
        <div className="hero-actions"><Link className="button primary" href="/classrooms">创建一次课堂复盘 <span aria-hidden>→</span></Link><a className="button secondary" href="#workflow">先了解完整流程</a></div>
        <ul className="trust-list" aria-label="产品边界"><li>无证据，不进入报告</li><li>教师始终保留最终决定权</li><li>不用于自动给教师打分</li></ul>
      </div>
      <aside className="hero-proof" aria-label="产品演示视频" data-reveal data-parallax>
        <div className={`video-frame ${playing ? "playing" : ""}`}><div className="video-aurora" aria-hidden /><span className="video-label">PRODUCT FILM · 01:28</span><button type="button" className="play-button" onClick={() => setPlaying((value) => !value)} aria-label={playing ? "暂停产品演示视频" : "播放产品演示视频"}><span aria-hidden>{playing ? "Ⅱ" : "▶"}</span></button><div className="video-caption"><span>课堂复盘 Agent</span><strong>从一段课堂，到一份可核验的改进记录</strong></div><div className="timeline"><span /></div></div>
      </aside>
    </div>
    <aside className="product-note" data-reveal aria-label="产品流程简述"><span className="product-note-label">HOW IT WORKS</span><p>上传课堂视频、课件或逐字稿，定位值得复盘的片段；教师核对原文、修改结论，再导出可信的改进报告。</p><span className="product-note-index">INPUT · REVIEW · REPORT</span></aside>
    <div className="value-grid"><article data-reveal><span className="card-number">01</span><h2>先确认，再分析</h2><p>Agent 通过追问形成可修改的分析契约，避免系统擅自决定复盘重点。</p></article><article data-reveal><span className="card-number">02</span><h2>证据与结论联动</h2><p>事实、判断和建议分层呈现，每条内容连接视频时间、原文或课件页。</p></article><article data-reveal><span className="card-number">03</span><h2>教师决定报告内容</h2><p>接受、修改或驳回分析，只有人工确认的内容才能进入最终报告。</p></article></div>
    <section className="workflow-section" id="workflow"><div data-reveal><p className="eyebrow">单节课堂 · M1 核心链路</p><h2>从一个真实问题开始，而不是从功能清单开始。</h2></div><ol className="workflow-steps" data-reveal><li><span>1</span>说清复盘目标</li><li><span>2</span>确认分析契约</li><li><span>3</span>上传课堂资料</li><li><span>4</span>核对证据与结论</li><li><span>5</span>确认并导出报告</li></ol></section>
  </section></SiteChrome>;
}
