# AWS 单机生产部署与运行记录

> 生产网站：**[https://15.134.73.60.sslip.io](https://15.134.73.60.sslip.io)**
>
> 最后核验：2026-09-25；区域：`ap-southeast-2`；CloudFormation 栈：`classroom-review-agent`。
> 当前应用发布包含公开注册与受控演示入口；精确提交以生产容器部署记录和 GitHub `main` 为准。

本方案把真实上传、Whisper 转写、本地翻译、证据分析、人工复核和报告导出部署在一台
Ubuntu 24.04 EC2 上。PostgreSQL、后端、Worker、Agent 和 Ollama 都只在 Docker 私有网络中
通信；公网只开放 Caddy 的 80/443 端口。管理入口使用 AWS Systems Manager Session Manager，
不开放 SSH。课堂资料进入实例内的持久化 MinIO bucket；MinIO 只连接 Docker 私有网络，
不暴露主机端口。浏览器通过后端签发的限时 URL 上传，公网无法直接浏览 bucket。

## 规格与免费额度边界

Free Plan 默认使用悉尼区当前允许的 `m7i-flex.large`（2 vCPU、8 GiB），并配置 8 GiB
加密主机上的 swap、单推理并发和分角色模型，以容纳 `qwen3.5:4b` 翻译、`qwen3.5:0.8b` 候选分析、Whisper tiny、PostgreSQL 及
应用容器。该规格适合低并发验收，转写和模型推理会明显慢于推荐的 `t3a.xlarge`（4 vCPU、
16 GiB）。AWS 新账户额度是限期抵扣，不等于实例永久免费；上线后必须在 Billing 中设置预算
告警，并在复核结束后停止或删除不用的资源。

## 当前生产实例

- EC2：`i-0062e17d2e678b453`，通过 Systems Manager 管理，不开放 SSH；
- HTTPS：Caddy 自动管理 `15.134.73.60.sslip.io` 的证书；
- 公网仅开放 80/443，Next.js、FastAPI、PostgreSQL、Worker、Agent 与 Ollama 按生产 Compose
  规则运行，数据库与内部服务不直接暴露；
- 对象存储：实例内私有 MinIO，使用独立持久卷且不开放公网端口；
- 正式账号显示名为“验收教师”，凭据只保存在 AWS SecureString 与受限运维文件中；
- 公开注册已开启：每个注册账号拥有独立数据空间，入口有同源校验、限流、强密码和重复邮箱保护；
- 受控演示账号已开启：访客无需口令即可进入共享演示空间，页面要求只使用无隐私测试材料；
- `GET /api/backend-health` 返回 database=`ok`、object_storage=`ok`。

这是一套低并发技术验收环境。2 vCPU 上的本地 4B 翻译仍可能需要数分钟；候选分析使用 0.8B，
并由教师证据门禁拦截低质量输出。本地模型请求上限为 600 秒。该规格不代表多人并发容量已经通过压测。

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
MinIO 的独立访问标识和随机密钥。所有随机口令应使用独立的 32 字节以上随机值，文件权限
必须设为 `600`。

公网自助注册必须显式设置 `PUBLIC_REGISTRATION_ENABLED=true`；共享演示入口还需设置一个至少 16 位的
随机 `DEMO_ACCOUNT_PASSWORD`。该随机值只作为服务器端启用门禁，不会提供给浏览器或访客。

```sh
cd /opt/classroom-review-agent
cp deploy/.env.aws.example .env.production
chmod 600 .env.production
# 使用安全编辑器填入真实值后：
sudo -u classroom deploy/aws-start.sh
```

启动脚本先验证合并后的 Compose 配置，然后构建并启动容器。`minio-init` 会幂等创建私有
bucket 并显式关闭匿名访问；后端启动时还会写入并读取两字节 readiness sentinel。MinIO 没有
公网端口，因此 AWS 部署不需要对象存储 CORS。Caddy 会为 `PUBLIC_HOST` 自动申请和续期 HTTPS 证书。Ollama
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

2026-09-25 又使用 MIT OpenCourseWare `AI 101` 前 10 分钟视频与官方 54 页 PPTX 完成公开授权
材料的生产技术 E2E。任务 `515e9263-6b29-4f58-bef6-e7b713e0be46`，最终 Trace
`d1c40b7169984d11abe1a8051d44d48f`；生成 182 条双语逐字稿和 5 条候选结论。教师修改确认
3 条、驳回 2 条，报告只纳入 3 条确认事实并成功导出 Markdown/PDF。

该轮验收先后发现并修复 Whisper 最终片段边界和长任务中课件预签名地址过期两个生产缺陷。
PR #67、#68、#69 均经三项 CI 后合并。任务保留三次重试及错误历史，最终从安全阶段恢复，
没有复用旧结果冒充本次成功。

同日继续使用该演讲 10:00–20:00 的归一化片段完成 M2 第二轮生产机制验收。第二轮任务
`4a684a30-f781-4bae-93ba-026381762bcd`、最终处理 Trace
`cc59c9ea89b84522bc54d08c7658e708`；5 条 Agent 候选经教师逐条核对后全部驳回。改进循环
`5663038c-b587-495a-8271-0df8e2dd22a9` 生成并修改确认 1 条 `insufficient_evidence` 对比，Trace
`43cc7a1d28454676bc134e208bad3c7a`，最终状态为 `completed`。PR #79 使没有教师保留结论的第二轮
直接按证据规则返回不足，避免空证据模型调用；当前生产提交为 `dac0d9c`。该片段来自同一场演讲，
没有执行教学干预，所以只证明 M2 机制和教师质量控制，不证明教学效果。

## 剩余门禁与停止条件

当前可以声明“AWS 已部署并完成合成资料及公开授权课堂资料的生产技术 E2E”，不能声明真实教学
效果已经验证。仍需：

- 非开发教师独立试用；
- 由资料权利人或课程团队确认公开展示范围；MIT OCW 的课程主体为 CC BY-NC-SA 4.0，但课件内明确排除的第三方图片不得作为可再许可素材传播；
- 使用独立第二次授课、已执行的改进行动和可比证据验证 M2 教学效果，并以至少两门课程真实闭环验证 M3；
- 两个正式教师账号在生产站复验隔离；
- 在非生产副本实际执行一次数据库备份恢复；
- 进行并发、长视频和资源容量测试。

任何健康检查、数据库、对象存储、上传或模型处理失败都应停止对外验收，不得用旧结果代替当次状态。

日常备份使用 `deploy/backup-database.sh`；恢复前必须设置脚本要求的显式确认变量。停止服务使用
同一组 Compose 文件。删除 CloudFormation 栈前必须同时导出数据库与 `minio_data` 持久卷；
两者共同构成课堂证据链，缺少任何一个都不能视为可恢复备份。
