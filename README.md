# 课堂复盘与教学分析系统

> Evidence-grounded Classroom Review and Teaching Analysis Agent

本项目面向高校教师。教师上传真实课堂视频、课件或逐字稿后，系统生成带时间戳的逐字稿与可定位证据的教学分析；教师接受、修改或驳回结论后，仅将已确认内容组合进报告。

## 当前状态

截至 2026-09-04，前端已通过同源 BFF 接通正式教师与可关闭的演示会话、
课程/课堂、真实上传、任务、证据工作台、教师复核和服务端报告；后端已具备账号隔离、
私有对象存储、任务租约、逐字稿、证据结论、复核历史和三格式导出。短期 JWT 只保存在
HttpOnly Cookie，长期对象存储密钥不进入浏览器。

资料上传前的“复盘 Agent”已由固定话术替换为真实本地模型对话：它结合当前课程、课堂和教师
连续输入，按需提出一个关键追问并生成可编辑、默认未确认的分析契约。回复展示实际模型名与
`trace_id`；模型不可用或结构化输出校验失败时透明报错，不生成伪结果。教师修改并确认契约后
才能上传资料和创建任务，Agent 在这一阶段不得声称已经看过尚未上传的课堂证据。

两段内容不同的真实课程视频（计算机/人工智能、人文社科各一段）均已完成
`B2 上传 → HEAD 核验 → Worker → FFmpeg → Whisper → PostgreSQL 时间戳逐字稿 →
Ollama qwen3.5:4b → 事实/判断/建议 → 接受/修改/驳回 → Markdown/HTML/PDF` 技术 E2E。
两份当前 ASR 与配套原始 ASR 的规范化文本相似度均为 1.0，但配套文件未经人工校订，不能当作
准确率或地面真值。Worker 已接通 loopback-only 的 Ollama 自动逐句翻译，并以真实
`qwen3.5:4b` 验证结构、顺序、中文覆盖与提示注入边界，并已完成一段真实英文课堂的浏览器
全链路验收。课件页级写回、账号隔离、Agent 引用和前端原页定位已通过自动化与真实 PostgreSQL
接口集成；另以公开视频画面和 ASR 人工重建的 8 页可编辑课件完成真实对象存储、Worker 解析、
PostgreSQL 写回和 Agent 原页引用技术 E2E，3/3 结论均含课件页证据；真实浏览器还验证了视频、
逐字稿、课件原页和分析卡片在桌面/窄屏下不会互相覆盖。该课件明确标注为重建材料，不能冒充授课教师
原始课件。两段媒体的中国大学 MOOC 官方课程页已定位，但平台服务协议不构成书面复用授权，媒体仍只在
本机私有验收且不进入仓库；公开演示前必须替换为单独获授权资料或取得需求方书面许可。因此当前结果不等于
非开发教师试用或完整发布验收已通过。M2 已实现“教师确认建议 → 改进行动 → 同课程第二轮课堂
→ 两轮证据对比候选 → 教师确认”，M3 已实现多课程总览、课堂完成度比较与只纳入真实且经教师
确认内容的汇总报告。当前没有同课程第二轮真实视频，因此 M2/M3 已通过代码、Schema、真实
PostgreSQL 和合成机制边界验证，但尚未宣称真实教学效果改善。逐项状态、证据与阻塞统一记录在
[`docs/product-and-technology-handbook.md`](docs/product-and-technology-handbook.md)。

生产候选包已经完成正式教师登录、可撤销会话、账号隔离、课堂及对象删除、数据库备份恢复、
分层健康检查、依赖降级、同源/限流门禁、非 root 前后端镜像、纯 CPU 媒体 Worker、容器私网和
Cloudflare 命名隧道 profile；最新回归为 Python `349 passed, 12 skipped`，
前端契约、类型检查和生产构建通过，真实 Playwright 浏览器验收为 `12 passed, 4 skipped`。
永久公网地址仍需受控域名、持续运行主机和远程托管 Tunnel
token；这些外部条件未提供前，不把临时预览冒充正式部署。

## 里程碑

