# 后端模块说明

负责人：成员 3。

目的：提供 FastAPI、PostgreSQL、认证、权限、对象存储地址、任务状态、复核版本、报告和审计 API。M1 默认通过统一 S3 Provider 接入 Backblaze B2 私有 Bucket，由后端生成限时预签名 URL；不得让前端接触长期应用密钥。
输入：前端请求以及 Worker/Agent 的状态与结果。
输出：受权限保护的 API、数据库记录和审计事件。

完成定义：两账号隔离；真实视频进入 B2 而二进制不进入数据库；重启后任务、对象、逐字稿与
报告仍可读取；签名过期、越权、上传失败和删除流程有清晰结果；Provider 有独立测试且业务层
不直接依赖 B2。

> 上一行的完成定义来自 `main`（成员 1 确定 M1 采用 Backblaze B2 方案时写入），原文结尾的
> "当前仅为阶段 0 占位"已删除——下面的实现状态表给出逐项的真实状态，继续写"仅为占位"
> 会与事实不符。

## 当前实现状态（如实标注）

| 部分 | 状态 |
|---|---|
| `app/schemas/`（common、task、transcript、analysis_report） | **已实现**，含校验器 |
| `app/config.py` | **已实现**，启动即校验、密钥 `SecretStr` 不可打印 |
| `app/database.py` | **已实现**，async 引擎、会话工厂、请求级事务 |
| `app/errors.py` | **已实现**（新增文件，见下） |
| `app/main.py` | **部分实现**：全局能力、健康检查，并已注册认证、课程、课堂、上传、任务、逐字稿和分析路由 |
| `app/models/` | **已实现**：15 张业务/关联表；关键跨资源关系用 `(资源 ID, owner_id)` 复合外键阻止跨账号串联 |
| 认证与课程/课堂 API | **已实现 M1 最短边界**：登录、可选演示账号、`/auth/me`、课程与课堂读写 |
| 对象存储与上传 API | **已实现**：S3 Provider、预签名上传、HEAD 完成核验、限时下载地址和未关联对象删除 |
| 任务 API | **已实现最短边界**：创建/读取/列表、事件、失败重试、取消，以及 Worker/Agent 领取、心跳和状态回写 |
| 逐字稿 API | **已实现最短边界**：教师读取/编辑与 Worker 批量写入 |
| 分析结论 API | **部分实现**：教师读取与 Agent 批量写入已实现；教师接受/修改/驳回和历史尚未实现 |
| 报告 API | **尚未实现**：`app/api/reports.py` 仍为保存、预览和导出的 `TODO` |
| `migrations/` | **已实现首个迁移** `0b5123afcf23`；PostgreSQL 17 CI 已验证 `upgrade → downgrade → upgrade` 与无模型漂移 |
| 后端自动测试 | **已实现**：含真实 PostgreSQL 持久化、跨账号写入拒绝、审计保留与 HTTP 登录/课堂流程 |

任何 `TODO`、占位实现均不代表已完成。跨模块契约见 `../docs/interface-contracts.md`（v1 已冻结）。

### 相对方案文件清单的新增文件

`app/errors.py`：领域异常与 `trace_id` ContextVar。`docs/project-plan-v5.md` §2.2 的文件
清单里没有这个文件，但异常类不能放进 `main.py`——`services/` 与 `repositories/` 要抛这些
异常，而 `main.py` 要 import 它们，同处一文件会形成循环 import。属 `backend/` 内部结构，
不改跨模块契约。**待成员 1 确认文件清单。**

## 技术选型

