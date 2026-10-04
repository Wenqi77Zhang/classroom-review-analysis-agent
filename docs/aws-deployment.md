# AWS 单机生产部署与运行记录

> 生产网站：**[https://15.134.73.60.sslip.io](https://15.134.73.60.sslip.io)**
>
> 最新公网检查：2026-10-05，HTTPS 与数据库/对象存储健康检查通过，服务已恢复。区域：`ap-southeast-2`；
> CloudFormation 栈：`classroom-review-agent`。
> 事故前应用发布包含公开注册与 M3 教学效果门禁；共享演示账号已停用，演示输入改用仓库内单独许可
> 的材料。事故前验收提交为
> `5881af158d3e6a6eedfd5a31b292a3f57a041ce2`，数据库迁移为 `c8f91a2d7e04`。

## 当前运行状态与恢复验收（2026-10-05）

2026-09-27 的备份基础设施更新重新解析了动态 Ubuntu AMI 参数，触发 EC2 主机替换。
旧主机根盘配置为终止时删除，导致其中 PostgreSQL 与 MinIO 数据丢失。当次排查未找到 EBS
快照、回收站保留或可用异机备份；此前隔离恢复演练的临时备份已按设计清理，因此不能用于本次恢复。
旧生产资源不可再访问；本文“事故前”章节保留历史 UUID、行数与演练结果，本节单独记录重建后证据。

- [PR #89](https://github.com/Wenqi77Zhang/classroom-review-analysis-agent/pull/89) 已实现独立私有 S3
  备份、每日备份及每周隔离恢复脚本；本轮已完成首次完整备份、恢复校验并启用定时器。
- [PR #90](https://github.com/Wenqi77Zhang/classroom-review-analysis-agent/pull/90) 固定 AMI，并为主机
  设置删除/替换保留策略、关闭根盘随实例终止删除。2026-09-27 实测栈为 `UPDATE_COMPLETE`，
  修复前后实例均为 `i-036ae859f5cb5e702`，根盘 `DeleteOnTermination=False`。
- [PR #91](https://github.com/Wenqi77Zhang/classroom-review-analysis-agent/pull/91) 修复 Ubuntu 24.04
  没有 `awscli` 软件包导致初始化提前退出的问题，改用 AWS 官方 CLI v2 安装包。388 项单元测试及
  三项 GitHub CI 通过。2026-10-05 已在保留的新实例完成 AWS CLI、Docker 与应用初始化。
- [PR #92](https://github.com/Wenqi77Zhang/classroom-review-analysis-agent/pull/92) 修复后续实际恢复
  暴露的问题：MinIO 镜像拉取 401，改为固定上游源码及 SHA-256 构建；Next.js 更新到 `16.3.8`；
  登录页隐藏未启用的共享演示入口；AWS CLI 公共可执行文件允许服务账号读取，备份定时器使用
  独立 HOME/DOCKER_CONFIG，保留 `ProtectHome` 和私有临时目录。

当前主机为 `i-036ae859f5cb5e702`，固定 AMI `ami-090b1140798d2d006`，根盘
`vol-0a87bbf962ca2f5ff` 的 `DeleteOnTermination=False`。应用构建基线为 `8b4d0b1`，
定时器修复基线为 `2e8925a`；PostgreSQL、MinIO、后端、前端、Ollama 均健康，Worker/Agent 正常运行。
配置从 SecureString 恢复并校正为私有 MinIO，`.env.production` 为 `classroom` 所有、权限 `0600`。
临时参数读取策略已撤销，主机临时教师口令文件已删除，保留的正式口令未写入日志或仓库。

正式教师账号已重建；新注册账号获得独立空间，双向课程可见性与六项跨账号访问检查通过。
临时账号停用、临时课程清理，审计记录保留。共享演示账号保持停用，访客使用公开注册。

新输入采用仓库 `examples/public-demo` 第一轮 CC BY 4.0 合成材料。课堂
`4b84116b-a38b-4383-af6e-43bb2a89bf37`、任务 `fa4e1775-86ee-4c4e-b8b8-84b32e985d19`、
Trace `92890a7b909249ac9c4510b44a529f31` 完成上传、Whisper、课件解析、证据索引和 Qwen 分析，
约 114 秒无重试生成 12 条逐字稿、3 页课件和 3 条候选。开发者代行技术复核，修改确认 1 条事实、
驳回 2 条证据不足的候选；报告 `746bb323-a90c-48ae-aa42-9dcfe4a9da98` 只包含确认事实。
Markdown/PDF 私有导出、签名下载、摘要校验与 PDF 实际页面检查通过；未复核内容不能绕过门禁，
旧版本编辑返回 409。该轮不属于独立教师试用，也不证明真实教学效果。

首次异地备份批次 `20261004T173336Z-78888`（UTC；当地已为 10 月 5 日）包含 85949 字节数据库
转储、5 个对象，共 4698369 字节对象原文。S3 完整批次下载后摘要全部通过，恢复得到 20 张 public
表，Alembic 版本 `c8f91a2d7e04`；临时目录与隔离容器已清理，生产健康保持正常。每日备份计划为
03:20 UTC、每周日恢复验证为 04:20 UTC，均带最多 30 分钟随机延迟；两项定时器为 enabled，
首次手动触发的 service 均为 success、退出码 0。后续自动运行仍须查阅日志，首次成功不代替持续监测。

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

## 事故前生产实例与配置

- EC2：`i-0062e17d2e678b453`，通过 Systems Manager 管理，不开放 SSH；
- HTTPS：Caddy 自动管理 `15.134.73.60.sslip.io` 的证书；
- 公网仅开放 80/443，Next.js、FastAPI、PostgreSQL、Worker、Agent 与 Ollama 按生产 Compose
  规则运行，数据库与内部服务不直接暴露；
- 对象存储：实例内私有 MinIO，使用独立持久卷且不开放公网端口；
- 正式账号显示名为“验收教师”，凭据只保存在 AWS SecureString 与受限运维文件中；
- 公开注册已开启：每个注册账号拥有独立数据空间，入口有同源校验、限流、强密码和重复邮箱保护；
- 共享演示账号已停用：访客通过公开注册获得隔离空间，并使用仓库内 CC BY 4.0 演示材料；
- `GET /api/backend-health` 返回 database=`ok`、object_storage=`ok`。

这是一套低并发技术验收环境。2 vCPU 上的本地 4B 翻译仍可能需要数分钟；候选分析使用 0.8B，
并由教师证据门禁拦截低质量输出。本地模型请求上限为 600 秒。2026-09-27 已验证最多 4 个并发
演示会话读取和一个 40 分钟处理任务；该结果不代表更高并发、多个同时推理任务或持续高负载容量。

## 创建基础设施

1. 在 AWS CloudFormation 控制台上传 `deploy/cloudformation.aws.yml`。
2. Free Plan 保持默认 `m7i-flex.large`；升级 Paid plan 后可改为 `t3a.xlarge`。分支保持 `main`。
3. 模板会创建独立 VPC、公网子网、加密 100 GiB gp3 根盘、Elastic IP、仅开放 80/443 的
   安全组，以及带最小 SSM 管理策略的实例角色。
4. 栈完成后记录 `PublicHost` 输出，例如 `203.0.113.10.sslip.io`。该地址在 Elastic IP 保留
   期间稳定，避免临时隧道失效。

## 注入生产配置并启动

AWS Compose 从 [MinIO 官方源码](https://github.com/minio/minio) 构建对象存储及客户端，避免依赖
已经无法匿名拉取的旧镜像地址。`deploy/Dockerfile.minio` 固定源码提交、校验下载 SHA-256，并保留
许可证与来源标签；首次编译比拉取现成镜像更慢，后续使用构建缓存。

通过 Session Manager 进入主机后，把 `deploy/.env.aws.example` 复制为仓库根目录下的
`.env.production`。将 `PUBLIC_HOST` 与 `FRONTEND_ORIGIN` 改成 CloudFormation 输出，并填入
MinIO 的独立访问标识和随机密钥。所有随机口令应使用独立的 32 字节以上随机值，文件权限
必须设为 `600`。

公网自助注册必须显式设置 `PUBLIC_REGISTRATION_ENABLED=true`。当前生产不设置
`DEMO_ACCOUNT_PASSWORD`，登录页不会显示共享演示按钮；若在独立测试环境启用该选项，必须使用
至少 16 位的随机值作为服务器端门禁，不向浏览器或访客提供该值。

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

## 事故前已完成验收

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
直接按证据规则返回不足，避免空证据模型调用；该阶段部署提交为 `dac0d9c`。该片段来自同一场演讲，
没有执行教学干预，所以只证明 M2 机制和教师质量控制，不证明教学效果。

2026-09-27 完成 M3 多课程总览与教学效果专用门禁的生产复核。当前演示教师空间有 2 门课程、
3 节课堂和 1 个符合汇总门禁的真实循环；该循环的行动仍为 `planned`，对比为
`insufficient_evidence`，因此效果证据课程数严格显示为 0/2。只有教师确认独立第二次授课和
行动已执行，且系统同时核对到已完成行动、来源有效的 `improved` 对比及教师复核后，课程才会
计入效果证据；至少两门不同课程通过后才显示 M3 效果就绪。PR #82 的三项 CI 均通过，部署后
健康检查确认 database=`ok`、object_storage=`ok`，后端回归为 `381 passed, 12 skipped`。

同日使用两个临时注册教师账号完成生产隔离复验。每个账号分别创建一门空课程和一节空课堂；两边
课程列表仅返回本人课程，跨账号课堂读取、修改、删除、课程课堂列表和报告读取均返回不泄露资源
存在性的 HTTP 404。失败探测后双方自己的课堂仍可读取。临时课堂通过各自账号删除，随后使用精确
账号 UUID 和运行标识 `76c6dcefeee2` 清理 2 个临时账号、2 门空课程和 8 条临时审计记录；数据库
复核临时账号和课程均为 0，原有正式账号数量恢复为 1，健康检查仍为 database=`ok`、
object_storage=`ok`。本轮未上传媒体或个人信息，也未修改既有课程。

同日完成隔离数据库恢复演练。脚本只从生产 PostgreSQL 读取一份自定义格式备份，将其恢复到没有
端口和持久卷的一次性 PostgreSQL 17 容器；20 张 public 表逐表行数完全一致，迁移版本为
`c8f91a2d7e04`，备份大小 218664 字节、权限 `600`。运行标识为
`restore-20260926T183002`，行数清单摘要为
`4c281d29abf005adb7a95ec9906d5b22100f9e0a2ef38a87d6de1bb63b24bc33`。退出后临时目录、备份和
容器均已清理，生产健康仍为 database=`ok`、object_storage=`ok`。生产数据库未停止、覆盖或写入。
新增的标准脚本随后以运行标识 `restore-drill-3217115` 再次得到相同表数、摘要与迁移版本，退出码为
0；再次复核一次性容器和工作目录均已清理。

同日完成免费规格的有界容量验收。`scripts/verify_production_read_capacity.py` 使用独立演示会话逐级
执行 1、2、4 并发读取；三轮分别为 100、200、400 个请求，全部 HTTP 200，P95 分别为
280.36、280.83、281.56 ms，4 并发吞吐为 13.52 请求/秒。读取范围为健康、当前会话、课程和任务，
不包含写入或模型推理。

长视频使用 MIT OCW `AI 101` 完整 40 分 40 秒、50885026 字节视频。任务
`0dbfd93b-17fb-47b7-ba86-c46fbe9e3f34` 在 352.61 秒内无重试完成，Trace 为
`a433f6b383aa4167ba67632e21f5e969`，生成 726 段逐字稿和 3 条候选。长任务运行时第二个任务保持
`queued`，随后安全取消并删除其课堂。Worker 峰值约 100% 单核和 628.8 MiB，Ollama 峰值约
98.8% 单核和 1.651 GiB；主机观测到的最低可用内存仍约 4.44 GiB，Swap 从 80 MiB 增至 83 MiB，
全部容器重启计数保持 0，结束后 database=`ok`、object_storage=`ok`。

同日完成对象存储隔离恢复演练。`deploy/verify-object-storage-restore.sh` 从生产私有 MinIO 只读镜像
对象，生成权限受限的临时归档，再恢复到无端口映射、无生产卷的一次性 MinIO。运行标识
`20260926T193749Z-3258055` 覆盖 10 个对象、142647210 字节，恢复前后逐文件 SHA-256 清单一致；
归档摘要为 `30e2889dab7aa909574563d8c56bc087838683827a769d173a79b5f88e007877`，清单摘要为
`0e42ae110314f794d663c1655ec77a35e555f55676fc630e9a516fe307914930`。脚本退出后复核临时容器、
网络、目录、归档和脚本副本均不存在，生产健康保持 database=`ok`、object_storage=`ok`。

## 剩余门禁与停止条件

当前可以声明“AWS 网站已恢复，并以新合成材料重新完成技术 E2E、异地备份及隔离恢复”。
事故前公开授权课堂资料的验收仍是历史证据，旧数据没有恢复；真实教学效果未验证。仍需：

- 非开发教师独立试用；
- 既有真实课程资料仅限私有验收；MIT OCW 的课程主体为 CC BY-NC-SA 4.0，但课件中排除的第三方
  图片不得再许可。公开演示统一使用仓库内 CC BY 4.0 的两轮原创合成材料；
- 使用独立第二次授课、已执行的改进行动和可比证据验证 M2 教学效果，并把当前 M3 效果证据从
  0/2 推进到至少两门不同课程各自通过门禁；
- 若目标改为多人同时推理或持续高负载，再单独执行更高并发、耐久性和容量上限测试。

任何健康检查、数据库、对象存储、上传或模型处理失败都应停止对外验收，不得用旧结果代替当次状态。

日常备份使用 `deploy/backup-database.sh`；定期以 `deploy/verify-database-restore.sh` 和
`deploy/verify-object-storage-restore.sh` 分别在一次性 PostgreSQL 与 MinIO 中复验数据库和对象可恢复。
生产数据库恢复前必须设置脚本要求的显式确认变量，
并使用同一组 Compose 文件停止业务服务。删除 CloudFormation 栈前必须同时导出数据库与
`minio_data` 持久卷；
两者共同构成课堂证据链，缺少任何一个都不能视为可恢复备份。

CloudFormation 模板同时声明一个独立 S3 备份桶：默认 AES256 服务端加密、阻止全部公开访问、启用
版本控制，并对当前版本保留 14 天、非当前版本保留 7 天。实例角色只能列出指定前缀并读取、写入
备份对象，没有删除权限。栈被删除或替换时，备份桶使用 `Retain` 保留策略。

栈更新完成后，从输出读取 `OffsiteBackupBucketName`，在实例上安装每日备份和每周隔离恢复定时器：

```bash
sudo OFFSITE_BACKUP_BUCKET='CloudFormation 输出值' \
  OFFSITE_BACKUP_REGION=ap-southeast-2 \
  deploy/install-offsite-backup-timer.sh
sudo systemctl start classroom-offsite-backup.service
sudo systemctl start classroom-offsite-restore-check.service
sudo journalctl -u classroom-offsite-backup.service -u classroom-offsite-restore-check.service --since today
```

`backup-offsite-s3.sh` 在权限为 700 的临时目录中生成 PostgreSQL 自定义格式转储和 MinIO 对象归档，
逐文件生成 SHA-256 清单，以 `--sse AES256` 上传，并最后写入 `COMPLETE` 标记。只有带完成标记的批次
可被恢复脚本选择。`verify-offsite-s3-restore.sh` 下载最新完整批次，校验摘要后，在一次性 PostgreSQL
和临时对象目录中恢复；生产容器、数据库和 MinIO 均不停止、不覆盖。
