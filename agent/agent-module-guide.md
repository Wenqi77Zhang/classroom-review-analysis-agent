# Agent 模块说明

负责人：成员 5；学科规则与专业证据校验协作：成员 4。

## 目的与边界

Agent 在教师已确认的分析契约和当前任务可定位证据范围内生成事实、判断和建议。它不加工媒体、不直连数据库、不自动接受结论，也不修改教师复核状态。

输入是分析契约、任务/账号 ID、逐字稿或课件等证据索引；输出使用成员 3 冻结的 `InternalConclusionBatchWrite`，包含结构化结论、证据引用、模型/Skill/Prompt 版本和 Trace ID。

## 当前已实现

- `contracts.py`：分析范围、课程领域、分析契约、任务内证据、分析计划和模型候选输出；结论与证据字段复用 `backend/app/schemas/`。
- `state.py`：有限状态转移，分析必须依次经过规划、模型调用、结构校验和等待人工复核。
- `providers/`：统一异步接口、OpenAI-compatible 结构化输出、本地/云端隐私路由；云端强制 HTTPS，本地模式只允许 loopback 地址。
- `skills/common.py`：通用课堂结构、提问、等待、例证和总结规则。
- `tools/retrieve_evidence.py`：只在当前 `task_id + owner_id` 范围内检索，模型引用未知证据 ID 时拒绝输出。
- `orchestrator.py`：执行已确认的时间范围和双语条件；调用前筛选证据，落地前复核引用范围；一次规划、选择 Skill、调用 Provider、校验模型 JSON并生成后端写入批次。不可信课堂文本以 Base64 数据区发送，不能充当 Prompt 指令。
- `job_store.py`：使用独立 `AGENT_SERVICE_TOKEN` 领取当前任务证据、续租、写入结论和状态；
  错误不记录响应正文、服务令牌或课堂原文。
- `runner.py`：单次领取 `analyze` 任务，维持 Agent 租约，调用协调器并批量写入
  `pending` 结论；失败只写稳定错误码与教师可读脱敏提示，不写半成品结论。
- `reporting/composer.py`：确定性过滤复核状态；只组合 `accepted/modified`，修改项使用 `reviewed_content`。
- `observability/tracing.py`：记录规划、模型、校验和错误事件；错误只保留稳定类型、错误码和阶段，不保存可能包含课堂原文或输入值的异常消息。

## 尚未完成与协作依赖

- 学科 Skill 与证据门禁已有确定性实现和单元测试，但尚未用真实 Worker 证据索引完成端到端验证。
- Worker → Agent 的显式交棒、Agent 领取/心跳、一次运行与结论/状态回写已实现并有离线
  自动化测试；尚未用真实 PostgreSQL、真实 Worker 逐字稿和真实模型完成端到端验收，
  因此不能描述成生产链路已经通过。
- 报告后端路由仍未实现，Trace 也尚未形成可由后端审计找回的持久化链路。
- 当前 Agent 领取包只包含真实逐字稿片段证据；课件页、画面证据和独立证据索引尚未串联。
- Provider 已实现调用协议，但真实模型端点与模型名仍需通过环境配置注入；云端密钥不得
  来自前端或写入 Trace，本地模式只允许 loopback 地址。

## 单次运行

后端与模型服务启动且 `.env` 已配置后，在仓库根目录执行：

```powershell
.\.venv\Scripts\python.exe -m agent.runner
```

必要配置为 `BACKEND_URL`、`AGENT_SERVICE_TOKEN`，以及与任务隐私模式对应的一组模型
配置。私有课堂使用 `LOCAL_MODEL_CHAT_COMPLETIONS_URL` 与 `LOCAL_MODEL_NAME`；公开课堂
明确选择云模式时才读取 `CLOUD_MODEL_CHAT_COMPLETIONS_URL`、`CLOUD_MODEL_NAME` 和
`CLOUD_MODEL_API_KEY`。命令行不接收令牌或密钥，避免进入 Shell 历史和进程列表。

## 测试

项目 Python 基线为 3.13，必须使用仓库根目录 `.venv`：

```powershell
.\.venv\Scripts\python.exe -m pytest tests/unit/test_agent.py tests/integration/test_review_to_report.py -q
.\.venv\Scripts\python.exe -m ruff check agent tests/unit/test_agent.py tests/integration/test_review_to_report.py
```

2026-07-29 PR #13 审查修复后，在仓库根目录 Python 3.13.14 `.venv` 执行：两组定向测试共 20 项通过；全仓 Python 测试为 119 项通过、9 项跳过；`ruff check backend agent tests` 与路径级敏感文件检查通过。跳过项是成员 4 的 Stage-0 Worker/视频链路，以及未配置 PostgreSQL `TEST_DATABASE_URL` 的账号隔离和持久化测试。该结果只证明已执行的离线规则、编排、安全边界和报告门禁，不代表真实模型、Worker、后端回写或 E2E 已运行。

## 完成定义

真实完成还要求：至少一个真实模型按隐私模式运行；无证据结论被拒；新结论保持
`pending`；教师复核后报告过滤测试通过；Trace 可由后端审计找回；相关自动化与真实
E2E 均留下脱敏证据。
