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

## 当前合并基线说明

截至 `main@f2349d6`，PR #14 已补充本地真实视频 Worker 测试，PR #18、#19
已补充后端处理接口、账号隔离和前端业务 API 测试，PR #20 又覆盖 B2 下载、大小/ETag
校验、失败清理与真实逐字稿写回。合并最新 `main` 前的最终回归为 Ruff 通过、
169 项通过、10 项按外部环境条件跳过；PR #20 的三项 GitHub CI 全部成功。

前端当前基线已执行 `npm test`、`npm run typecheck` 和 `npm run build`。这些结果
证明前端门禁；PR #20 另有单输入 Worker/B2 真实链路证据，但仍不证明 Agent、
教师复核和报告的完整 E2E。

## Agent 运行时集成分支验证

`member-1/agent-runtime-integration` 已增加 Worker→Agent 交接、Agent HTTP
领取/续租、编排、结论写回、完成状态和安全失败测试。合并最新 `main` 前执行：

- Ruff 全仓通过；
- Python 全仓 `174 passed, 10 skipped`；
- 前端 `npm test`、`npm run typecheck`、`npm run build` 通过；
- `verify.ps1`、路径级敏感文件检查和 `git diff --check` 通过。

10 项跳过包含需要独立 `TEST_DATABASE_URL` 或真实外部媒体条件的用例。Python 测试
通过主仓库已安装的 `.venv` 执行，并将 `PYTHONPATH` 指向当前工作树；当前工作树自己的
`.venv` 因外部 PyPI 域名解析失败未完成依赖安装。因此这些结果是源码回归证据，
不是独立环境安装、真实 PostgreSQL、真实模型或浏览器完整 E2E 证据。
