# 成员 5 发布门禁与联调记录

> 日期：2026-07-30
> 结论：本机代码发布门禁通过；真实基础设施与浏览器 E2E 未通过，不计入 M1 完成。

## 已实际执行

1. 本地 Ollama 0.32.5 与 `qwen3.5:4b` 真实 HTTP 调用：严格简单 Schema 通过；
   完整 Agent Schema 使用明确的合成时间戳证据返回 3 条结构化结论，模型、Prompt、
   Skill、Trace 和证据范围校验通过。
2. `powershell.exe -NoProfile -ExecutionPolicy Bypass -File .\verify.ps1`：
   Python `183 passed, 10 skipped`；Ruff、前端契约测试、TypeScript 和 Next.js 生产构建通过。
3. `powershell.exe -NoProfile -ExecutionPolicy Bypass -File .\scripts\verify-readme.ps1`：
   README 命令/模型契约及完整发布门禁通过。
4. `start.ps1` / `start.sh`：四服务静态覆盖、PowerShell 语法、服务令牌不进入命令行、
   子进程清理和缺 `.env` fail-closed 测试通过。
5. Trace：JSONL 持久化、任务面板 `trace_id` 展示以及逐字稿、译文、Prompt、原始输入/
   响应、引用正文和错误详情脱敏测试通过。
6. 文档同步后复跑 Agent、Trace、报告过滤和统一启动定向测试：`36 passed`。

## 条件跳过与阻塞

- 当前机器没有 PostgreSQL、Docker、真实 `.env` 和对象存储配置；10 项环境条件测试跳过，
  因此教师复核/历史和报告持久化只具备代码与测试用例证据，没有本轮数据库执行证据。
- 团队已提供临时网页联调入口，但当前会话没有可控 Chrome 或内置浏览器实例，无法执行
  成功流程、失败/重试、双账号、重启恢复、桌面/手机和常见浏览器 E2E；访问码不入库。
- `agent/skills/computer_ai.py`、`agent/skills/humanities.py` 和
  `agent/validators/evidence_gate.py` 仍由成员 4 负责且保持 `TODO`。成员 5 的条件加载、
  契约校验和缺失时 fail-closed 集成点已就绪，不越权代写成员 4 实现。
- 前端证据工作台仍使用 Mock 结论/复核状态和 `/reports/demo`；真实复核与报告页面接线属于
  成员 1/2，成员 5 仅记录阻塞，不改动其接口或页面。
- Cloudflare Quick Tunnel 建设依据 `跳过.md` 由其他成员接手，本记录不把临时入口称为正式部署。

## 复测准入条件

1. 提供可用 PostgreSQL、对象存储与获授权的两段不同真实课堂输入。
2. 成员 4 完成两类专业 Skill、证据校验器、翻译/证据索引并通过本人模块测试。
3. 成员 1/2 将真实结论、复核历史和持久化报告接入页面。
4. 提供可控浏览器实例后，按 `docs/validation-plan.md` 执行六项人工流程并记录脱敏 Trace。
