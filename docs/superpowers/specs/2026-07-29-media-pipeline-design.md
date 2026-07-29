# 成员 4：真实媒体处理链路设计

日期：2026-07-29  
分支：`member-4/media-pipeline`  
负责人：成员 4  
协作：成员 3（内部 API）、成员 5（证据索引与 Agent）

## 1. 目标与范围

本次实现把真实课堂视频加工为可定位、可持久化的逐字稿证据。首轮使用两段本地测试视频：

- `人工智能导论.mp4`：计算机/人工智能课程，约 8 分 41 秒。
- `语文基础模块上册.mp4`：人文社科课程，约 6 分 55 秒。

两个原始视频、派生音频和模型权重均不进入 GitHub。本次提交只包含处理代码、自动化测试、来源与许可记录，以及不构成课程内容替代品的少量脱敏结构样例。

本次不生成教学判断，不实现报告组合，也不修改教师复核状态。这些职责分别属于 `agent/` 和后端。

## 2. 技术方案

采用“真实本地实现 + 可替换边界”：

1. FFmpeg 将 MP4 音轨抽取为 16 kHz、单声道 WAV。
2. `LocalWhisperAdapter` 调用本地 Whisper，返回原始分段文本、语言和时间戳。
3. `transcribe` 阶段将秒级时间转换为整数毫秒，并校验时间区间与句序。
4. `pipeline` 按阶段执行，记录真实状态，失败时保留明确错误码。
5. `LocalJobStore` 支持在成员 3 的内部 API 完成前独立验证。
6. `HttpJobStore` 对接冻结的 `/api/internal/*` 契约；媒体阶段不直接连接数据库。
7. `cleanup` 在成功和失败路径都删除本地临时媒体。

默认采用本地 Whisper，避免依赖云端密钥、费用与课堂数据外传。ASR 通过适配器隔离，后续可新增云端实现，但云端调用必须服从任务的 `privacy_mode`。

## 3. 模块边界

### `worker/stages/extract_audio.py`

- 输入：本地视频路径、临时工作目录。
- 输出：16 kHz 单声道 WAV 路径。
- 责任：安全调用 FFmpeg、设置超时、检查退出码和非空输出。
- 禁止：使用 shell 字符串拼接用户文件名。

### `worker/adapters/asr.py`

- 定义统一 ASR 接口和结构化结果。
- `LocalWhisperAdapter` 是本次真实实现。
- 适配器只负责识别，不负责后端状态回写。

### `worker/stages/transcribe.py`

- 将 ASR 结果转换为 `InternalTranscriptWrite`。
- 时间统一为整数毫秒。
- `index` 从 0 开始、唯一且递增。
- 当前未实现可靠说话人分离时，`speaker` 为 `null`，不得伪造标签。

### `worker/job_store.py`

- `LocalJobStore`：读取本地任务描述并保存本地结果，供独立开发和测试。
- `HttpJobStore`：领取任务、续租、回写状态和整批写入逐字稿。
- Worker 不直连数据库。

### `worker/pipeline.py`

- 编排抽音频、识别、结构转换和清理。
- 每个阶段可独立失败并报告可操作错误。
- 当前最短闭环完成后再扩展翻译、课件解析和证据索引。

## 4. 数据输出

逐字稿使用 `backend/app/schemas/transcript.py::InternalTranscriptWrite`：

- `source_language`
- `translation_language`
- `duration_ms`
- `segments`
- `trace_id`

每个 segment 至少包含：

- `index`
- `start_ms`
- `end_ms`
- `speaker`
- `text`
- `translation`

必须满足 `start_ms >= 0`、`end_ms > start_ms`，批内索引唯一且升序。重跑采用整批替换语义，防止新旧视频结果混合。

## 5. 错误与重试

Worker 使用稳定、可测试的错误类别：

- `INPUT_NOT_FOUND`
- `FFMPEG_NOT_FOUND`
- `AUDIO_EXTRACTION_FAILED`
- `AUDIO_EXTRACTION_TIMEOUT`
- `ASR_UNAVAILABLE`
- `ASR_TIMEOUT`
- `INVALID_TIMESTAMP`
- `TRANSCRIPT_SCHEMA_INVALID`
- `UPSTREAM_UNAVAILABLE`
- `CLEANUP_FAILED`
- `JOB_STORE_FAILED`
- `STOPPED`

前三组之外的运行期错误同样保持稳定：输入缺失不得伪装成 FFmpeg 失败；临时媒体删除失败
必须可观察、可重试；内部任务接口或 heartbeat 失败必须与 ASR 失败区分；租约停止后不得
持久化转写结果。错误码集合由 `test_worker_error_codes_match_media_design` 做精确相等断言，
防止实现与设计再次漂移。

失败状态必须包含错误码；日志不得输出密钥、服务令牌、Cookie 或完整签名 URL。ASR 等长阶段需通过 `HttpJobStore` 定期续租。失败任务由后端状态机重新排队，Worker 不自行修改重试次数。

## 6. 测试与验收

自动化测试至少覆盖：

1. FFmpeg 能从真实 MP4 生成非空 WAV。
2. 输出音频为 16 kHz 单声道。
3. 逐字稿时间区间合法。
4. segment 索引唯一且递增。
5. 两段不同视频产生不同逐字稿或时间结构。
6. 人为制造 ASR 失败后得到明确错误码。
7. 成功和失败后临时音频均被清理。
8. `tests/unit/test_worker.py` 不再整文件跳过。
9. `tests/integration/test_video_pipeline.py` 验证本地视频到结构化逐字稿的真实链路；依赖模型的慢测试用显式标记与运行说明管理。

完成定义：

- 两段视频均生成真实、带毫秒时间戳的逐字稿。
- 结果通过冻结的 Pydantic Schema。
- 本地失败可定位、可清理、可重试。
- 代码和测试推送至 `member-4/media-pipeline` 并创建 PR。
- 原始视频、完整逐字稿、模型权重和秘密配置未进入 GitHub。

## 7. 后续扩展顺序

最短闭环通过后，按以下顺序扩展：

1. 英文/中英混合检测与逐句中文翻译。
2. 从对象存储安全读取视频。
3. PDF/PPTX 课件解析。
4. 时间、原文、课件页和画面的证据索引。
5. 与成员 5 协作接入证据门禁。

这些扩展不得阻塞首个“真实视频 → 时间戳逐字稿”PR。
