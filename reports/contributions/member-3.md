# 成员 3 贡献（平台后端）

责任范围：FastAPI 应用与 API 契约、PostgreSQL 数据模型、认证与权限、对象存储地址、
任务状态与重试、审计、数据库迁移、后端测试与启动说明。

> 本文件同时充当成员 3 的每日工作证据包（`docs/project-plan-v5.md` §7.2）。
> 每条"已完成"都对应可运行代码或可复现的命令输出；未实现内容一律标注，不写成已完成。

---

## 2026-07-30 合并状态补充

本节更新 `main@d27c592` 的仓库事实；下方按日期保存的“当时尚未实现”记录属于历史
证据，不应再当作当前状态。

- 已合并：认证、课程/课堂、统一 S3 Provider、预签名上传与 HEAD 核验、任务
  创建/领取/心跳/状态/重试、逐字稿读写和结论读写的最短后端边界。
- PR #18、#19 的平台后端最短链路协作补齐归属成员 1；其 CI 已通过，自动化覆盖
  PostgreSQL 账号隔离和跨账号资源拒绝。
- PR #22 的教师复核、版本历史、报告持久化和最小审计归属成员 3，当前分支待合并。
- PR #20 的 Worker/B2 下载协作、大小/ETag 校验和时间戳逐字稿写回 PostgreSQL 的
  真实单输入验收归属成员 1；该项不改写为成员 3 独立成果。
- 当前叠加分支实现服务端 Markdown/HTML/PDF 报告导出；尚未完成完整部署 E2E、第二段
  远程输入与整机/Worker 崩溃恢复演练。
- 后续审计收尾分支补齐课程/课堂、上传核验、教师任务操作和逐字稿写入/编辑的白名单审计；
  任务 Trace API 可按任务找回用户操作、Worker 逐字稿写入和 Agent Trace，正文与对象凭据不入审计。
- 上述各 PR 按本节分别归属，不把成员 1 的 #18/#19/#20 协作成果与成员 3 的 #22
  复核、历史、报告和最小审计成果混写。

## 一、历史累计证据（后续状态以上方补充为准）

## Day 4：复核、报告持久化与最小审计（当前分支待合并）

- 实现结论复核写入与历史读取；每次决定保留版本化历史，且按账号隔离返回 404。
- 实现课堂报告读取/保存；PUT 只接收标题，正文由后端从 `accepted` / `modified` 结论
  生成，`modified` 使用教师改写内容；驳回会同步移除既有报告正文和关联。
- 复核与报告操作记录脱敏审计元数据，不保存教师备注、改写内容或报告正文。
- 新增真实 PostgreSQL HTTP 集成测试，覆盖复核、报告门禁、跨账号拒绝和审计脱敏。
- 已验证：合入最新 `main` 后端全量 `184 passed, 1 skipped`、`ruff check backend tests`，以及前端测试、
  TypeScript 类型检查和生产构建。报告导出、浏览器端实际接线和真实视频 E2E 不在本项中。

## MVP 加固：Trace、幂等、恢复与权限（堆叠于 PR #22）

- 新增 Agent Trace 写入与教师任务审计读取 API；只接收白名单元数据，拒绝 Prompt 等
  未声明字段，结论 Trace 强制与任务 Trace 一致。
- 以 Agent 生成的 `event_id` 作为幂等键；完全相同的重放返回同一事件，冲突重放返回
  `STATE_CONFLICT`。
- 权限回归覆盖 Worker/教师不得写 Agent Trace、服务令牌不得读取教师审计、跨账号读取
  返回 404。
- PostgreSQL HTTP 流程重复写入逐字稿和待复核结论，验证整批替换不会累积重复结果；
  重建 FastAPI 实例后，过期租约可由新 Worker 重新领取并保留事件历史。
- 验证：合入最新 `main` 后全量 `pytest` 为 184 passed / 1 skipped，Ruff 与
  Alembic drift check 通过。
  该恢复测试不冒充真实 Worker 进程崩溃或整机重启演练。

## MVP 收尾：服务端报告导出（堆叠于 PR #24）

- 增加 Markdown、HTML、PDF 三种服务端渲染，导出对象通过统一 S3 Provider 写入 B2/MinIO，
  教师只获得限时下载地址。
- 导出前锁定课堂并重建当前受控正文；对象 key 绑定标题与正文版本，复核或标题变化后旧版本
  不再能通过 API 获取新签名，旧对象交由存储生命周期清理。
