# AI 协作记录

| 日期 | 成员 | 任务 | 关键提示词 | AI 输出摘要 | 人工核验 | 修改原因 | 最终处理 | 证据链接 |
|---|---|---|---|---|---|---|---|---|
| 2026-07-30 | 成员 3 + Codex | Day 4 复核、报告持久化与最小审计 | “优先完成可演示 MVP：教师审核结论后，报告只能持久化已接受或已修改的结论。” | 实现复核决定/历史、课堂报告 GET/PUT、报告关联门禁及脱敏审计；新增真实 PostgreSQL HTTP 集成测试 | 已验证定向 PostgreSQL 测试与 Ruff；提交前将重跑全量后端与前端门禁 | 单次 flush 直接播种外键会造成顺序错误；新报告在 flush 后再写异步关系会触发 `MissingGreenlet` | 按父子顺序 flush；新报告在首次 flush 前注入结论，既有报告以 `selectinload` 加载；服务端导出和浏览器端接线仍明确为待完成 | `backend/app/repositories/reviews.py`、`tests/integration/test_review_report_api.py` |
| 2026-07-30 | 成员 1 + Codex | 同步 Day 3 与 M1 项目说明 | “只更新 `.md` 和其他说明性文件；已合并代码算完成，其他对话实现标记为进行中” | 盘点 `main@1e52c9c` 的前端、后端、Worker、Agent 与测试事实；新增统一进度页并同步 README、v5 计划、验收矩阵、评分卡、模块指南、手工记录和报告材料 | 成员 1 确认状态口径；Codex 对照合并提交、API 路由、Worker/Agent 入口和现有测试记录，执行文档一致性扫描与 `git diff --check` | 多份指南仍把已经合并的上传、任务和结论接口写成未实现；同时必须防止把其他对话正在实现的 Worker/B2 集成提前写成完成 | 历史记录保留原结论并增加时间说明；当前文档统一区分已合并、局部验证、进行中和未通过，不修改业务代码 | `docs/current-progress.md`、`docs/acceptance-matrix.md`、`reports/group-report.md` |
| 2026-07-30 | 成员 1 | 修复成员 2 证据组件回归并接通真实上传前端 | “先修复 `aba-evidence-v2` 的证据组件问题，然后把真实上传链路也接通” | 保留成员 2 的证据定位与重置意图，恢复受控复核状态、修改/驳回说明和报告门禁；新增 Next.js 同源 BFF、HttpOnly 演示会话、真实课程/课堂创建、预签名直传、XHR 进度、后端 HEAD complete、失败清理、任务创建与真实状态轮询 | 成员 1 确认从成员 2 分支派生独立修复分支；前端契约测试、TypeScript 和生产构建通过；PostgreSQL、后端路由及真实 B2 presign/PUT/HEAD/download/delete 由同轮协作验收独立通过；沙箱外网套接字限制下未把浏览器真实视频复跑冒充已完成 | 成员 2 v2 把复核状态移入子组件，导致父页面、报告门禁和既有测试失联；上传按钮仍被硬编码禁用。联调又发现 204 响应被 BFF 附加空 body、移除已上传文件会遗留对象、任务可重复创建 | 修复公共组件契约并补定位/重置回归测试；JWT 仅存 HttpOnly Cookie，B2 长期密钥不进前端；失败对象尽力删除，任务创建后锁定入口；证据和报告未完成部分继续标 Mock | `frontend/src/components/evidence/`、`frontend/src/components/upload/UploadPanel.tsx`、`frontend/src/app/api/`、`frontend/src/lib/api.ts`、`frontend/tests/business-api.test.mjs` |
| 2026-07-30 | 成员 1 | 协作补齐平台后端最短链路 | “完成对象存储与上传接口、任务创建/查询/事件/重试、Worker/Agent 内部写入，并接通课堂—上传—任务—结果最短链路” | 实现可替换的 S3 Provider、B2 预签名上传与 HEAD 核验、任务租约和状态事件、逐字稿与证据化结论持久化边界及 PostgreSQL 集成测试 | 人工核对 B2 私有 Bucket CORS；审查账号/任务/文件/逐字稿证据归属、Worker 与 Agent 阶段权限、失败重试和事务边界；本机正常权限下执行 126 项通过、11 项因缺少 PostgreSQL 跳过，Ruff 通过 | 初版需防止 Worker 领取 analyze、Agent 接管后遗留 Worker 租约、逐字稿越过媒体时长，以及范围外文件或句子被写成当前任务证据 | 增加 fail-closed 校验与回归场景；真实 PostgreSQL 用例交由 PR CI 执行；不把接口测试冒充真实视频处理或前端端到端 | `backend/app/api/uploads.py`、`backend/app/api/tasks.py`、`backend/app/api/transcripts.py`、`backend/app/api/analyses.py`、`tests/integration/test_processing_api.py` |
| 2026-07-30 | 成员 4 + Codex | 修复 PR #14 剩余 Worker 阻断并补真实视频证据 | “一个一个问题修复；先合最新 main；不得强推；补 heartbeat、严格时间戳、清理失败、真实来源、HttpJobStore 测试和 PR 记录” | 普通合并最新 `main`；实现非终态阶段交接、HTTP claim 与周期 heartbeat、停止后禁止持久化、严格毫秒证据区间、可重试清理失败、稳定错误码和内部 HTTP 契约测试；补两段公开课程来源与脱敏 ASR 摘要 | 成员 4 人工确认两条中国大学 MOOC 课程 URL 与本地视频来源一致，并确认仅作本地功能验收、不主张开放版权；自动验证：Worker 单元与真实视频集成共 32 项通过，全仓 157 项通过/9 项条件跳过，Ruff、脚手架、敏感文件、前端测试、TypeScript 和生产构建通过；成员 4 尚未逐行人工审计代码 | 首次真实复跑发现 Whisper 默认温度回退会造成分段不稳定，固定温度后又暴露长音频尾部提示重复；关闭两种非确定/幻觉路径。严格秒级比较还把 `359.64000000000004` 与 `359.64` 误判为重叠，改为按冻结的毫秒整数 Schema 比较，真实零区间、倒序、重叠和越界仍全部拒绝 | 采纳自动化验证通过的修复；视频、完整逐字稿、模型和本地安装的辅助 skill 保持未跟踪；远程入口当前要求对象存储已挂载到 `object_root`，翻译、课件处理和证据索引继续如实标记为未完成 | PR #14；提交 `01956b9`、`2972cc4`、`e6294af`；`tests/fixtures/fixture-catalog.md` |
| 2026-07-30 | 成员 1 | 补充 PR #16 证据上限筛选顺序回归测试 | “验证超过 200 条范围外证据不会挤掉后续范围内有效证据” | 增加 201 条范围外证据位于有效证据之前的回归场景 | 核对模型 Prompt 仍包含范围内证据，且不包含任一范围外证据 | 防止未来把 200 条上限错误地提前到身份与时间范围过滤之前 | 保留先过滤、后截断的安全顺序并纳入自动化测试 | `tests/unit/test_agent.py`、PR #16 |
| 2026-07-30 | 成员 5 + Codex | PR #13 合并后跨账号证据隔离热修复 | “`_select_evidence()` 未筛 `task_id + owner_id`，从最新 main 新建热修复 PR，只修复对应问题” | 在模型调用前按当前任务与账号过滤原始证据；增加校验后混入外部证据的 Prompt 泄漏测试，以及模型引用已过滤外部证据的拒绝测试 | 从最新 `main` 复现防御缺口；验证外部证据 ID 与 Base64 正文均不进入模型 Prompt，外部引用返回 `EVIDENCE_NOT_FOUND`；执行 Agent 定向、全仓、Ruff、敏感检查和 GitHub CI | 首版虽创建了任务范围内 `EvidenceRetriever`，但 `_select_evidence()` 仍直接遍历原列表，模型调用发生在输出引用校验之前 | 仅修改证据选择过滤与对应测试；不变更契约、Prompt、Provider 或其他成员模块 | `agent/orchestrator.py`、`tests/unit/test_agent.py`、热修复 PR |
| 2026-07-29 | 成员 5 + Codex | 修复 PR #13 契约与隐私阻断 | “范围/双语硬门禁、Trace 不保存异常消息、不可信逐字稿 Prompt 边界、专业 Skill 缺失不得伪成功” | 增加范围筛选和引用复核、双语译文校验、稳定 Agent 错误码、Base64 证据数据区、专业 Skill fail-closed 及 7 项回归/对抗测试 | 线程感知读取确认 4 项均为未解决的 CHANGES_REQUESTED；定向 20 项、全仓 119 项通过/9 项跳过，Ruff 与路径级敏感检查通过 | 首版只校验范围参数、Trace 记录 `str(error)`、JSON 中放原始证据且专业 Skill 静默降级，均不足以落实教师契约和隐私边界 | 四项全部修改后采纳；PostgreSQL 完整测试交由 PR CI 服务执行，真实模型/Worker/E2E 仍保持 `TODO` | PR #13、`agent/orchestrator.py`、`agent/observability/tracing.py`、`agent/prompts/analysis.md`、`tests/unit/test_agent.py` |
| 2026-07-29 | 成员 5 + Codex | 按成员 5 边界实现 Agent 核心与报告门禁 | “只完成成员 5；尽量不调整其他成员内容；接口变量名称以其他成员为准” | 生成分析契约、状态机、Provider 隐私路由、通用 Skill、证据检索、协调器、报告过滤、Trace 和对应测试 | 逐项对照 `OWNERSHIP.md`、成员 5 责任包、成员 3 Schema 与接口契约；确认未改前端、后端路由、Worker 和成员 4 占位；安装 Python 3.13.14 并在独立发布克隆验证，全仓 112 项通过/9 项跳过，Ruff 与路径级敏感文件检查通过 | 初始计划可能把成员 4 的学科规则/校验器一并实现，按责任边界改成可注入集成点；Ruff 首轮发现 5 个导入/无效注释格式问题并修正；禁止用假 Provider 结果宣称真实模型已运行 | 代码与离线测试采纳；真实 API、Worker、模型与 E2E 继续 `TODO` | `agent/`、`tests/unit/test_agent.py`、`tests/integration/test_review_to_report.py`、`reports/contributions/member-5.md` |
| 2026-07-29 | 成员 2 + 成员 1 + Codex | 无共同历史的证据工作台审核与安全整合 | “审核通过后直接协助完成 `--allow-unrelated-histories` 合并” | 审核成员 2 四个证据组件；设计保留第二父历史但不导入旧快照的合并；补类型、Mock 边界、复核状态、响应式样式与静态测试 | 成员 1 确认采用审核后合并；`npm test` 四组通过，TypeScript 检查和 Next.js 生产构建通过 | 原分支会回滚后端、迁移和 CI；组件存在 `onSeek` 类型错误、缺失测试视频、固定结论冒充真实结果及复核无状态边界 | 用 `-s ours --allow-unrelated-histories` 保留成员 2 历史，再在合并提交中协作整合修复；不把修复冒充成员 2 独立成果 | `aba-evidence` 提交 `c2f7b445`、`frontend/src/components/evidence/`、`frontend/tests/evidence-workbench.test.mjs` |
| 2026-07-29 | 成员 3 | Day 3 ORM 与首个数据库迁移 | “拉取最新 main；实现 PostgreSQL ORM、Alembic 首迁移与持久化测试；不改冻结 Schema” | 生成 15 张表的模型、异步迁移环境、迁移与结构/读写测试 | 人工核对 owner 字段、外键删除策略；真实 PostgreSQL 执行升降级、92 项测试及 `alembic check` | 首版关联表误用 `mapped_column`；INI 中文注释在 Windows 触发 GBK 解码失败；关系存在多外键歧义 | 改用 Core `Column`、纯 ASCII INI、显式 `foreign_keys`，增加 mapper/真实读写测试 | `member-3/day2-persistence`（分支名误写 Day 2，实际为 Day 3）、迁移 `0b5123afcf23` |
| 2026-07-29 | 成员 3 | 认证、服务身份与账号隔离基础 | “实现密码/JWT、请求依赖、服务令牌最小权限和真实两账号隔离；暂不扩展未确认的登录请求 Schema” | Argon2/JWT 原语、当前用户依赖、服务身份识别、owner-scoped 查询与 7 项测试 | 使用真实 PostgreSQL 建立两个账号及课堂；验证本人可读、他人和随机 UUID 均为 NotFound；JWT 覆盖过期和错误签名 | 测试首版用 `model_copy` 绕过 Pydantic 产生非法 SecretStr 状态，改为经正常配置校验构造 | 修改后采纳；HTTP 登录路由仍如实标为未实现 | `backend/app/api/auth.py`、`tests/integration/test_account_isolation.py` |
| 2026-07-29 | 成员 3 | 修复 PR #10 backend-check | “检查 failing check；修复 CI 并在当前 PR 说明” | PostgreSQL 17 service、迁移/漂移步骤、集成测试专用 `TEST_DATABASE_URL` | 读取失败 job 原始日志；本地创建临时 CI 数据库，按迁移→检查→99 项测试→Ruff 顺序验证，完成后删除临时库和用户 | 首版把完整配置放 job 级 env，污染 6 项配置默认/缺失测试；改为迁移步骤局部配置，集成测试只读取专用数据库 URL | 修改后采纳并更新当前 PR | `.github/workflows/ci.yml`、PR #10 CI |
| 2026-07-29 | 成员 3 | 登录与课程/课堂基础 API | “从 PR #10 派生后续分支；按成员 1 已确认页面字段实现真实登录与课堂 API” | 认证/身份 Schema、身份仓储、课程创建/列表、课堂创建/列表/读取/修改及真实 HTTP 隔离测试 | OpenAPI 路径检查；临时 PostgreSQL 执行迁移后跑登录→课程→课堂→越权→修改流程 | 首版形成循环依赖并在 PATCH 后触发 MissingGreenlet；PR #12 审核又发现标题可被写为 null/空串、删除会绕过对象清理与审计 | 拆出 authentication 服务、PATCH 后 refresh；Schema 层拒绝必填字段 null/空白，保留 description 清空语义；对象清理与审计完成前 DELETE 返回 `STATE_CONFLICT` | `backend/app/api/auth.py`、`backend/app/api/classrooms.py`、`tests/integration/test_auth_classroom_api.py` |
| 2026-07-26 | 成员 3 | 通读仓库、确定成员 3 责任范围与四天节奏 | "我现在作为成员三参与到这个多 Agent 项目中，请你完整地阅读这个初步的 GitHub 仓库，告诉我我具体的任务内容以及要用到哪些东西" | 责任边界、主责文件清单、技术选型与依据、四天逐日计划 | 结论逐条对回 `project-plan-v5.md` §4「成员 3」、§6、§8、§9 与 Issue #3 原文 | 无 | 采纳 | Issue #3、`docs/project-plan-v5.md` |
| 2026-07-26 | 成员 3 | 冻结跨模块 Schema 契约 v1 | 承接上一条已确认的计划，要求"契约优先，先写 schemas 再写路由" | 4 个 Schema 文件、枚举表、错误码表、任务状态机、端点契约、内部接口族 | 自动化：52 项测试全过；契约条款逐条对回 `interface-contracts.md` 原有强制字段 | 4 项偏离阶段 0 草案之处未擅自定稿 | 采纳，并在 `interface-contracts.md` 变更节列出待成员 1/2/4/5 确认 | `backend/app/schemas/`、`docs/interface-contracts.md` |
| 2026-07-26 | 成员 3 | 配置校验、异步数据库、领域异常、FastAPI 应用 | 同上计划的 Day 1「基础设施」与「认证权限骨架」时间块 | `config.py`、`database.py`、`errors.py`、`main.py` | 自动化：`/health` 与 `/health/ready` 实连 PostgreSQL 17.10 通过；CORS 允许/拒绝、错误外层、trace_id 透传均有测试 | 见下方「被修改或推翻的 AI 输出」第 3、4 条 | 修改后采纳 | `backend/app/`、`tests/unit/test_backend.py` |
| 2026-07-26 | 成员 3 | 后端测试 | 要求把临时验证脚本转成仓库内可复现测试 | `tests/unit/test_backend.py`，初版 52 项 | 自动化：`pytest -q` → 52 passed | 无 | 采纳 | `tests/unit/test_backend.py` |
| 2026-07-26 | 成员 3 | 按 PR #6 审查意见修正 | "这次 PR 被审查之后没有被合并，其中给出了一些审查意见，请你看一下，然后给出解决方案" | 逐条修正状态集合语义、内部逐字稿校验、`modified` 状态闭合、服务令牌拆分、上传核对契约、trace_id 约束、文档数字同步 | 自动化：`pytest -q` → 85 passed；`ruff` 通过 | 均为 AI 先前实现中的真实缺陷，由成员 1 独立审查发现 | 8 项全部采纳并补回归测试。第 6 项一度因 Docker 引擎崩溃而阻塞，未按猜测填写版本号；排查出僵尸 socket 后读到真实版本才固定 | `reports/contributions/member-3.md` 第四节 |
| 2026-07-26 | 成员 3 | 本地环境与基础设施 | "帮我装"、"我的储存空间已经严重不足了，你能不能把 Docker 安装在 D 盘上？"、"已重启" | Python 3.13 安装、C 盘清理、Docker Desktop 装到 D 盘、WSL2 修复、compose 加入 MinIO | 自动化：`wsl --status` 退出码 0、`docker info` 可用、两容器 healthy、桶已建、`D:\Docker\wsl` 已生成 | 见下方第 5 条：AI 原先归因 UAC 未批准，实测证伪 | 修改后采纳 | `docker-compose.yml`、`backend/backend-module-guide.md` |
| 2026-07-26 | 成员 3 | 合并 `main` 并对齐 B2 对象存储方案 | "推送"、"合并对齐 + 按 B2 调整" | 识别出远端 main 已定 B2 方案且与本分支 5 个文件重叠；统一变量名、修正 path-style 默认值、MinIO 降级为离线替代品 | 自动化：56 项测试全过、`setup.ps1` 端到端退出 0、无残留冲突标记 | AI 原方案基于本地 MinIO，与团队已定的 B2 方案冲突，以 `main` 为准 | 修改后采纳；Provider 抽象层与 B2 凭据列入已知限制 | `backend/app/config.py`、`docs/interface-contracts.md` |
| 2026-07-26 | 成员 3 | 缺陷修复（4 个） | 无专门提示词；均在执行上述计划过程中由实际运行或自建测试暴露 | `.ps1` 编码修复、`verify` README 检查改用 `git ls-files`、日志脱敏两处修正 | 自动化：`setup.ps1` 跑通、`verify.ps1`/`verify.sh` 在 `.pytest_cache/README.md` 存在时退出 0、脱敏回归用例通过 | 见下方第 1、2 条 | 修改后采纳；涉及成员 5 主责文件的部分标注待确认 | `reports/contributions/member-3.md` 第 5 项 |
| 2026-07-27 | 成员 1 + Codex | UI Baseline v1 设计迭代与正式迁移 | 雾境画廊、朦胧竹影、Glassmorphism、霞鹜文楷、Fraunces、字号可读性、Mock 边界、Next.js 迁移 | AI 生成临时原型、竹影背景、Next.js 组件、样式和检查脚本 | 成员 1 多轮标注布局、色彩、背景、字号和文案，最终确认 v1；自动执行测试、类型检查、生产构建和依赖审计 | 初稿过于扁平且像 PPT；背景、留白、层级、字体与色调不符合目标；TypeScript 7 与 Next 不兼容；依赖出现高危公告 | 采用 v2 竹影背景和雾面玻璃基准；固定 TypeScript 6；用 overrides 升级 PostCSS/Sharp；0 个已知漏洞；保留 Mock 标识并移交成员 2 | `docs/ui-baseline-v1.md`、`frontend/src/components/baseline/`、构建日志 |
| 2026-07-28 | 成员 1 + Codex | Day 1 上传入口、诚实状态边界与合并门禁补强 | 文件分类、扩展名/大小校验、视频证据门禁、预签名接口、禁止伪造进度、GitHub CI | AI 实现上传组件、共享样式、静态契约测试和前端 CI job | 核对 `interface-contracts.md`、`uploads.py` 与 `storage.py`，确认真实接口仍为 TODO；成员 1 继续按已确认产品边界推进，并发现原 CI 只检查脚手架和敏感文件 | 若直接模拟上传会违反网页真实性要求；若等待后端则流程前端无入口；若不补 CI，绿色状态不能证明前端测试、类型和构建通过 | 完成本地选择与校验，禁用真实上传按钮并标注服务未接通；在成员 5 质量交付范围内协作补充 `frontend-check`，待成员 3 冻结 Schema 后接入 | `frontend/src/components/upload/UploadPanel.tsx`、`frontend/tests/upload-panel.test.mjs`、`.github/workflows/ci.yml` |
| 2026-07-29 | 成员 1 + Codex | PR #6 后端基础集成复核与冲突处理 | 复核成员 3 修订版是否满足合并条件；验证日志脱敏、后端测试、CI 和文本冲突 | AI 辅助比较 PR、复现合并冲突、构造异常日志泄密用例并提出最终文本脱敏方案 | 成员 1 决定暂不直接合并；在独立环境复跑后端测试和 Ruff，并确认 AI 协作记录必须保留双方历史 | 原实现只过滤 `LogRecord.msg/args`，Formatter 后生成的 traceback 仍可能泄露令牌；绿色 CI 也未执行后端测试 | 保留成员 3 原成果；由成员 1 协作补异常堆栈脱敏、回归测试和后端 CI，再按真实结果决定合并 | PR #6、`backend/app/main.py`、`tests/unit/test_backend.py`、`.github/workflows/ci.yml` |
| 2026-07-29 | 成员 1 + Codex | 前端冻结契约对齐与后端健康检查 | 仅接入已真实实现的后端接口；修正资料类型和大小漂移；不得把健康检查描述为上传已接通 | AI 比对前后端契约、实现 Next.js 同源健康代理、共享类型、状态文案和契约测试 | 成员 1 确认采用最小衔接范围；自动执行 3 组前端测试、TypeScript 类型检查和 Next.js 生产构建 | 初版补丁的新路由尾部因 diff 行数误算被截断，单元测试未覆盖语法完整性，但类型检查将其拦截 | 补齐路由并从头复跑三项门禁，全部通过；上传按钮继续禁用，页面明确区分“基础服务可达”和“上传接口待实现” | `frontend/src/app/api/backend-health/route.ts`、`frontend/src/components/upload/UploadPanel.tsx`、`frontend/tests/backend-health.test.mjs` |
| 2026-07-29 | 成员 1 + Codex | PR #10 账号隔离与审计保留复核修复 | 复核 owner 隔离是否不可绕过；删除账号不得同步销毁审计；合入最新 main 后复测 | AI 审计 ORM/迁移，补复合外键、跨账号写入测试、审计限制删除、暂行保留说明和迁移往返 CI | 成员 1 确认继续处理 PR #10；本地静态检查和单元测试已执行；首轮新 CI 的 PostgreSQL 写入测试、漂移检查与 Ruff 通过后，成员 1 继续要求补迁移降级实测；最终 CI 为 106 项通过、4 项跳过，迁移往返与前端门禁均通过 | 原实现只给表加 `owner_id` 和可选辅助函数，关联外键仍仅校验资源 ID；审计 owner 使用级联删除；修改首迁移后的首轮 CI 只测升级未测降级 | 关键父子/关联关系改为 `(资源 ID, owner_id)` 数据库约束；有审计记录的账号只能停用；CI 补为 `upgrade → downgrade → upgrade`；正式保留期限和匿名化流程待成员 1 后续确认 | `backend/app/models/`、`backend/migrations/versions/0b5123afcf23_initial_persistence_schema.py`、`tests/integration/test_account_isolation.py`、`.github/workflows/ci.yml` |
| 2026-07-29 | 成员 1 + Codex | Day 2 完整流程前端与报告边界 | 按 v5 审查输入、追问、契约、视频门禁、任务状态、证据复核和报告；不得把本地状态冒充真实后端 | AI 辅助实现任务面板、报告编辑/预览、会话级复核交接、测试与样式 | 成员 1 确认分三小步推进，并保持上传、Worker、Agent、持久化和 DOCX 未实现标识；自动测试、类型检查、生产构建和 Git 空白检查通过 | 初版流程首次输入后直接形成契约；没有视频也能切换任务状态；复核结果没有跨页传递；新增门禁后旧测试仍匹配组件旧参数顺序 | 增加一次明确追问、视频就绪门禁、失败重试预览、`sessionStorage` 演示交接和修改说明门禁；更新旧测试后全量复跑通过；Edge 无头截图因 GPU 沙箱崩溃，保留人工视觉复核限制 | `frontend/src/components/baseline/ReviewTaskBaseline.tsx`、`frontend/src/components/tasks/TaskStatusPanel.tsx`、`frontend/src/components/reports/ReportEditor.tsx`、`tests/manual/day2-member1-flow-audit.md` |
| 2026-07-29 | 成员 1 + Codex | PR #15 合并前状态机复核 | 检查失败与重试状态是否符合真实阶段依赖 | AI 定位任务阶段索引逻辑并提出阻断问题 | 成员 1 授权修复；以流程因果关系复核“ASR 失败后翻译与分析不得继续” | 初版失败状态只覆盖 ASR 卡片，但沿用最后阶段索引，导致下游显示完成或处理中 | 失败索引固定为 ASR；下游统一等待；增加回归断言并重跑门禁 | `frontend/src/components/tasks/TaskStatusPanel.tsx`、`frontend/tests/task-status-panel.test.mjs` |
| 2026-07-30 | 成员 1 + Codex | PR #14 Worker 安全复核 | 核验长任务租约、服务令牌输入和媒体错误信息是否满足隐私与并发边界 | AI 审查 Worker/后端冻结契约，补 CLI 密钥与错误事件泄露回归用例并形成跨分支门禁 | 成员 1 要求拉取最新进展并处理 PR #14；明确保留成员 4 的真实媒体链路成果归属 | `--service-token` 会进入 Shell 历史与进程列表；FFmpeg stderr 可能把本地路径、对象键或租户信息写入 TaskEvent；Heartbeat 客户端检查不能替代服务端租约持有者校验 | 移除 CLI 令牌参数，仅从环境注入；持久化事件只使用稳定公开错误文案；服务端过期租约拒写列为成员 1/3 后端集成门禁，不虚报为 PR #14 已完成 | `worker/runner.py`、`worker/errors.py`、`worker/pipeline.py`、`tests/unit/test_worker.py`、`docs/interface-contracts.md` |

