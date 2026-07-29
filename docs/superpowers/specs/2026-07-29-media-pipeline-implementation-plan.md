# 成员 4：真实媒体处理链路实施计划

设计文档：`2026-07-29-media-pipeline-design.md`

## 环境基线

- 项目要求 Python `>=3.13,<3.14`，使用 `/opt/miniconda3/bin/python3.13` 创建仓库内 `.venv`。
- 系统已安装 FFmpeg/FFprobe 8.1。
- 本机为 Apple Silicon。
- ASR 首选 `openai-whisper` 的 Python 接口；模型默认 `tiny`，通过环境变量覆盖。
- 模型与两段测试视频仅保存在本地，不进入 GitHub。

## 任务 1：媒体与错误基础类型

修改：

- `worker/errors.py`
- `worker/types.py`
- `worker/cleanup.py`

完成：

- 定义稳定错误码与 `WorkerError`。
- 定义 ASR 分段、ASR 结果和媒体探测结果。
- 实现临时工作目录的幂等清理。

验证：

- 错误码可序列化。
- 不存在的临时路径清理不报错。

## 任务 2：FFmpeg 音频抽取

修改：

- `worker/stages/extract_audio.py`
- `tests/unit/test_worker.py`

完成：

- 使用参数数组调用 FFmpeg，不启用 shell。
- 输出 PCM 16-bit、16 kHz、单声道 WAV。
- 验证输入存在、输出非空、超时和退出码。

验证：

- 用测试生成的小型媒体文件验证声道与采样率。
- 验证缺失输入、FFmpeg 失败和超时错误。

## 任务 3：本地 Whisper 与 Schema 转换

修改：

- `worker/adapters/asr.py`
- `worker/stages/transcribe.py`
- `pyproject.toml`
- `tests/unit/test_worker.py`

完成：

- 定义 `AsrAdapter` 协议。
- 实现延迟加载的 `LocalWhisperAdapter`。
- 将秒转换为整数毫秒并修正舍入边界。
- 生成 `InternalTranscriptWrite`，由 Pydantic 执行最终校验。
- 未实现说话人分离时保持 `speaker=None`。

验证：

- 使用假适配器快速测试时间戳、句序、语言和失败转换。
- 依赖缺失时返回 `ASR_UNAVAILABLE`。

## 任务 4：JobStore 与最短流水线

修改：

- `worker/job_store.py`
- `worker/pipeline.py`
- `worker/runner.py`
- `tests/unit/test_worker.py`

完成：

- `LocalJobStore` 保存本地任务、状态事件和逐字稿。
- `HttpJobStore` 实现冻结的 claim、heartbeat、state、transcript 请求。
- Pipeline 执行抽取、识别、状态更新和 finally 清理。
- Runner 提供本地单次运行入口。

验证：

- 用假 ASR 运行成功闭环。
- 人为失败时写入失败阶段和错误码。
- 成功与失败后临时 WAV 都不存在。

## 任务 5：真实视频验证与来源记录

修改：

- `tests/integration/test_video_pipeline.py`
- `tests/fixtures/fixture-catalog.md`
- `worker/media-worker-guide.md`

本地生成但不提交：

- 两段完整逐字稿 JSON。
- FFmpeg/ASR 运行日志。

完成：

- 使用 `tiny` 模型运行两段真实 MP4。
- 验证逐字稿非空、时间戳合法且两段结果不同。
- 记录课程名称、平台、访问日期、用途和禁止提交原视频。
- 在 README 中写明安装、运行、模型选择和慢测试方法。

## 任务 6：质量检查与 GitHub 交付

执行：

- `pytest tests/unit/test_worker.py`
- `pytest tests/integration/test_video_pipeline.py`
- `ruff check worker tests/unit/test_worker.py tests/integration/test_video_pipeline.py`
- `git diff --check`

交付：

- 提交实现与测试。
- 推送 `member-4/media-pipeline`。
- 创建 PR，说明真实输入、测试证据、限制和不进入仓库的文件。

## 非目标

- 不提交视频、音频、模型权重或完整课程逐字稿。
- 不实现说话人分离。
- 不修改跨模块 Schema。
- 不等待课件解析、翻译和证据索引才提交首个真实 ASR PR。
