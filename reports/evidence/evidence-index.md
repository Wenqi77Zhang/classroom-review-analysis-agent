# 报告证据索引

文件命名：`YYYYMMDD-member-module-description.ext`。

提交前检查来源、许可、脱敏和引用位置。不得保存真实密钥、学生信息、私有课堂视频或完整数据库。

## 当前可引用的仓库证据

| 结论 | 证据位置 | 边界 |
|---|---|---|
| 前端静态可用性和打印检查 | `../../tests/manual/day3-member1-static-audit.md` | 不是非开发成员试用 |
| 真实 B2 上传与任务创建 | PR #19、`../../frontend/src/app/api/` | 不证明 Worker 或 Agent 已运行 |
| 后端处理接口与账号隔离 | PR #18、`../../tests/integration/test_processing_api.py`、`../../tests/integration/test_account_isolation.py` | API 测试不等于真实服务 E2E |
| 两段真实视频本地 ASR | `../../tests/fixtures/fixture-catalog.md`、`../../tests/integration/test_video_pipeline.py` | 原视频和完整逐字稿不入库；不证明 B2 集成 |
| Agent 证据与报告门禁规则 | `../../tests/unit/test_agent.py`、`../../tests/integration/test_review_to_report.py` | 不证明真实模型与持久化 |

正在其他对话实现的 Worker/B2 集成在合并和复测前不得加入“已完成证据”。