- 里程碑 M1：单节课堂从上传到报告导出的真实全链路——技术实现完成，剩书面授权、独立教师试用与正式部署门禁。
- 里程碑 M2：改进行动、同课程第二轮课堂、证据对比与教师复核——功能实现完成，等待同课程第二轮真实视频验证效果。
- 里程碑 M3：多课程总览、课堂比较和教师确认内容汇总——功能实现完成，真实汇总内容随 M2 真实轮次产生。

启动后可访问：`/login` 登录正式教师账号，`/classrooms` 创建、继续或删除课堂，
`/improvements` 建立改进循环，`/portfolio` 查看多课程总览。

## 快速入口

Windows：

```powershell
.\setup.ps1
ollama pull qwen3.5:4b
.\start.ps1
.\verify.ps1
```

macOS/Linux：

```bash
chmod +x setup.sh start.sh verify.sh
./setup.sh
ollama pull qwen3.5:4b
./start.sh
./verify.sh
```

`start.ps1` / `start.sh` 会读取本机 `.env`，启动前端、FastAPI、Worker 轮询和 Agent
轮询，并把运行日志写入已忽略的 `logs/`。脚本会先检查 `.venv`、`.env`、npm、
必需变量、端口和 Worker/Agent 令牌隔离，再自动把 PostgreSQL 迁移到当前 Alembic head；
配置、迁移或端口存在问题时 fail-closed。默认访问
`http://localhost:3000`，课堂后端使用 `http://127.0.0.1:8100`，避免与其他常用本地项目的
8000 端口串线。只有后端健康检查和前端代理均确认连接到本项目后，Worker 与 Agent 才会启动。
成员 1 的 Windows
环境已经完成真实双输入启动与技术 E2E，仍需在干净机器和其他成员环境复现。

安装脚本在项目内创建 `.venv`，安装当前声明并锁定的 Python/前端依赖，并在缺少时复制
`.env.example`。脚本不会生成或写入真实密钥。

### 真实浏览器验收

普通 GitHub CI 只运行 `npm run test:e2e:spec`，确认浏览器用例能够被 Playwright 正确收集；
它不会把未启动完整服务的 Runner 冒充成真实验收环境。下面的 `test:e2e:real` 必须连接正在运行的
前端、后端、Worker、Agent、PostgreSQL 与对象存储，并以实际任务数据留证。

先保持 `start.ps1` / `start.sh` 运行，再在另一个终端提供一条已经成功处理的真实任务 ID：

```powershell
Set-Location .\frontend
$env:E2E_BASE_URL = "http://127.0.0.1:3000"
$env:E2E_TASK_ID = "<已成功处理的真实任务 UUID>"
npm run test:e2e:real
```

验收器默认只建立一次本地演示会话，并在四种视口下串行复用；登录状态仅写入已忽略的
`frontend/test-results/`。长期服务器应关闭演示账号，并通过受保护的 CI Secret 同时提供
`E2E_TEACHER_EMAIL` 与 `E2E_TEACHER_PASSWORD`，不要把教师口令写入命令、仓库、Issue 或日志。
若未提供 `E2E_CYCLE_ID`，涉及某一条具体 M2 改进循环的 4 个视口用例会明确跳过，而不会伪造通过。

### 临时团队联调入口（非最终部署）

当成员不在同一电脑或局域网时，可由入口负责人按
[`docs/product-and-technology-handbook.md`](docs/product-and-technology-handbook.md) 第 10.6 节启动
Cloudflare Quick Tunnel。组员无需安装项目环境，使用浏览器打开负责人私聊发送的地址，
再输入本次访问码。

每次启动后由负责人私下填写和发送以下模板；**访问码必须保持为空再提交到 GitHub**：

```text
临时联调地址：https://<本次随机名称>.trycloudflare.com
本次访问码：
用途：仅供组员短时联调，不是最终部署环境
```

入口依赖负责人电脑、后端及隧道进程持续运行，停止后地址和访问码立即失效。不要把真实
访问码、Cookie、预签名 URL 或课堂隐私数据写入群公告、Issue、PR 和仓库文件。

### 生产部署

