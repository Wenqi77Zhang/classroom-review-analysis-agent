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

当前实现位于 `agent/observability/tracing.py`，提供脱敏事件和可替换的 `TraceSink`。进程内 Sink 已用于离线测试；接入成员 3 的审计持久化接口仍为 `TODO`，因此当前不能宣称 Trace 可跨进程找回。

## 当前实现边界（2026-07-29）

- 分析契约、结构化候选输出和任务内证据定义在 `agent/contracts.py`，跨模块结论字段直接复用成员 3 的后端 Schema。
- `AgentOrchestrator` 只执行已确认契约，按隐私模式选择 Provider，并拒绝模型引用当前任务之外的证据。
- 专业 Skill 通过注册表接入，成员 4 尚未提供的 `computer_ai`、`humanities` 不会被伪装成已启用。
- 报告组合不调用模型，只按复核状态确定性过滤；`modified` 使用教师改写内容。
- Provider 协议和离线 Fake Provider 测试已完成；真实模型调用、内部 API 回写、Worker 证据和 E2E 仍为 `TODO`。

## MCP

里程碑 M1 不为展示概念强行接入 MCP。未来真实连接高校课程库、网易平台或文档系统时再评估。
