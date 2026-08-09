# Agent 设计

## 模式

采用确定性任务状态机与受约束 Agent 的混合架构：

1. 有限 ReAct 完成范围追问和工具选择。
2. 确认分析契约后一次规划。
3. 两类学科 Skill 可并行分析。
4. 证据校验器拒绝不可定位结论。
5. 教师人工复核是进入报告的强制门。

Perceive–Reason–Action–Learn 作为产品级框架；Learn 只记录教师接受、修改和驳回形成的显式反馈，不自动改变模型或评分标准。

## 可观测性

记录 Trace ID、模型、Prompt、Skill 版本、证据、延迟、错误、调用量和教师修改版本。

当前实现位于 `agent/observability/tracing.py`，提供脱敏事件和可替换的 `TraceSink`。错误事件只记录稳定错误类型、错误码和阶段，禁止记录原始异常消息；含口令、令牌和课堂文本的 Pydantic `ValidationError` 已有回归测试。运行器默认写入权限收敛的本地 JSONL，任务与结论同时持久化同一 `trace_id`，前端任务面板可展示该标识；这支持本机跨进程回溯，但仍不是集中式生产可观测平台。

## 当前实现边界（更新至 2026-08-10）

- 分析契约、结构化候选输出和任务内证据定义在 `agent/contracts.py`，跨模块结论字段直接复用成员 3 的后端 Schema。
- `AgentOrchestrator` 只执行已确认契约，按隐私模式选择 Provider；时间范围在模型调用前筛选、结论落地前复核，双语模式拒绝缺少逐句译文的范围内证据。
- 逐字稿、课件和证据文本是不可议信息，以标记边界内的 Base64 UTF-8 数据发送；系统 Prompt 明确禁止执行证据中的命令，输出仍受契约、Skill 和证据 ID 三层校验。
- 专业 Skill 通过注册表接入；`computer_ai`、`humanities` 与证据门禁已有
  确定性实现和自动化测试，但尚未用真实 Worker 证据索引完成端到端验收。
- 报告组合不调用模型，只按复核状态确定性过滤；`modified` 使用教师改写内容。
- Provider 协议和离线 Fake Provider 测试已完成；M1 本地模型选定 Ollama
  `qwen3.5:4b`。真实 HTTP 调用已验证简单 Schema 与完整 Agent Schema；本地 Provider
  关闭 thinking，并移除 Ollama 0.32.5 无法编译的生成期 Schema 元数据/长度约束，模型
  返回后仍使用完整 Pydantic Schema 和证据门禁校验。2026-08-10 已以真实 Worker
  时间戳逐字稿生成事实、判断、建议各 1 条，每条绑定有效起止时间证据。后端结论写入 API 已合并。
  Worker → Agent 原子交棒、Agent 领取/心跳、一次运行及结论/状态回写已实现并通过离线
  测试；真实 PostgreSQL/B2/Worker/Agent/复核/报告的单输入技术 E2E 已通过。专业 Skill
  真实输入、课件/画面证据、第二输入、浏览器全程用户验收和生产级 Trace 平台仍未完成。

## Worker → Agent 接力

Worker 完成转写后不直接调用模型，而是向后端提交一次受租约约束的 handoff。后端确认
逐字稿已持久化后，原子地将任务从 `transcribe / running` 切到 `analyze / queued`，
清除 Worker 租约。Agent 使用独立服务令牌领取，只得到当前任务和账号范围内的分析契约
及证据。Agent 在模型调用期间续租，运行中状态不释放租约；成功或失败才进入终态。

这一设计避免用一个大进程混合媒体处理与教学推理，也避免 Worker 和 Agent 同时认为自己
拥有任务。它是确定性编排，不需要用 ReAct 来决定基础设施状态迁移；ReAct 只适合后续
受限的分析工具选择。

## MCP

里程碑 M1 不为展示概念强行接入 MCP。未来真实连接高校课程库、网易平台或文档系统时再评估。
