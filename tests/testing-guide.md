# 测试说明

成员 5 统筹跨模块测试；每位成员必须测试本人模块。

测试层次：

- `unit/`：快速规则和模块测试。
- `integration/`：后端、Worker、Agent 与数据接口测试。
- `e2e/`：浏览器核心全链路。
- `manual/`：真实用户试用和失败重试记录。

公开仓库不得提交真实课堂视频；测试样例来源和许可记录在 `fixtures/fixture-catalog.md`。

## 成员 5 Agent 测试入口

仅使用仓库根目录 Python 3.13 `.venv`：

```powershell
.\.venv\Scripts\python.exe -m pytest tests/unit/test_agent.py tests/integration/test_review_to_report.py -q
.\.venv\Scripts\python.exe -m ruff check agent tests/unit/test_agent.py tests/integration/test_review_to_report.py
```

`test_agent.py` 覆盖分析契约、账号/任务证据边界、时间范围双重校验、双语硬门禁、Prompt 注入数据边界、专业 Skill 缺失失败、状态机、隐私路由、结构化输出、未知证据拦截和 Trace 异常脱敏；`test_review_to_report.py` 覆盖 `pending/rejected` 过滤及 `modified` 使用教师改写内容。

2026-07-29 PR #13 审查修复后执行上述命令：20 项定向测试通过；全仓 pytest 为 119 项通过、9 项跳过；`ruff check backend agent tests` 与路径级敏感文件检查通过。9 项跳过包括成员 4 尚未实现的 Worker/视频链路 2 项，以及缺少 `TEST_DATABASE_URL` 的 PostgreSQL 集成测试 7 项。这里是离线测试结果，不得扩写为真实模型、视频链路、数据库集成或浏览器 E2E 已通过。