- 权限和隐私回归覆盖跨账号 404、缺失导出 404、三格式内容、驳回后失效及审计不包含正文、
  对象 key 或签名 URL。前端导出交互仍归成员 1，不改写为成员 3 成果。
- 验证：后端全量 186 passed / 1 skipped，Ruff、Alembic drift check、前端测试、类型检查
  和生产构建通过；PDF 实际渲染为 A4 PNG 检查，中文标题和正文可见且无裁切。

## MVP 收尾：写操作审计完整性（堆叠于报告导出分支）

- 为课程/课堂创建与修改、上传请求/核验/删除、任务创建/重试/取消、逐字稿替换/编辑记录
  白名单审计元数据；任务状态迁移继续由版本化 `TaskEvent` 保存，不重复保存错误原文。
- 任务相关审计显式绑定任务 `trace_id` 与 `processing_task`，教师可从既有任务审计 API 找回；
  跨账号仍返回 404，服务令牌不能读取教师审计。
- PostgreSQL 用例验证失败上传的状态和审计在 `commit_changes` 事务语义下同时持久化；审计详情
  不含文件名、对象 key、逐字稿正文、临时失败消息、教师输入或签名 URL。

| 内容 | 位置 | 可核对方式 |
|---|---|---|
| 跨模块 Schema 契约 v1（冻结） | `backend/app/schemas/`、`docs/interface-contracts.md` | `pytest tests/unit/test_backend.py` |
| 配置校验与密钥保护 | `backend/app/config.py` | 测试中"配置"一节 |
| 异步数据库引擎与请求级事务 | `backend/app/database.py` | `GET /health/ready` |
| 领域异常体系 | `backend/app/errors.py` | 测试中"统一错误格式"一节 |
| FastAPI 应用、CORS、trace_id、统一错误、日志脱敏、健康检查 | `backend/app/main.py` | 同上 |
| 后端相关测试 99 项 | 后端单元与集成测试 | `pytest -q` |
| 15 张 ORM 表与首个迁移 | `backend/app/models/`、`backend/migrations/` | `alembic upgrade head`、`alembic check` |
| 本地基础设施（PostgreSQL 17 + MinIO，自动建桶） | `docker-compose.yml` | `docker compose --profile local-infra ps` |
| 后端依赖声明与已验证版本 | `pyproject.toml`、`backend/backend-module-guide.md` | `pip freeze` |

## 二、历史状态（写于后续 API 合并之前）

- 本节原记录了当时业务路由、仓储和领域服务尚未实现的事实；这些项目中的一部分
  已由后续 PR #18、#19 补齐，当前状态以上方补充和
  `../../docs/current-progress.md` 为准。
- 账号隔离测试已使用真实 PostgreSQL；跨账号写入拒绝与审计保留用例已由最新 PR CI 验证。
- 当时 MinIO 镜像仍用 `latest` 标签；后续已固定为实际验证过的 RELEASE 标签。

---

## 三、每日工作证据包

### Day 3 — 2026-07-29（持久化与账号隔离基础）

**当天完成**

- 从最新 `main`（`cfa63cc`，已包含 PR #6）建立开发分支。远端分支名中的 `day2`
  是创建时的日期编号误判；实际开发日按团队时间线记为 Day 3。
- 实现身份、课堂、对象、任务、事件、逐字稿、证据、结论、复核、报告与审计 ORM，共 15 张业务/关联表。
- 每张业务表显式保存 `owner_id`；视频表只保存对象 key、类型、大小和校验元数据，不含二进制列。
- 接通异步 Alembic 环境并生成首迁移 `0b5123afcf23`，数据库 URL 只从 `Settings` 读取。
- 新增 5 项元数据不变量测试和 1 项真实 PostgreSQL 新会话读写测试。
- 实现 Argon2 密码哈希、带 issuer/audience/过期校验的 JWT、当前用户依赖和 Worker/Agent 独立服务身份校验。
- 将账号隔离占位测试替换为真实 PostgreSQL 测试：本人资源可读，他人资源与不存在资源均返回同一 404 语义。

**验证证据**

```text
alembic upgrade head -> 0b5123afcf23
public schema -> 15 business/association tables + alembic_version
alembic downgrade base -> only alembic_version remains
alembic upgrade head -> success
pytest -> 99 passed, 4 skipped
alembic check -> No new upgrade operations detected
```

**问题与处理**

