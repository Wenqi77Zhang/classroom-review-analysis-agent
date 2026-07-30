# 媒体处理 Worker 说明

负责人：成员 4；接口协作：成员 3、成员 5。

目的：把对象存储中的视频和课件加工成可检索证据。Worker 不生成教学判断。

当前最短闭环已经实现：

`真实视频 → FFmpeg 16 kHz 单声道 WAV → 本地 Whisper → 带毫秒时间戳逐字稿 → JobStore`

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

`LocalJobStore` 用于本地验证；成员 3 的内部接口上线后使用 `HttpJobStore`。它已经按冻结
契约实现任务领取、续租、状态回写和逐字稿写入。服务令牌只能通过环境变量或部署密钥注入。

## 当前边界

- 已实现：真实视频读取、音频抽取、带时间戳 ASR、状态回写、失败记录、临时文件清理。
- 已实现但仅局部验证：`HttpJobStore` 任务领取、租约心跳、状态回写和逐字稿写入。
- 进行中：从 B2 获取浏览器上传对象并消费 `queued` 任务；当前由其他对话实现，
  尚未合并到 `main`，合并与真实输入复测前不得标记为完成。
- 待实现或待串联：长音频切片、逐句翻译、课件解析、证据索引，以及向 Agent
  阶段的任务交接。
- 未实现说话人分离，因此 `speaker` 为 `null`，不伪造教师或学生身份。