仓库现提供 `deploy/compose.production.yml`、前后端独立 Dockerfile 和生产配置预检。
部署拓扑只向公网映射 Next.js 前端；FastAPI、Worker、Agent 与 PostgreSQL 位于容器私网，
浏览器不会接触服务令牌或数据库。复制 `deploy/.env.production.example` 为根目录
`.env.production`，替换其中所有占位值并配置 B2 对精确 HTTPS 域名的 CORS 后运行：

```bash
docker compose --env-file .env.production -f deploy/compose.production.yml up -d --build
docker compose --env-file .env.production -f deploy/compose.production.yml ps
```

首次部署由服务器管理员在受信任终端创建正式教师账号；口令采用隐藏输入，不进入命令历史：

```bash
docker compose --env-file .env.production -f deploy/compose.production.yml exec backend \
  python scripts/manage_teacher_accounts.py create --email teacher@example.edu --display-name "教师姓名"
```

长期服务器默认不配置 `DEMO_ACCOUNT_PASSWORD`。教师忘记口令时使用同一脚本的
`reset-password`，系统会立即撤销该账号已有登录令牌。数据库备份和受确认保护的恢复脚本位于
`deploy/backup-database.sh` 与 `deploy/restore-database.sh`；备份包含私密课堂元数据，必须加密
保存且不得提交 Git。

若已经在 Cloudflare 控制台创建稳定域名的远程托管 Tunnel，并把源站配置为
`http://frontend:3000`，可将令牌只写入本机 `.env.production` 后启用命名隧道：

```bash
docker compose --profile tunnel --env-file .env.production -f deploy/compose.production.yml up -d --build
```

前端端口默认只绑定服务器 loopback，不直接暴露 FastAPI、数据库或服务令牌。生产入口必须位于
带托管 TLS 的反向代理或远程托管 Cloudflare Tunnel 之后。Quick Tunnel
只用于临时验收；其地址随机、依赖本机进程，不能写成永久上线。详见产品与技术手册的
“生产部署与回滚”一节。

## 开发环境基线

- Node.js 24 LTS：前端统一使用当前长期支持版本，版本约束写入 `frontend/package.json`。
- Python 3.13：后端、Worker 与 Agent 统一使用这一版本，版本约束写入 `pyproject.toml`。

没有选择 Node.js 的非 LTS Current 版本，是为了减少四天集中开发期间的依赖波动；没有选择 Python 3.14，是为了降低语音识别、视频处理及其原生依赖尚未提供兼容构建的风险。Windows 安装脚本优先通过 `py -3.13` 创建项目环境，因此系统默认 Python 可以保留其他版本；`setup.ps1` 与 `setup.sh` 会拒绝不符合基线的项目解释器，避免成员得到不一致结果。

前端实际依赖树由 `frontend/package-lock.json` 锁定。日常初始化与部署使用 `npm ci`；只有成员 2 在有意新增或升级依赖时使用 npm 修改依赖并同时提交清单与锁文件。

## 文档与目录导航

本文件是仓库唯一使用通用名称 `README.md` 的总入口。子目录说明均使用能直接表达用途的唯一文件名，避免出现多个同名 README。

- 产品、需求、UI、架构、接口、安全、运行、进度与项目治理：`docs/product-and-technology-handbook.md`
- 测试方法、测试数据、失败重试、阶段验收与可用性记录：`tests/test-and-acceptance-record.md`
- 小组报告、证据索引、贡献审计及成员 1–5 实际贡献：`reports/group-report.md`
- 跨网络临时联调入口：`scripts/start-team-tunnel.ps1`（非最终部署，使用前阅读手册第 10.6 节）
- 目录职责、模块边界、接口约定和运行指南均已并入产品与技术手册。

旧拆分文档可通过 Git 历史追溯；当前信息只维护在以上三个主文档中，避免重复和状态冲突。

## 安全提醒

- 不提交真实课堂视频、学生信息、账号、Cookie、令牌或 `.env`。
- `.env.example` 只能包含变量名和非敏感说明。
- 公开样例必须记录来源、版本与许可。
- 模拟、部分实现和未实现内容必须如实标注。
