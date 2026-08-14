# 媒体处理 Worker 说明

负责人：成员 4；接口协作：成员 3、成员 5。

目的：把对象存储中的视频和课件加工成可检索证据。Worker 不生成教学判断。

当前媒体闭环已经实现：

`真实视频 → FFmpeg 16 kHz 单声道 WAV → 本地 Whisper → 带毫秒时间戳逐字稿 → 可选 SRT/VTT 中文译文时间对齐 → JobStore`

## 本地运行

项目要求 Python 3.13，并要求系统能直接运行 `ffmpeg`。先安装 Worker 专用依赖：

```bash
python -m pip install -e ".[dev,worker]"
```

Whisper 模型在第一次运行时下载到本机缓存，不得提交模型目录。只运行后端和常规测试的
环境继续安装 `.[dev]`，无需下载 Whisper 或 PyTorch。

```bash
python -m worker.runner "/绝对路径/课堂.mp4" \
  --output "/本地私有目录/transcript.json" \
  --model tiny
```

可用 `--language zh` 固定中文；不传则自动检测。`tiny` 适合快速联调，验收质量建议
使用 `small`，代价是下载和推理时间更长。

## 两段真实视频测试

```bash
CLASSROOM_TEST_VIDEOS="/路径/a.mp4:/路径/b.mp4" \
WHISPER_MODEL=tiny \
pytest tests/integration/test_video_pipeline.py
```

测试要求两段结果都非空、每段时间区间合法，且更换输入后逐字稿不同。

## 接入后端

`LocalJobStore` 用于本地验证；远程模式使用 `HttpJobStore`。Worker 领取任务后，由后端
即时签发当前对象的限时只读地址，再使用不携带服务令牌的独立 HTTP 客户端下载视频。
对象存储长期密钥和教师 JWT 都不会进入 Worker。下载文件会核对后端登记大小，并将响应
ETag 与上传完成时后端 HEAD 保存的 ETag 对照；成功、失败或租约停止后都会清理。服务令牌
只能通过环境变量或部署密钥注入。

```bash
export WORKER_SERVICE_TOKEN
python -m worker.runner \
  --api-base-url http://127.0.0.1:8000 \
  --model tiny
```

远程模式默认常驻轮询。没有任务时按 `WORKER_POLL_INTERVAL_SECONDS=5` 等待；连接、
限流和后端临时故障从 1 秒开始退避，最大不超过
`WORKER_MAX_BACKOFF_SECONDS=30`。401/403 鉴权失败和其他不可重试的客户端错误会立即
退出，不会无限请求。`SIGINT`/`SIGTERM` 会触发安全停止；租约已停止后不再写入任务状态
或逐字稿。

`--once` 只用于诊断，一次请求领取后即退出：

```bash
python -m worker.runner \
  --api-base-url http://127.0.0.1:8000 \
  --model tiny \
  --once
```

`--object-root` 仅保留给 MinIO 本地挂载等离线调试；B2 正常模式无需配置本地对象目录。

## 翻译阶段

`translate` 内部阶段复用现有逐字稿整批写入接口，不新增后端 API。它逐句检测中文、
英文和中英混合文本；英文与混合片段只写 `translation`，原始 `text`、时间戳、句序和
说话人字段保持不变。中文逐字稿不调用翻译适配器。

当前只完成了可替换 `TranslationAdapter` 契约、确定性语言检测和失败门禁。测试中的
`fake-translation-for-tests` 只验证逐句对齐，不能作为真实翻译验收。组长尚未确认候选
模型的 revision、许可证、权重大小和运行要求，因此：

- 没有新增或下载真实翻译模型；
- 没有把测试译文写成真实验收结果；
- 教师可补充 UTF-8 的 SRT/VTT 中文译文字幕。远程 Worker 会使用独立、无服务令牌的
  下载客户端读取该 `transcript` 资产，仍以视频生成的 ASR 原文为主，按时间重叠写入
  `translation`；每个 ASR 片段至少需要一条译文覆盖其一半时长；
- TXT/DOCX 没有可靠时间轴，不能用于修复双语门禁；SRT/VTT 缺中文、乱序、重叠或覆盖
  不全时返回 `TRANSLATION_SCHEMA_INVALID`，不得静默跳过；
- 远程 Worker 未配置真实 `TranslationAdapter` 时停在
  `transcribe / running / 1.0`，通过现有 `handoff-agent` 交给 Agent，不进入
  `translate`；若任务携带合规 SRT/VTT，则进入真实 `translate` 对齐阶段；
- 直接调用内部翻译阶段处理英文/中英混合逐字稿时仍然 fail closed，未配置适配器会返回
  `TRANSLATION_UNAVAILABLE`；
- `translate` 的教师补充字幕路径已接入远程领取与 Agent 交接；真实对象存储和浏览器
  人工复验仍待执行。`parse_courseware` 和 `build_evidence_index` 仍是经过单元测试的
  内部能力，尚未接入远程纵向链路。

## 课件与证据草稿

P0 已支持按可信 MIME 解析 PDF 和 PPTX：

- PDF 提取每页文字并保留从 1 开始的页码；
- PPTX 按幻灯片顺序提取文本框、表格单元格和已有备注；
- 加密、损坏、空页集、页数超限或不支持的 MIME 会返回稳定错误；
- 异常信息不包含本地绝对路径或课件正文。

`build_evidence_index` 会把逐字稿时间段生成 TRANSCRIPT 证据，把非空课件页生成
COURSEWARE 证据。它不会把音频转写伪装成 VIDEO/FRAME 视觉证据；视觉证据必须等待真实
画面处理或人工定位。证据 ID 对同一任务、来源、定位和正文哈希保持确定性；每条证据都通过
成员 3 已有的 `EvidenceReference` 定位校验。当前产物只在内存中，未伪造数据库
`segment_id`，也未写入后端。

页面 PNG、截图对象引用和派生资源上传仍是 P1。最新 `main` 已提供基础
`handoff-agent`：Worker 写回逐字稿后可以把任务交给 Agent，后端从逐字稿生成领取包。
独立课件/画面证据的持久化、版本冻结和审计仍须等待成员 3 审核
`worker/m1-backend-contract-proposal.md` 并冻结契约。

## 当前边界

- 已实现并通过真实输入验收：`HttpJobStore` 领取 `uploaded` 任务、对象存储限时下载、
  文件大小与已验证 ETag 校验、真实视频读取、音频抽取、带时间戳 ASR、租约心跳、
  状态回写、逐字稿写入、失败记录、临时文件清理，以及单 Worker 常驻轮询与有界退避。
- M1 只允许部署一个 Worker。成员 3 冻结并实现 `lease_id` fencing 前，不声称多 Worker
  并发安全，也不横向扩容。
- `transcribe` 租约过期后可由新 Worker 在同阶段恢复。本地重新下载视频和准备音频不会
  回写更早的数据库阶段；下载、媒体处理或清理失败也保持在 `transcribe` 并使用现有稳定
  错误码。
- 待实现或待串联：自动本地翻译适配器、长音频切片，以及课件/画面/独立证据的后端
  持久化和 Agent 领取；基于逐字稿的基础 Agent 交接已经接通。
- 第二段非预置视频的完整远程链路、自动翻译、补充字幕浏览器人工复验、课件/独立证据持久化和阶段化教师重试仍
  未完成，不能以内部单元测试替代这些验收。
- 独立指标 HTTP 端口、完整生产容器和高级退避指标属于 P1，本次常驻实现只有不含租户
  数据的进程内计数。
- 未实现说话人分离，因此 `speaker` 为 `null`，不伪造教师或学生身份。
