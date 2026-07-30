# 课堂复盘与教学分析系统

> Evidence-grounded Classroom Review and Teaching Analysis Agent

本项目面向高校教师。教师上传真实课堂视频、课件或逐字稿后，系统生成带时间戳的逐字稿与可定位证据的教学分析；教师接受、修改或驳回结论后，仅将已确认内容组合进报告。

## 当前状态

截至 2026-07-30 的已合并基线为 `main@d27c592`。前端已通过同源 BFF
接通演示会话、课程/课堂、`presign → B2 PUT → HEAD complete` 上传和任务
创建/查询；后端已具备账号隔离、私有对象存储、任务、逐字稿和结论的最小权限
读写接口。短期 JWT 只保存在 HttpOnly Cookie，长期对象存储密钥不进入浏览器。

PR #20 已接通 Worker 对 `uploaded` 任务的领取、B2 限时下载、文件大小与 ETag
校验、FFmpeg、Whisper 和 PostgreSQL 逐字稿写回，并用一段获授权真实视频完成验收。
证据工作台仍使用明确标注的演示数据，翻译、课件、证据索引、Agent、教师复核状态和
报告尚未形成完整持久化链路。里程碑 M1 因此仍未通过。逐项状态、证据与阻塞统一记录在
[`docs/current-progress.md`](docs/current-progress.md)。

## 里程碑

- 里程碑 M1：四天内必须完成单节课堂从上传到报告导出的真实全链路。
- 里程碑 M2：仅在 M1 全部通过后评估第二轮课堂改进对比。
- 里程碑 M3：可选的多门课程管理。

## 快速入口

Windows：

```powershell
.\setup.ps1
.\start.ps1
.\verify.ps1
```

macOS/Linux：

```bash
chmod +x setup.sh start.sh verify.sh
./setup.sh
./start.sh
./verify.sh
```

当前 `start.ps1` / `start.sh` 仍是成员 5 的统一启动占位入口，不能一次启动完整
前端、后端和 Worker；其退出非零属于已知未完成项。现阶段应按各模块指南分别启动，
不得把阶段 0 脚本检查通过描述成 M1 冒烟验证通过。

阶段 0 的安装脚本只创建项目内 `.venv` 并安装当前已声明依赖；后续依赖由责任成员在实现时补充并锁定。脚本不会写入真实密钥。

### 临时团队联调入口（非最终部署）

当成员不在同一电脑或局域网时，可由入口负责人按
[`docs/local-development-setup.md`](docs/local-development-setup.md) 第 6 节启动
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

## 开发环境基线

- Node.js 24 LTS：前端统一使用当前长期支持版本，版本约束写入 `frontend/package.json`。
- Python 3.13：后端、Worker 与 Agent 统一使用这一版本，版本约束写入 `pyproject.toml`。

没有选择 Node.js 的非 LTS Current 版本，是为了减少四天集中开发期间的依赖波动；没有选择 Python 3.14，是为了降低语音识别、视频处理及其原生依赖尚未提供兼容构建的风险。Windows 安装脚本优先通过 `py -3.13` 创建项目环境，因此系统默认 Python 可以保留其他版本；`setup.ps1` 与 `setup.sh` 会拒绝不符合基线的项目解释器，避免成员得到不一致结果。

前端实际依赖树由 `frontend/package-lock.json` 锁定。日常初始化与部署使用 `npm ci`；只有成员 2 在有意新增或升级依赖时使用 npm 修改依赖并同时提交清单与锁文件。

## 文档与目录导航

本文件是仓库唯一使用通用名称 `README.md` 的总入口。子目录说明均使用能直接表达用途的唯一文件名，避免出现多个同名 README。

- 正式需求、产品、架构、安全与验收文档：`docs/documentation-index.md`
- 当前已合并进度、进行中任务与集成阻塞：`docs/current-progress.md`
- 全体成员本地软件、环境变量、分服务启动与排错：`docs/local-development-setup.md`
- 跨网络临时联调入口：`scripts/start-team-tunnel.ps1`（非最终部署，使用前阅读统一环境指南第 6 节）
- 完整四天五人规划与目标骨架：`docs/project-plan-v5.md`
- 文件和模块责任：`OWNERSHIP.md`
- 前端模块：`frontend/frontend-module-guide.md`（含成员 2 交接）
- 第一版界面基准：`docs/ui-baseline-v1.md`
- 后端模块：`backend/backend-module-guide.md`
- 媒体处理 Worker：`worker/media-worker-guide.md`
- Agent 模块：`agent/agent-module-guide.md`
- 测试策略与执行：`tests/testing-guide.md`
- 报告编写与证据：`reports/reporting-guide.md`
- 辅助脚本：`scripts/script-guide.md`

正式项目文档的推荐阅读顺序和维护规则统一记录在 `docs/documentation-index.md`。

## 安全提醒

- 不提交真实课堂视频、学生信息、账号、Cookie、令牌或 `.env`。
- `.env.example` 只能包含变量名和非敏感说明。
- 公开样例必须记录来源、版本与许可。
- 模拟、部分实现和未实现内容必须如实标注。