- Alembic 在中文 Windows 上按系统区域编码读取 INI，中文注释触发 GBK 解码失败；将 INI 保持纯 ASCII。
- 纯关联表误用了 ORM `mapped_column`；改用 Core `Column`，并增加 mapper 配置测试。
- PR #10 首轮 CI 未给真实 PostgreSQL 测试提供数据库和配置，导致 2 项测试在读取 `Settings`
  时失败；为 `backend-check` 增加 PostgreSQL 17 service、Alembic 迁移和 `TEST_DATABASE_URL`。
  数据库地址不写进全局 `DATABASE_URL`，避免污染“缺少配置应失败”和 B2 默认值单元测试。

**当前限制与下一步**

- 登录 HTTP 路由、课堂/上传/任务仓储和业务 API 仍未实现，不得把安全原语描述成用户已可登录。
- 下一步实现课程与课堂基础接口，并把 owner-scoped 查询绑定到所有对外路由。

### PR #10 — 成员 1 审核后协作修复

- 成员 1 复核发现：原实现虽有 `owner_id` 与 `assert_same_owner()`，数据库仍允许跨账号
  课程—课堂、任务—资料、结论—证据、报告—结论关联；该问题不归为成员 3 已独立完成。
- 成员 1 与 Codex 协作把关键关系改为 `(资源 ID, owner_id)` 复合外键，并给两张关联表
  增加 `owner_id`，使调用者即使漏掉服务层校验，PostgreSQL 仍会拒绝跨账号写入。
- 将 `AuditEvent.owner_id` 从级联删除改为限制删除；M1 暂行策略为停用账号，不得在未确认
  保留期限和匿名化流程前硬删除有审计记录的账号。
- 新增 5 项真实 PostgreSQL 写入/删除测试与 2 项元数据不变量测试；GitHub CI 使用
  PostgreSQL 17 实测为 `106 passed, 4 skipped`，Ruff 全部通过。
- 成员 1 与 Codex 协作把 PostgreSQL CI 从单向升级补强为
  `upgrade head → downgrade base → upgrade head`；最终 CI 往返和漂移检查均通过。
  该工作流第一负责人是成员 5，待其确认。

**后续开发：认证与课程/课堂基础 API**

- 实现 `POST /api/auth/login`、可配置的 `/api/auth/demo` 与 `GET /api/auth/me`。
- 实现课程创建/列表及课堂创建/列表/读取/修改，并注册到 FastAPI/OpenAPI。
- 普通登录对未知邮箱和错误密码返回相同 `UNAUTHENTICATED`；演示账号未配置时返回
  `PERMISSION_DENIED`，无硬编码演示密码。
- 所有课程/课堂查询带 `owner_id`，跨账号资源与随机 UUID 返回相同 404 语义。
- 真实 HTTP + PostgreSQL 流程覆盖登录、创建、读取、越权、修改、输入边界和禁用删除；
  课堂删除在对象清理与审计完成前返回 `STATE_CONFLICT`；完整测试结果为
  `111 passed, 4 skipped`（具备 `TEST_DATABASE_URL` 时）。
- 课程/课堂写操作尚未记录 `AuditEvent`，不得描述为已完成审计链路。
- 当前仍未实现上传、任务、逐字稿、复核和报告 API，不将课堂基础接口描述成纵向链路已完成。

### Day 1 — 2026-07-26

**1. 当天完成的功能**

- 搭起可运行的本地后端环境：Python 3.13.14 项目内 `.venv`、PostgreSQL 17.10、MinIO（S3 兼容），并自动创建桶 `classroom-review`。
- 冻结跨模块 Schema 契约 v1 并写入 `docs/interface-contracts.md`，供成员 1、2、4、5 对齐。
- 实现配置校验、异步数据库连接与事务边界、领域异常体系、FastAPI 应用骨架（CORS、trace_id、统一错误格式、日志脱敏、存活/就绪健康检查）。
- 补齐后端测试 85 项（初版 52 项，按 PR #6 审查意见补充回归用例后为 85 项）。
- 修复 3 个阻塞全队的缺陷（见第 5 项）。

**2. 为什么这样设计**