禁止把未经人工核验的 AI 内容直接写成事实、引用、测试结果或个人独立成果。

---

## 2026-07-26 成员 3 补充说明

### 使用的 AI 工具

Claude Code（Anthropic，模型 Opus 5），在本机以命令行 Agent 方式运行，可读写仓库文件、
执行 PowerShell/Bash 命令与容器命令。

### 核验方式与当前核验状态

**必须如实区分两件事：**

- **已完成的自动化核验**：85 项 pytest 断言、`ruff check`、`verify.ps1` / `verify.sh` /
  `check-secrets` 退出码、`docker compose ps` 健康状态、`psql` 版本输出、
  `/health/ready` 实连数据库。这些是可复现的机器验证，命令与输出记录在
  `reports/contributions/member-3.md` 第 4 项。
- **尚未完成的人工核验**：成员 3 本人对代码与文档的逐行阅读复核**尚未进行**。
  契约 v1 中 4 项偏离阶段 0 草案之处也**尚未取得**成员 1、2、4、5 确认。

因此本轮成果目前只能声明为"自动化验证通过、待人工复核"，不得写成"已由人工核验"。

TODO(成员 3)：完成逐行阅读复核后更新本节，并在小组报告中如实描述该核验过程。

### 被修改或推翻的 AI 输出

