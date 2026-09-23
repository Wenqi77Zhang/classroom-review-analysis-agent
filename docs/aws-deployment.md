# AWS 单机生产部署与运行记录

> 生产网站：**[https://15.134.73.60.sslip.io](https://15.134.73.60.sslip.io)**
>
> 最后核验：2026-09-23；区域：`ap-southeast-2`；CloudFormation 栈：`classroom-review-agent`。
> 当前应用部署提交：`cb60b3f04e0bcb38b839901dd0c4de1b58cda04a`。

本方案把真实上传、Whisper 转写、本地翻译、证据分析、人工复核和报告导出部署在一台
Ubuntu 24.04 EC2 上。PostgreSQL、后端、Worker、Agent 和 Ollama 都只在 Docker 私有网络中
通信；公网只开放 Caddy 的 80/443 端口。管理入口使用 AWS Systems Manager Session Manager，
不开放 SSH。课堂资料仍进入既有私有 Backblaze B2 bucket，浏览器上传只允许生产站点的精确
HTTPS origin。

## 规格与免费额度边界

Free Plan 默认使用悉尼区当前允许的 `m7i-flex.large`（2 vCPU、8 GiB），并配置 8 GiB
加密主机上的 swap、单模型和单推理并发，以容纳 `qwen3.5:4b`、Whisper tiny、PostgreSQL 及
应用容器。该规格适合低并发验收，转写和模型推理会明显慢于推荐的 `t3a.xlarge`（4 vCPU、
16 GiB）。AWS 新账户额度是限期抵扣，不等于实例永久免费；上线后必须在 Billing 中设置预算
告警，并在复核结束后停止或删除不用的资源。

## 当前生产实例

- EC2：`i-0062e17d2e678b453`，通过 Systems Manager 管理，不开放 SSH；
- HTTPS：Caddy 自动管理 `15.134.73.60.sslip.io` 的证书；
- 公网仅开放 80/443，Next.js、FastAPI、PostgreSQL、Worker、Agent 与 Ollama 按生产 Compose
  规则运行，数据库与内部服务不直接暴露；
- 对象存储：私有 Backblaze B2，生产 Origin 的 CORS 预检已通过；
- 正式账号显示名为“验收教师”，凭据只保存在 AWS SecureString 与受限运维文件中；
- 演示账号已关闭，`POST /api/session/demo` 返回 HTTP 403；
- `GET /api/backend-health` 返回 database=`ok`、object_storage=`ok`。

这是一套低并发技术验收环境。2 vCPU 上的本地 `qwen3.5:4b` 响应可能需要数分钟；生产环境已把
本地模型请求上限设为 600 秒并完成真实调用验证。该规格不代表多人并发容量已经通过压测。

## 创建基础设施

1. 在 AWS CloudFormation 控制台上传 `deploy/cloudformation.aws.yml`。
2. Free Plan 保持默认 `m7i-flex.large`；升级 Paid plan 后可改为 `t3a.xlarge`。分支保持 `main`。
3. 模板会创建独立 VPC、公网子网、加密 100 GiB gp3 根盘、Elastic IP、仅开放 80/443 的
   安全组，以及带最小 SSM 管理策略的实例角色。
4. 栈完成后记录 `PublicHost` 输出，例如 `203.0.113.10.sslip.io`。该地址在 Elastic IP 保留
   期间稳定，避免临时隧道失效。

## 注入生产配置并启动

通过 Session Manager 进入主机后，把 `deploy/.env.aws.example` 复制为仓库根目录下的
`.env.production`。将 `PUBLIC_HOST` 与 `FRONTEND_ORIGIN` 改成 CloudFormation 输出，并填入
既有 B2 私有 bucket 的受限应用密钥。所有随机口令应使用独立的 32 字节以上随机值，文件权限
必须设为 `600`。

```sh
cd /opt/classroom-review-agent
cp deploy/.env.aws.example .env.production
chmod 600 .env.production
# 使用安全编辑器填入真实值后：
sudo -u classroom deploy/aws-start.sh
```

启动脚本先验证合并后的 Compose 配置，然后构建并启动容器，写入一条独立的 B2 生产 CORS
规则并执行真实 OPTIONS 预检。Caddy 会为 `PUBLIC_HOST` 自动申请和续期 HTTPS 证书。Ollama
模型通过持久卷保留，首次下载期间 Agent 和 Worker 不会开始消费任务。

## 已完成验收

2026-09-23 使用不含个人信息的合成课堂视频和 PPTX，在正式账号下完成：

```text
直接私有上传 → 服务端 HEAD 核验 → FFmpeg 音频抽取 → Whisper 时间戳逐字稿
→ 课件页解析 → 证据索引 → qwen3.5:4b 分析 → 教师接受/修改
→ 仅纳入已复核结论的报告 → Markdown/PDF 私有导出
```

生产任务为 `ea3ab213-56ef-41f1-ab28-9006982f35f3`，Trace 为
`12d6a36dc49a4064ac6d4285cf7210e1`。六段带时间戳逐字稿和三页课件证据均可在工作台核对；
三条结论逐条完成教师复核，报告保留证据位置、摘录、复核状态、模型、Prompt 版本与 Trace。

PR #60 还完成了任务创建前的契约持久化。生产课堂 `22d6418b-cf19-4909-8bbc-88e744b42c16`
先后在未确认和已确认状态刷新，均恢复教师输入、模型回复、Trace、契约字段和确认状态，未重新
运行模型。验证 Trace 为 `811488f1cd6a4c8994d3e13d3f3e5014`。

## 剩余门禁与停止条件

当前可以声明“AWS 已部署并完成合成资料生产技术 E2E”，不能声明真实教学效果已经验证。仍需：

- 非开发教师独立试用；
- 使用取得明确授权的公开课堂媒体与原始课件；
- 使用同课程第二轮真实视频验证 M2，并以至少两门课程真实闭环验证 M3；
- 两个正式教师账号在生产站复验隔离；
- 在非生产副本实际执行一次数据库备份恢复；
- 进行并发、长视频和资源容量测试。

任何健康检查、数据库、对象存储、上传或模型处理失败都应停止对外验收，不得用旧结果代替当次状态。

日常备份使用 `deploy/backup-database.sh`；恢复前必须设置脚本要求的显式确认变量。停止服务使用
同一组 Compose 文件，删除 CloudFormation 栈前先导出数据库备份并确认 B2 保留策略。
