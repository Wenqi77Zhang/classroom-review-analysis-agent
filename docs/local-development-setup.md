# 本地开发环境统一配置与启动指南

本文面向第一次拉取项目的成员，统一说明“需要安装什么、哪些服务必须同时运行、
环境变量放在哪里、如何判断链路是否可用”。各模块的实现细节仍以对应模块指南为准。

> 仓库根目录的 `start.ps1` / `start.sh` 已提供前端、后端、Worker 和 Agent 统一入口；
> PostgreSQL、对象存储和 Ollama 属于外部基础设施，需要在统一入口前单独启动或配置。
> 统一入口已完成一条真实视频的单输入技术 E2E；第二输入、真实翻译、课件证据、浏览器
> 全程用户验收和其他成员部署复现完成前，仍不能描述为完整 M1 已通过。

## 1. 先选择需要运行的范围

| 使用目的 | 必须运行 | 能验证什么 | 不能验证什么 |
|---|---|---|---|
| 只开发前端静态交互 | Node.js、前端 | 布局、文案、Mock 交互、前端测试 | 创建真实课堂、上传、真实任务 |
| 前后端联调 | 前端、FastAPI、PostgreSQL、对象存储 | 登录、课程/课堂、上传、任务创建与查询 | Worker/Agent 未启动时，任务不会完成 |
| 完整真实链路 | 前端、FastAPI、PostgreSQL、对象存储、Worker、Agent | 从视频到逐字稿、分析结论和后续复核链路 | 尚未实现或未验收的功能仍不能视为完成 |

`localhost` 永远指“正在运行当前程序的那台电脑”。成员 2 在自己电脑运行前端时，
`http://localhost:8000` 指向成员 2 自己电脑上的后端，不会自动连接成员 1 的电脑。
跨电脑联调应使用团队部署的 HTTPS 测试后端；不要直接把本地数据库、MinIO 控制台或
无认证的开发后端暴露到公网。

仓库另提供 Cloudflare Quick Tunnel 临时联调入口：它只把成员 1 本机的
Next.js 前端/BFF 暴露为随机 HTTPS 地址，后端、数据库和对象存储管理端口仍仅限本机。
该入口用于短时组员联调，不属于最终部署，详见第 6 节。

## 2. Windows 前置软件

完整本地链路需要：

- Git；
- Node.js 24 LTS；
- Python 3.13；
- FFmpeg；
- Docker Desktop（提供 PostgreSQL 17；本地离线对象存储使用 MinIO）。

在 PowerShell 中检查：

```powershell
git --version
node --version
npm --version
py -3.13 --version
ffmpeg -version
docker --version
docker compose version
```

Node.js 必须是 `v24.x`，Python 必须是 `3.13.x`。Docker 命令存在但无法连接时，先启动
Docker Desktop，等待其显示运行正常。只开发前端时不强制安装 Python、FFmpeg 和 Docker，
但页面会明确显示后端不可用，真实创建与上传按钮也会禁用。

## 3. 拉取代码与初始化项目环境

先进入自己的仓库目录。下面的路径只是格式示例，成员应替换为自己的实际路径。需要
前后端或完整链路的成员执行完整初始化：

```powershell
Set-Location 'C:\你的路径\classroom-review-analysis-agent'
git status --short
git pull --ff-only
.\setup.ps1
```

如果 `git status --short` 显示未提交修改，不要直接覆盖或删除；先提交到个人分支，或与
对应负责人确认。`setup.ps1` 会在仓库根目录创建独立 `.venv`、安装 Python 与前端依赖，
并在缺少时把 `.env.example` 复制为 `.env`。

`setup.ps1` 只负责初始化，不会代替成员填写本地配置，也不会启动完整系统。
只开发前端的成员可以不运行该脚本，直接按第 5.4 节在 `frontend/` 中执行 `npm ci` 和
`npm run dev`。

## 4. 配置根目录 `.env`

`.env` 同时服务于 Docker Compose、后端以及内部服务。它已被 Git 忽略，绝对不能提交。
以 `.env.example` 为模板填写，不要删除模板中已有的变量。

### 4.1 本地 MinIO 联调所需的关键变量

下面只展示格式，所有尖括号内容都必须在成员自己的 `.env` 中替换：