1. **日志脱敏破坏了数值格式串**（AI 引入的缺陷）。首版 `RedactingFilter` 把
   `record.args` 全部 `str()` 化，第三方库的 `%d` 收到字符串后抛 `TypeError`，
   httpx 的 `'HTTP Request: %s %s "%s %d %s"'` 每条都会报错。**改为**只脱敏字符串类型参数、
   保留其余类型，并补回归用例覆盖 `%d`、`%.2f` 与多参数。

2. **日志脱敏漏遮登录令牌**（AI 引入的缺陷，且命中发布门禁阻断项）。首版
   `Authorization` 正则 `(\S+)` 只匹配到 `Bearer` 一词，真正的令牌原样留在日志里。
   **改为**显式吃掉 `Bearer`/`Basic`/`Token` 前缀，并覆盖三种 `Authorization` 形态。

3. **泛型写法过时**。AI 首版 `class Page(OrmModel, Generic[T])` 被 `ruff` 判为
   应改用类型参数语法。**改为** PEP 695 的 `class Page[T](OrmModel)`，与项目
   Python 3.13 基线一致。

4. **`main.py` 结尾出现绕弯写法**。AI 首版写了
   `app = create_app() if False else None` 来"占位"模块级 `app`，语义混乱。
   **改为**完全不提供模块级实例，并用注释说明启动方式为 `uvicorn --factory`。