| 层 | 选型 | 依据 |
|---|---|---|
| Web 框架 | FastAPI + uvicorn | 自动生成 OpenAPI，满足"Day 1 冻结 OpenAPI"的交付要求 |
| 校验/序列化 | Pydantic v2 | 一份定义同时产出校验、OpenAPI 与前端 TS 类型 |
| 配置 | pydantic-settings | 启动即校验环境变量；密钥用 `SecretStr`，避免被 `repr` 打印 |
| ORM | SQLAlchemy 2.0 async + asyncpg | Worker 长轮询与前端并发查询共存，异步可避免连接池被拖死 |
| 迁移 | Alembic | "迁移可由他人复现"是完成定义之一 |
| 数据库 | PostgreSQL 17 | 需要 JSONB（`evidence_refs`、Trace 元数据）、`ON CONFLICT`（任务领取幂等）与事务隔离（多 Worker 抢任务） |
| 对象存储 | **Backblaze B2**（M1 默认，走其 S3 兼容 API）+ boto3 预签名；本地可用 MinIO 替代 | 供应商由成员 1 确定。`generate_presigned_url` 是纯本地签名计算、无网络 IO，在 async 路由中调用不阻塞事件循环。变量名保持通用（`OBJECT_STORAGE_*`），换供应商不必改前端、数据库与 Worker |
| 认证 | PyJWT + argon2-cffi | 无状态 JWT 便于 Worker/Agent 用同机制回写；Argon2 为当前口令哈希首选 |
| 测试 | pytest + pytest-asyncio + httpx | 不用 SQLite 替身：账号隔离、JSONB 与事务语义要真 Postgres 才算数 |

**明确不引入** `python-multipart` / 后端直传文件：上传走"后端签名 → 浏览器直传对象存储 →
后端确认"，既满足"视频二进制不进数据库"，也避免后端成为大文件瓶颈。

## 已验证的依赖版本

在 Windows 11 + Python 3.13.14 上实际解析并导入通过（2026-07-26）：

```
fastapi==0.140.0        uvicorn==0.51.0        pydantic==2.13.4
pydantic-settings==2.14.2  SQLAlchemy==2.0.51  asyncpg==0.31.0
alembic==1.18.5         PyJWT==2.13.0          argon2-cffi==25.1.0
boto3==1.43.56
pytest==9.1.1           pytest-asyncio==1.4.0  httpx==0.28.1   ruff==0.16.0
```

`pyproject.toml` 只给下界与主版本上界，不做精确锁定：四天集中开发期有三个成员各自追加
依赖，精确锁定会频繁互相冲突。例外是 `ruff`，锁到小版本以保证 CI 结果稳定。

## 本地环境

前置：Python 3.13（`py -3.13` 可用）、Node.js 24 LTS、FFmpeg、Docker Desktop。

```powershell
.\setup.ps1
```

`setup.ps1` 会创建仓库根 `.venv`、安装依赖、由 `.env.example` 复制 `.env`，并调用 `verify.ps1`。
`.env` 中的 `DATABASE_URL` 必须填异步驱动形式：
`postgresql+asyncpg://<user>:<password>@localhost:5432/classroom_review`。

起本地基础服务（PostgreSQL 17，以及可选的 MinIO）：

```powershell
docker compose --profile local-infra up -d
```

**对象存储**：M1 的目标是 Backblaze B2，填真实 B2 的 `OBJECT_STORAGE_ENDPOINT` /
`OBJECT_STORAGE_BUCKET` / 应用密钥即可，并保持
`OBJECT_STORAGE_USE_PATH_STYLE=false`（B2 用 virtual-host 风格寻址）。

compose 里的 MinIO 只是**离线开发替代品**，便于无 B2 凭据时也能跑通上传链路；
用它时把 `OBJECT_STORAGE_ENDPOINT` 指向 `http://localhost:9000` 并设
`OBJECT_STORAGE_USE_PATH_STYLE=true`。控制台在 `http://localhost:9001`，桶由
`minio-init` 一次性任务按 `OBJECT_STORAGE_BUCKET` 创建，浏览器直传所需的 CORS 由
`MINIO_API_CORS_ALLOW_ORIGIN` 收紧到 `FRONTEND_ORIGIN`。

两者的差异由 `app/services/storage.py` 的统一 S3 Provider 边界吸收；上传路由
通过 `ObjectStorage` 接口使用预签名、HEAD、下载和删除能力，不直接绑定 B2 SDK。

启动后端（用工厂而非模块级实例，配置缺失会在启动命令处明确报错）：

```powershell
.\.venv\Scripts\python.exe -m uvicorn --factory backend.app.main:create_app --port 8000 --reload
```

