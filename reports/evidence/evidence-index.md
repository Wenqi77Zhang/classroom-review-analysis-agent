# 报告证据索引

文件命名：`YYYYMMDD-member-module-description.ext`。

提交前检查来源、许可、脱敏和引用位置。不得保存真实密钥、学生信息、私有课堂视频或完整数据库。

## 当前可引用的仓库证据

| 结论 | 证据位置 | 边界 |
|---|---|---|
| 前端静态可用性和打印检查 | `../../tests/manual/day3-member1-static-audit.md` | 不是非开发成员试用 |
| 真实 B2 上传与任务创建 | PR #19、`../../frontend/src/app/api/` | 仅证明浏览器上传与任务创建 |
| 后端处理接口与账号隔离 | PR #18、`../../tests/integration/test_processing_api.py`、`../../tests/integration/test_account_isolation.py` | API 测试不等于真实服务 E2E |
| 两段真实视频本地 ASR | `../../tests/fixtures/fixture-catalog.md`、`../../tests/integration/test_video_pipeline.py` | 原视频和完整逐字稿不入库；不证明 B2 集成 |
| 单输入 B2 到 PostgreSQL 时间戳逐字稿 | PR #20、`../../worker/`、`../../tests/unit/test_worker.py` | 一段获授权真实视频；不证明第二输入、前端展示或 Agent 已运行 |
| Agent 证据与报告门禁规则 | `../../tests/unit/test_agent.py`、`../../tests/integration/test_review_to_report.py` | 不证明真实模型与持久化 |
| Worker→Agent 自动接管与结论写回 | `../../agent/job_store.py`、`../../agent/runner.py`、`../../tests/unit/test_agent.py`、`../../tests/integration/test_processing_api.py` | 已合并并完成单输入真实逐字稿模型联调；专业 Skill 真实输入仍未验收 |
| 单输入真实数据技术 E2E | `../../tests/manual/failure-and-retry-record.md`、`../../docs/current-progress.md` | 真实视频到三格式报告及两类失败恢复；不等于非开发教师浏览器试用、第二输入或同任务复测 |

PR #20 本身仍只支持 Worker/B2 单输入纵向切片；后续 Agent、复核和报告证据必须引用
2026-08-10 的独立真实 E2E 记录。两者都不得扩写为翻译、课件、第二输入或完整 M1 已完成。
