# 成员 5 贡献

## 2026-07-29：Agent 核心与报告门禁

已完成代码：

- 对齐成员 3 冻结 Schema 的分析契约、任务内证据与模型候选输出。
- 有限状态工作流和本地/云端 Provider 隐私路由。
- 通用课堂分析 Skill、任务/账号范围内证据检索和未知证据引用拦截。
- 一次规划、结构化模型调用、证据解析及 `InternalConclusionBatchWrite` 输出。
- `accepted/modified` 报告过滤、教师改写优先和来源/Trace 保留。
- Trace 事件及敏感字段脱敏。
- Agent 单元测试与“复核到报告”集成测试代码。

设计依据：`AGENTS.md`、`OWNERSHIP.md`、`docs/project-plan-v5.md`、`docs/interface-contracts.md` 和 `docs/acceptance-matrix.md`。跨模块字段没有另造名称，直接复用成员 3 的枚举、证据结构和内部结论写入 Schema。

人工边界核验：未修改成员 1、2 的前端，未实现成员 3 的 API 路由，也未替成员 4 实现 Worker、两类学科规则或专业证据校验器。成员 4 的三个文件继续保留 `TODO`，Agent 仅提供注入式集成点。

## PR #13 审查修复

- 对 `time_range` 在模型调用前筛选证据，并在结论落地前再次拒绝范围外引用。
- `bilingual_required=true` 时，范围内任一证据缺少非空逐句译文即拒绝调用模型。
- Trace 错误事件不再持久化 `str(error)`，只保存稳定错误类型、错误码和阶段。
- 不可信证据正文使用 Base64 UTF-8 数据区，Prompt 明确忽略数据中的命令；增加恶意逐字稿对抗测试。
- 专业 Skill 缺失时以 `SKILL_UNAVAILABLE` 明确失败，不再用通用 Skill 返回看似完整的结果。

测试状态：安装 Python 3.13.14 后，在仓库根目录 `.venv` 执行成员 5 定向测试，结果为 `20 passed`；独立发布克隆全仓复测为 `119 passed, 9 skipped`；`ruff check backend agent tests` 与路径级敏感文件检查通过。跳过项来自成员 4 Stage-0 Worker/视频链路和未配置 PostgreSQL 的既有集成测试。这只证明实际执行的离线契约、编排、安全门禁与过滤规则，不能写成真实模型、数据库集成或 E2E 已通过。

## 2026-07-30 合并状态补充

后端内部任务和结论写入路由现已通过 PR #18 合并；这只提供 Agent 可调用的接口，
不代表 Agent 已经自动运行。当前仍缺少持续领取 `analyze` 任务的运行器、真实 Worker
证据索引、真实模型配置、Trace 持久化、报告 API 和真实 E2E。专业 Skill 与证据门禁
已有确定性实现和自动化测试，但尚未在真实视频全链路中验收。

## 2026-07-30 暂代集成边界

成员 1 在独立分支暂代补齐 Worker→Agent 任务交接、Agent 领取与续租、结论写回、
完成状态和安全失败处理。该工作复用成员 5 已实现的编排、Provider、Skill、证据门禁
和 Trace 结构，不改写为成员 5 已独立完成的运行时工作，也不转移成员 5 对 Agent 与
质量的主责。分支合并、真实模型、真实证据和完整 E2E 通过前，Agent 仍不得标为完成。

后续状态：PR #26 已由成员 1 合并，暂代运行时集成到此结束；这部分不计作成员 5 独立
实现。成员 5 从真实模型 P0 继续。

## 2026-07-30：Ollama `qwen3.5:4b` 真实 Provider 接入

- 安装并选定本地 Ollama `qwen3.5:4b`，沿用 `LOCAL_MODEL_CHAT_COMPLETIONS_URL` 与
  `LOCAL_MODEL_NAME`，新增可选 `LOCAL_MODEL_REASONING_EFFORT=none`，不改跨模块 Schema。
- 实测简单严格 JSON Schema 请求成功；完整 Agent Schema 首轮暴露 thinking 空正文和
  Ollama 0.32.5 `failed to parse grammar`。按 Ollama 官方兼容能力关闭 thinking，并仅在
  本地模型生成期剥离其语法编译器不支持的描述、格式和长度约束；返回结果仍通过原完整
  Pydantic Schema、Skill 与证据 ID 门禁。
- 完整 Agent 编排真实调用返回 3 条结构化结论，记录模型 `qwen3.5:4b`、Prompt
  `analysis-v1`、Skill `common`、Trace，并验证所有引用保持在输入的毫秒时间范围内。
- 自动验证：成员 5 定向测试 `26 passed`，`ruff check agent tests/unit/test_agent.py`
  通过。完整 Agent 调用输入为明确的合成时间戳证据；团队临时网页因当前没有可用浏览器
  控制实例而未进入，因此真实视频逐字稿、后端写回和 P0 完整验收仍标记 `TODO`。

## 2026-07-30：Trace 与统一启动入口

- 复核已有 JSONL Trace Sink、运行器接线、后端任务/结论 `trace_id` 和前端展示，修复
  Trace 对逐字稿、Prompt、译文、引用正文和原始输入/响应只截断不全量脱敏的问题。
- Trace/后端定向测试 `113 passed`，前端包含 `trace_id` 展示在内的完整契约测试通过；
  错误继续只记录稳定错误类型、错误码和阶段。
- 将 `start.ps1` / `start.sh` 从阶段 0 占位替换为四服务入口；Worker/Agent 使用成员 5
  循环包装持续领取，令牌只从环境继承，日志进入忽略目录，父入口退出时清理子进程。
- PowerShell 两个脚本语法通过，启动脚本静态测试 `3 passed`，缺少 `.env` 时实测在启动
  任何服务前失败。因当前无真实 `.env`、PostgreSQL 和对象存储，本轮不把统一启动代码
  描述为完整环境已运行。

## 2026-07-30：发布门禁与剩余链路复核

- 将 `verify.ps1` / `verify.sh` 从阶段 0 棐架检查升级为 Python 全仓测试、Ruff、前端
  契约测试、TypeScript、生产构建、README 契约和敏感文件路径检查；无 `.git` 的源码
  快照使用排除虚拟环境、依赖、缓存、日志和临时目录的保守回退扫描。
- 本机 `verify.ps1` 初次结果为 `183 passed, 10 skipped`；恢复复核/报告专用回归并修复
  CI 后复跑为 `184 passed, 11 skipped`。Ruff、前端测试、类型检查和 Next.js 生产构建
  全部通过；`scripts/verify-readme.ps1` 再次执行同一发布门禁并通过。
  11 项跳过来自未配置 PostgreSQL 等外部环境条件，不能算数据库验收通过。
- 复核成员 3 新增接口后确认：教师复核/历史、报告保存读取以及仅收录
  `accepted/modified` 的数据库集成测试代码已经存在；当前机器没有 PostgreSQL/Docker，
  前端证据工作台也仍使用本地 Mock 状态和 `/reports/demo`，故只标记“局部通过”。
- 团队临时联调网址已提供，但当前会话没有可控 Chrome 或内置浏览器实例，未执行网页
  E2E；访问码未写入仓库。Quick Tunnel 建设按 `跳过.md` 由其他成员负责。
- 收口检查确认 Ollama 模型仍在、本机 PostgreSQL 5432 未监听；Agent、Trace、报告过滤和
  统一启动定向测试复跑 `36 passed`。