- **契约优先于路由**：四位成员的工作都依赖后端的数据结构，先冻结 Schema 能避免第二天出现五套互不兼容的字段命名。
- **约束写进校验器而非文档**：无证据结论、缺时间范围的证据、失败不带错误码等，都在 Pydantic 层直接拒绝。发布门禁里"结论没有证据""未复核内容进报告"是阻断项，靠口头约定不可验证。
- **上传走"后端签名 → 浏览器直传对象存储 → 后端确认"**：满足"视频二进制不进数据库"，也避免后端成为大文件瓶颈。
- **跨账号访问返回 404 而非 403**：403 会泄漏"该 ID 存在"。
- **错误格式与日志脱敏集中在一处**：分散实现必然出现某个路由漏包装、某处日志漏遮盖。
- **配置启动即失败、密钥用 `SecretStr`**：配置错误是最常见的"看起来像 bug 的非 bug"；`SecretStr` 让 `repr`、日志与异常页都带不出明文。

**3. 对应提交或 PR**

分支 `member-3/day1-backend-foundation`，按语义拆分的提交见 `git log`。已推送并开出
**PR #6**（仓库首个 PR），GitHub CI 通过。成员 1 审查后提出 8 项必须修正，已逐条处理，
详见下方"PR #6 审查意见处理"。合并待成员 1 复审。

**4. 页面、日志、数据或测试证据**

```
$ pytest -q
52 passed, 5 skipped

$ docker compose --profile local-infra ps
minio      running   Up (healthy)
postgres   running   Up (healthy)

$ docker compose logs minio-init
Bucket created successfully `local/classroom-review`.
Access permission for `local/classroom-review` is set to `private`

$ psql -c "SELECT version();"
PostgreSQL 17.10 on x86_64-pc-linux-musl

$ ./verify.ps1 ; ./scripts/check-secrets.ps1
阶段 0 骨架检查通过。
路径级敏感文件检查通过。
```

TODO(成员 3)：按 `reports/evidence/evidence-index.md` 的命名规则补截图文件。

**5. 遇到的问题（问题 → 原因 → 修复 → 复测）**

*问题 A：一键安装脚本在中文 Windows 上完全无法执行。*
- 原因：5 个 `.ps1` 均为 UTF-8 无 BOM；本机 ANSI 代码页为 GB2312，Windows PowerShell 5.1 按 ANSI 解码脚本文件，中文字符串中的 `。`/`？` 字节被当作引号提前闭合字符串，产生 ParserError。未安装 PowerShell 7 的成员全部受影响。
- 修复：为 `setup.ps1`、`verify.ps1`、`start.ps1`、`scripts/check-secrets.ps1`、`scripts/verify-readme.ps1` 添加 UTF-8 BOM，内容与 CRLF 不变。`.sh` **不加** BOM（会破坏 shebang）。
- 复测：`setup.ps1` 完整跑通并创建 `.venv`；`verify.ps1` 退出码 0。
- 归属提示：除 `setup.ps1` 外 4 个文件第一负责人是成员 5，**待其确认**。

*问题 B：`verify.ps1` / `verify.sh` 在任何人跑过一次测试后永久失败。*
- 原因：README 唯一性检查扫描整个工作区，会把被 `.gitignore` 忽略目录里的第三方 `README.md` 算进来（pytest 生成 `.pytest_cache/README.md`）。而 `setup.ps1` 最后一步正是调用 `verify.ps1`。CI 因每次全新 checkout 而侥幸未暴露。
- 修复：改用 `git ls-files '*README.md'`，只检查 Git 跟踪的文件，与 `check-secrets` 已有做法一致；并补上 `verify.ps1` 缺失的显式 `exit 0`（§2.2 要求"全部通过为 0"）。
- 复测：在 `.pytest_cache/README.md` 存在的情况下，`verify.ps1` 与 `bash verify.sh` 均退出 0。
- 归属提示：两文件第一负责人是成员 5，**待其确认**。

*问题 C：自己新写的日志脱敏有两处缺陷。*
- 原因一：`RedactingFilter` 把 `record.args` 全部 `str()` 化，导致第三方库的 `%d` 格式串收到字符串而抛 `TypeError`（httpx 的 `'HTTP Request: %s %s "%s %d %s"'` 每条都会报错）。
- 原因二：`Authorization` 的正则用 `(\S+)` 只匹配到 `Bearer` 一词，**真正的令牌原样留在日志中**——命中发布门禁"密钥出现在日志"这一阻断项。
- 修复：只脱敏字符串类型的参数、保留其余类型；正则显式吃掉 `Bearer`/`Basic`/`Token` 前缀。
- 复测：新增回归用例 `test_redaction_preserves_non_string_arg_types` 与 `test_redaction_masks_secrets`，覆盖 `%d`、`%.2f`、多参数以及三种 `Authorization` 形态。
- 说明：该缺陷由本人当天新写的代码引入，并由本人补写的测试发现。

