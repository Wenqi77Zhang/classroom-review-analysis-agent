# 课堂复盘与教学分析系统

> Evidence-grounded Classroom Review and Teaching Analysis Agent

本项目面向高校教师。教师上传真实课堂视频、课件或逐字稿后，系统生成带时间戳的逐字稿与可定位证据的教学分析；教师接受、修改或驳回结论后，仅将已确认内容组合进报告。

## 当前状态

当前仓库处于“阶段 0：项目骨架与方案冻结”。目录、责任、配置样例和测试模板已建立，但核心功能尚未实现。任何 `TODO`、占位实现或模拟内容均不代表已完成。

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

## 文档与目录导航

本文件是仓库唯一使用通用名称 `README.md` 的总入口。子目录说明均使用能直接表达用途的唯一文件名，避免出现多个同名 README。

- 正式需求、产品、架构、安全与验收文档：`docs/documentation-index.md`
- 完整四天五人规划与目标骨架：`docs/project-plan-v5.md`
- 文件和模块责任：`OWNERSHIP.md`
- 前端模块：`frontend/frontend-module-guide.md`
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
