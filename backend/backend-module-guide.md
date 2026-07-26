# 后端模块说明

负责人：成员 3。

目的：提供 FastAPI、PostgreSQL、认证、权限、对象存储地址、任务状态、复核版本、报告和审计 API。
输入：前端请求以及 Worker/Agent 的状态与结果。
输出：受权限保护的 API、数据库记录和审计事件。

完成定义：两账号隔离；视频二进制不进入数据库；重启后任务与报告仍可读取；错误与重试清晰。

## 当前实现状态（如实标注）

| 部分 | 状态 |
|---|---|
| `app/schemas/`（common、task、transcript、analysis_report） | **已实现**，含校验器 |
| `app/config.py` | **已实现**，启动即校验、密钥 `SecretStr` 不可打印 |
| `app/database.py` | **已实现**，async 引擎、会话工厂、请求级事务 |
| `app/errors.py` | **已实现**（新增文件，见下） |
| `app/main.py` | **部分实现**：应用工厂、CORS、trace_id、统一错误处理、日志脱敏、健康检查。**业务路由尚未注册** |
| `app/api/`、`app/models/`、`app/repositories/`、`app/services/` | **尚未实现**，仍为 `TODO` 占位 |
| `migrations/` | **尚未实现**，无迁移版本 |
| `tests/unit/test_backend.py` | **已实现** 52 项：契约校验、配置、错误格式、日志脱敏 |

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
| 对象存储 | MinIO（本地，S3 兼容）+ boto3 预签名 | `generate_presigned_url` 是纯本地签名计算、无网络 IO，在 async 路由中调用不阻塞事件循环 |
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

起本地基础服务（PostgreSQL 17 + MinIO，并自动建桶）：

```powershell
docker compose --profile local-infra up -d
```

MinIO 控制台在 `http://localhost:9001`，S3 API 在 `http://localhost:9000`，桶名取
`OBJECT_STORAGE_BUCKET`，由 `minio-init` 一次性任务创建。浏览器直传所需的 CORS 由
compose 里的 `MINIO_API_CORS_ALLOW_ORIGIN` 收紧到 `FRONTEND_ORIGIN`，不用手工配置。

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

TODO(成员 3)：Alembic 迁移命令待 `models/` 实现后补入本节。

## 已知限制

- 业务端点尚未实现，`docs/interface-contracts.md` 的端点表目前只是契约，不可调用。
- ORM 模型与迁移尚未实现，`/health/ready` 只验证连接可用，库里还没有表。
- 测试覆盖集中在契约、配置与错误格式；权限、账号隔离、任务状态机与持久化尚未覆盖。
- `docker-compose.yml` 的 MinIO 部分由成员 3 加入，该文件第一负责人是成员 5，**待其确认**。
- MinIO 镜像仍用 `latest` 标签，可复现性不足；首次拉取后应改为具体 RELEASE 标签。
