# 跨模块接口契约

当前为阶段 0 草案，Day 1 冻结第一版 Pydantic/TypeScript Schema。

## 核心实体

- User、Course、Classroom
- Asset、ProcessingTask、TaskEvent
- TranscriptSegment、TranslationSegment
- EvidenceReference、AnalysisConclusion
- ReviewDecision、Report、AuditEvent

## 强制字段

所有分析结论至少包含：

- `id`
- `type`: `fact | judgment | suggestion`
- `content`
- `evidence_refs`
- `review_status`: `pending | accepted | modified | rejected`
- `created_at`
- `trace_id`

证据引用至少包含来源类型和可定位信息；视频/原文证据必须有时间范围，课件证据必须有页码或画面引用。

## 变更规则

任何 Schema 变更必须由成员 3 更新本文件，并由受影响的前端、Worker 和 Agent 负责人确认。