健康检查：`GET /health` 不查数据库（存活），`GET /health/ready` 查数据库（就绪）。
交互文档 `http://localhost:8000/docs`，生产环境自动关闭。

跑测试：

```powershell
.\.venv\Scripts\python.exe -m pytest tests/unit/test_backend.py -q
```

执行迁移及检查模型漂移：

```powershell
.\.venv\Scripts\python.exe -m alembic -c backend\alembic.ini upgrade head
.\.venv\Scripts\python.exe -m alembic -c backend\alembic.ini check
```

## M1 审计保留策略

- 有 `AuditEvent` 的账号不得硬删除；`audit_events.owner_id` 使用 `ON DELETE RESTRICT`，
  删除请求必须先转为停用账号（`is_active=false`）。
- `actor_user_id` 可在合法匿名化流程中置空，但事件的动作、资源类型、trace_id、时间和
  非敏感详情继续保留，避免删除账号时同步抹除操作证据。
- 当前尚未实现账号删除/匿名化业务流程，也尚未确定到期清理时长；在成员 1 确认正式
  隐私与保留期限前，不得绕过外键手工删除审计记录。

## 复核与报告（当前分支，待合并）

- 教师可通过 `POST /api/conclusions/{id}/review` 接受、修改或驳回结论；
  `GET /api/conclusions/{id}/history` 返回按时间排序的复核历史。
- `GET|PUT /api/classrooms/{id}/report` 持久化报告。PUT 只接收标题；Markdown 正文由后端
  从课堂中当前 `accepted` / `modified` 的结论生成，`modified` 使用教师改写内容。每次保存
  或复核状态变化都会重建正文与关联，驳回已纳入的结论会立即从两者中移除。
- 复核和报告创建/更新会写入不含教师备注、改写文本或报告正文的 `AuditEvent`。
  其他写接口的审计仍未补齐。
- Agent 可通过独立服务令牌向任务写入白名单 Trace 元数据；教师只能读取本人任务的
  脱敏审计时间线。`event_id` 提供幂等重放，结论 Trace 必须与任务 Trace 一致。
- PostgreSQL HTTP 回归已覆盖应用实例重建后对过期租约任务的重新领取，以及逐字稿、
  待复核结论和 Trace 事件的重复提交语义。该测试验证后端恢复边界，不等于操作系统级
  Worker 进程崩溃演练或完整部署恢复。

## 已知限制

- 认证、课程/课堂、上传、任务、逐字稿、分析、教师复核和报告读取/保存的最短 API
  已实现；服务端 DOCX/PDF 导出接口仍是 `TODO`。
- API 集成测试会以内部接口模拟 Worker/Agent 回写，不等于真实 Worker、真实模型或
  浏览器到报告的端到端运行。
- PR #20 已通过后端签发的限时只读 URL 让 Worker 从 B2 取得浏览器上传对象，
  并以文件大小和已验证 ETag 做完整性校验；一段真实输入已写回 PostgreSQL 逐字稿。
  该结果不等于 Agent、教师复核和报告全链路完成。
- 每张业务表都有 `owner_id`；关键父子关系和两张关联表已由复合外键强制同 owner。仓储仍须使用 owner-scoped 查询并统一返回 404，数据库约束只负责最后一道写入防线。
- 课程/课堂写操作尚未记录 `AuditEvent`。课堂删除在对象存储原始/派生对象清理、失败重试和删除审计完成前返回 `STATE_CONFLICT`，不会执行数据库级联删除。
- `docker-compose.yml` 的 MinIO 部分由成员 3 加入，该文件第一负责人是成员 5，**待其确认**。
- MinIO 与 mc 镜像已固定为本机实际验证过的 RELEASE 标签
  （`RELEASE.2025-09-07T16-13-09Z` / `RELEASE.2025-08-13T08-35-41Z`，digest 记在
  `docker-compose.yml` 注释中）。升级时必须重新拉取、重新验证后再改标签，不得凭猜测填写。
- 真实 B2 已用于 PR #19 的浏览器上传人工验证；凭据只存在于本地/部署环境，
  不得提交到仓库或复制进测试记录。