*问题 D：`verify.ps1` 新加的锁文件检查在 Windows 上必然失败。*
- 原因：该检查（随 `main` 的 `06ff4dd` 引入）把 JS 代码放在 PowerShell 单引号串内并在其中使用双引号；Windows PowerShell 向原生命令传参时会吃掉这些双引号，node 实际收到 `require(./frontend/package.json)`，抛 `SyntaxError: Unexpected token '.'`。`setup.ps1` 最后一步调用 `verify.ps1`，因此安装流程同样失败。`verify.sh` 用 grep，不受影响。
- 修复：校验逻辑不变，只把引号写法改为「JS 侧单引号、PowerShell 侧双引号」。**未**改用 `ConvertFrom-Json`——`package-lock.json` 含空字符串键 `"packages": { "": {...} }`，Windows PowerShell 5.1 的 `ConvertFrom-Json` 无法处理空属性名（已实测确认）。
- 复测：`verify.ps1` 退出 0；`setup.ps1` 端到端跑通（含 `npm ci`）。
- 归属提示：该文件第一负责人是成员 5，**待其确认**。

*方案对齐：`main` 将 M1 对象存储定为 Backblaze B2。*
- 背景：`main` 的 `19901dc` 确定 M1 走 B2 的 S3 兼容 API，并在后端完成定义中加入「Provider 有独立测试且业务层不直接依赖 B2」「不得让前端接触长期应用密钥」。
- 处理：本分支原按本地 MinIO 搭建，已对齐——预签名有效期变量统一到 `main` 的 `OBJECT_STORAGE_PRESIGNED_URL_TTL_SECONDS`（本分支原用同义的 `PRESIGN_EXPIRE_SECONDS`，已废弃）；新增 `OBJECT_STORAGE_PROVIDER`（枚举）与 `OBJECT_STORAGE_RETENTION_DAYS`；`OBJECT_STORAGE_USE_PATH_STYLE` 默认值由 `true` 改为 `false`（B2 用 virtual-host 寻址，原默认值只对 MinIO 正确）。
- MinIO 保留但降级为「离线开发替代品」，已在 `docker-compose.yml` 与模块说明中显著标注，不是 M1 交付目标。
- 复测：新增 4 项配置测试（默认供应商、未知供应商被拒、保留天数边界）。
- 当时待办：统一 S3 Provider 抽象层和 B2 凭据在本段记录时尚未完成；Provider
  后续已由 PR #18 实现，B2 配置已用于 PR #19 人工验收，当前状态以上方
  “2026-07-30 合并状态补充”为准。

