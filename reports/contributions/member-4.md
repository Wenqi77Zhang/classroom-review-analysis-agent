# 成员 4 贡献

## 已完成

- 建立真实媒体最短链路：读取本地或挂载目录中的视频，使用 FFmpeg 抽取 16 kHz、
  单声道、PCM WAV，再通过本地 `openai-whisper` 生成带毫秒时间戳的结构化逐字稿。
- 逐字稿按成员 3 冻结的 `InternalTranscriptWrite` 整批写入，重跑不会混合新旧片段。
- Worker 只把转写阶段写为 `RUNNING / progress=1.0`，不再越权把整个任务写为终态
  `SUCCEEDED`。
- 远程单次入口通过 `HttpJobStore.claim()` 领取任务，并在长 ASR 阶段由独立线程周期
  heartbeat；续租停止或失败后不持久化转写结果。
- 严格拒绝非有限、负数、零长度、倒序、重叠、超过真实 WAV 时长或转换到毫秒后退化
  的时间区间，不钳位或伪造证据。
- 临时音频清理保持幂等；占用、权限等删除失败会返回可重试的稳定错误并使阶段失败，
  不再被静默吞掉。
- 对齐 Worker 稳定错误码，并使用 `httpx.MockTransport` 覆盖 claim `204`、冻结响应解析、
  路径、Bearer 鉴权、heartbeat、状态、整批 transcript、非 2xx、连接失败和超时。
- 对两段成员 4 确认来源的中国大学 MOOC 视频完成真实 ASR 验收；仓库只记录来源、
  文件 SHA-256、时长、片段数、首末时间范围和不可逆正文摘要哈希。
- 在成员 4 原有媒体流水线基础上，成员 1 通过 PR #20 协作接通 `uploaded` 任务领取、
  B2 限时下载、文件大小与已验证 ETag 校验、下载失败清理及 PostgreSQL 逐字稿写回；
  一段获授权真实视频已完成远程纵向切片验收。该项属于成员 1 的跨模块协作，不改写为
  成员 4 独立完成。
- Whisper 继续作为 Worker 可选依赖，不拖入纯后端 CI；Worker Ruff 已在本地全仓检查中
  单独执行。

## 验证结果

- Worker 单元测试与两段真实视频集成测试：32 项通过。
- 全仓 pytest：157 项通过，9 项因缺少对应外部环境按既定条件跳过。
- Ruff、阶段 0 脚手架、路径级敏感文件检查和 `git diff --check`：通过。
- 前端契约测试、TypeScript 检查、Next.js 生产构建：通过。
- 原视频、抽取音频、完整逐字稿、模型权重、密钥和本地辅助 skill：均未提交。
- PR #20 回归：Ruff 通过，全仓 169 项通过、10 项按环境条件跳过；真实输入验收未记录
  文件名、逐字稿正文、长期密钥或预签名 URL。

## 尚未完成的边界

- 翻译、课件解析和证据索引尚未实现，不能描述为成员 4 全部职责已经完成。
- 当前 runner 能领取一次 `uploaded` 任务并完成受控下载与转写；生产级常驻消费、
  退避、指标、部署编排和第二段远程输入复测尚未完成。

## 主要证据

- `worker/`
- `tests/unit/test_worker.py`
- `tests/integration/test_video_pipeline.py`
- `tests/fixtures/fixture-catalog.md`
- PR #14
- PR #20（成员 1 协作补齐）
