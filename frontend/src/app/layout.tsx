import type { Metadata } from "next";
import "@fontsource-variable/fraunces/full.css";
import "lxgw-wenkai-screen-webfont/lxgwwenkaiscreenr.css";
import "./globals.css";

export const metadata: Metadata = {
  title: "课堂复盘 Agent",
  description: "上传课堂资料、核对证据并形成由教师确认的教学改进报告。",
};

export default function RootLayout({ children }: Readonly<{ children: React.ReactNode }>) {
  return (
    <html lang="zh-CN">
      <body>{children}</body>
    </html>
  );
}