*问题 E：Docker Desktop 反复启动即崩溃，阻塞审查意见 6。*
- 现象：引擎始终起不来，`docker-desktop` WSL 发行版 Stopped，`docker info` 报找不到管道。
- 原因：日志中 `backend crashed ... initializing Inference manager ... remove .../dockerInference: The file cannot be accessed by the system`。`%LOCALAPPDATA%\Docker\run\` 与 `%LOCALAPPDATA%\docker-secrets-engine\` 下残留了 0 字节的 AF_UNIX socket reparse point（重启中断留下）。Docker 启动时要先删旧 socket 再重建，删不掉即崩溃；而每次崩溃又会留下新的僵尸文件，形成循环。这些文件用 `Remove-Item` 与 `System.IO.File.Delete` 均报"文件无法被系统访问"。
- 修复：不删文件，改为**重命名其父目录**（`run` → `run.stale-2`、`docker-secrets-engine` → `.stale`），Docker 启动时自行重建。重命名可随时还原，比"恢复出厂设置"安全——后者会清空已拉取的镜像，而本次正需要读取这些镜像的真实版本。
- 复测：引擎 35 秒就绪；随后读到实际版本并完成审查意见 6。
- 与 C 盘空间无关（当时 2.38 GB），是独立问题。

*环境类问题：WSL2 安装两次失败。*
- 原因：C 盘可用空间仅 0.3 GB，WSL 的 MSIX 包（约 200 MB）安装中断，留下"正在安装"日志但无已注册包。
- 修复：清理 pip / npm / uv 缓存与冗余的 uv 托管 Python 共回收约 4.6 GB 后重试成功；Docker Desktop 以 `--installation-dir=D:\Docker\DockerDesktop`、`--wsl-default-data-root=D:\Docker\wsl` 安装到 D 盘，使镜像与容器数据不再占用 C 盘。
- 复测：`wsl --status` 退出码 0（WSL 2.7.11.0）；`docker info` 可用；`D:\Docker\wsl` 已生成。

**6–8. AI 协作**

详见 `docs/ai-collaboration-log.md` 中日期为 2026-07-26、成员为"成员 3"的记录行（含关键提示词、AI 输出、核验方式与修改原因）。

**9. 问题最终如何解决**

三个缺陷均已修复并有复测证据；其中问题 A、B 涉及成员 5 主责文件，已在本文件与
`backend/backend-module-guide.md` 标注待确认，未擅自视为定稿。

**10. 当前限制与下一步**

限制见本文件第二节和下方审查意见处理表。下一步顺序：

1. `backend/app/models/` 三个模型文件 + Alembic 首个迁移（每张业务表带 `owner_id`）。
2. `dependencies.py`、`api/auth.py`、`services/permissions.py`：登录、当前用户、归属校验。
3. 打通"创建课堂 → 上传记录 → 建立任务 → 保存结果"最短纵向链路，并把内部接口交给成员 4、5。

---

## 四、PR #6 审查意见处理

成员 1 于 2026-07-26 独立核验 head `b33533a` 后提出 8 项必须修正。处理如下：

| # | 意见 | 处理 | 回归测试 |
|---|---|---|---|
| 1 | `FAILED` 既可迁回 `QUEUED` 又被列入 `TERMINAL_STATUSES`，语义冲突 | 拆成三个集合：`TERMINAL_STATUSES={succeeded,cancelled}`、`RETRYABLE_STATUSES={failed}`、`INACTIVE_STATUSES`（二者之并） | 加**不变量测试**：终态集合中每个状态的允许迁移集合必须为空，防止再次自相矛盾 |
| 2 | `InternalTranscriptSegmentWrite` 未校验时间区间，Worker 可写入对外 Schema 会拒绝的数据 | 复用同一约束；并新增批内 `index` 唯一且升序校验 | ✅ 倒置区间、重复 index、乱序 index 各一条 |
| 3 | `modified` 未强制非空 `reviewed_content`，`reportable_content()` 静默回退模型原文 | 加状态一致性校验；`reportable_content()` 对不可进报告的状态直接抛错，不回退 | ✅ 空/空白/缺失三种、`pending`/`rejected` 抛错、两种可报告状态取值正确 |
| 4 | Worker 与 Agent 共用高权限令牌 | 拆为 `WORKER_SERVICE_TOKEN` / `AGENT_SERVICE_TOKEN`，新增 `ServiceIdentity`、`INTERNAL_ENDPOINT_SCOPES` 端点权限表，以及 `AGENT_WRITABLE_STAGES`（Agent 仅可回写 `analyze`）。配置层拒绝两个令牌填成同值 | ✅ 端点范围、阶段划分不重叠且完备、令牌同值被拒、缺 agent 令牌启动失败 |
| 5 | `/assets/{id}/complete` 不能信任浏览器自报 | 契约与 Schema 文档明确：标记 `uploaded` 前后端必须 HEAD 对象并核对 key/size/content_type/校验值，**以 HEAD 结果为准写库**，核对不过落 `failed` | ⏳ 路由未实现，暂无法测；已在 Schema 与契约中写死要求并留 `TODO` |
| 6 | MinIO / mc 镜像必须固定为实际验证过的 RELEASE 标签 | 已修好 Docker（见问题 E）后读取实际镜像：`minio/minio:RELEASE.2025-09-07T16-13-09Z`、`minio/mc:RELEASE.2025-08-13T08-35-41Z`，digest 一并记入 compose 注释 | ✅ `docker compose down -v` 后用固定标签重新拉起，minio/postgres 均 healthy、桶创建成功 |
| 7 | 报告文字与事实不符（"52 项""尚未推送"） | 全仓库同步为 85 项；提交状态更正为已推送并开出 PR #6 | — |
| 8 | `X-Trace-Id` 无输入约束 | 限制字符集 `[A-Za-z0-9_-]` 与长度 1–128，不合法则静默生成新 ID；契约文档写明理由 | ✅ 超长、空格、换行（日志注入）、控制字符、HTML 片段、空值各一条，外加端到端"伪造头部不得回显"一条 |

另接受意见 5（新增 `errors.py`）的附带要求，已把该文件补入 `docs/project-plan-v5.md` 的文件清单。

**仍需成员 5 确认**：其主责脚本的 BOM / README 检查 / 锁文件引号修复，以及
`docker-compose.yml` 的 MinIO 部分。