```dotenv
APP_ENV=development
FRONTEND_ORIGIN=http://localhost:3000
BACKEND_URL=http://localhost:8000

POSTGRES_DB=classroom_review
POSTGRES_USER=classroom_review
POSTGRES_PASSWORD=<本机独立数据库密码>
DATABASE_URL=postgresql+asyncpg://classroom_review:<与上面相同的数据库密码>@localhost:5432/classroom_review

JWT_SECRET=<至少32个字符的随机值>
DEMO_ACCOUNT_PASSWORD=<本机演示账号密码>
WORKER_SERVICE_TOKEN=<仅供本机Worker使用的随机令牌>
AGENT_SERVICE_TOKEN=<仅供本机Agent使用且与Worker不同的随机令牌>

OBJECT_STORAGE_PROVIDER=minio
OBJECT_STORAGE_ENDPOINT=http://localhost:9000
OBJECT_STORAGE_REGION=us-east-1
OBJECT_STORAGE_BUCKET=classroom-review-local
OBJECT_STORAGE_ACCESS_KEY_ID=<本机MinIO账号>
OBJECT_STORAGE_SECRET_ACCESS_KEY=<本机MinIO强密码>
OBJECT_STORAGE_USE_PATH_STYLE=true
```

密码中如含 `@`、`:`、`/`、`#` 等 URL 特殊字符，写入 `DATABASE_URL` 时需要进行 URL
编码。初次配置者可先使用密码管理器生成只含大小写字母和数字的高强度本地密码，减少
连接串编码错误。

安全要求：

- `JWT_SECRET` 至少 32 个字符；
- `WORKER_SERVICE_TOKEN` 和 `AGENT_SERVICE_TOKEN` 必须不同；
- 本地、测试和生产环境必须使用不同密钥；
- 不在群聊、截图、Issue、PR、日志或 Codex 对话中发送真实密码和密钥；
- 成员 2 只做前端静态开发时，不需要取得 B2、Worker 或 Agent 的真实密钥；
- Backblaze B2 应使用权限受限的 Application Key，不使用网站登录密码。

### 4.2 使用团队 Backblaze B2

需要验证真实 B2 上传时，由有权限的负责人通过安全渠道把受限配置写入本机或部署平台，
并设置：

```dotenv
OBJECT_STORAGE_PROVIDER=backblaze_b2
OBJECT_STORAGE_ENDPOINT=<B2的S3兼容端点>
OBJECT_STORAGE_REGION=<B2区域>
OBJECT_STORAGE_BUCKET=<私有Bucket名称>
OBJECT_STORAGE_ACCESS_KEY_ID=<受限Application Key ID>
OBJECT_STORAGE_SECRET_ACCESS_KEY=<受限Application Key>
OBJECT_STORAGE_USE_PATH_STYLE=false
```

真实值不得写进本文、`.env.example` 或任何 Git 跟踪文件。B2 Application Key 需要允许
后端写入和读取报告导出对象，但仍应限制到本项目 Bucket；不要使用只读 Key 冒充导出链路
可用。没有 B2 权限的成员应使用本地 MinIO，不应互相复制个人 B2 网站密码。

## 5. 启动前后端联调链路

以下命令均从仓库根目录执行，建议每个长期运行的服务使用单独的 PowerShell 窗口。

完成第 5.1、5.2 节的基础设施和迁移后，可以统一启动四个应用服务：

```powershell
.\start.ps1
```

macOS/Linux 使用 `./start.sh`。日志写入 `logs/runtime/`，按 `Ctrl+C` 会停止本次启动的
全部子进程。若需要逐个调试服务，仍可使用下列分窗口命令。

### 5.1 启动 PostgreSQL 和本地 MinIO

```powershell
docker compose --profile local-infra up -d
docker compose --profile local-infra ps
```

`postgres` 和 `minio` 应显示为健康状态，`minio-init` 是一次性建桶任务，正常完成后退出
不代表故障。

### 5.2 执行数据库迁移

```powershell
.\.venv\Scripts\python.exe -m alembic -c backend\alembic.ini upgrade head
```

迁移用于创建当前代码需要的数据库表。没有执行迁移时，后端可能能启动，但创建课堂等
请求会失败。

### 5.3 启动后端

```powershell
.\.venv\Scripts\python.exe -m uvicorn --factory backend.app.main:create_app --port 8000 --reload
```

保持该窗口运行。随后在浏览器检查：

- `http://localhost:8000/health`：后端进程存活；
- `http://localhost:8000/health/ready`：后端与数据库均就绪；
- `http://localhost:8000/docs`：开发环境 API 文档。

只有 `/health/ready` 成功，才能证明数据库链路可用。

