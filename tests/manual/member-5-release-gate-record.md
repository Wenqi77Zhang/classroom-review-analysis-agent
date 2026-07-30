# 成员 5 发布门禁与联调记录

> 日期：2026-07-30
> 结论：本机代码发布门禁通过；真实基础设施与浏览器 E2E 未通过，不计入 M1 完成。

## 已实际执行

1. 本地 Ollama 0.32.5 与 `qwen3.5:4b` 真实 HTTP 调用：严格简单 Schema 通过；
   完整 Agent Schema 使用明确的合成时间戳证据返回 3 条结构化结论，模型、Prompt、
   Skill、Trace 和证据范围校验通过。
2. `powershell.exe -NoProfile -ExecutionPolicy Bypass -File .\verify.ps1`：
   初次结果为 Python `183 passed, 10 skipped`；恢复复核/报告专用回归并修复 CI 后复跑为
   `184 passed, 11 skipped`。Ruff、前端契约测试、TypeScript 和 Next.js 生产构建通过。
3. `powershell.exe -NoProfile -ExecutionPolicy Bypass -File .\scripts\verify-readme.ps1`：
   README 命令/模型契约及完整发布门禁通过。
4. `start.ps1` / `start.sh`：四服务静态覆盖、PowerShell 语法、服务令牌不进入命令行、
   子进程清理和缺 `.env` fail-closed 测试通过。
5. Trace：JSONL 持久化、任务面板 `trace_id` 展示以及逐字稿、译文、Prompt、原始输入/
   响应、引用正文和错误详情脱敏测试通过。
6. 文档同步后复跑 Agent、Trace、报告过滤和统一启动定向测试：`36 passed`。
7. PR #31 GitHub Actions：scaffold、backend-check、frontend-check 全绿；PostgreSQL
   后端全仓 `190 passed, 5 skipped`，Ruff 通过。
8. 同步已修复并合并的 PR #27 后，两类专业 Skill、证据校验器及 Worker 新阶段专项
   `63 passed`；完整发布门禁更新为 Python `265 passed, 11 skipped`，前端测试、类型检查和构建通过。

## 条件跳过与阻塞

- 当前机器没有 PostgreSQL、Docker、真实 `.env` 和对象存储配置；本机环境条件测试跳过。
  教师复核/历史和报告持久化已由 GitHub PostgreSQL CI 复验，但完整本地/部署运行仍未执行。
- 团队已提供临时网页联调入口，但当前会话没有可控 Chrome 或内置浏览器实例，无法执行
  成功流程、失败/重试、双账号、重启恢复、桌面/手机和常见浏览器 E2E；访问码不入库。
- PR #27 已完成并合并两类专业 Skill 与专业证据校验器；真实 Translation Provider、
  课件/证据后端写回和远程纵向阶段仍未完成，不能用 fake adapter 或内部草稿冒充真实链路。
- 前端证据工作台仍使用 Mock 结论/复核状态和 `/reports/demo`；真实复核与报告页面接线属于
  成员 1/2，成员 5 仅记录阻塞，不改动其接口或页面。
- PR #30 的 Cloudflare Quick Tunnel 与访问门禁已恢复保留；当前没有正在运行的完整服务和
  本次入口地址，因此未执行远程网页验收，也不把临时入口称为正式部署。

## 复测准入条件

1. 提供可用 PostgreSQL、对象存储与获授权的两段不同真实课堂输入。
2. 成员 4/3 接通真实 Translation Provider、课件/证据后端写回和第二段远程输入；
   专业 Skill 与证据校验器已完成自动化，不再列为准入阻塞。
3. 成员 1/2 将真实结论、复核历史和持久化报告接入页面。
4. 提供可控浏览器实例后，按 `docs/validation-plan.md` 执行六项人工流程并记录脱敏 Trace。
