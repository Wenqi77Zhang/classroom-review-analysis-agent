# 技术架构

## 模块

- `frontend/`：Next.js/TypeScript 页面与证据工作台。
- `backend/`：FastAPI、PostgreSQL、认证、权限、对象地址和业务 API。
- `worker/`：对象读取、FFmpeg、ASR、翻译、课件解析、证据索引和重试。
- `agent/`：分析契约、模型路由、Skill、证据门禁、报告组合和 Trace。

## 数据流

浏览器预签名上传 → 对象存储 → 数据库登记任务 → Worker 生成逐字稿/译文/证据索引 → Agent 生成结构化分析 → 教师人工复核 → 已确认内容进入报告。

## 关键边界

- Worker 回答“怎样把输入加工成证据”。
- Agent 回答“怎样基于证据形成教学分析”。
- 后端持久化归属、状态和版本。
- 前端不持有长期对象存储密钥。