### 5.4 启动前端

另开一个 PowerShell 窗口：

```powershell
Set-Location 'C:\你的路径\classroom-review-analysis-agent\frontend'
npm ci
npm run dev
```

本地后端使用默认的 `http://localhost:8000`，通常不需要额外配置。若前端需要连接已获
授权的团队测试后端，在 `frontend/.env.local` 中填写：

```dotenv
BACKEND_URL=https://<团队测试后端域名>
```

修改后必须重启前端。HTTPS 网页不得连接 HTTP 后端，否则浏览器会按混合内容风险拦截。

打开 `http://localhost:3000/` 后，应从页面创建真实课堂。真实任务地址应类似：

```text
http://localhost:3000/tasks/xxxxxxxx-xxxx-xxxx-xxxx-xxxxxxxxxxxx
```

`/tasks/demo-review`、`/tasks/day3-audit` 等演示名称不是数据库 UUID，只能用于演示界面，
不能创建真实上传任务。

## 6. 跨网络的临时团队联调入口

当成员不在同一台电脑或同一局域网时，可以由成员 1 在完整本地链路已启动后，临时开放
Cloudflare Quick Tunnel。该方案无需注册 Cloudflare 账号，但地址随机、无可用性保证，
成员 1 的电脑和相关进程必须持续运行；因此只能用于开发测试，不能作为 M1 最终部署。

### 6.1 安装并检查 `cloudflared`

只有负责开启入口的成员需要安装，其他成员不需要：

```powershell
winget install --id Cloudflare.cloudflared --exact
cloudflared --version
```

安装后若当前 PowerShell 仍提示找不到命令，关闭并重新打开 PowerShell。不要从群文件或
不明镜像下载可执行文件。

### 6.2 开启入口

先按第 5 节启动 PostgreSQL、迁移和后端，但不要另行启动 3000 端口前端。确认
`http://localhost:8000/health/ready` 返回就绪后，在仓库根目录执行：

```powershell
.\scripts\start-team-tunnel.ps1
```

脚本会依次执行以下安全检查与动作：

1. 确认后端和数据库就绪，并为本次生产前端选择独立的本地随机端口；
2. 使用密码学安全随机数生成本次团队访问码，不写入磁盘或 Git；
3. 构建并隐藏启动生产版 Next.js，通过随机实例挑战值确认不是旧前端，再只向隧道暴露
   这个 Next.js 本地端口；
4. 在终端输出访问码，并由 `cloudflared` 输出随机的
   `https://<随机名称>.trycloudflare.com` 地址；
5. 关闭窗口或按 `Ctrl+C` 后，停止本次前端与临时入口。

首次使用或修改脚本后，可先运行只启动本地生产前端、不创建公网入口的预检：

```powershell
.\scripts\start-team-tunnel.ps1 -PreflightOnly
```

成员 1 只通过团队私聊分别发送地址和访问码，不把访问码放进群公告、Issue、PR、截图、
`.env` 或其他仓库文件。组员打开地址后会先看到“临时团队联调环境”门禁；验证成功后，
浏览器只保存限时 `HttpOnly` Cookie，不保存访问码明文。

### 6.3 真实上传前的对象存储限制

Quick Tunnel 只解决网页和同源 BFF 的访问。远程成员的浏览器无法访问成员 1 本机
`localhost` 上的 MinIO，因此跨网络真实上传必须使用已配置的私有 Backblaze B2。
每次 Quick Tunnel 的随机地址变化后，还必须由 B2 管理员把**本次精确 HTTPS 来源**
加入 Bucket CORS；不要长期允许所有 `trycloudflare.com` 子域。

由持有受限 B2 配置的成员执行（路径替换为实际安全 `.env`）：

```powershell
.\.venv\Scripts\python.exe .\scripts\configure-team-tunnel-cors.py `
  --env-file '.\.env' apply `
  --origin 'https://<本次随机名称>.trycloudflare.com'
```

随后运行不上传任何对象的真实预检：

```powershell
.\.venv\Scripts\python.exe .\scripts\configure-team-tunnel-cors.py `
  --env-file '.\.env' verify `
  --origin 'https://<本次随机名称>.trycloudflare.com'
```

入口停止后立即移除临时规则，脚本会保留 Bucket 原有的其他 CORS 规则：

```powershell
.\.venv\Scripts\python.exe .\scripts\configure-team-tunnel-cors.py `
  --env-file '.\.env' remove