5. **AI 的一项技术判断被实测证伪**。AI 在计划中断言：因 `backend/` 缺少
   `__init__.py`，`pip install -e` 可能失败，需补该文件。实测 `pip install -e ".[dev]"`
   正常，`backend` 以 namespace package 形式可导入，**该假设不成立，未添加该文件**。
   同类情况：AI 最初把 Docker Desktop 安装失败归因于"UAC 未批准"，实测发现
   `ConsentPromptBehaviorAdmin=0`（管理员静默提权），真实原因是 C 盘仅剩 0.3 GB。

6. **依赖版本不凭推测书写**。AI 计划中建议直接给依赖写上下界。改为先不带版本安装、
   由 `pip freeze` 读出真实解析结果，再回填下界与主版本上界，并把已验证版本记录在
   `backend/backend-module-guide.md`，避免凭猜测写出不存在或过紧的版本约束。

### 由人工审查发现的 AI 缺陷（PR #6，成员 1 提出）

以下 5 项都是 AI 已写完、自测通过、且自己没有发现的真实缺陷，由成员 1 的独立审查揪出。
它们说明自动化测试通过**不等于**设计正确——测试只能验证"我想到的情况"。

7. **状态集合自相矛盾**：`FAILED` 同时被列为可重试和终态。AI 写了两处定义却没做交叉检查。
   修正后增加**不变量测试**（终态集合中每个状态的迁移集合必须为空），把"交叉检查"这件事
   交给测试而不是记性。
