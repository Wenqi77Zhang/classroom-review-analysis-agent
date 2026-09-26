# 课堂复盘与教学分析系统

> Evidence-grounded Classroom Review and Teaching Analysis Agent

## 🌐 已部署网站

**[打开 AWS 生产网站：15.134.73.60.sslip.io](https://15.134.73.60.sslip.io)**

当前生产环境位于 AWS 悉尼区，使用 HTTPS、独立教师账号、实例内私有 MinIO、PostgreSQL、
Whisper、Ollama（4B 用于翻译、免费规格下 0.8B 用于候选分析）、Worker 与 Agent。访客可注册独立账号，也可免注册进入共享演示
工作区；共享空间只能使用无隐私且已获授权的测试材料。
部署拓扑、验收证据与仍未完成的真实教师试用边界见
[AWS 部署说明](docs/aws-deployment.md)和[测试与验收记录](tests/test-and-acceptance-record.md)。

本项目面向高校教师。教师上传真实课堂视频、课件或逐字稿后，系统生成带时间戳的逐字稿与可定位证据的教学分析；教师接受、修改或驳回结论后，仅将已确认内容组合进报告。

## 当前状态

2026-09-27：核心工作流已部署到 AWS；除合成资料外，MIT OpenCourseWare `AI 101` 的公开授权
视频片段与官方 PPTX 也已完成生产技术 E2E。验收覆盖 182 条双语逐字稿、54 页课件、5 条结论
的教师逐条复核，以及仅含 3 条确认结论的 Markdown/PDF 报告。独立教师试用与真实 M2/M3 教学
效果仍待完成，不能将工程验证等同于教学效果。M2 已使用同一公开演讲的 10:00–20:00 片段完成
第二轮生产机制验收：5 条低质量 Agent 候选全部由教师驳回，1 条两轮对比修改确认为证据不足。

| 能力 | 当前实现与验证边界 |
|---|---|
| M1 单节课堂复盘 | AWS 已完成合成资料和 MIT OCW 公开授权资料的上传、处理、证据定位、教师复核、报告编辑和 Markdown/PDF 导出；MIT 任务包含 182 条双语逐字稿、54 页课件、3 条确认及 2 条驳回结论 |
| 报告编辑 | 标题与已确认结论可保存，正文修改追加教师复核历史；原文、时间/页码和模型来源随报告导出。并发修改冲突返回 409，保留当前草稿 |
| 故障恢复 | 重试和取消写入后端任务；任务与模型生成的分析契约均服务端持久化；刷新可恢复对话、Trace、契约和教师确认状态；过期会话显式登录并返回原资源 |
| M2 两轮改进 | AWS 已完成同课程第二轮真实资料的处理、关联、候选复核和对比闭环；第二轮 5 条低质量候选全部驳回，对比按规则确认为证据不足。输入是同一公开演讲的连续片段，未执行教学干预，因此仍缺独立第二次授课的改进效果证据 |
| M3 多课程总览 | AWS 已显示 2 门课程、3 节课堂及 1 个符合汇总门禁的真实循环；教学效果另设严格门禁，要求教师确认独立第二次授课和行动执行，且存在来源有效、行动已执行、教师已确认的“有改善”对比。当前为 0/2 门课程，未达到 M3 效果验收条件 |

最新后端回归为 `381 passed, 12 skipped`；12 项需要显式外部集成环境或真实媒体，未被伪装成通过。
前端契约、类型检查和生产构建通过。Next.js 已升级到
`16.3.4`，sharp 升级到 `0.35.4`，修复本次扫描发现的依赖漏洞；实时 `npm audit` 返回 0 项漏洞。
浏览器及导出验证细节统一见[测试与验收记录](tests/test-and-acceptance-record.md)。

正式教师会话使用 HttpOnly Cookie，媒体进入私有对象存储，长期服务密钥不进入浏览器。
注册账号之间按后端资源所有权隔离；受控演示账号只在用户显式选择后建立真实后端会话，所有演示
访客共享同一工作区，因此页面明确禁止上传真实课堂隐私数据。
产品入口已移除前端手动进度、固定证据和浏览器临时报告。

稳定 HTTPS 入口与 AWS 受控主机已经完成；公开展示真实课程内容仍需获授权媒体，产品效果仍需
非开发教师独立试用，数据库灾备仍需在非生产副本执行恢复演练。
完整需求、架构、部署和逐项门禁见[产品与技术手册](docs/product-and-technology-handbook.md)，
五位成员的原始实现、后续整合和 AI 协作见[小组报告](reports/group-report.md)。

启动后从 `/login` 登录，`/classrooms` 管理课程与课堂，`/improvements` 建立改进循环，
`/portfolio` 查看课程总览。复盘任务与报告只使用真实后端资源 ID。

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

当前 AWS 生产站点为 **[https://15.134.73.60.sslip.io](https://15.134.73.60.sslip.io)**。
实际部署与复现方案见 [`docs/aws-deployment.md`](docs/aws-deployment.md)：CloudFormation、自动 HTTPS、
私有 Docker 网络、本地 Ollama、非公网 MinIO 和 Session Manager 管理入口均已落地。

仓库现提供 `deploy/compose.production.yml`、前后端独立 Dockerfile 和生产配置预检。
部署拓扑只向公网映射 Next.js 前端；FastAPI、Worker、Agent 与 PostgreSQL 位于容器私网，
浏览器不会接触服务令牌或数据库。复制 `deploy/.env.production.example` 为根目录
`.env.production`，替换其中所有占位值后运行。AWS Compose 会创建只在 Docker 私网可见的
MinIO bucket，无须开放对象存储端口或配置跨域规则：

```bash
docker compose --env-file .env.production -f deploy/compose.production.yml up -d --build
docker compose --env-file .env.production -f deploy/compose.production.yml ps
```

当 `PUBLIC_REGISTRATION_ENABLED=true` 时，访客可在 `/login` 自助注册独立教师工作区；公网注册
入口有同源校验与按来源限流，密码至少 12 位并同时包含字母和数字。管理员仍可在受信任终端创建、
重置或停用正式教师账号；口令采用隐藏输入，不进入命令历史：

```bash
docker compose --env-file .env.production -f deploy/compose.production.yml exec backend \
  python scripts/manage_teacher_accounts.py create --email teacher@example.edu --display-name "教师姓名"
```

共享演示入口由 `DEMO_ACCOUNT_PASSWORD` 显式启用，演示口令不发送到浏览器。教师忘记口令时使用同一脚本的
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

项目固定 Node.js 24 与 Python 3.13，以保持团队、CI 和部署环境一致。更高主版本尚未通过本项目完整验证。Windows 安装脚本优先通过 `py -3.13` 创建独立 `.venv`，不会替换系统默认 Python；安装脚本会拒绝不符合基线的解释器。

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