```

在 B2 CORS 尚未更新前，页面浏览、登录和普通 BFF 请求可以工作，但浏览器直传 B2 会被
CORS 拦截。预签名 URL、B2 Application Key、数据库密码和内部服务令牌均不得发送给
普通联调成员。若后端日志或浏览器控制台报错，截图前仍需按第 8 节脱敏。

若 `cloudflared` 提示用户目录中的 `config.yml` / `config.yaml` 与 Quick Tunnel 冲突，
不要删除已有正式 Tunnel 配置；先停止操作，由配置所有者临时移走该文件后重试。

## 7. Worker 与 Agent

前后端联调只会把任务创建为待处理状态。要继续消费视频和生成分析，还必须启动 Worker
与 Agent。两者必须使用同一后端地址，并分别使用 `.env` 中不同的服务令牌：

- Worker 只处理媒体、逐字稿和证据，参见 `../worker/media-worker-guide.md`；
- Agent 只读取证据并生成受约束分析，参见 `../agent/agent-module-guide.md`。

首次运行 Worker 可能下载 Whisper/PyTorch 或模型权重，耗时和磁盘占用会明显增加。
只有负责 Worker 或完整链路验收的成员需要安装 `.[dev,worker]`；普通前端开发者不需要。
Agent 的真实模型端点和密钥只应通过本机或部署平台环境变量注入。

当前是否已经具备可启动的 Worker/Agent 运行入口，以各模块指南和
`current-progress.md` 的最新合并事实为准；占位代码和单元测试通过不能当作完整链路完成。

## 8. 常见问题定位

| 页面或终端现象 | 最可能原因 | 首先检查 |
|---|---|---|
| “后端服务暂时不可用” | 只启动了前端，或 `BACKEND_URL` 错误 | 后端窗口、`/health` |
| `/health` 成功但 `/health/ready` 失败 | PostgreSQL 未启动、密码不一致或未迁移 | `docker compose ps`、`DATABASE_URL`、Alembic |
| 视频已校验但上传按钮仍为灰色 | 后端不可达，或任务地址不是 UUID | 上传区后端状态、浏览器地址 |
| B2/MinIO 上传出现 CORS 错误 | 对象存储未允许当前前端来源 | `FRONTEND_ORIGIN`、Bucket CORS、是否重启服务 |
| 上传成功但任务一直不继续 | Worker 未启动或令牌/后端地址不匹配 | Worker 终端和脱敏日志 |
| Agent 无法回写结论 | Agent 未启动、令牌错误或真实运行入口尚未接通 | Agent 指南和当前进度 |
| `EADDRINUSE` | 端口已被其他进程占用 | 确认已有服务是否就是本项目，不要重复启动 |
| Quick Tunnel 页面要求访问码 | 临时联调门禁正常工作 | 向成员 1 私聊索取本次访问码 |
| Quick Tunnel 可浏览但 B2 上传失败 | 随机入口尚未加入 B2 CORS | 由 B2 管理员加入本次精确 HTTPS 来源 |

排错截图可以包含页面状态和追踪号，但必须遮住 Cookie、Authorization、Token、密码、
Application Key、数据库连接串和预签名 URL。

## 9. 停止本地服务

前端、后端、Worker 和 Agent 窗口使用 `Ctrl+C` 停止。停止 Docker 基础服务：

```powershell
docker compose --profile local-infra down
```

该命令保留数据库和 MinIO 卷中的本地数据。不要随意添加 `-v`；`-v` 会删除卷及其中
数据，只能在明确需要重置本地环境并确认数据可丢弃时使用。

## 10. 文档维护责任

- 成员 5：统一启动、部署方式和本文第一负责人；
- 成员 3：后端、PostgreSQL、迁移和对象存储配置核对；
- 成员 2：前端启动、BFF 地址和浏览器联调现象核对；
- 成员 4：Worker 依赖与运行命令核对；
- 成员 1：范围、安全边界和最终验收确认。

`scripts/start-team-tunnel.ps1` 是成员 1 为当前团队联调提供的临时辅助入口，不能替代
成员 5 的最终部署交付责任。成员 5 选择并验收最终托管方案后，应删除或降级本文对临时
入口的依赖，并同步架构、验收矩阵与交付说明。

新增环境变量时，代码负责人必须同步更新 `.env.example`、对应模块指南和本文。统一启动
脚本实现后，必须先由未参与实现的成员在干净环境复现，再删除本文中的“分窗口启动”限制。