8. **内部接口绕过校验**：AI 只在对外 Schema 上加了时间区间校验，忘了同一约束在内部写入
   接口同样必要，等于给 Worker 留了写入坏数据的口子。
9. **状态与内容不闭合**：`modified` 允许缺教师改写内容，且 `reportable_content()` 静默回退
   模型原文——AI 当初把"回退"当成健壮性，实际是把"教师已确认"变成了假象。
10. **权限拆分不到位**：AI 设计了单一 `WORKER_SERVICE_TOKEN` 给 Worker 和 Agent 共用，
    违反最小权限。修正为双令牌 + 端点权限表 + 阶段范围。
11. **信任了客户端自报**：AI 设计的 `/assets/{id}/complete` 直接依据浏览器回调标记上传完成，
    未要求后端独立核对对象。修正为必须 HEAD 核对后以服务端结果为准。

## 2026-07-30：成员 1 Day 3 静态流程审查

- **人工决定**：成员 1 决定暂时延期非开发同学独立试用；该步骤没有被取消，
  也不得标记为已通过。
- **AI 协助**：Codex 对本地生产构建进行静态页面审查，发现核心内容默认依赖
  JavaScript 进入动画才能显示，并协助修改 CSS、组件和回归测试。
- **人工边界**：本轮结果仅是静态审查，不包含真实用户反馈，不能替代 v5
  要求的“试用—修改—同任务复测”。
- **核验**：`npm test`、`npm run typecheck`、`npm run build` 通过；关闭
  JavaScript 后的 Edge 截图确认核心任务内容保持可见。
- **报告审查**：Codex 发现打印样式引用不存在的 `.site-nav`，以及编辑模式
  通过零延迟定时器触发打印的时序风险；协助将站点壳层和会话提示排除出打印版，
  并改为预览渲染完成后调用打印。
- **人工反馈后的修正与复核**：成员 1 先确认按钮能够从编辑模式切换报告预览，
  随后通过 `Ctrl+P` 打开系统打印预览，并确认打印版只保留报告正文。Codex
  补充外部 Chrome/Edge 与 `Ctrl+P` 兜底指引，并将该提示排除出打印版；此
  反馈属于成员 1 人工复核，不冒充非开发用户试用。
