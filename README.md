# 课堂复盘与教学分析系统

> Evidence-grounded Classroom Review and Teaching Analysis Agent

本项目面向高校教师。教师上传真实课堂视频、课件或逐字稿后，系统生成带时间戳的逐字稿与可定位证据的教学分析；教师接受、修改或驳回结论后，仅将已确认内容组合进报告。

## 当前状态

阶段 0 已完成，`UI Baseline v1` 与成员 2 的证据工作台已迁入 `frontend/`。后端现已具备账号/课堂、私有对象存储预签名上传与核验、任务/事件/重试、Worker/Agent 最小权限回写，以及逐字稿和证据化结论的读写接口。前端现已通过同源 BFF 接通演示会话、课程/课堂、`presign → B2 PUT → HEAD complete` 上传和任务创建/查询；短期 JWT 只保存在 HttpOnly Cookie，长期对象存储密钥不进入浏览器。证据与报告页面仍包含明确标注的 Mock 数据，真实视频抽取、ASR、翻译与证据索引仍依赖成员 4 的 Worker，报告持久化与完整端到端部署也尚未完成，因此不得把“上传和任务 API 已接通”描述成真实全链路已经跑通。

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

阶段 0 的安装脚本只创建项目内 `.venv` 并安装当前已声明依赖；后续依赖由责任成员在实现时补充并锁定。脚本不会写入真实密钥。

## 开发环境基线

- Node.js 24 LTS：前端统一使用当前长期支持版本，版本约束写入 `frontend/package.json`。
- Python 3.13：后端、Worker 与 Agent 统一使用这一版本，版本约束写入 `pyproject.toml`。

没有选择 Node.js 的非 LTS Current 版本，是为了减少四天集中开发期间的依赖波动；没有选择 Python 3.14，是为了降低语音识别、视频处理及其原生依赖尚未提供兼容构建的风险。Windows 安装脚本优先通过 `py -3.13` 创建项目环境，因此系统默认 Python 可以保留其他版本；`setup.ps1` 与 `setup.sh` 会拒绝不符合基线的项目解释器，避免成员得到不一致结果。

前端实际依赖树由 `frontend/package-lock.json` 锁定。日常初始化与部署使用 `npm ci`；只有成员 2 在有意新增或升级依赖时使用 npm 修改依赖并同时提交清单与锁文件。

## 文档与目录导航

本文件是仓库唯一使用通用名称 `README.md` 的总入口。子目录说明均使用能直接表达用途的唯一文件名，避免出现多个同名 README。

- 正式需求、产品、架构、安全与验收文档：`docs/documentation-index.md`
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
