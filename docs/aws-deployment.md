# AWS 单机生产候选部署

本方案把真实上传、Whisper 转写、本地翻译、证据分析、人工复核和报告导出部署在一台
Ubuntu 24.04 EC2 上。PostgreSQL、后端、Worker、Agent 和 Ollama 都只在 Docker 私有网络中
通信；公网只开放 Caddy 的 80/443 端口。管理入口使用 AWS Systems Manager Session Manager，
不开放 SSH。课堂资料仍进入既有私有 Backblaze B2 bucket，浏览器上传只允许生产站点的精确
HTTPS origin。

## 规格与免费额度边界

默认 `t3a.xlarge`（4 vCPU、16 GiB）用于同时容纳 `qwen3.5:4b`、Whisper tiny、PostgreSQL
及应用容器。`t3a.large`（2 vCPU、8 GiB）可以降低费用，但转写和模型推理会明显变慢，且在
并发处理时更容易出现内存压力。AWS 新账户额度是限期抵扣，不等于实例永久免费；上线后必须
在 Billing 中设置预算告警，并在复核结束后停止或删除不用的资源。

## 创建基础设施

1. 在 AWS CloudFormation 控制台上传 `deploy/cloudformation.aws.yml`。
2. 默认实例规格选择 `t3a.xlarge`，分支保持 `main`。
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

## 验收和停止条件

部署完成必须依次验证：HTTPS 首页、后端就绪、独立教师账号、授权样本上传、Whisper 逐字稿、
英文样本翻译、课件页证据、结论引用跳转、人工修改、复核状态、PDF/DOCX 报告导出、失败重试、
数据库备份和恢复。任何一项失败都保持“已部署但未验收”状态，不能写成正式交付完成。

日常备份使用 `deploy/backup-database.sh`；恢复前必须设置脚本要求的显式确认变量。停止服务使用
同一组 Compose 文件，删除 CloudFormation 栈前先导出数据库备份并确认 B2 保留策略。
